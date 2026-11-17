import asyncio
import logging

import uvicorn

from mqtt.mqtt_interface import MQTTInterface
from vlc_interface.vlc_main import run_vlc_watcher
from web.app import create_app
from web.app_settings import SettingsStore
from web.state import AppState

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    settings_store = SettingsStore()
    settings = settings_store.get_all()

    # Settings store starts from env vars (VLC_HOST, MQTT_PORT, ...) and
    # applies persisted overrides from data/settings.json on top
    vlc_host = settings["vlc_host"]
    vlc_port = settings["vlc_port"]
    vlc_key = settings["vlc_key"]
    mqtt_host = settings["mqtt_host"]
    mqtt_port = settings["mqtt_port"]

    mqtt_interface = MQTTInterface(mqtt_host, mqtt_port)

    # Shared baseline VLC components for the web API (status + controls)
    from vlc_interface.vlc_listener import VLCListener
    from vlc_interface.vlc_emitter import VLCEmitter
    vlc_listener = VLCListener(vlc_host, vlc_port, vlc_key)
    vlc_emitter = VLCEmitter(vlc_host, vlc_port, vlc_key, None)

    # nCore tracker session (ncoreparser); credentials/settings-editable at
    # runtime, no restart required
    from ncore_interface.ncore_service import NcoreService
    ncore_service = NcoreService(settings_store)

    app_state = AppState()
    app = create_app(app_state, settings_store, vlc_listener, vlc_emitter, ncore_service=ncore_service)

    web_host = settings["web_host"]
    web_port = settings["web_port"]
    web_config = uvicorn.Config(app, host=web_host, port=web_port, log_level="info")
    web_server = uvicorn.Server(web_config)

    watcher_task = asyncio.create_task(
        run_vlc_watcher(vlc_host, vlc_port, vlc_key, mqtt_interface, state=app_state, settings_store=settings_store)
    )
    web_task = asyncio.create_task(web_server.serve())

    done, pending = await asyncio.wait(
        {watcher_task, web_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc:
            logging.getLogger(__name__).error(f"Task crashed: {exc}", exc_info=exc)

if __name__ == "__main__":
    asyncio.run(main())
