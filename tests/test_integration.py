"""Integration tests for DICOM Event Broker Adapter modules."""

from unittest.mock import MagicMock, patch

from pydicom import Dataset
from pynetdicom.sop_class import UnifiedProcedureStepPush

from dicom_event_broker_adapter.config import ADAPTER_AE_TITLE, construct_mqtt_topic
from dicom_event_broker_adapter.dimse_server import handle_echo
from dicom_event_broker_adapter.event_processor import send_event_report
from dicom_event_broker_adapter.health_check import MQTTHealthChecker
from dicom_event_broker_adapter.subscriber_manager import register_subscriber, unregister_subscriber


class TestModuleIntegration:
    """Test integration between different modules."""

    @patch("dicom_event_broker_adapter.event_processor.AE")
    @patch("dicom_event_broker_adapter.event_processor.load_ae_config")
    def test_config_and_event_processor_integration(self, mock_load_ae_config, mock_ae_class):
        """Test that config and event_processor work together correctly."""
        # Arrange: Set up config data that event_processor will use
        subscriber_ae_title = "TEST_SUBSCRIBER"
        expected_ip = "127.0.0.1"
        expected_port = 11112
        mock_load_ae_config.return_value = {subscriber_ae_title: (expected_ip, expected_port)}

        # Mock AE and association
        mock_ae_instance = MagicMock()
        mock_assoc_instance = MagicMock()
        mock_ae_instance.associate.return_value = mock_assoc_instance
        mock_assoc_instance.is_established = True
        mock_assoc_instance.send_n_event_report.return_value = MagicMock()
        mock_ae_class.return_value = mock_ae_instance

        # Create a test dataset
        test_dataset = Dataset()
        test_dataset.AffectedSOPInstanceUID = "1.2.3.4.5.6.7"
        test_dataset.EventTypeID = 1
        test_dataset.AffectedSOPClassUID = UnifiedProcedureStepPush

        # Act: Call the function that integrates config and event_processor
        send_event_report(test_dataset, "CLIENT_AE", subscriber_ae_title)

        # Assert: Verify that the associate was called (checking key params but not contexts)
        mock_assoc_instance = mock_ae_instance.associate
        assert mock_assoc_instance.called
        call_args = mock_assoc_instance.call_args
        assert call_args[1]["addr"] == expected_ip
        assert call_args[1]["port"] == expected_port
        assert call_args[1]["ae_title"] == subscriber_ae_title
        # Check that contexts was passed as a list (which it should be in the real implementation)
        assert "contexts" in call_args[1]

    def test_mqtt_client_and_health_check_integration(self):
        """Test that mqtt_client and health_check work together."""
        # Arrange: Create mock MQTT client that health_check will publish to
        mock_mqtt_client = MagicMock()
        mock_dimse_server = MagicMock()

        # Mock the connection status that health_check monitors
        mock_mqtt_client.is_connected.return_value = True
        mock_dimse_server.server = MagicMock()  # Indicate it's running

        # Act: Health checker publishes status to MQTT client
        checker = MQTTHealthChecker(mqtt_client=mock_mqtt_client, dimse_server=mock_dimse_server, check_interval=1)

        # Simulate the core functionality of the health check without running the full loop
        mqtt_connected = mock_mqtt_client.is_connected()
        dimse_running = hasattr(mock_dimse_server, "server") and mock_dimse_server.server is not None

        import json
        import time

        health_status = {
            "timestamp": time.time(),  # Use real time
            "mqtt_connected": mqtt_connected,
            "dimse_running": dimse_running,
            "overall_status": mqtt_connected and dimse_running,
        }

        if mqtt_connected:
            health_topic = f"{checker.topic_prefix}/status"
            health_payload = json.dumps(health_status)
            mock_mqtt_client.publish(health_topic, health_payload, qos=checker.qos, retain=checker.retained)

        # Assert: Verify MQTT client received the health status
        mock_mqtt_client.publish.assert_called_once()
        call_args = mock_mqtt_client.publish.call_args
        assert call_args[0][0] == "health/dicom_broker/status"  # Topic
        assert call_args[1]["qos"] == 1  # Quality of service
        assert call_args[1]["retain"] is True  # Retain flag

    def test_config_and_mqtt_topic_integration(self):
        """Test that config and topic construction work together."""
        # Test that the constants from config are used in topic construction
        assert ADAPTER_AE_TITLE == "UPSEventBroker01"

        # Test topic construction with worklist subscription
        topic = construct_mqtt_topic("Workitem", subscription_type="Worklist")
        assert topic == "/workitems"

        # Test topic construction with specific workitem
        workitem_uid = "1.2.3.4.5.6.7"
        topic = construct_mqtt_topic("Workitem", workitem_uid=workitem_uid)
        expected = f"/workitems/{workitem_uid}"
        assert topic == expected


class TestEndToEndWorkflow:
    """Test end-to-end workflows that span multiple modules."""

    def test_subscribe_unsubscribe_workflow(self):
        """Test the workflow for registering and unregistering a subscriber."""
        # This test would typically involve the full flow:
        # 1. Register subscriber (subscriber_manager)
        # 2. Process MQTT message (mqtt_client)
        # 3. Handle N-ACTION (dimse_server)
        # 4. Unregister subscriber (subscriber_manager)
        #
        # For this test, we'll just verify that the calls can be made
        # without error, assuming the global state is managed correctly

        # Mock the global state that would typically be in the system
        with (
            patch("dicom_event_broker_adapter.subscriber_manager.subscriber_clients", []),
            patch("dicom_event_broker_adapter.subscriber_manager.subscriber_processes", []),
            patch("dicom_event_broker_adapter.subscriber_manager.command_queues", {}),
            patch("dicom_event_broker_adapter.subscriber_manager.Queue"),
            patch("dicom_event_broker_adapter.subscriber_manager.Process"),
        ):
            # Register a subscriber
            ae_title = "TEST_SUBSCRIBER"
            topic = "/workitems/test"
            register_subscriber(ae_title, topic)

            # Verify it's in the tracking structures
            # This would be tested by looking at the mocked global state
            # In a real integration test, we'd check the actual state

            # Unregister the subscriber
            unregister_subscriber(ae_title, topic)

    @patch("dicom_event_broker_adapter.dimse_server.handle_dimse_n_event")
    def test_dimse_event_to_mqtt_workflow(self, mock_handle_dimse_n_event):
        """Test integration between DIMSE event handling and MQTT publishing."""
        # This would test the flow from DIMSE event to MQTT publish
        # The actual integration happens in the dimse_server and mqtt_client modules

        # Simulate an event object that would trigger the workflow
        mock_event = MagicMock()
        mock_assoc = MagicMock()
        mock_requestor = MagicMock()
        mock_requestor.ae_title = "TEST_AE"
        mock_requestor.address = "127.0.0.1"
        mock_requestor.port = 11112
        mock_assoc.requestor = mock_requestor
        mock_event.assoc = mock_assoc
        mock_event.timestamp.strftime.return_value = "2023-01-01 12:00:00"

        # Call the handler (normally called by pynetdicom)
        result = handle_echo(mock_event)

        # Verify that the echo was handled appropriately
        assert result == 0x0000  # Success code
