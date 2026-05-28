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
        self.command_api_url = self.base_api_url+"status.json?command="
    
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
                    self._upsert_postion(media_name, position)
                    message = f"{media_name} new position: {position}"
                case "error":
                    message = action["payload"]["error_message"]
                case "info":
                    message = action["payload"]["info_message"]
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

    # IO methods
    def _upsert_postion(self, media_name: str, position: float):
        upsert_position(media_name, position)