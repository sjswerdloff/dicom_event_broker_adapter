import json
from queue import Empty
from unittest.mock import MagicMock, patch

import pytest

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import (
    mqtt_client_process,
    on_connect,
    on_message,
    process_mqtt_message,
)


class TestMQTTClient:
    def test_on_connect(self, mqtt_client_mock):
        """Test MQTT client connect callback handling."""
        # Create test parameters
        mock_userdata = MagicMock()
        mock_flags = {"flag1": 1}
        mock_properties = MagicMock()

        # Setup the process name
        with patch("multiprocessing.current_process") as mock_process:
            mock_process.return_value.name = "TEST_PROCESS"

            # Call the function
            on_connect(mqtt_client_mock, mock_userdata, mock_flags, 0, mock_properties)

            # No assertions needed, just make sure it doesn't raise exceptions

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.process_mqtt_message")
    def test_on_message(self, mock_process_message, mqtt_client_mock):
        """Test MQTT client message callback handling."""
        # Create needed objects
        mock_userdata = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "test/topic"
        mock_msg.payload.decode.return_value = '{"test": "data"}'

        # Call the function
        on_message(mqtt_client_mock, mock_userdata, mock_msg)

        # Verify process_mqtt_message was called
        mock_process_message.assert_called_once_with(this_client=mqtt_client_mock, userdata=mock_userdata, message=mock_msg)

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report")
    @patch("multiprocessing.current_process")
    def test_process_mqtt_message_state_event(self, mock_process, mock_send_event, mqtt_client_mock, test_dataset):
        """Test processing of MQTT messages for state report events."""
        # Setup mocks
        mock_process.return_value.name = "TEST_AE"

        # Create mock message
        mock_userdata = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "/workitems/1.2.3.4/state"
        mock_msg.payload.decode.return_value = '{"test": "data"}'

        # Setup Dataset mock
        with patch("json.loads", return_value={"test": "data"}):
            with patch("pydicom.Dataset.from_json", return_value=test_dataset):
                # Call the function
                process_mqtt_message(mqtt_client_mock, mock_userdata, mock_msg)

                # Verify event report was sent
                mock_send_event.assert_called_once()
                # Check first argument is the Dataset
                args, _ = mock_send_event.call_args
                assert args[0] == test_dataset

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report")
    @patch("multiprocessing.current_process")
    def test_process_mqtt_message_cancel_request(self, mock_process, mock_send_event, mqtt_client_mock, test_dataset):
        """Test processing of MQTT messages for cancel request events."""
        # Setup mocks
        mock_process.return_value.name = "TEST_AE"

        # Create mock message
        mock_userdata = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "/workitems/1.2.3.4/cancelrequest"
        mock_msg.payload.decode.return_value = '{"test": "cancel_data"}'

        # Setup Dataset mock
        with patch("json.loads", return_value={"test": "cancel_data"}):
            with patch("pydicom.Dataset.from_json", return_value=test_dataset):
                # Call the function
                process_mqtt_message(mqtt_client_mock, mock_userdata, mock_msg)

                # Verify event report was sent
                mock_send_event.assert_called_once()
                # Check first argument is the Dataset with correct EventTypeID
                args, _ = mock_send_event.call_args
                ds = args[0]
                assert ds.EventTypeID == 2  # Cancel request event type

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report")
    @patch("multiprocessing.current_process")
    def test_process_mqtt_message_invalid_json(self, mock_process, mock_send_event, mqtt_client_mock):
        """Test handling of invalid JSON in MQTT messages."""
        # Setup mocks
        mock_process.return_value.name = "TEST_AE"

        # Create mock message with invalid JSON
        mock_userdata = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "/workitems/1.2.3.4/state"
        mock_msg.payload.decode.return_value = "invalid json"

        # Setup json.loads to raise exception
        with patch("json.loads", side_effect=json.JSONDecodeError("test error", "doc", 0)):
            with patch("builtins.print") as mock_print:
                # Call the function
                process_mqtt_message(mqtt_client_mock, mock_userdata, mock_msg)

                # Verify error was printed
                mock_print.assert_called_with("Error decoding JSON from MQTT message: invalid json")

                # Verify send_event_report was not called
                mock_send_event.assert_not_called()

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report")
    @patch("multiprocessing.current_process")
    def test_process_mqtt_message_invalid_topic(self, mock_process, mock_send_event, mqtt_client_mock, test_dataset):
        """Test processing of MQTT messages with an unknown/invalid topic."""
        # Setup mocks
        mock_process.return_value.name = "TEST_AE"

        # Create mock message with invalid topic
        mock_userdata = MagicMock()
        mock_msg = MagicMock()
        mock_msg.topic = "/invalid/topic"
        mock_msg.payload.decode.return_value = '{"test": "data"}'

        # Setup Dataset mock
        with patch("json.loads", return_value={"test": "data"}):
            with patch("pydicom.Dataset.from_json", return_value=test_dataset):
                with patch("builtins.print") as mock_print:
                    # Call process_mqtt_message with an invalid topic
                    process_mqtt_message(mqtt_client_mock, mock_userdata, mock_msg)

                    # Verify topic parts were printed (debugging output)
                    mock_print.assert_any_call(["", "invalid", "topic"])

                    # Verify send_event_report is not called for invalid topics
                    # This is the key assertion - we want to make sure no event report is sent
                    # for topics that don't match our expected patterns
                    mock_send_event.assert_not_called()

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    def test_mqtt_client_process_command_handling(self, mock_sleep, mock_mqtt_client):
        """Test MQTT client process handling of subscribe commands."""
        # Create mock objects
        mock_client = MagicMock()
        mock_mqtt_client.Client.return_value = mock_client
        mock_mqtt_client.CallbackAPIVersion.VERSION2 = 2
        mock_queue = MagicMock()

        # Setup commands
        subscribe_command = {"action": "subscribe", "topic": "/workitems/test"}
        mock_queue.get_nowait.side_effect = [subscribe_command, Empty(), Empty(), Empty()]

        # Stop the infinite loop after a few iterations
        mock_sleep.side_effect = [None, None, Exception("Stop")]

        # Call the function
        with pytest.raises(Exception, match="Stop"):
            mqtt_client_process("TEST_PROCESS", "localhost", 1883, mock_queue)

        # Verify client was properly setup
        mock_mqtt_client.Client.assert_called_once_with(
            client_id="TEST_PROCESS", callback_api_version=mock_mqtt_client.CallbackAPIVersion.VERSION2
        )
        mock_client.enable_logger.assert_called_once()
        mock_client.connect.assert_called_once_with("localhost", 1883, 60)
        mock_client.loop_start.assert_called_once()

        # Verify subscription was made
        mock_client.subscribe.assert_called_once_with("/workitems/test")

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    def test_mqtt_client_process_unsubscribe(self, mock_sleep, mock_mqtt_client):
        """Test MQTT client process handling of unsubscribe commands."""
        # Create mock objects
        mock_client = MagicMock()
        mock_mqtt_client.Client.return_value = mock_client
        mock_mqtt_client.CallbackAPIVersion.VERSION2 = 2
        mock_queue = MagicMock()

        # Setup commands - first subscribe, then unsubscribe
        subscribe_command = {"action": "subscribe", "topic": "/workitems/test"}
        unsubscribe_command = {"action": "unsubscribe", "topic": None}
        mock_queue.get_nowait.side_effect = [subscribe_command, unsubscribe_command, Empty(), Empty()]

        # Stop the infinite loop after a few iterations
        mock_sleep.side_effect = [None, None, None, Exception("Stop")]

        # Call the function
        with pytest.raises(Exception, match="Stop"):
            mqtt_client_process("TEST_PROCESS", "localhost", 1883, mock_queue)

        # Verify unsubscription was made - at least once
        assert mock_client.unsubscribe.call_count >= 1
