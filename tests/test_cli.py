import argparse
from unittest.mock import MagicMock, patch

import pytest

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import main


class TestCLI:
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.MQTTHealthChecker")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.start_dimse_server")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.AE")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_publishing_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_client")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_default_args(
        self,
        mock_parse_args,
        mock_mqtt_client,
        mock_mqtt_publishing_client,
        mock_ae,
        mock_start_dimse,
        mock_sleep,
        mock_health_checker,
    ):
        # Setup mock arguments with all required attributes including health check ones
        args = argparse.Namespace(
            broker_address="127.0.0.1",
            broker_port=1883,
            server_ae_title="UPSEventBroker01",
            server_listening_port=11119,
            health_check_interval=30,
            health_check_topic="health/dicom_broker",
            disable_health_check=False,
        )
        mock_parse_args.return_value = args

        # Setup MQTT client mock
        mock_client = MagicMock()
        mock_mqtt_client.Client.return_value = mock_client
        mock_mqtt_client.CallbackAPIVersion.VERSION2 = 2
        mock_client.is_connected.return_value = True

        # Setup AE mock
        mock_ae_instance = MagicMock()
        mock_ae.return_value = mock_ae_instance

        # Setup DIMSE server mock
        mock_dimse_server = MagicMock()
        mock_start_dimse.return_value = mock_dimse_server
        mock_dimse_server.server_address = ("127.0.0.1", 11119)

        # Setup Health Checker mock
        mock_health_checker_instance = MagicMock()
        mock_health_checker.return_value = mock_health_checker_instance

        # Make sleep raise exception to break out of infinite loop
        mock_sleep.side_effect = [None, Exception("Stop")]

        # Call main and expect it to raise the exception from sleep
        with pytest.raises(Exception, match="Stop"):
            main()

        # Verify MQTT client setup
        mock_mqtt_client.Client.assert_called_once_with(
            mock_mqtt_client.CallbackAPIVersion.VERSION2, client_id="UPSEventBroker01"
        )
        mock_client.connect.assert_called_once_with(host="127.0.0.1", port=1883)
        mock_client.loop_start.assert_called_once()

        # Verify that on_disconnect handler was registered
        assert mock_client.on_disconnect is not None

        # Verify AE setup
        mock_ae.assert_called_once_with("UPSEventBroker01")

        # Verify DIMSE server setup
        mock_start_dimse.assert_called_once_with(ae=mock_ae_instance, listening_port=11119)

        # Verify Health Checker was created with proper parameters
        mock_health_checker.assert_called_once_with(
            mqtt_client=mock_client,
            dimse_server=mock_dimse_server,
            check_interval=30,
            topic_prefix="health/dicom_broker",
            qos=1,
            retained=True,
        )

        # Verify health checker was started
        mock_health_checker_instance.start.assert_called_once()

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.MQTTHealthChecker")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.start_dimse_server")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.AE")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_publishing_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_client")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_custom_args(
        self,
        mock_parse_args,
        mock_mqtt_client,
        mock_mqtt_publishing_client,
        mock_ae,
        mock_start_dimse,
        mock_sleep,
        mock_health_checker,
    ):
        # Setup mock arguments with custom values including health check ones
        args = argparse.Namespace(
            broker_address="192.168.1.100",
            broker_port=8883,
            server_ae_title="CUSTOM_AE",
            server_listening_port=12345,
            health_check_interval=45,  # Custom value
            health_check_topic="custom/health/topic",  # Custom value
            disable_health_check=False,
        )
        mock_parse_args.return_value = args

        # Setup MQTT client mock
        mock_client = MagicMock()
        mock_mqtt_client.Client.return_value = mock_client
        mock_mqtt_client.CallbackAPIVersion.VERSION2 = 2
        mock_client.is_connected.return_value = True

        # Setup AE mock
        mock_ae_instance = MagicMock()
        mock_ae.return_value = mock_ae_instance

        # Setup DIMSE server mock
        mock_dimse_server = MagicMock()
        mock_start_dimse.return_value = mock_dimse_server
        mock_dimse_server.server_address = ("192.168.1.100", 12345)

        # Setup Health Checker mock
        mock_health_checker_instance = MagicMock()
        mock_health_checker.return_value = mock_health_checker_instance

        # Make sleep raise exception to break out of infinite loop
        mock_sleep.side_effect = [None, Exception("Stop")]

        # Call main and expect it to raise the exception from sleep
        with pytest.raises(Exception, match="Stop"):
            main()

        # Verify MQTT client setup with custom values
        mock_mqtt_client.Client.assert_called_once_with(mock_mqtt_client.CallbackAPIVersion.VERSION2, client_id="CUSTOM_AE")
        mock_client.connect.assert_called_once_with(host="192.168.1.100", port=8883)

        # Verify that on_disconnect handler was registered
        assert mock_client.on_disconnect is not None

        # Verify AE setup with custom AE title
        mock_ae.assert_called_once_with("CUSTOM_AE")

        # Verify DIMSE server setup with custom port
        mock_start_dimse.assert_called_once_with(ae=mock_ae_instance, listening_port=12345)

        # Verify Health Checker was created with custom parameters
        mock_health_checker.assert_called_once_with(
            mqtt_client=mock_client,
            dimse_server=mock_dimse_server,
            check_interval=45,
            topic_prefix="custom/health/topic",
            qos=1,
            retained=True,
        )

        # Verify health checker was started
        mock_health_checker_instance.start.assert_called_once()

    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.MQTTHealthChecker")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.time.sleep")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.start_dimse_server")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.AE")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_publishing_client")
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.mqtt_client")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_disabled_health_check(
        self,
        mock_parse_args,
        mock_mqtt_client,
        mock_mqtt_publishing_client,
        mock_ae,
        mock_start_dimse,
        mock_sleep,
        mock_health_checker,
    ):
        # Setup mock arguments with health check disabled
        args = argparse.Namespace(
            broker_address="127.0.0.1",
            broker_port=1883,
            server_ae_title="UPSEventBroker01",
            server_listening_port=11119,
            health_check_interval=30,
            health_check_topic="health/dicom_broker",
            disable_health_check=True,  # Health check is disabled
        )
        mock_parse_args.return_value = args

        # Setup MQTT client mock
        mock_client = MagicMock()
        mock_mqtt_client.Client.return_value = mock_client
        mock_mqtt_client.CallbackAPIVersion.VERSION2 = 2
        mock_client.is_connected.return_value = True

        # Setup AE mock
        mock_ae_instance = MagicMock()
        mock_ae.return_value = mock_ae_instance

        # Setup DIMSE server mock
        mock_dimse_server = MagicMock()
        mock_start_dimse.return_value = mock_dimse_server
        mock_dimse_server.server_address = ("127.0.0.1", 11119)

        # Make sleep raise exception to break out of infinite loop
        mock_sleep.side_effect = [None, Exception("Stop")]

        # Call main and expect it to raise the exception from sleep
        with pytest.raises(Exception, match="Stop"):
            main()

        # Verify MQTT client setup
        mock_mqtt_client.Client.assert_called_once_with(
            mock_mqtt_client.CallbackAPIVersion.VERSION2, client_id="UPSEventBroker01"
        )

        # Verify Health Checker was NOT created when disabled
        mock_health_checker.assert_not_called()
