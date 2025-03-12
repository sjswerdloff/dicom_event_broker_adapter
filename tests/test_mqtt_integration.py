"""Integration tests using a real MQTT broker (Mosquitto)."""

import time

import pytest
from conftest import mqtt_integration
from paho.mqtt import client as mqtt_client

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import _construct_mqtt_topic


@pytest.mark.mqtt_integration
class TestMQTTIntegration:
    """Test integration with real MQTT broker."""

    @pytest.fixture
    def mqtt_client(self):
        """Create and connect an MQTT client."""
        broker = "localhost"
        port = 1883
        client_id = f"python-mqtt-test-{time.time()}"

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print("Connected to MQTT Broker!")
            else:
                print(f"Failed to connect, return code {rc}")

        client = mqtt_client.Client(callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2, client_id=client_id)
        client.on_connect = on_connect

        try:
            client.connect(broker, port)
            client.loop_start()

            # Allow time to connect
            time.sleep(0.2)

            if not client.is_connected():
                pytest.skip("Could not connect to MQTT broker at localhost:1883")

            yield client
        except Exception as e:
            pytest.skip(f"Failed to connect to MQTT broker: {e}")
        finally:
            if client.is_connected():
                client.loop_stop()
                client.disconnect()

    def test_publish_and_receive(self, mqtt_client):
        """Test publishing a message and receiving it."""
        # Arrange
        topic = "test/topic"
        test_message = "Hello MQTT"
        received_messages = []

        def on_message(client, userdata, msg, properties=None):
            received_messages.append(msg.payload.decode())

        mqtt_client.subscribe(topic)
        mqtt_client.on_message = on_message

        # Act
        result = mqtt_client.publish(topic, test_message)

        # Wait for message to be received using a polling mechanism
        timeout = 2
        start_time = time.time()
        while time.time() - start_time < timeout and not received_messages:
            time.sleep(0.1)

        # Assert
        assert result.rc == 0  # MQTT_ERR_SUCCESS
        assert len(received_messages) == 1
        assert received_messages[0] == test_message

    def test_construct_topic_for_workitem(self, mqtt_client):
        """Test constructing a topic for a workitem."""
        # Arrange
        received_messages = []
        event_type = "Workitem"
        workitem_uid = "1.2.3.4.5"
        workitem_subtopic = "state"
        expected_topic = f"/workitems/{workitem_uid}/{workitem_subtopic}"
        test_message = "UPS State Change Event"

        def on_message(client, userdata, msg, properties=None):
            received_messages.append({"topic": msg.topic, "payload": msg.payload.decode()})

        mqtt_client.subscribe("/workitems/#")
        mqtt_client.on_message = on_message

        # Act
        topic = _construct_mqtt_topic(event_type=event_type, workitem_uid=workitem_uid, workitem_subtopic=workitem_subtopic)
        result = mqtt_client.publish(topic, test_message)

        # Allow time for message to be received
        time.sleep(0.5)

        # Assert
        assert topic == expected_topic
        assert result.rc == 0  # MQTT_ERR_SUCCESS
        assert len(received_messages) == 1
        assert received_messages[0]["topic"] == expected_topic
        assert received_messages[0]["payload"] == test_message
