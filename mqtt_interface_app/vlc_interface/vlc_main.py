from .vlc_listener import VLCListener
from .vlc_event_builder import VLCEventBuilder
from .vlc_emitter import VLCEmitter
from mqtt.mqtt_interface import MQTTInterface

import asyncio
import logging

from .subtitle_delay_manager import get_delay

logger = logging.getLogger("vlc_interface.vlc_main")


async def execute_action(topic: str, action, emitter, mqtt_interface: MQTTInterface, state=None):
    """
    Execute a VLC action and publish result to MQTT.

    Args:
        topic: MQTT topic to publish to
        action: VLC action to execute
        emitter: VLCEmitter instance
        mqtt_interface: MQTTInterface instance
        state: optional AppState for the web UI event feed

    Returns:
        The MQTT publish result object
    """
    vlc_result = emitter.send(action)
    mqtt_result = await mqtt_interface.publish_event(topic, vlc_result.message)
    logger.info(f"Message sent to {topic} with response: {mqtt_result.status}")
    if state is not None:
        level = "info"
        if action and action.get("action") == "error":
            level = "error"
        elif vlc_result.status != "ok":
            level = "warning"
        state.add_event(topic, vlc_result.message, level=level)
    return mqtt_result


def should_retry(is_retrying: bool, retry_count: int, max_retries: int) -> bool:
    """
    Pure function to determine if retry should continue.
    
    Args:
        is_retrying: Whether we are in retry mode
        retry_count: Current retry attempt number (1-indexed)
        max_retries: Maximum number of retry attempts allowed
    
    Returns:
        True if we should retry, False otherwise
    """
    return is_retrying and retry_count <= max_retries


def process_ok_status(
    status,
    last_media: str,
    builder,
    emitter,
    mqtt_interface: MQTTInterface,
    subtitle_language: str = "English"
) -> tuple:
    """
    Process VLC OK status and return updated state with actions to execute.
    
    This function handles the logic when VLC is in "ok" state:
    - Detects new media and triggers setup actions (continue, subtitle, audio)
    - For existing media, triggers position update
    
    Args:
        status: VLC status object with .status, .payload, and .error attributes
        last_media: Previously loaded media filename (or None)
        builder: VLCEventBuilder instance
        emitter: VLCEmitter instance  
        mqtt_interface: MQTTInterface instance (for action execution)
    
    Returns:
        Tuple of (new_last_media, actions_list) where:
        - new_last_media: The current media filename
        - actions_list: List of (topic, action) tuples to execute
    """
    payload = status.payload
    meta = payload["information"]["category"]["meta"]
    current_media = meta.get("filename")
    actions = []

    if current_media != last_media:
        # New media detected - trigger setup actions
        logger.info(f"Loaded new media: {current_media}")
        actions.append(("vlc_update", builder.set_position_action(current_media)))
        actions.append(("vlc_update", builder.select_subtitle_stream_action(subtitle_language)))
        actions.append(("vlc_update", builder.select_audio_stream_action()))
        # Re-apply a previously saved subtitle delay so all clients (and VLC
        # restarts) converge on the stored, shared offset
        saved_delay = get_delay(current_media)
        if saved_delay:
            actions.append(("vlc_update", builder.set_subtitle_delay_action(saved_delay)))
        return current_media, actions
    else:
        # Existing media - just update position
        action = builder.upsert_position_action(current_media, payload["position"], payload.get("length"))
        if action:
            # unchanged positions produce no action at all
            actions.append(("vlc_positions", action))
        return last_media, actions


def process_error_status(
    status,
    last_media: str,
    last_error: str,
    retry_count: int,
    max_retries: int,
    is_retrying: bool,
    builder
) -> tuple:
    """
    Process VLC error status and return updated state.
    
    This function handles the logic when VLC is NOT in "ok" state:
    - Tracks error state changes
    - Manages retry counter and state
    - Generates error action when needed
    
    Args:
        status: VLC status object with .status, .payload, and .error attributes
        last_media: Previously loaded media filename (or None)
        last_error: Last error message encountered (or None)
        retry_count: Current retry attempt number (1-indexed)
        max_retries: Maximum number of retry attempts allowed
        is_retrying: Whether we are currently in retry mode
        builder: VLCEventBuilder instance
    
    Returns:
        Tuple of (new_last_media, new_last_error, new_retry_count, new_is_retrying, error_action) where:
        - new_last_media: Updated media state (cleared after max retries)
        - new_last_error: Updated error state
        - new_retry_count: Updated retry counter
        - new_is_retrying: Updated retry mode flag
        - error_action: Tuple of (topic, action) for error publishing, or None
    """
    new_last_error = status.error if status.error != last_error else last_error
    new_is_retrying = is_retrying
    new_retry_count = retry_count
    new_last_media = last_media
    error_action = None

    # If we had media playing before, enter retry mode
    if last_media:
        new_is_retrying = True

    # Handle retry logic
    # Note: retry_count starts at 1, so we check < for continuing, >= for max reached
    if new_retry_count < max_retries and new_is_retrying:
        logger.warning(f"Error: {status.error}, retrying {new_retry_count} of {max_retries}...")
        new_retry_count += 1
    elif new_retry_count >= max_retries and new_is_retrying:
        # Max retries reached - reset state
        new_last_media = None
        new_is_retrying = False
        new_retry_count = 1
        logger.error(f"Retry limit ({max_retries}) reached, last media cleared - {status.error}")
    else:
        # First error or not in retry mode - publish error
        error_action = ("vlc_errors", builder.create_error_action(status.error))

    return new_last_media, new_last_error, new_retry_count, new_is_retrying, error_action


async def run_vlc_watcher(vlc_host: str, vlc_port: int, vlc_key: str, mqtt_interface: MQTTInterface, state=None, settings_store=None):
    """
    Main VLC watcher loop.

    Continuously monitors VLC status and publishes events to MQTT:
    - When media changes: Sets position, subtitle (English), and audio
    - When media plays: Updates position periodically
    - On connection errors: Retries up to max_retries times
    - On persistent errors: Publishes to vlc_errors topic

    Args:
        vlc_host: VLC HTTP interface host
        vlc_port: VLC HTTP interface port
        vlc_key: VLC HTTP interface password/key
        mqtt_interface: MQTTInterface instance for publishing events
        state: optional AppState shared with the web UI
        settings_store: optional SettingsStore; watch interval and subtitle
            language are read from it each loop so changes apply live
    """
    # Initialize VLC components
    listener = VLCListener(vlc_host, vlc_port, vlc_key)
    builder = VLCEventBuilder(listener)
    emitter = VLCEmitter(vlc_host, vlc_port, vlc_key, builder)

    # State tracking
    retry_count: int = 1
    max_retries: int = 3
    is_retrying: bool = False
    last_media: str = None
    last_error: str = None

    # Main watcher loop
    while True:
        try:
            if state is not None:
                state.update_watcher(loop_count=state.watcher.loop_count + 1)

            status = listener.get_status()

            if state is not None:
                state.update_watcher(vlc_status=status.status)

            if status.status == "ok":
                # VLC is running - process OK status
                last_media, actions = process_ok_status(
                    status, last_media, builder, emitter, mqtt_interface,
                    subtitle_language=settings_store.get("subtitle_language") if settings_store else "English"
                )
                # Execute all generated actions
                for topic, action in actions:
                    await execute_action(topic, action, emitter, mqtt_interface, state)
                last_error = None
                # VLC responded, so any previous error episode is over - a
                # stale counter here would exhaust retries on the very next
                # transient blip and force an unnecessary media reload
                retry_count = 1
                is_retrying = False

            else:
                # VLC not running or connection error - process error status
                last_media, last_error, retry_count, is_retrying, error_action = process_error_status(
                    status, last_media, last_error, retry_count, max_retries, is_retrying, builder
                )
                # Execute error action if present
                if error_action:
                    topic, action = error_action
                    await execute_action(topic, action, emitter, mqtt_interface, state)

        except Exception as e:
            # Catch any unexpected errors in listener
            logger.error(f"Unexpected error in VLC listener: {str(e)}", exc_info=True)
            await asyncio.sleep(5)
            continue

        if state is not None:
            state.update_watcher(
                last_media=last_media,
                last_error=last_error,
                retry_count=retry_count,
                is_retrying=is_retrying,
            )

        if settings_store is not None:
            interval = settings_store.get("watch_interval")
        else:
            interval = 2
        await asyncio.sleep(interval)
