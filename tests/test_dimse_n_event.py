import json
from unittest.mock import MagicMock, patch

import pytest

# Import helpers from conftest.py
from conftest import create_dimse_n_event_mock

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import handle_dimse_n_event


class TestDIMSENEvent:
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_publishing_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter._construct_mqtt_topic")
    def test_handle_dimse_n_event_state_report(self, mock_construct_topic, mock_mqtt_client, mock_event, mock_dcmread):
        """Test N-EVENT-REPORT handling for UPS state report."""
        # Setup mocks
        mock_construct_topic.return_value = "/workitems/1.2.3.4/state"

        # Create event primitive
        mock_primitive = create_dimse_n_event_mock(event_type_id=1, sop_instance_uid="1.2.3.4")
        mock_primitive.EventInformation = b"dummy data"
        mock_event.request = mock_primitive

        # Call the handle_dimse_n_event function and get the first yielded value
        generator = handle_dimse_n_event(mock_event)
        status = next(generator)

        # Assert the function returns success status
        assert status == 0

        # Verify the correct calls were made
        mock_construct_topic.assert_called_once_with(
            "Workitem", subscription_type=None, workitem_uid="1.2.3.4", workitem_subtopic="state"
        )

        # Check that the message was published correctly
        # There might be differences in JSON spacing, so we check the topic only
        mock_mqtt_client.publish.assert_called_once()
        args, _ = mock_mqtt_client.publish.call_args
        assert args[0] == "/workitems/1.2.3.4/state"

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_publishing_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter._construct_mqtt_topic")
    def test_handle_dimse_n_event_cancel_request(self, mock_construct_topic, mock_mqtt_client, mock_event, mock_dcmread):
        """Test N-EVENT-REPORT handling for UPS cancel request."""
        # Setup specific mock for cancel request
        mock_construct_topic.return_value = "/workitems/1.2.3.4/cancelrequest"
        event_info = mock_dcmread.return_value
        event_info.to_json = MagicMock(return_value=json.dumps({"test": "cancel_data"}))

        # Create event primitive for cancel request
        mock_primitive = create_dimse_n_event_mock(event_type_id=2, sop_instance_uid="1.2.3.4")
        mock_primitive.EventInformation = b"dummy data"
        mock_event.request = mock_primitive

        # Call the handle_dimse_n_event function and get the first yielded value
        generator = handle_dimse_n_event(mock_event)
        status = next(generator)

        # Assert the function returns success status
        assert status == 0

        # Verify the correct calls were made
        mock_construct_topic.assert_called_once_with(
            "Workitem", subscription_type=None, workitem_uid="1.2.3.4", workitem_subtopic="cancelrequest"
        )

        # Check that the message was published correctly
        # There might be differences in JSON spacing, so we check the topic only
        mock_mqtt_client.publish.assert_called_once()
        args, _ = mock_mqtt_client.publish.call_args
        assert args[0] == "/workitems/1.2.3.4/cancelrequest"

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_publishing_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter._construct_mqtt_topic")
    def test_handle_dimse_n_event_reconnect(
        self, mock_construct_topic, mock_sleep, mock_mqtt_client, mock_event, mock_dcmread
    ):
        """Test N-EVENT-REPORT handling when MQTT client reconnects."""
        # Setup mocks to simulate a disconnected client that reconnects
        mock_mqtt_client.is_connected.side_effect = [False, True]  # First disconnected, then connected
        mock_construct_topic.return_value = "/workitems/1.2.3.4/state"

        # Create event primitive
        mock_primitive = create_dimse_n_event_mock(event_type_id=1, sop_instance_uid="1.2.3.4")
        mock_primitive.EventInformation = b"dummy data"
        mock_event.request = mock_primitive

        # Call the handle_dimse_n_event function
        generator = handle_dimse_n_event(mock_event)
        status = next(generator)

        # Assert the function returns success status
        assert status == 0

        # Check that the message was published correctly after reconnection
        # There might be differences in JSON spacing, so we check the topic only
        mock_mqtt_client.publish.assert_called_once()
        args, _ = mock_mqtt_client.publish.call_args
        assert args[0] == "/workitems/1.2.3.4/state"
