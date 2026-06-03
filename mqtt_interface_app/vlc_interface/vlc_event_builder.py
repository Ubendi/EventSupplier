import time
from helper.string_utils import normalize
from .positions_manager import get_position_of_media

class VLCEventBuilder:
    def __init__(self, vlc_listener):
        self.vlc_listener = vlc_listener

    @staticmethod
    def create_action(action: str, payload: dict | None = None):
        return {
            "action" : action,
            "payload" : payload,
            "time" : time.time()
        }

    def select_subtitle_stream_id(self, language: str) -> dict[str, any]:
        subtitle_streams = self._get_streams("Subtitle", language)
        if not subtitle_streams:
            action = self.create_action("error", {"error_message" : f"No subtitle track found"})
        else:
            stream = subtitle_streams[0]
            action = self.create_action("set_subtitle", {"id" : stream[0], "language" : language})
        return action
    
    def select_audio_stream_id(self):
        audio_streams = self._get_streams("Audio")
        if not audio_streams:
            action = self.create_action("error", {"error_message" : f"No audio track found"})
        else:
            stream = audio_streams[0]
            lang = stream[1].get("Language")
            action = self.create_action("set_audio", {"id" : stream[0], "language" : lang})
        return action
    
    def set_position_action(self, media_name):
        pos = get_position_of_media(media_name)
        if not pos:
            action = self.create_action("info", {"info_message" : f"{media_name} is new, starting from 0"})
        else:
            action = self.create_action("set_position", {"media_name" : media_name, "position" : pos*100})
        return action
    
    def upsert_position(self, media_name, pos):
        action = self.create_action("upsert_position", {"media_name" : media_name, "position" : pos})
        return action




    # Internal functions
    def _get_streams(self, type: str, language: str | None = "") -> list[tuple[str,dict]] | None:
        response = self.vlc_listener.get_status()
        if response.status != "ok":
            return None
        streams = response.payload["information"]["category"]
        list_streams = []
        for stream in streams.items():
            info = stream[1]
            if info.get("Type") != type:
                continue
            stream_item = (str((stream[0]).split(" ")[1]), info)
            list_streams.append(stream_item)
        match type:
            case "Subtitle":
                list_streams = [s for s in list_streams if s[1].get("Language") == language]
                list_streams.sort(key=lambda x: self._score_subtitle_stream(x[1]))
            case "Audio":
                list_streams.sort(key=lambda x: self._score_audio_streams(x[1]))  
            case "Video":
                pass
        if not list_streams:
            return None
        else:
            return list_streams
        
    def _score_subtitle_stream(self, stream) -> int:
        desc = stream.get("Description", "")
        if desc == "":
            return 1
        if "Full" in desc:
            return 2
        if "SDH" in desc:
            return 3
        if "Forced" in desc:
            return 5
        return 4
    
    def _score_audio_streams(self, stream) -> int:
        english = {"English", "Angol", "Eng", "ENG"}
        hungarian = {"Hungarian", "Magyar", "Hun", "HUN"}
        lang = stream.get("Language", "")
        if lang == "":
            return 1
        if lang not in english and lang not in hungarian:
            return 2
        if lang in english:
            return 3
        if lang in hungarian:
            return 4
        return 5