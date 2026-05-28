
class VLCConnectionBase:
    def __init__(self, host, port, vlc_key):
        self.base_api_url = host + ":" + str(port) + "/requests/"
        self.vlc_auth = '',vlc_key