from .vlc_connection_base import VLCConnectionBase
import requests
from dataclasses import dataclass
from .positions_manager import upsert_position

@dataclass
class SendResult:
    status: str
    message: str | None
    http_code: int | None
    error: str | None


class VLCEmitter(VLCConnectionBase):
    def __init__(self, host, port, vlc_key, vlc_event_builder):
        super().__init__(host, port, vlc_key)
        self.vlc_event_builder = vlc_event_builder
        self.command_api_url = f"{self.status_api_url}?command=" 
    
    def send(self, action) -> SendResult:
        if not action:
            return SendResult("error", "Action couldn't be processed", None, "invalid_action")
        else:
            match action["action"]:
                case "set_subtitle":
                    id = action["payload"]["id"]
                    self._set_subtitle_stream(id)
                    message = f"Subtitle track {id} set ({action["payload"]["language"]})"
                case "set_audio":
                    id = action["payload"]["id"]
                    self._set_audio_stream(id)
                    message = f"Audio track {id} set ({action["payload"]["language"]})"
                case "set_position":
                    media_name = action["payload"]["media_name"]
                    position = action["payload"]["position"]
                    self._set_position(position)
                    message = f"{media_name} resumed from position {position}"
                case "upsert_position":
                    media_name = action["payload"]["media_name"]
                    position = action["payload"]["position"]
                    length = action["payload"].get("length")
                    self._upsert_postion(media_name, position, length)
                    message = f"{media_name} new position: {position}"
                case "play":
                    self._play()
                    message = "Playback started"
                case "pause":
                    self._pause()
                    message = "Playback paused/resumed"
                case "stop":
                    self._stop()
                    message = "Playback stopped"
                case "set_volume":
                    volume = action["payload"]["volume"]
                    self._set_volume(volume)
                    message = f"Volume set to {volume}%"
                case "set_subtitle_id":
                    id = action["payload"]["id"]
                    self._set_subtitle_stream(id)
                    message = f"Subtitle track {id} set"
                case "set_audio_id":
                    id = action["payload"]["id"]
                    self._set_audio_stream(id)
                    message = f"Audio track {id} set"
                case "play_file":
                    uri = action["payload"]["uri"]
                    name = action["payload"].get("name", uri)
                    self._play_file(uri)
                    message = f"Playing {name}"
                case "load_subtitle":
                    uri = action["payload"]["uri"]
                    name = action["payload"].get("name", uri)
                    self._add_subtitle_file(uri)
                    message = f"Loaded subtitle {name}"
                case "set_subtitle_delay":
                    offset = action["payload"]["offset"]
                    self._set_subtitle_delay(offset)
                    message = f"Subtitle delay set to {offset:+.1f}s"
                case "error":
                    message = action["payload"]["error_message"]
                case "info":
                    message = action["payload"]["info_message"]
                case _:
                    return SendResult("error", "Action couldn't be processed", None, "unknown_action")
        return SendResult("ok", message, 200, None)


    # VLC methods
    def _set_subtitle_stream(self, id: int):
        request = f"{self.command_api_url}subtitle_track&val={id}"
        requests.get(request, auth=self.vlc_auth)

    def _set_audio_stream(self, id: int):
        request = f"{self.command_api_url}audio_track&val={id}"
        requests.get(request, auth=self.vlc_auth)

    def _set_position(self, position: float):
        request = f"{self.command_api_url}seek&val={position}%"
        requests.get(request, auth=self.vlc_auth)

    def _play(self):
        request = f"{self.command_api_url}pl_play"
        requests.get(request, auth=self.vlc_auth)

    def _pause(self):
        request = f"{self.command_api_url}pl_pause"
        requests.get(request, auth=self.vlc_auth)

    def _stop(self):
        request = f"{self.command_api_url}pl_stop"
        requests.get(request, auth=self.vlc_auth)

    # val is a percentage of max volume; bare values are treated by VLC as
    # absolute on the 0-512 scale
    def _set_volume(self, volume: int):
        request = f"{self.command_api_url}volume&val={volume}%25"
        requests.get(request, auth=self.vlc_auth)

    # in_play replaces the current playlist item with the given MRL
    # The builder passes an as_uri() path, which is already percent-encoded
    def _play_file(self, uri: str):
        request = f"{self.command_api_url}in_play&val={uri}"
        requests.get(request, auth=self.vlc_auth)

    # addsubtitle attaches an external subtitle file to the current input
    def _add_subtitle_file(self, uri: str):
        request = f"{self.command_api_url}addsubtitle&val={uri}"
        requests.get(request, auth=self.vlc_auth)

    # subdelay sets the absolute subtitle offset in seconds (can be negative)
    def _set_subtitle_delay(self, seconds: float):
        request = f"{self.command_api_url}subdelay&val={seconds}"
        requests.get(request, auth=self.vlc_auth)

    # IO methods
    def _upsert_postion(self, media_name: str, position: float, length: float | None = None):
        upsert_position(media_name, position, length)