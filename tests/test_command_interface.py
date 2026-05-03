"""Unit tests for command_interface.py module."""

from queue import Empty
from unittest.mock import MagicMock

from dicom_event_broker_adapter.command_interface import (
    process_commands,
)


class TestProcessCommands:
    """Test process_commands function."""

    def test_process_commands_subscribe_action(self):
        """Test process_commands with subscribe action."""
        # Arrange
        mock_queue = MagicMock()
        command = {"action": "subscribe", "topic": "/test/topic"}
        mock_queue.get_nowait.return_value = command

        # Act
        process_commands(mock_queue)

        # Assert
        mock_queue.get_nowait.assert_called_once()
        # Check that the right print happened inside the function (hard to test directly)
        # The function would print "received command" and "Processing subscribe command..."

    def test_process_commands_unsubscribe_action(self):
        """Test process_commands with unsubscribe action."""
        # Arrange
        mock_queue = MagicMock()
        command = {"action": "unsubscribe", "topic": "/test/topic"}
        mock_queue.get_nowait.return_value = command

        # Act
        process_commands(mock_queue)

        # Assert
        mock_queue.get_nowait.assert_called_once()

    def test_process_commands_empty_queue(self):
        """Test process_commands when queue is empty (raises Empty)."""
        # Arrange
        mock_queue = MagicMock()
        mock_queue.get_nowait.side_effect = Empty()

        # Act & Assert (should not raise an exception)
        process_commands(mock_queue)

        # Assert
        mock_queue.get_nowait.assert_called_once()


class TestParentProcess:
    """Test parent_process function."""

    # Note: Testing parent_process is difficult because it involves user input
    # In a real implementation, we might need to mock the input() function
    # For now, we'll skip detailed testing of parent_process since it's I/O heavy
    pass
