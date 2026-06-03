from .vlc_listener import VLCListener
from .vlc_event_builder import VLCEventBuilder
from .vlc_emitter import VLCEmitter

from ..mqtt_publisher import MQTTPublisher
import time
import os

vlc_host = os.getenv("VLC_HOST", "http://localhost")
vlc_port = os.getenv("VLC_PORT", 8080)
vlc_key = os.getenv("VLC_KEY", 'F8006B8645')

def run_vlc_watcher():
    listener = VLCListener(vlc_host, vlc_port, vlc_key)
    builder = VLCEventBuilder(listener)
    emitter = VLCEmitter(vlc_host, vlc_port, vlc_key, builder)
    publisher = MQTTPublisher("localhost", 1883)

    def do_action(topic, action):
        result = emitter.send(action)
        print(f"{result.message}")
        publisher.publish_message(topic,result.message)

    last_media = None
    last_error = None
    while True:
        status = listener.get_status()
        if status.status == "ok":
            payload = status.payload
            meta = payload["information"]["category"]["meta"]
            current_media = meta.get("filename")

            if current_media != last_media: # New media - check continue & set sub and audio
                last_media = current_media
                continue_from_action = builder.set_position_action(current_media)
                do_action("vlc_update", continue_from_action)
                set_subtitle_action = builder.select_subtitle_stream_id("English")
                do_action("vlc_update", set_subtitle_action)
                set_audio_action = builder.select_audio_stream_id()
                do_action("vlc_update", set_audio_action)

            else: # Not new media - insert/update position of media
                upsert_positions_action = builder.upsert_position(current_media, payload["position"])
                do_action("vlc_positions", upsert_positions_action)

            last_error=None

        else:
            last_media=None
            if status.error != last_error:
                last_error = status.error
                print(status.error)

        time.sleep(2)