from .vlc_listener import VLCListener
from .vlc_event_builder import VLCEventBuilder
from .vlc_emitter import VLCEmitter
import time
import datetime

host = "http://localhost"
port = 8080
vlc_key = 'F8006B8645'

def run_vlc_watcher():
    listener = VLCListener(host, port, vlc_key)
    builder = VLCEventBuilder(listener)
    emitter = VLCEmitter(host, port, vlc_key, builder)
    last_media = None
    while True:
        status = listener.get_status()
        if status.status == "ok":
            payload = status.payload
            meta = payload["information"]["category"]["meta"]
            current_media = meta.get("filename")

            if current_media != last_media: # New media
                last_media = current_media
                continue_from_action = builder.set_position_action(current_media)
                result = emitter.send(continue_from_action)
                print(f"{result.message}")
                set_subtitle_action = builder.select_subtitle_stream_id("English")
                result = emitter.send(set_subtitle_action)
                print(f"{result.message}")
                set_audio_action = builder.select_audio_stream_id("English")
                result = emitter.send(set_audio_action)
                print(f"{result.message}")
            # else: # Not new media
            #     print(f"{datetime.datetime.now()} {meta["filename"]}, {payload["position"]}")

            # Update / Insert into positions.json
            upsert_positions_action = builder.upsert_position(current_media, payload["position"])
            result = emitter.send(upsert_positions_action)
        else:
            last_media=None
            print(status.error)

        time.sleep(3)


# FUNCTIONS TO DO:
# - On VLC close write filename + stop point in file, then load back if file found
# - On media start set subtitle and audio track to english