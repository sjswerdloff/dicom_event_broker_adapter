from unittest.mock import MagicMock, patch

import pytest

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import Command, register_subscriber, unregister_subscriber


class TestMQTTFunctions:
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.command_queues", {})
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_clients", [])
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_processes", [])
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.Process")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.Queue")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    def test_register_subscriber_new(self, mock_sleep, mock_queue, mock_process):
        # Setup mocks
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_process_instance = MagicMock()
        mock_process.return_value = mock_process_instance

        # Call the function
        register_subscriber("TEST_AE", "/workitems/123")

        # Assert that a new subscriber was registered correctly
        from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import (
            command_queues,
            subscriber_clients,
            subscriber_processes,
        )

        assert "TEST_AE" in subscriber_clients
        assert "TEST_AE" in command_queues
        assert mock_process_instance in subscriber_processes
        mock_process_instance.start.assert_called_once()

        # Assert that a command was put in the queue
        mock_queue_instance.put.assert_called_once()
        args, _ = mock_queue_instance.put.call_args
        command = args[0]
        assert command["action"] == "subscribe"
        assert command["topic"] == "/workitems/123/#"

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.command_queues", {})
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_clients", [])
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_processes", [])
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.Process")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.Queue")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    def test_register_subscriber_with_default_topic(self, mock_sleep, mock_queue, mock_process):
        # Setup mocks
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance

        # Call the function with None topic
        register_subscriber("TEST_AE", None)

        # Assert that a default topic was used
        mock_queue_instance.put.assert_called_once()
        args, _ = mock_queue_instance.put.call_args
        command = args[0]
        assert command["topic"] == "/workitems/#"

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.command_queues")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_clients", ["EXISTING_AE"])
    def test_unregister_subscriber_existing(self, mock_command_queues):
        # Setup mock queue
        mock_queue = MagicMock()
        mock_command_queues.__getitem__.return_value = mock_queue

        # Call the function
        unregister_subscriber("EXISTING_AE", "/workitems/123")

        # Assert command was put in queue
        mock_queue.put.assert_called_once()
        args, _ = mock_queue.put.call_args
        command = args[0]
        assert command["action"] == "unsubscribe"
        assert command["topic"] == "/workitems/123"

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.command_queues")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_clients", ["EXISTING_AE"])
    @patch("builtins.print")
    def test_unregister_subscriber_with_default_topic(self, mock_print, mock_command_queues):
        # Setup mock queue
        mock_queue = MagicMock()
        mock_command_queues.__getitem__.return_value = mock_queue

        # Call the function with None topic
        unregister_subscriber("EXISTING_AE", None)

        # Assert default topic was used
        mock_queue.put.assert_called_once()
        args, _ = mock_queue.put.call_args
        command = args[0]
        assert command["topic"] == "/workitems/#"

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.subscriber_clients", [])
    @patch("builtins.print")
    def test_unregister_nonexistent_subscriber(self, mock_print):
        # Call the function with a non-existent AE title
        unregister_subscriber("NONEXISTENT_AE")

        # Assert error message was printed
        mock_print.assert_called_with("Subscriber not found: NONEXISTENT_AE")
