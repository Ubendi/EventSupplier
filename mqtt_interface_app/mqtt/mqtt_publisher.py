import paho.mqtt.publish as publish

from dataclasses import dataclass

@dataclass
class PublishResult:
    status: str
    message: str | None
    error: str | None

class MQTTPublisher:
    def __init__(self, host, port):
        self.host = host
        self.port = port


    def publish_message(self, topic: str, payload) -> PublishResult:
        print(self.host, self.port)
        publish.single(topic,payload,hostname=self.host,port=self.port)
        result: PublishResult = {"ok", f"Message published to {topic}: {payload}", None}
        return result