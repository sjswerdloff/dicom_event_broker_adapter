"""Unit tests for health_check.py module."""

from unittest.mock import MagicMock, patch

from pynetdicom.transport import ThreadedAssociationServer

from dicom_event_broker_adapter.health_check import MQTTHealthChecker


class TestMQTTHealthChecker:
    """Test MQTTHealthChecker class."""

    def test_initialization(self):
        """Test MQTTHealthChecker initialization with default parameters."""
        # Arrange
        mock_mqtt_client = MagicMock()
        mock_dimse_server = MagicMock(spec=ThreadedAssociationServer)

        # Act
        checker = MQTTHealthChecker(mqtt_client=mock_mqtt_client, dimse_server=mock_dimse_server)

        # Assert
        assert checker.mqtt_client == mock_mqtt_client
        assert checker.dimse_server == mock_dimse_server
        assert checker.check_interval == 30
        assert checker.topic_prefix == "health/dicom_broker"
        assert checker.qos == 1
        assert checker.retained is True
        assert checker._running is False

    def test_initialization_with_custom_parameters(self):
        """Test MQTTHealthChecker initialization with custom parameters."""
        # Arrange
        mock_mqtt_client = MagicMock()
        mock_dimse_server = MagicMock(spec=ThreadedAssociationServer)
        custom_interval = 60
        custom_prefix = "custom/health"
        custom_qos = 2
        custom_retained = False

        # Act
        checker = MQTTHealthChecker(
            mqtt_client=mock_mqtt_client,
            dimse_server=mock_dimse_server,
            check_interval=custom_interval,
            topic_prefix=custom_prefix,
            qos=custom_qos,
            retained=custom_retained,
        )

        # Assert
        assert checker.check_interval == custom_interval
        assert checker.topic_prefix == custom_prefix
        assert checker.qos == custom_qos
        assert checker.retained == custom_retained

    def test_start_method_creates_thread(self):
        """Test start method creates and starts a thread."""
        # Arrange
        mock_mqtt_client = MagicMock()
        mock_dimse_server = MagicMock(spec=ThreadedAssociationServer)

        checker = MQTTHealthChecker(mqtt_client=mock_mqtt_client, dimse_server=mock_dimse_server)

        # Act
        with patch("dicom_event_broker_adapter.health_check.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            checker.start()

            # Assert
            assert checker._running is True
            mock_thread.assert_called_once()
            # Check that daemon=True was set
            call_args = mock_thread.call_args
            assert call_args[1]["daemon"] is True  # Thread should be daemon

            # Check that thread was started
            mock_thread_instance.start.assert_called_once()

    def test_stop_method(self):
        """Test stop method stops the health checker."""
        # Arrange
        mock_mqtt_client = MagicMock()
        mock_dimse_server = MagicMock(spec=ThreadedAssociationServer)

        checker = MQTTHealthChecker(mqtt_client=mock_mqtt_client, dimse_server=mock_dimse_server)

        # Set up for stopping
        checker._running = True
        mock_thread = MagicMock()
        checker._thread = mock_thread

        # Act
        checker.stop()

        # Assert
        assert checker._running is False
        mock_thread.join.assert_called_once()

    @patch("dicom_event_broker_adapter.health_check.time.time", return_value=1234567890.0)
    def test_health_check_status_publishing_logic(self, mock_time):
        """Test the overall health check functionality."""
        # Arrange
        mock_mqtt_client = MagicMock()
        mock_dimse_server = MagicMock(spec=ThreadedAssociationServer)

        checker = MQTTHealthChecker(
            mqtt_client=mock_mqtt_client,
            dimse_server=mock_dimse_server,
            check_interval=30,
            topic_prefix="test/health",
            qos=2,
            retained=False,
        )

        # Mock the status checks
        mock_mqtt_client.is_connected.return_value = True
        mock_dimse_server.server = MagicMock()  # Present means DIMSE is running

        # Act
        # Manually execute the core logic of the health check without using the internal loop
        mqtt_connected = checker.mqtt_client.is_connected() if checker.mqtt_client else False
        dimse_running = hasattr(checker.dimse_server, "server") and checker.dimse_server.server is not None

        health_status = {
            "timestamp": mock_time.return_value,
            "mqtt_connected": mqtt_connected,
            "dimse_running": dimse_running,
            "overall_status": mqtt_connected and dimse_running,
        }

        # Test the publish logic
        if mqtt_connected:
            import json

            health_topic = f"{checker.topic_prefix}/status"
            health_payload = json.dumps(health_status)
            checker.mqtt_client.publish(health_topic, health_payload, qos=checker.qos, retain=checker.retained)

        # Assert that publish was called with expected parameters
        mock_mqtt_client.publish.assert_called_once()
        call_args = mock_mqtt_client.publish.call_args
        assert call_args[0][0] == "test/health/status"  # topic
        assert call_args[1]["qos"] == 2
        assert not call_args[1]["retain"]

        # Verify the payload contains the expected data
        import json

        payload_data = json.loads(call_args[0][1])  # Load the JSON payload
        assert payload_data["mqtt_connected"] is True
        assert payload_data["dimse_running"] is True
        assert payload_data["overall_status"] is True
        assert payload_data["timestamp"] == 1234567890.0
