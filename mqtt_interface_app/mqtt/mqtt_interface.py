import paho.mqtt.client as mqtt
from dataclasses import dataclass

@dataclass
class PublishResult:
    status: str
    message: str | None
    error: str | None

class MQTTInterface():
    def __init__(self, mqtt_host, mqtt_port):
        self.client = mqtt.Client()
        try:
            self.client.connect(mqtt_host,mqtt_port)
            print(f"Successfully connected to {mqtt_host}:{mqtt_port}")
        except:
            print(f"Error connecting to {mqtt_host}:{mqtt_port}")

    def publish_event(self, topic: str, payload) -> PublishResult:
        self.client.publish(topic,payload)
        return PublishResult(
            status="ok",
            message=f"Message published to {topic}: {payload}",
            error=None
        )