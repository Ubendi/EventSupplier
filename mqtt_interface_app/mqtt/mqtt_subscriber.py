import paho.mqtt.client as mqtt


class MQTTSubscriber():
    def __init__(self, host, port, topics): 
        self.client = mqtt.Client()

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.topics = topics

        self.client.connect(host, port, 60)

    def start(self):
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code):
        for topic in self.topics:
            client.subscribe(topic)
            print(f"Subscribed to {topic}")
        print(f"Connected with result: {reason_code}")

    def on_message(self, client, userdata, msg):
        print(f"{msg.topic} {str(msg.payload.decode())}")
