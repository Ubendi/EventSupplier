from dataclasses import dataclass

import requests
from .vlc_connection_base import VLCConnectionBase
from requests.exceptions import RequestException

@dataclass
class StatusResult:
     status: str
     http_code: int | None
     payload: dict | None
     error: str | None

class VLCListener(VLCConnectionBase):
    def __init__(self, host, port, vlc_key):
        super().__init__(host, port, vlc_key)
        

    def get_status(self) -> StatusResult:
        try:
            response = requests.get(self.status_api_url, auth=self.vlc_auth, timeout=1)
            response.encoding = 'utf-8'
            if response.json()["state"] == "stopped":
                return StatusResult("no_active_media", 200, None, "No active media")
            if response.status_code == 200:
                return StatusResult("ok", 200, response.json(), None)
            else:
                return StatusResult("http_error", response.status_code, None, f"HTTP {response.status_code}")
        except RequestException as e:
            if "actively refused" in str(e) or "Failed to establish a new connection" in str(e) or "Max retries exceeded" in str(e):
                return StatusResult("vlc_not_running", None, None, "VLC not running")
            else:
                return StatusResult("connection_error", None, None, str(e))
