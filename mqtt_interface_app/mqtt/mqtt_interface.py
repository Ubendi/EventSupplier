import asyncio
import paho.mqtt.client as mqtt
from dataclasses import dataclass

@dataclass
class PublishResult:
    status: str | None = None
    message: str | None = None
    error: str | None = None

class MQTTInterface():
    def __init__(self, mqtt_host, mqtt_port):
        self.client = mqtt.Client()
        try:
            self.client.connect(mqtt_host,mqtt_port)
            print(f"Successfully connected to {mqtt_host}:{mqtt_port}")
        except Exception as ex:
            print(f"Error connecting to {mqtt_host}:{mqtt_port} : {ex}")
        try:
            self.client.connect(mqtt_host,mqtt_port)
            print(f"Successfully connected to {mqtt_host}:{mqtt_port}")
        except:
            print(f"Error connecting to {mqtt_host}:{mqtt_port}")

    async def publish_event(self, topic: str, payload, retries: int = 3, delay: float = 1.0) -> PublishResult:
        result = PublishResult()
        for attempt in range(1, retries+1):
            try:
                await asyncio.to_thread(self.client.publish,topic,payload)
                result.status="ok",
                result.message=f"Message published to {topic}: {payload}",
                result.error=None
                return result
            except Exception as ex:
                error = getattr(ex, 'message', str(ex))
                result.status="error"
                result.message=f"Publish error: {error}"
                result.error=error
                if attempt < retries:
                    await asyncio.sleep(delay)
                else:
                    return result