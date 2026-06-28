from vlc_interface.vlc_main import run_vlc_watcher
from mqtt.mqtt_interface import MQTTInterface

import os

VLC_HOST = os.getenv("VLC_HOST", "http://localhost")
VLC_PORT = int(os.getenv("VLC_PORT", 8080))
VLC_KEY = os.getenv("VLC_KEY", 'pwd1234')
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

def main():
    mqtt_interface = MQTTInterface(MQTT_HOST, MQTT_PORT)
    run_vlc_watcher(VLC_HOST, VLC_PORT, VLC_KEY, mqtt_interface)

if __name__ == "__main__":
    main()