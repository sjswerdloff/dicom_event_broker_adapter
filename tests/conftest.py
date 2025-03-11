"""
Common fixtures and utilities for tests.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from pydicom import Dataset
from pynetdicom.sop_class import UnifiedProcedureStepPush, UPSGlobalSubscriptionInstance


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
