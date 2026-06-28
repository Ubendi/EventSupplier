from .vlc_listener import VLCListener
from .vlc_event_builder import VLCEventBuilder
from .vlc_emitter import VLCEmitter
from mqtt.mqtt_interface import MQTTInterface

import time

def run_vlc_watcher(vlc_host: str, vlc_port: int, vlc_key: str, mqtt_interface: MQTTInterface):
    listener = VLCListener(vlc_host, vlc_port, vlc_key)
    builder = VLCEventBuilder(listener)
    emitter = VLCEmitter(vlc_host, vlc_port, vlc_key, builder)

    retry_count: int = 1
    max_retries: int = 3
    is_retrying: bool = False
    last_media: str = None
    last_error: str = None

    def do_action(topic, action): # TO DO: add logging
        vlc_result = emitter.send(action)
        mqtt_result = mqtt_interface.publish_event(topic,vlc_result.message)
        print(f"Message sent to {topic} with response: {mqtt_result.status}")

    while True:
        status = listener.get_status()
        if status.status == "ok": # VLC running
            payload = status.payload
            meta = payload["information"]["category"]["meta"]
            current_media = meta.get("filename")
            if current_media != last_media: # New media - check continue & set sub and audio
                last_media = current_media
                print(f"Loaded new media: {current_media}")
                continue_from_action = builder.set_position_action(current_media)
                do_action("vlc_update", continue_from_action)
                set_subtitle_action = builder.select_subtitle_stream_action("English")
                do_action("vlc_update", set_subtitle_action)
                set_audio_action = builder.select_audio_stream_action()
                do_action("vlc_update", set_audio_action)
            else: # Not new media - insert/update position of media
                upsert_positions_action = builder.upsert_position_action(current_media, payload["position"])
                do_action("vlc_positions", upsert_positions_action)
            last_error = None
        else: # VLC not running / Connection error
            if status.error != last_error:
                    last_error = status.error
            if last_media:
                is_retrying = True
            # else:
            #     print(f"No media present")
            #     continue
            if retry_count <= max_retries and is_retrying:
                print(f"Error: {status.error}, retrying {retry_count} of {max_retries}...")
                retry_count+=1
            else:
                last_media = None
                is_retrying = False
                retry_count = 1
                print(f"Retry limit ({max_retries}) reached, last media cleared - {status.error}")
                error_action = builder.create_error_action(status.error)
                do_action("vlc_errors", error_action)  
        time.sleep(2)