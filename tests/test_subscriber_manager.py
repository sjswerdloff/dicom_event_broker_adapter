"""Unit tests for subscriber_manager.py module."""

from multiprocessing import Process, Queue
from unittest.mock import MagicMock, patch

from dicom_event_broker_adapter.subscriber_manager import (
    cleanup_subscribers,
    register_subscriber,
    unregister_subscriber,
)


class TestRegisterSubscriber:
    """Test register_subscriber function."""

    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_clients", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_processes", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.command_queues", new_callable=dict)
    @patch("dicom_event_broker_adapter.subscriber_manager.Process")
    def test_register_subscriber_new_client(
        self, mock_process_class, mock_command_queues, mock_subscriber_processes, mock_subscriber_clients
    ):
        """Test registering a new subscriber creates process and adds to tracking structures."""
        # Arrange
        mock_process_instance = MagicMock(spec=Process)
        mock_process_class.return_value = mock_process_instance
        ae_title = "TEST_AE"
        topic = "/workitems/test"

        # Act
        register_subscriber(ae_title, topic)

        # Assert
        # Check that Process was created
        mock_process_class.assert_called_once()

        # Check that the process was started
        mock_process_instance.start.assert_called_once()

        # Check that the AE title was added to subscriber_clients
        assert ae_title in mock_subscriber_clients

        # Check that a command queue was created for this client
        assert ae_title in mock_command_queues

        # Check that the process was added to subscriber_processes
        assert mock_process_instance in mock_subscriber_processes

    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_clients", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_processes", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.command_queues", new_callable=dict)
    @patch("dicom_event_broker_adapter.subscriber_manager.Process")
    @patch("dicom_event_broker_adapter.subscriber_manager.time.sleep")
    def test_register_subscriber_existing_client(
        self, mock_sleep, mock_process_class, mock_command_queues, mock_subscriber_processes, mock_subscriber_clients
    ):
        """Test registering an existing subscriber doesn't create a new process."""
        # Arrange
        existing_ae = "EXISTING_AE"
        mock_subscriber_clients.append(existing_ae)
        mock_command_queues[existing_ae] = Queue()  # Simulate existing queue

        mock_queue_put = MagicMock()
        mock_queue = MagicMock()
        mock_queue.put = mock_queue_put
        mock_command_queues[existing_ae] = mock_queue

        # Act
        register_subscriber(existing_ae, "/workitems/existing")

        # Assert
        # Process should not be created again since client already exists
        mock_process_class.assert_not_called()

        # But the queue should receive a subscribe command
        assert mock_queue_put.called
        # The call should be a subscribe command to the topic with /# appended
        call_args = mock_queue_put.call_args[0][0]
        assert call_args["action"] == "subscribe"
        assert call_args["topic"] == "/workitems/existing/#"


class TestUnregisterSubscriber:
    """Test unregister_subscriber function."""

    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_clients", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.command_queues", new_callable=dict)
    def test_unregister_subscriber_existing(self, mock_command_queues, mock_subscriber_clients):
        """Test unregistering an existing subscriber sends unsubscribe command."""
        # Arrange
        ae_title = "TEST_AE"
        topic = "/workitems/test"
        mock_subscriber_clients.append(ae_title)

        mock_queue_put = MagicMock()
        mock_queue = MagicMock()
        mock_queue.put = mock_queue_put
        mock_command_queues[ae_title] = mock_queue

        # Act
        unregister_subscriber(ae_title, topic)

        # Assert
        # The queue should receive an unsubscribe command with the exact topic provided (no suffix added)
        mock_queue_put.assert_called_once()
        call_args = mock_queue_put.call_args[0][0]
        assert call_args["action"] == "unsubscribe"
        assert call_args["topic"] == "/workitems/test"

    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_clients", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.command_queues", new_callable=dict)
    @patch("dicom_event_broker_adapter.subscriber_manager.print")
    def test_unregister_subscriber_nonexistent(self, mock_print, mock_command_queues, mock_subscriber_clients):
        """Test unregistering a non-existent subscriber prints a message."""
        # Arrange
        nonexistent_ae = "NONEXISTENT_AE"

        # Act
        unregister_subscriber(nonexistent_ae)

        # Assert
        # Should print that subscriber was not found
        mock_print.assert_called_once_with(f"Subscriber not found: {nonexistent_ae}")


class TestCleanupSubscribers:
    """Test cleanup_subscribers function."""

    @patch("dicom_event_broker_adapter.subscriber_manager.subscriber_processes", new_callable=list)
    @patch("dicom_event_broker_adapter.subscriber_manager.print")
    def test_cleanup_subscribers(self, mock_print, mock_subscriber_processes):
        """Test cleanup_subscribers terminates and joins all processes."""
        # Arrange
        mock_process1 = MagicMock(spec=Process)
        mock_process2 = MagicMock(spec=Process)
        mock_process1.is_alive.return_value = True
        mock_process2.is_alive.return_value = False
        mock_subscriber_processes.extend([mock_process1, mock_process2])

        # Act
        cleanup_subscribers()

        # Assert
        # Only alive processes should have terminate() called
        mock_process1.terminate.assert_called_once()
        mock_process2.terminate.assert_not_called()  # Not called for dead processes

        # Both processes should have join() called to wait for completion
        mock_process1.join.assert_called_once()
        mock_process2.join.assert_called_once()

        # Should print completion message
        assert any(
            "All subscriber processes have been terminated" in str(call)
            for call in [str(call_arg) for call_arg in mock_print.call_args_list]
        )
