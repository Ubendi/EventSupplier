from mqtt_publisher import MQTTPublisher

import time

mqtt_host = "localhost"
mqtt_port = 1883

def run_mqtt_interface():
    publisher = MQTTPublisher(mqtt_host,mqtt_port)
    while True:
        result = publisher.publish_message("test",f"Test message at {time.time()}")
        print(result)
        time.sleep(3)


if __name__ == "__main__":
    run_mqtt_interface()