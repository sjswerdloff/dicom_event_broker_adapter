"""End-to-end integration tests from MQTT to real DICOM UPS SCP using tdwii_plus_examples."""

import json
import logging
import os
import tempfile
import threading
import time
from typing import Dict, List
from unittest.mock import patch

import paho.mqtt.client as mqtt_client_module
import pytest
from pydicom import Dataset
from pynetdicom import AE
from pynetdicom.presentation import build_context
from pynetdicom.sop_class import UnifiedProcedureStepEvent, UnifiedProcedureStepPush, UnifiedProcedureStepWatch
from tdwii_plus_examples.upsneventreceiver import UPSNEventReceiver

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import ADAPTER_AE_TITLE, _construct_mqtt_topic

# Configure detailed logging for debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mqtt_dicom_e2e_test")
logger.setLevel(logging.DEBUG)


@pytest.mark.mqtt_integration
class TestMQTTToDICOME2E:
    """Test the complete end-to-end flow from MQTT to a real DICOM UPS SCP using tdwii_plus_examples."""

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

        client = mqtt_client_module.Client(
            callback_api_version=mqtt_client_module.CallbackAPIVersion.VERSION2, client_id=client_id
        )
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
            try:
                # Always attempt to stop the loop and disconnect
                logger.debug(f"Cleaning up MQTT client {client_id}")
                client.loop_stop()

                # Wait a moment for the loop to fully stop
                time.sleep(0.2)

                if client.is_connected():
                    client.disconnect()
                    logger.debug(f"MQTT client {client_id} properly disconnected")
            except Exception as e:
                logger.warning(f"Error during MQTT client cleanup: {e}")

    @pytest.fixture
    def ups_scp_server(self):
        """Create a real DICOM UPS SCP server using tdwii_plus_examples UPSNEventReceiver."""
        received_events: List[Dict] = []

        # Create a custom UPS event callback
        def ups_event_callback(ups_instance, ups_event_type, ups_event_info, app_logger):
            """
            Custom callback for UPS N-EVENT-REPORT events.

            Parameters
            ----------
            ups_instance : pydicom.uid.UID
                The UPS SOP Instance UID.
            ups_event_type : int
                The UPS Event Type ID.
            ups_event_info : pydicom.dataset.Dataset
                The N-EVENT-REPORT-RQ Event Information dataset.
            app_logger : logging.Logger
                The application's logger instance
            """
            logger.info(f"✅ Received UPS event for UPS Instance {ups_instance}")
            logger.info(f"✅ UPS Event Type: {ups_event_type}")

            # Store the event information
            received_events.append(
                {
                    "event_type_id": ups_event_type,
                    "affected_sop_class_uid": UnifiedProcedureStepPush,
                    "affected_sop_instance_uid": ups_instance,
                    "dataset": ups_event_info,
                    "timestamp": time.time(),
                }
            )

        # Create the UPS N-EVENT receiver from tdwii_plus_examples
        ups_receiver = UPSNEventReceiver(
            ae_title="TEST_UPS_SCP", bind_address="127.0.0.1", port=11112, ups_event_callback=ups_event_callback, logger=logger
        )

        # Manually add support for the UPS Push SOP Class since we'll be receiving N-EVENT-REPORT
        # for this SOP Class. This is in addition to the UPS Event SOP Class that's added by default
        # in UPSNEventReceiver
        ups_receiver.ae.add_supported_context(UnifiedProcedureStepPush)

        # Create a temporary ApplicationEntities.json file for the UPS adapter to find our SCP
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as temp_ae_config:
            json.dump([{"AETitle": "TEST_UPS_SCP", "IPAddr": "127.0.0.1", "Port": 11112}], temp_ae_config)
            temp_ae_path = temp_ae_config.name

        # Start the receiver
        server = None
        server_thread = None

        try:
            # Use a thread to run the server
            stop_flag = threading.Event()

            def run_server():
                """Background thread to run the UPS N-EVENT receiver server."""
                nonlocal server
                # The run() method in BaseSCP doesn't have a block parameter
                # It already runs in a non-blocking mode
                ups_receiver.run()
                server = ups_receiver.threaded_server
                while not stop_flag.is_set():
                    time.sleep(0.1)

            server_thread = threading.Thread(target=run_server)
            server_thread.daemon = True
            server_thread.start()

            # Give the server time to start
            time.sleep(0.5)

            yield {"ae": ups_receiver.ae, "server": server, "received_events": received_events, "temp_ae_path": temp_ae_path}

        finally:
            # Clean up the server
            if server:
                try:
                    logger.debug("Shutting down DICOM server...")
                    server.shutdown()
                    logger.debug("DICOM server shutdown completed")
                except Exception as e:
                    logger.error(f"Error shutting down server: {e}")

            # Stop the thread with more robust termination
            if server_thread:
                logger.debug("Stopping server thread...")
                stop_flag.set()

                # Join with an increased timeout
                max_attempts = 3
                for attempt in range(max_attempts):
                    server_thread.join(timeout=3)  # 3 seconds timeout
                    if not server_thread.is_alive():
                        logger.debug("Server thread stopped successfully")
                        break
                    elif attempt < max_attempts - 1:
                        logger.warning(f"Server thread still alive after join attempt {attempt+1}, retrying...")
                    else:
                        logger.warning("Server thread did not terminate properly after multiple attempts")
                        # Thread is daemon so it won't prevent pytest from exiting
                        break

            # Clean up temporary file
            if os.path.exists(temp_ae_path):
                logger.debug(f"Removing temporary AE config file: {temp_ae_path}")
                os.unlink(temp_ae_path)

    @pytest.mark.parametrize("event_type", ["state", "cancelrequest"])
    def test_mqtt_to_real_dicom_scp_adapter_initiated(self, mqtt_client, ups_scp_server, event_type):
        """Test the complete end-to-end flow from MQTT to a real DICOM UPS SCP using tdwii_plus_examples UPSNEventReceiver."""
        # Import os to avoid UnboundLocalError
        import os

        # Save the original ApplicationEntities.json to restore later
        original_ae_content = None
        if os.path.exists("ApplicationEntities.json"):
            with open("ApplicationEntities.json", "r") as f:
                original_ae_content = f.read()

        try:
            # Copy the temporary ApplicationEntities.json for the test
            with open(ups_scp_server["temp_ae_path"], "r") as src:
                with open("ApplicationEntities.json", "w") as dst:
                    dst.write(src.read())

            # Create test data based on event type
            workitem_uid = "1.2.3.4.5.6.7"
            test_dataset = Dataset()
            test_dataset.PatientID = "TestPatient"
            test_dataset.PatientName = "Test^Patient"

            if event_type == "state":
                test_dataset.ProcedureStepState = "IN PROGRESS"
                expected_event_type_id = 1
            else:  # cancelrequest
                test_dataset.ReasonForCancellation = "Test cancellation"
                expected_event_type_id = 2

            # Create the MQTT topic
            topic = _construct_mqtt_topic(event_type="Workitem", workitem_uid=workitem_uid, workitem_subtopic=event_type)

            # Convert the dataset to JSON for MQTT
            json_payload = test_dataset.to_json()

            # Import the adapter module here to avoid circular imports
            from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import (
                mqtt_publishing_client,
                process_mqtt_message,
                register_subscriber,
            )

            # Ensure the mqtt_publishing_client is connected
            if mqtt_publishing_client is None or not mqtt_publishing_client.is_connected():
                # Initialize the publishing client if needed
                import dicom_event_broker_adapter.ups_event_mqtt_broker_adapter as adapter

                adapter.mqtt_publishing_client = mqtt_client_module.Client(
                    mqtt_client_module.CallbackAPIVersion.VERSION2, client_id=ADAPTER_AE_TITLE
                )
                adapter.mqtt_publishing_client.connect(host="localhost", port=1883)
                adapter.mqtt_publishing_client.loop_start()
                # Wait for connection
                time.sleep(0.5)

            # Register our SCP as a subscriber to receive events
            register_subscriber(ae_title="TEST_UPS_SCP", topic=topic)

            # Create a mock MQTT message
            class MockMessage:
                def __init__(self, topic, payload):
                    self.topic = topic
                    self.payload = payload.encode()

            mqtt_message = MockMessage(topic, json_payload)

            # Use the process_mqtt_message function directly with process name patched
            with patch("multiprocessing.current_process") as mock_process:
                # Set process name as subscriber AE title
                mock_process.return_value.name = "TEST_UPS_SCP"

                # Process the message
                process_mqtt_message(this_client=mqtt_client, userdata=None, message=mqtt_message)

            # Wait for the event to be processed by the SCP
            timeout = 10  # Increased timeout for debugging
            start_time = time.time()

            logger.info("Waiting for DICOM event to be received by the SCP...")

            # Debug: Print information about our SCP server
            logger.debug(f"SCP server details: {ups_scp_server['server']}")
            logger.debug(f"SCP AE details: {ups_scp_server['ae']}")

            # Print connection information
            logger.debug("ApplicationEntities.json content:")
            with open("ApplicationEntities.json", "r") as f:
                logger.debug(f.read())

            # Poll with logging to see progress
            wait_count = 0
            while time.time() - start_time < timeout and not ups_scp_server["received_events"]:
                time.sleep(0.5)
                wait_count += 1
                if wait_count % 4 == 0:  # Log every 2 seconds
                    logger.debug(f"Still waiting for DICOM event... ({wait_count/2}s elapsed)")

                    # Try to debug what's happening - check if the DICOM association is being formed
                    from pynetdicom import debug_logger

                    debug_logger()  # Enable detailed PyNetDICOM debug logs

            # Verify the SCP received the event
            if not ups_scp_server["received_events"]:
                logger.error("❌ No events received by SCP after timeout!")
                # Debug information to help troubleshoot
                logger.debug("Topic used: " + topic)
                logger.debug("JSON payload: " + json_payload)
                logger.debug("Attempted to send to AE: TEST_UPS_SCP at 127.0.0.1:11112")
            else:
                logger.info(f"✅ Successfully received {len(ups_scp_server['received_events'])} events!")

            assert len(ups_scp_server["received_events"]) == 1

            # Verify the event details
            received_event = ups_scp_server["received_events"][0]
            assert received_event["event_type_id"] == expected_event_type_id
            assert received_event["affected_sop_class_uid"] == UnifiedProcedureStepPush
            assert received_event["affected_sop_instance_uid"] == workitem_uid

            # Verify the dataset contains our test data
            received_dataset = received_event["dataset"]
            assert received_dataset.PatientID == "TestPatient"
            assert received_dataset.PatientName == "Test^Patient"

            if event_type == "state":
                assert received_dataset.ProcedureStepState == "IN PROGRESS"
            else:  # cancelrequest
                assert received_dataset.ReasonForCancellation == "Test cancellation"

        finally:
            # Restore the original ApplicationEntities.json if it existed
            if original_ae_content is not None:
                with open("ApplicationEntities.json", "w") as f:
                    f.write(original_ae_content)

            # Clean up the MQTT client if we created one
            try:
                import dicom_event_broker_adapter.ups_event_mqtt_broker_adapter as adapter

                if adapter.mqtt_publishing_client:
                    logger.debug("Cleaning up adapter MQTT publishing client")
                    try:
                        adapter.mqtt_publishing_client.loop_stop()
                        logger.debug("MQTT client loop stopped")
                    except Exception as e:
                        logger.warning(f"Error stopping MQTT client loop: {e}")

                    try:
                        # Allow time for loop to fully stop before disconnecting
                        time.sleep(0.2)
                        if adapter.mqtt_publishing_client.is_connected():
                            adapter.mqtt_publishing_client.disconnect()
                            logger.debug("Adapter MQTT publishing client disconnected")
                    except Exception as e:
                        logger.warning(f"Error disconnecting MQTT client: {e}")

                    # Clear the client reference to help with garbage collection
                    adapter.mqtt_publishing_client = None

                # Clean up any subscriber processes that might be running with more robust termination
                if adapter.subscriber_processes:
                    logger.debug(f"Cleaning up {len(adapter.subscriber_processes)} subscriber processes")
                    for process in adapter.subscriber_processes:
                        try:
                            if process.is_alive():
                                # First try graceful termination
                                process.terminate()
                                # Use shorter timeout for first join attempt
                                process.join(timeout=0.5)

                                # If process is still alive, try again with longer timeout
                                if process.is_alive():
                                    logger.warning(f"Process {process.name} still alive after terminate, retrying...")
                                    process.join(timeout=1.0)

                                    # If still alive after second attempt, force kill on Unix systems
                                    if process.is_alive():
                                        logger.warning(f"Process {process.name} did not terminate properly, force killing...")
                                        import os
                                        import signal

                                        try:
                                            os.kill(process.pid, signal.SIGKILL)
                                            # Short wait to allow OS to clean up
                                            time.sleep(0.1)
                                        except Exception as kill_error:
                                            logger.error(f"Failed to kill process {process.name}: {kill_error}")
                                else:
                                    logger.debug(f"Process {process.name} terminated successfully")
                        except Exception as e:
                            logger.warning(f"Error terminating process {process.name}: {e}")

                    # Clear the lists to avoid re-terminating processes
                    adapter.subscriber_processes = []
                    adapter.subscriber_clients = []
                    adapter.command_queues = {}
            except Exception as e:
                logger.error(f"Error during module MQTT client cleanup: {e}")

    def test_mqtt_producer_to_dicom_consumer(self, mqtt_client, ups_scp_server):
        """
        Test MQTT producer to DICOM consumer flow:
        1. Send MQTT message with UPS state change
        2. Broker converts to DICOM N-EVENT-REPORT
        3. Verify UPS N-EVENT-REPORT is received by UPSNEventReceiver
        """
        # Import os to avoid UnboundLocalError
        import os

        # Save the original ApplicationEntities.json to restore later
        original_ae_content = None
        if os.path.exists("ApplicationEntities.json"):
            with open("ApplicationEntities.json", "r") as f:
                original_ae_content = f.read()

        try:
            # Copy the temporary ApplicationEntities.json for the test
            with open(ups_scp_server["temp_ae_path"], "r") as src:
                with open("ApplicationEntities.json", "w") as dst:
                    dst.write(src.read())

            # Setup a subscriber to receive MQTT messages and forward to DICOM
            from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import (
                load_ae_config,
                mqtt_publishing_client,
                process_mqtt_message,
                register_subscriber,
            )

            # Ensure the mqtt_publishing_client is connected
            if mqtt_publishing_client is None or not mqtt_publishing_client.is_connected():
                import dicom_event_broker_adapter.ups_event_mqtt_broker_adapter as adapter

                adapter.mqtt_publishing_client = mqtt_client_module.Client(
                    mqtt_client_module.CallbackAPIVersion.VERSION2, client_id=ADAPTER_AE_TITLE
                )
                adapter.mqtt_publishing_client.connect(host="localhost", port=1883)
                adapter.mqtt_publishing_client.loop_start()
                # Wait for connection
                time.sleep(0.5)

            # Create a special AE to handle sending the N-EVENT-REPORT messages
            # This is normally handled by the adapter module, but we need to ensure
            # it has the correct presentation contexts
            send_event_ae = AE(ae_title=ADAPTER_AE_TITLE)

            # Add the context needed for N-EVENT-REPORT
            send_event_ae.add_requested_context(UnifiedProcedureStepPush)
            send_event_ae.add_requested_context(UnifiedProcedureStepEvent)
            send_event_ae.add_requested_context(UnifiedProcedureStepWatch)

            # Patch the send_event_report function to use our special AE
            def patched_send_event_report(dataset, client_ae_title, subscriber_ae_title):
                """Patched version that ensures the right presentation contexts are used."""
                # Create custom presentation contexts for UPS
                contexts = [
                    build_context(UnifiedProcedureStepPush),
                    build_context(UnifiedProcedureStepEvent),
                    build_context(UnifiedProcedureStepWatch),
                ]

                known_aes = {}
                if subscriber_ae_title not in known_aes:
                    known_aes = load_ae_config()
                if subscriber_ae_title not in known_aes:
                    print(f"AE {subscriber_ae_title} not found in Application Entities configuration file")
                    return None

                ip, port = known_aes[subscriber_ae_title]
                send_event_assoc = send_event_ae.associate(addr=ip, port=port, contexts=contexts, ae_title=subscriber_ae_title)
                if send_event_assoc.is_established:
                    status = send_event_assoc.send_n_event_report(
                        dataset, dataset.EventTypeID, UnifiedProcedureStepPush, dataset.AffectedSOPInstanceUID
                    )
                    print(f"N-EVENT-REPORT status: {status}")
                    send_event_assoc.release()
                    return status
                else:
                    print(f"Association rejected, aborted or never connected with {subscriber_ae_title}")
                    return 0xC000

            # Patch the function
            with patch(
                "dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.send_event_report",
                side_effect=patched_send_event_report,
            ):
                # Create a workitem UID
                workitem_uid = "1.2.3.4.5.6.7"

                # Create a test dataset
                test_dataset = Dataset()
                test_dataset.PatientID = "TestPatient"
                test_dataset.PatientName = "Test^Patient"
                test_dataset.ProcedureStepState = "IN PROGRESS"

                # Create the MQTT topic for state changes
                topic = _construct_mqtt_topic(event_type="Workitem", workitem_uid=workitem_uid, workitem_subtopic="state")

                # Register our SCP as a subscriber to receive events
                register_subscriber(ae_title="TEST_UPS_SCP", topic=topic)

                # Mock the multiprocessing.current_process for the adapter
                with patch("multiprocessing.current_process") as mock_process:
                    mock_process.return_value.name = "TEST_UPS_SCP"

                    # Subscribe to the MQTT topic that will receive UPS state changes
                    def on_message(client, userdata, msg, properties=None):
                        """Handle incoming MQTT messages and convert to DICOM N-EVENT-REPORT."""
                        logger.info(f"Received MQTT message on topic: {msg.topic}")

                        # Process the message with our adapter
                        process_mqtt_message(this_client=client, userdata=userdata, message=msg)

                    # mqtt_client is already a client instance from the fixture
                    mqtt_client.subscribe(topic)
                    mqtt_client.on_message = on_message

                    # Convert the dataset to JSON and publish to MQTT
                    json_payload = test_dataset.to_json()
                    result = mqtt_client.publish(topic, json_payload)
                    assert result.rc == 0  # MQTT_ERR_SUCCESS

                    logger.info(f"Published UPS state change for {workitem_uid} to MQTT topic: {topic}")

                    # Wait for the event to be processed by the SCP
                    timeout = 10
                    start_time = time.time()

                    logger.info("Waiting for DICOM event to be received by the SCP...")

                    # Poll with logging to see progress
                    wait_count = 0
                    while time.time() - start_time < timeout and not ups_scp_server["received_events"]:
                        time.sleep(0.5)
                        wait_count += 1
                        if wait_count % 4 == 0:  # Log every 2 seconds
                            logger.debug(f"Still waiting for DICOM event... ({wait_count/2}s elapsed)")

                    # Verify the SCP received the event
                    if not ups_scp_server["received_events"]:
                        logger.error("❌ No events received by SCP after timeout!")
                        logger.debug("Topic used: " + topic)
                        logger.debug("JSON payload: " + json_payload)
                    else:
                        logger.info(f"✅ Successfully received {len(ups_scp_server['received_events'])} events!")

                    assert len(ups_scp_server["received_events"]) == 1

                    # Verify the event details
                    received_event = ups_scp_server["received_events"][0]
                    assert received_event["event_type_id"] == 1  # State Report
                    assert received_event["affected_sop_class_uid"] == UnifiedProcedureStepPush
                    assert received_event["affected_sop_instance_uid"] == workitem_uid

                    # Verify the dataset contains our test data
                    received_dataset = received_event["dataset"]
                    assert received_dataset.PatientID == "TestPatient"
                    assert received_dataset.PatientName == "Test^Patient"
                    assert received_dataset.ProcedureStepState == "IN PROGRESS"

        finally:
            # Restore the original ApplicationEntities.json if it existed
            if original_ae_content is not None:
                with open("ApplicationEntities.json", "w") as f:
                    f.write(original_ae_content)

            # Clean up the MQTT client if we created one
            try:
                import dicom_event_broker_adapter.ups_event_mqtt_broker_adapter as adapter

                if adapter.mqtt_publishing_client:
                    logger.debug("Cleaning up adapter MQTT publishing client")
                    try:
                        adapter.mqtt_publishing_client.loop_stop()
                        logger.debug("MQTT client loop stopped")
                    except Exception as e:
                        logger.warning(f"Error stopping MQTT client loop: {e}")

                    try:
                        # Allow time for loop to fully stop before disconnecting
                        time.sleep(0.2)
                        if adapter.mqtt_publishing_client.is_connected():
                            adapter.mqtt_publishing_client.disconnect()
                            logger.debug("Adapter MQTT publishing client disconnected")
                    except Exception as e:
                        logger.warning(f"Error disconnecting MQTT client: {e}")

                    # Clear the client reference to help with garbage collection
                    adapter.mqtt_publishing_client = None

                # Clean up any subscriber processes that might be running with more robust termination
                if adapter.subscriber_processes:
                    logger.debug(f"Cleaning up {len(adapter.subscriber_processes)} subscriber processes")
                    for process in adapter.subscriber_processes:
                        try:
                            if process.is_alive():
                                # First try graceful termination
                                process.terminate()
                                # Use shorter timeout for first join attempt
                                process.join(timeout=0.5)

                                # If process is still alive, try again with longer timeout
                                if process.is_alive():
                                    logger.warning(f"Process {process.name} still alive after terminate, retrying...")
                                    process.join(timeout=1.0)

                                    # If still alive after second attempt, force kill on Unix systems
                                    if process.is_alive():
                                        logger.warning(f"Process {process.name} did not terminate properly, force killing...")
                                        import os
                                        import signal

                                        try:
                                            os.kill(process.pid, signal.SIGKILL)
                                            # Short wait to allow OS to clean up
                                            time.sleep(0.1)
                                        except Exception as kill_error:
                                            logger.error(f"Failed to kill process {process.name}: {kill_error}")
                                else:
                                    logger.debug(f"Process {process.name} terminated successfully")
                        except Exception as e:
                            logger.warning(f"Error terminating process {process.name}: {e}")

                    # Clear the lists to avoid re-terminating processes
                    adapter.subscriber_processes = []
                    adapter.subscriber_clients = []
                    adapter.command_queues = {}
            except Exception as e:
                logger.error(f"Error during module MQTT client cleanup: {e}")
