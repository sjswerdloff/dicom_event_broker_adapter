"""
Common fixtures and utilities for tests.
"""

import json
import logging
import signal
import socket
import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest
from pydicom import Dataset
from pynetdicom.sop_class import UnifiedProcedureStepPush, UPSGlobalSubscriptionInstance


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "mqtt_integration: mark test as requiring a real MQTT broker")


# Configure logger for conftest
logger = logging.getLogger("conftest")
logger.setLevel(logging.DEBUG)


def is_port_open(host, port):
    """Check if a port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0


# Skip if Mosquitto is not running
mqtt_integration = pytest.mark.skipif(
    not is_port_open("localhost", 1883), reason="Mosquitto broker not available on localhost:1883"
)


@pytest.fixture
def mqtt_client_mock():
    """Create a mock MQTT client for testing."""
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.publish.return_value = MagicMock(rc=0)  # Success return code
    return mock_client


@pytest.fixture
def mock_event():
    """Create a generic mock Event object for DIMSE testing."""
    mock_event = MagicMock()
    # Add timestamp for DIMSE N-EVENT tests
    mock_event.timestamp = MagicMock()
    mock_event.timestamp.strftime.return_value = "2023-01-01 12:00:00"

    # Add mock association and requestor
    mock_assoc = MagicMock()
    mock_requestor = MagicMock()
    mock_requestor.address = "127.0.0.1"
    mock_requestor.port = 11112
    mock_requestor.ae_title = "TEST_AE"
    mock_assoc.requestor = mock_requestor
    mock_event.assoc = mock_assoc

    return mock_event


@pytest.fixture
def test_dataset():
    """Create a test DICOM Dataset for testing."""
    dataset = Dataset()
    dataset.SOPInstanceUID = "1.2.3.4.5.6.7.8.9"
    dataset.PatientID = "TEST_PATIENT"
    return dataset


def create_dimse_n_event_mock(event_type_id=1, sop_instance_uid="1.2.3.4"):
    """
    Create a mock DIMSE N-EVENT primitive.

    Args:
        event_type_id: The event type ID (1=State Report, 2=Cancel Request)
        sop_instance_uid: The SOP Instance UID for the event

    Returns:
        mock_primitive: A mock N-EVENT primitive
    """
    mock_primitive = MagicMock()
    mock_primitive.EventTypeID = event_type_id
    mock_primitive.AffectedSOPClassUID = UnifiedProcedureStepPush
    mock_primitive.AffectedSOPInstanceUID = sop_instance_uid
    return mock_primitive


def create_dimse_n_action_mock(action_type_id=3, global_subscription=True):
    """
    Create a mock DIMSE N-ACTION primitive.

    Args:
        action_type_id: The action type ID (3=Subscribe, 4=Unsubscribe)
        global_subscription: Whether this is a global subscription

    Returns:
        mock_primitive: A mock N-ACTION primitive
    """
    mock_primitive = MagicMock()
    mock_primitive.ActionTypeID = action_type_id

    # Set the appropriate SOP Instance UID based on subscription type
    if global_subscription:
        mock_primitive.RequestedSOPInstanceUID = UPSGlobalSubscriptionInstance
    else:
        mock_primitive.RequestedSOPInstanceUID = "1.2.3.4.5.6.7.8.9"  # Specific UPS Instance

    return mock_primitive


@pytest.fixture
def mock_dcmread(request):
    """
    Mock the dcmread function to return a specific dataset.
    This is a parametrized fixture. Pass the desired dataset to use.
    """
    dataset = getattr(request, "param", None)
    if dataset is None:
        # Create a default dataset if none provided
        dataset = Dataset()
        dataset.ReceivingAE = "TEST_AE"
        dataset.DeletionLock = "FALSE"
        dataset.SOPInstanceUID = "1.2.3.4"

    # Create a JSON serializable version for to_json mock
    dataset.to_json = MagicMock(return_value=json.dumps({"test": "data"}))

    with patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.dcmread", return_value=dataset) as mock:
        yield mock


@pytest.fixture(scope="session", autouse=True)
def cleanup_zombie_processes():
    """Ensure any leftover processes are cleaned up after tests."""

    # Create a flag for cleanup timeout
    cleanup_completed = threading.Event()

    def timeout_handler():
        """Handler for cleanup timeout."""
        if not cleanup_completed.is_set():
            print("WARNING: Cleanup timed out, forcing exit")
            # Just return as pytest will handle cleanup after this fixture
            return

    import os  # without this, even though it was imported at the top, unbound error

    # By default, skip stopping Mosquitto between tests to avoid interruptions
    # Set STOP_MOSQUITTO=true to force stop Mosquitto after tests
    skip_mosquitto_stop = os.environ.get("STOP_MOSQUITTO", "false").lower() != "true"

    yield

    # Set a timeout for cleanup operations (5 seconds)
    timer = threading.Timer(5.0, timeout_handler)
    timer.daemon = True
    timer.start()

    # Keep track of the timer to ensure it's properly canceled in the finally block

    try:
        # Run Mosquitto stop script to ensure MQTT broker is properly stopped
        if not skip_mosquitto_stop:
            try:
                print("Stopping Mosquitto broker (STOP_MOSQUITTO=true was set)...")
                subprocess.run(["./scripts/run_mosquitto.sh", "stop"], check=False, timeout=2)
            except (subprocess.TimeoutExpired, Exception) as e:
                print(f"Error stopping Mosquitto: {e}")
        else:
            print("Keeping Mosquitto running (default behavior, set STOP_MOSQUITTO=true to change)")

        # Clean up any lingering DICOM or MQTT related processes
        try:
            # Reset any global state in the adapter module
            try:
                import dicom_event_broker_adapter.ups_event_mqtt_broker_adapter as adapter

                if hasattr(adapter, "mqtt_publishing_client") and adapter.mqtt_publishing_client is not None:
                    print("Cleaning up global MQTT publishing client...")
                    try:
                        adapter.mqtt_publishing_client.loop_stop()
                        if adapter.mqtt_publishing_client.is_connected():
                            adapter.mqtt_publishing_client.disconnect()
                    except Exception as e:
                        print(f"Error cleaning up MQTT publishing client: {e}")
                    adapter.mqtt_publishing_client = None

                # Terminate and clean up any subscriber processes
                if hasattr(adapter, "subscriber_processes") and adapter.subscriber_processes:
                    print(f"Cleaning up {len(adapter.subscriber_processes)} subscriber processes...")
                    for process in adapter.subscriber_processes:
                        try:
                            if process.is_alive():
                                process.terminate()
                                # Use a short timeout to avoid hanging
                                process.join(timeout=0.5)
                                # Force kill if still alive
                                if process.is_alive():
                                    print(f"Process {process.name} did not terminate gracefully, force killing...")
                                    import os  # without this, even if imported at the top unbound error on os.kill

                                    try:
                                        os.kill(process.pid, signal.SIGKILL)
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"Error terminating process {process.name}: {e}")

                    adapter.subscriber_processes = []
                    adapter.subscriber_clients = []
                    if hasattr(adapter, "command_queues"):
                        adapter.command_queues = {}
            except (ImportError, AttributeError) as e:
                print(f"Could not clean up adapter module state: {e}")

        except Exception as e:
            print(f"Error cleaning up processes: {e}")

        print("Session cleanup completed")

    finally:
        # Signal that cleanup is completed (or timed out)
        cleanup_completed.set()

        # Always cancel the timer to prevent resource leaks
        try:
            timer.cancel()
            logger.debug("Cleanup timer canceled successfully")
        except Exception as e:
            logger.warning(f"Error canceling cleanup timer: {e}")
