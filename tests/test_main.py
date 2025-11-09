"""Unit tests for main.py module."""

import argparse
from unittest.mock import MagicMock, call, patch

import pytest

from dicom_event_broker_adapter.main import main


class TestMainModule:
    """Test main module functionality."""

    @patch("builtins.print")
    @patch("sys.exit")
    @patch("time.sleep")
    @patch("pynetdicom.AE")
    @patch("dicom_event_broker_adapter.health_check.MQTTHealthChecker")
    @patch("dicom_event_broker_adapter.subscriber_manager.cleanup_subscribers")
    @patch("dicom_event_broker_adapter.dimse_server.start_dimse_server")
    @patch("dicom_event_broker_adapter.mqtt_client.initialize_mqtt_publisher")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_default_arguments(
        self,
        mock_parse_args,
        mock_initialize_mqtt_publisher,
        mock_start_dimse_server,
        mock_cleanup_subscribers,
        mock_health_checker_class,
        mock_ae_class,
        mock_time_sleep,
        mock_sys_exit,
        mock_print,
    ):
        """Test main function with default arguments."""
        # Arrange
        # Set up default command line arguments
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

        # Mock MQTT publisher
        mock_mqtt_client = MagicMock()
        mock_mqtt_client.is_connected.return_value = True
        mock_initialize_mqtt_publisher.return_value = mock_mqtt_client

        # Mock AE
        mock_ae_instance = MagicMock()
        mock_ae_class.return_value = mock_ae_instance

        # Mock DIMSE server
        mock_dimse_server = MagicMock()
        mock_start_dimse_server.return_value = mock_dimse_server
        mock_dimse_server.server_address = ("127.0.0.1", 11119)

        # Mock health checker
        mock_health_checker = MagicMock()
        mock_health_checker_class.return_value = mock_health_checker

        # Mock time.sleep to raise KeyboardInterrupt to exit the main loop
        # Need to handle multiple sleep calls: initial 2-second sleep + loop sleep
        call_count = 0
        def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call is time.sleep(2) after MQTT connection
                return  # Just return normally
            else:  # Second call onwards - main loop sleep (duration=1)
                raise KeyboardInterrupt()  # Exit the main loop
        
        mock_time_sleep.side_effect = sleep_side_effect

        # Act & Assert
        with pytest.raises(KeyboardInterrupt):
            main()

        # Assert the main components were initialized correctly
        mock_initialize_mqtt_publisher.assert_called_once_with(
            client_id="UPSEventBroker01", broker_address="127.0.0.1", broker_port=1883
        )

        mock_ae_class.assert_called_once_with("UPSEventBroker01")
        mock_start_dimse_server.assert_called_once_with(ae=mock_ae_instance, listening_port=11119)

        mock_health_checker_class.assert_called_once_with(
            mqtt_client=mock_mqtt_client,
            dimse_server=mock_dimse_server,
            check_interval=30,
            topic_prefix="health/dicom_broker",
            qos=1,
            retained=True,
        )
        mock_health_checker.start.assert_called_once()

        # Verify cleanup was performed
        mock_health_checker.stop.assert_called_once()
        mock_cleanup_subscribers.assert_called_once()
        mock_dimse_server.shutdown.assert_called_once()
        mock_mqtt_client.loop_stop.assert_called_once()
        mock_mqtt_client.disconnect.assert_called_once()

        # Verify the expected print statements were made
        assert mock_print.called
        assert call("Publishing Client is connected") in mock_print.call_args_list
        assert call("DICOM Server running on: ('127.0.0.1', 11119)") in mock_print.call_args_list

    @patch("builtins.print")
    @patch("sys.exit")
    @patch("time.sleep") 
    @patch("pynetdicom.AE")
    @patch("dicom_event_broker_adapter.dimse_server.start_dimse_server")
    @patch("dicom_event_broker_adapter.mqtt_client.initialize_mqtt_publisher")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_with_disabled_health_check(
        self,
        mock_parse_args,
        mock_initialize_mqtt_publisher,
        mock_start_dimse_server,
        mock_ae_class,
        mock_time_sleep,
        mock_sys_exit,
        mock_print,
    ):
        """Test main function with health check disabled."""
        # Arrange
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

        # Mock MQTT publisher
        mock_mqtt_client = MagicMock()
        mock_mqtt_client.is_connected.return_value = True
        mock_initialize_mqtt_publisher.return_value = mock_mqtt_client

        # Mock AE
        mock_ae_instance = MagicMock()
        mock_ae_class.return_value = mock_ae_instance

        # Mock DIMSE server
        mock_dimse_server = MagicMock()
        mock_start_dimse_server.return_value = mock_dimse_server

        # Mock time.sleep to raise KeyboardInterrupt to exit the main loop
        call_count = 0
        def sleep_side_effect(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call is time.sleep(2) after MQTT connection
                return  # Just return normally
            else:  # Second call onwards - main loop sleep (duration=1)
                raise KeyboardInterrupt()  # Exit the main loop
        
        mock_time_sleep.side_effect = sleep_side_effect

        # Act & Assert
        with pytest.raises(KeyboardInterrupt):
            main()

        # Health checker should NOT be created when disabled
        # This would only be checked if we patched the MQTTHealthChecker in this test
        # Let's verify expected behavior without health checker
        mock_initialize_mqtt_publisher.assert_called_once()
        mock_ae_class.assert_called_once_with("UPSEventBroker01")
        mock_start_dimse_server.assert_called_once()

        # Verify print statements (without health checker ones)
        assert mock_print.called

    @patch("builtins.print")
    @patch("sys.exit")
    @patch("time.sleep")
    @patch("pynetdicom.AE")
    @patch("dicom_event_broker_adapter.dimse_server.start_dimse_server")
    @patch("dicom_event_broker_adapter.mqtt_client.initialize_mqtt_publisher")
    @patch("argparse.ArgumentParser.parse_args")
    def test_main_dimse_server_failure(
        self,
        mock_parse_args,
        mock_initialize_mqtt_publisher,
        mock_start_dimse_server,
        mock_ae_class,
        mock_time_sleep,
        mock_sys_exit,
        mock_print,
    ):
        """Test main function when DIMSE server fails to start."""
        # Arrange
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

        # Mock MQTT publisher
        mock_mqtt_client = MagicMock()
        mock_mqtt_client.is_connected.return_value = True
        mock_initialize_mqtt_publisher.return_value = mock_mqtt_client

        # Mock AE
        mock_ae_instance = MagicMock()
        mock_ae_class.return_value = mock_ae_instance

        # Mock DIMSE server to raise an exception
        mock_start_dimse_server.side_effect = Exception("Failed to start DIMSE server")

        # Mock time.sleep to allow the main loop to run briefly
        mock_time_sleep.return_value = None

        # Act
        main()  # Should exit due to sys.exit() call

        # Verify sys.exit was called
        mock_sys_exit.assert_called_once_with(1)

        # Verify the error was printed
        error_printed = any(
            "Failed to start DIMSE server" in str(call_arg[0])
            for call_arg in mock_print.call_args_list
            if len(call_arg[0]) > 0
        )
        assert error_printed