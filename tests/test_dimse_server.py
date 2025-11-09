"""Unit tests for dimse_server.py module."""

from unittest.mock import MagicMock, patch

from pynetdicom.sop_class import (
    UnifiedProcedureStepEvent,
    UnifiedProcedureStepPush,
    UnifiedProcedureStepWatch,
    Verification,
)
from pynetdicom.transport import ThreadedAssociationServer

from dicom_event_broker_adapter.dimse_server import (
    handle_echo,
    start_dimse_server,
)


class TestHandleEcho:
    """Test handle_echo function."""

    def test_handle_echo_success(self):
        """Test handle_echo returns success code."""
        # Arrange
        mock_event = MagicMock()
        mock_assoc = MagicMock()
        mock_requestor = MagicMock()
        mock_requestor.ae_title = "TEST_AE"
        mock_requestor.address = "127.0.0.1"
        mock_requestor.port = 11112
        mock_assoc.requestor = mock_requestor
        mock_event.assoc = mock_assoc

        # Act
        result = handle_echo(mock_event)

        # Assert
        assert result == 0x0000  # Success code


class TestStartDimseServer:
    """Test start_dimse_server function."""

    @patch("dicom_event_broker_adapter.dimse_server.evt")
    @patch("dicom_event_broker_adapter.dimse_server.handle_n_action")
    @patch("dicom_event_broker_adapter.dimse_server.handle_dimse_n_event")
    @patch("dicom_event_broker_adapter.dimse_server.handle_echo")
    def test_start_dimse_server(self, mock_handle_echo, mock_handle_dimse_n_event, mock_handle_n_action, mock_evt):
        """Test start_dimse_server function with mocked AE."""
        # Arrange
        mock_ae = MagicMock()
        mock_server_instance = MagicMock(spec=ThreadedAssociationServer)
        mock_ae.start_server.return_value = mock_server_instance

        test_port = 11119

        # Create mock event handlers
        mock_evt.EVT_N_ACTION = MagicMock()
        mock_evt.EVT_N_EVENT_REPORT = MagicMock()
        mock_evt.EVT_C_ECHO = MagicMock()

        # Act
        result = start_dimse_server(mock_ae, test_port)

        # Assert
        # Check that the correct supported contexts were added
        mock_ae.add_supported_context.assert_any_call(UnifiedProcedureStepWatch)
        mock_ae.add_supported_context.assert_any_call(UnifiedProcedureStepEvent)
        mock_ae.add_supported_context.assert_any_call(UnifiedProcedureStepPush)
        mock_ae.add_supported_context.assert_any_call(Verification)

        # Verify start_server was called with correct parameters
        mock_ae.start_server.assert_called_once()

        # Check that the call args include the expected handlers
        args, kwargs = mock_ae.start_server.call_args
        assert args[0] == ("0.0.0.0", test_port)  # Check the address/port tuple

        # Check that event handlers are in the call
        # Verify the evt_handlers parameter exists and has the right structure
        call_kwargs = mock_ae.start_server.call_args[1] if len(mock_ae.start_server.call_args) > 1 else {}
        if "evt_handlers" in call_kwargs:
            handlers = call_kwargs["evt_handlers"]
            assert len(handlers) == 3  # 3 event handlers

        # The returned server should be the one from start_server
        assert result == mock_server_instance
