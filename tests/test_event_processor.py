"""Unit tests for event_processor.py module."""

from unittest.mock import MagicMock, patch

from pydicom import Dataset

from dicom_event_broker_adapter.event_processor import send_event_report


class TestSendEventReport:
    """Test send_event_report function."""

    @patch("dicom_event_broker_adapter.event_processor.load_ae_config")
    def test_send_event_report_success(self, mock_load_ae_config):
        """Test successful sending of event report to subscriber."""
        # Arrange
        mock_dataset = Dataset()
        mock_dataset.AffectedSOPInstanceUID = "1.2.3.4.5.6.7"
        mock_dataset.EventTypeID = 1
        mock_dataset.AffectedSOPClassUID = "1.2.840.10008.5.1.4.34.6.1"  # Simplified

        client_ae_title = "CLIENT_AE"
        subscriber_ae_title = "SUBSCRIBER_AE"

        # Mock AE configuration
        mock_load_ae_config.return_value = {subscriber_ae_title: ("127.0.0.1", 11112)}

        # Mock the AE and association
        mock_ae_instance = MagicMock()
        mock_assoc_instance = MagicMock()

        # Mock association is established
        mock_assoc_instance.is_established = True
        mock_assoc_instance.send_n_event_report.return_value = MagicMock()

        with (
            patch("dicom_event_broker_adapter.event_processor.AE", return_value=mock_ae_instance),
            patch.object(mock_ae_instance, "associate", return_value=mock_assoc_instance),
        ):
            # Act
            send_event_report(mock_dataset, client_ae_title, subscriber_ae_title)

            # Assert
            # Check that associate was called
            mock_assoc_instance.send_n_event_report.assert_called_once()

            # Check that association was properly released
            mock_assoc_instance.release.assert_called_once()

    @patch("dicom_event_broker_adapter.event_processor.load_ae_config")
    def test_send_event_report_unknown_subscriber(self, mock_load_ae_config):
        """Test send_event_report when subscriber AE is not in config."""
        # Arrange
        mock_dataset = Dataset()
        client_ae_title = "CLIENT_AE"
        subscriber_ae_title = "UNKNOWN_SUBSCRIBER"

        # Mock AE config doesn't contain this subscriber
        mock_load_ae_config.return_value = {"KNOWN_SUBSCRIBER": ("127.0.0.1", 11112)}

        # Act
        send_event_report(mock_dataset, client_ae_title, subscriber_ae_title)

        # Assert
        # Since the AE is not in config, the function should return early without creating AE
        # Mock creation should not have happened or should have been stopped early
        # The function should just print and return without creating association

    @patch("dicom_event_broker_adapter.event_processor.load_ae_config")
    def test_send_event_report_association_fails(self, mock_load_ae_config):
        """Test send_event_report when association establishment fails."""
        # Arrange
        mock_dataset = Dataset()
        mock_dataset.AffectedSOPInstanceUID = "1.2.3.4.5.6.7"
        mock_dataset.EventTypeID = 1

        client_ae_title = "CLIENT_AE"
        subscriber_ae_title = "SUBSCRIBER_AE"

        # Mock AE configuration
        mock_load_ae_config.return_value = {subscriber_ae_title: ("127.0.0.1", 11112)}

        # Mock the AE and association
        mock_ae_instance = MagicMock()
        mock_assoc_instance = MagicMock()

        # Mock association is NOT established
        mock_assoc_instance.is_established = False

        with (
            patch("dicom_event_broker_adapter.event_processor.AE", return_value=mock_ae_instance),
            patch.object(mock_ae_instance, "associate", return_value=mock_assoc_instance),
        ):
            # Act
            send_event_report(mock_dataset, client_ae_title, subscriber_ae_title)

            # Assert
            # send_n_event_report should NOT be called since association failed
            mock_assoc_instance.send_n_event_report.assert_not_called()

            # But the association would have been attempted
            mock_ae_instance.associate.assert_called_once()
