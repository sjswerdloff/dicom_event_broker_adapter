from unittest.mock import MagicMock, patch

from pynetdicom import AE
from pynetdicom.sop_class import UnifiedProcedureStepEvent, UnifiedProcedureStepPush, UnifiedProcedureStepWatch, Verification

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import start_dimse_server


class TestDIMSEServer:
    @patch("dicom_event_broker_adapter.ups_event_mqtt_broker_adapter.evt")
    def test_start_dimse_server(self, mock_evt):
        # Setup mocks
        mock_ae = MagicMock(spec=AE)
        listening_port = 11119

        # Mock the event handlers
        # mock_handlers = [(1, "handle_n_action"), (2, "handle_n_event"), (3, "handle_echo")]
        mock_evt.EVT_N_ACTION = 1
        mock_evt.EVT_N_EVENT_REPORT = 2
        mock_evt.EVT_C_ECHO = 3

        # Call the function
        start_dimse_server(ae=mock_ae, listening_port=listening_port)

        # Verify the AE was configured correctly
        mock_ae.add_supported_context.assert_any_call(UnifiedProcedureStepWatch)
        mock_ae.add_supported_context.assert_any_call(UnifiedProcedureStepEvent)
        mock_ae.add_supported_context.assert_any_call(UnifiedProcedureStepPush)
        mock_ae.add_supported_context.assert_any_call(Verification)

        # Verify the server was started
        mock_ae.start_server.assert_called_once()
        # Check that the address is correct (0.0.0.0 means all interfaces)
        args, kwargs = mock_ae.start_server.call_args
        assert args[0] == ("0.0.0.0", listening_port)
        # Check that block=False is passed
        assert kwargs["block"] is False
