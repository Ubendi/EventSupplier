
class VLCConnectionBase:
    def __init__(self, host, port, vlc_key):
        self.status_api_url = f"{host}:{str(port)}/requests/status.json"
        self.vlc_auth = '',vlc_key