"""Integration tests for the complete MQTT to DICOM UPS flow."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from conftest import mqtt_integration
from paho.mqtt import client as mqtt_client
from pydicom import Dataset
from pynetdicom import AE, evt
from pynetdicom.sop_class import UnifiedProcedureStepPush

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import (
    ADAPTER_AE_TITLE,
    _construct_mqtt_topic,
    handle_dimse_n_event,
    send_event_report,
)


@pytest.mark.mqtt_integration
class TestMQTTToDICOMIntegration:
    """Test the complete flow from MQTT to DICOM UPS."""

    @pytest.fixture
    def mqtt_client(self):
        """Create and connect an MQTT client."""
        broker = "localhost"
        port = 1883
        client_id = f"python-mqtt-test-{time.time()}"

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print(f"MQTT Client connected with client_id {client_id}")
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
            # Always stop the client loop first
            client.loop_stop()

            # Give time for the loop to fully stop
            time.sleep(0.2)

            # Then disconnect if still connected
            if client.is_connected():
                client.disconnect()
                print(f"MQTT client {client_id} properly disconnected")

    @pytest.fixture
    def mock_dicom_recipient(self):
        """Create a mock DICOM UPS recipient that will receive N-EVENT-REPORT messages."""
        mock_recipient = MagicMock()
        mock_recipient.received_events = []

        # This will be monkey-patched into the send_event_report function
        def mock_send_event_report(dataset, client_ae_title, subscriber_ae_title):
            print(f"Mock sending event report to {subscriber_ae_title}")
            # Copy the dataset to avoid any modification issues
            event_data = Dataset()
            for elem in dataset:
                event_data.add(elem)
            mock_recipient.received_events.append(
                {"dataset": event_data, "client_ae_title": client_ae_title, "subscriber_ae_title": subscriber_ae_title}
            )
            # Simulate successful send
            return 0x0000

        return mock_recipient, mock_send_event_report

    def test_mqtt_to_dicom_state_report(self, mqtt_client, mock_dicom_recipient):
        """Test publishing an MQTT message and verifying it's sent as a DICOM UPS State Report."""
        # Unpack the fixture
        mock_recipient, mock_send_event_report = mock_dicom_recipient

        # Setup test data
        workitem_uid = "1.2.3.4.5.6.7"
        test_dataset = Dataset()
        test_dataset.PatientID = "TestPatient"
        test_dataset.PatientName = "Test^Patient"
        test_dataset.ProcedureStepState = "IN PROGRESS"

        # Create the MQTT topic
        topic = _construct_mqtt_topic(event_type="Workitem", workitem_uid=workitem_uid, workitem_subtopic="state")

        # Convert the dataset to JSON for MQTT
        json_payload = test_dataset.to_json()

        # Patch the send_event_report function to capture the event
        with patch(
            "dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report", side_effect=mock_send_event_report
        ) as mock_send:
            # Create a mock MQTT message
            mqtt_message = MagicMock()
            mqtt_message.topic = topic
            mqtt_message.payload = json_payload.encode()

            # Create a mock MQTT client for the process_mqtt_message function
            mock_mqtt_process_client = MagicMock()

            # Patch the multiprocessing.current_process
            with patch("multiprocessing.current_process") as mock_process:
                # Set process name as subscriber AE title
                mock_process.return_value.name = "TEST_SUBSCRIBER"

                # Import process_mqtt_message here to avoid circular imports
                from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import process_mqtt_message

                # Call the function that would process MQTT messages and send DICOM events
                process_mqtt_message(this_client=mock_mqtt_process_client, userdata=None, message=mqtt_message)

                # Verify that send_event_report was called
                mock_send.assert_called_once()

                # Check that we have received the event in our mock recipient
                assert len(mock_recipient.received_events) == 1

                # Verify the event has the proper values
                received_event = mock_recipient.received_events[0]
                assert received_event["subscriber_ae_title"] == "TEST_SUBSCRIBER"
                assert received_event["client_ae_title"] == ADAPTER_AE_TITLE

                # Verify the dataset contains the expected attributes
                received_dataset = received_event["dataset"]
                assert received_dataset.EventTypeID == 1  # State Report
                assert received_dataset.AffectedSOPClassUID == UnifiedProcedureStepPush
                assert received_dataset.AffectedSOPInstanceUID == workitem_uid
                assert received_dataset.PatientID == "TestPatient"
                assert received_dataset.PatientName == "Test^Patient"
                assert received_dataset.ProcedureStepState == "IN PROGRESS"

    def test_mqtt_to_dicom_cancel_request(self, mqtt_client, mock_dicom_recipient):
        """Test publishing an MQTT cancel request and verifying it's sent as a DICOM UPS Cancel Request."""
        # Unpack the fixture
        mock_recipient, mock_send_event_report = mock_dicom_recipient

        # Setup test data
        workitem_uid = "1.2.3.4.5.6.7"
        test_dataset = Dataset()
        test_dataset.PatientID = "TestPatient"
        test_dataset.ReasonForCancellation = "Test cancellation"

        # Create the MQTT topic for a cancel request
        topic = _construct_mqtt_topic(event_type="Workitem", workitem_uid=workitem_uid, workitem_subtopic="cancelrequest")

        # Convert the dataset to JSON for MQTT
        json_payload = test_dataset.to_json()

        # Patch the send_event_report function to capture the event
        with patch(
            "dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report", side_effect=mock_send_event_report
        ) as mock_send:
            # Create a mock MQTT message
            mqtt_message = MagicMock()
            mqtt_message.topic = topic
            mqtt_message.payload = json_payload.encode()

            # Create a mock MQTT client for the process_mqtt_message function
            mock_mqtt_process_client = MagicMock()

            # Patch the multiprocessing.current_process
            with patch("multiprocessing.current_process") as mock_process:
                # Set process name as subscriber AE title
                mock_process.return_value.name = "TEST_SUBSCRIBER"

                # Import process_mqtt_message here to avoid circular imports
                from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import process_mqtt_message

                # Call the function that would process MQTT messages and send DICOM events
                process_mqtt_message(this_client=mock_mqtt_process_client, userdata=None, message=mqtt_message)

                # Verify that send_event_report was called
                mock_send.assert_called_once()

                # Check that we have received the event in our mock recipient
                assert len(mock_recipient.received_events) == 1

                # Verify the event has the proper values
                received_event = mock_recipient.received_events[0]
                assert received_event["subscriber_ae_title"] == "TEST_SUBSCRIBER"
                assert received_event["client_ae_title"] == ADAPTER_AE_TITLE

                # Verify the dataset contains the expected attributes
                received_dataset = received_event["dataset"]
                assert received_dataset.EventTypeID == 2  # Cancel Request
                assert received_dataset.AffectedSOPClassUID == UnifiedProcedureStepPush
                assert received_dataset.AffectedSOPInstanceUID == workitem_uid
                assert received_dataset.PatientID == "TestPatient"
                assert received_dataset.ReasonForCancellation == "Test cancellation"

    def test_mqtt_to_dicom_real_mqtt_simulated_dicom(self, mqtt_client, mock_dicom_recipient):
        """Test publishing to a real MQTT broker and verifying the message is correctly processed."""
        # Unpack the fixture
        mock_recipient, mock_send_event_report = mock_dicom_recipient

        # Setup test data
        workitem_uid = "1.2.3.4.5.6.7"
        test_dataset = Dataset()
        test_dataset.PatientID = "TestPatient"
        test_dataset.PatientName = "Test^Patient"
        test_dataset.ProcedureStepState = "IN PROGRESS"

        # Create the MQTT topic
        topic = f"/workitems/{workitem_uid}/state"

        # Convert the dataset to JSON for MQTT
        json_payload = test_dataset.to_json()

        # Setup the subscriber to handle the message
        received_messages = []
        processed_count = 0

        def on_message(client, userdata, msg, properties=None):
            received_messages.append({"topic": msg.topic, "payload": msg.payload.decode()})

            # Now process this message with our mocked DICOM endpoint
            with patch(
                "dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report",
                side_effect=mock_send_event_report,
            ):
                # Patch the multiprocessing.current_process
                with patch("multiprocessing.current_process") as mock_process:
                    # Set process name as subscriber AE title
                    mock_process.return_value.name = "TEST_SUBSCRIBER"

                    # Import process_mqtt_message here to avoid circular imports
                    from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import process_mqtt_message

                    # Call the function directly
                    process_mqtt_message(this_client=client, userdata=userdata, message=msg)
                    nonlocal processed_count
                    processed_count += 1

        # Subscribe to the topic
        mqtt_client.subscribe(topic)
        mqtt_client.on_message = on_message

        # Publish the message
        result = mqtt_client.publish(topic, json_payload)
        assert result.rc == 0  # MQTT_ERR_SUCCESS

        # Wait for message processing
        timeout = 2
        start_time = time.time()
        while time.time() - start_time < timeout and (not received_messages or processed_count == 0):
            time.sleep(0.1)

        # Verify we received the MQTT message
        assert len(received_messages) == 1
        assert received_messages[0]["topic"] == topic

        # The Dataset.to_json returns DICOM format JSON with numeric tags
        payload_dict = json.loads(received_messages[0]["payload"])
        # PatientID has tag (0010,0020)
        assert "00100020" in payload_dict
        assert payload_dict["00100020"]["Value"][0] == "TestPatient"

        # Verify the mock DICOM endpoint received the event
        assert len(mock_recipient.received_events) == 1

        # Verify the event data
        received_event = mock_recipient.received_events[0]
        assert received_event["subscriber_ae_title"] == "TEST_SUBSCRIBER"
        assert received_event["client_ae_title"] == ADAPTER_AE_TITLE

        # Verify the dataset
        received_dataset = received_event["dataset"]
        assert received_dataset.EventTypeID == 1  # State Report
        assert received_dataset.AffectedSOPClassUID == UnifiedProcedureStepPush
        assert received_dataset.AffectedSOPInstanceUID == workitem_uid
        assert received_dataset.PatientID == "TestPatient"
        assert received_dataset.PatientName == "Test^Patient"
        assert received_dataset.ProcedureStepState == "IN PROGRESS"
