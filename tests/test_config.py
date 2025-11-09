"""Unit tests for config.py module."""

import json
import tempfile
from pathlib import Path

import pytest

from dicom_event_broker_adapter.config import (
    ACTION_TYPE_DICT,
    ADAPTER_AE_TITLE,
    DEFAULT_BROKER_ADDRESS,
    DEFAULT_BROKER_PORT,
    DEFAULT_LISTENING_PORT,
    EVENT_TYPE_DICT,
    HEALTH_CHECK_TOPIC_PREFIX,
    ApplicationEntity,
    Command,
    construct_mqtt_topic,
    load_ae_config,
)


class TestConstants:
    """Test constants defined in config module."""

    def test_adapter_ae_title_constant(self) -> None:
        """Test ADAPTER_AE_TITLE constant."""
        assert ADAPTER_AE_TITLE == "UPSEventBroker01"

    def test_default_constants(self) -> None:
        """Test default configuration constants."""
        assert DEFAULT_BROKER_ADDRESS == "127.0.0.1"
        assert DEFAULT_BROKER_PORT == 1883
        assert DEFAULT_LISTENING_PORT == 11119

    def test_event_type_dict(self) -> None:
        """Test EVENT_TYPE_DICT content."""
        expected = {
            1: "UPS State Report",
            2: "UPS Cancel Request",
            3: "UPS Progress Report",
            4: "SCP Status Change",
            5: "UPS Assigned",
        }
        assert EVENT_TYPE_DICT == expected

    def test_action_type_dict(self) -> None:
        """Test ACTION_TYPE_DICT content."""
        expected = {
            3: "Subscribe to Receive UPS Event Reports",
            4: "Unsubscribe from Receiving UPS Event Reports",
            5: "Suspend Global Subscription",
        }
        assert ACTION_TYPE_DICT == expected

    def test_health_check_constant(self) -> None:
        """Test HEALTH_CHECK_TOPIC_PREFIX constant."""
        assert HEALTH_CHECK_TOPIC_PREFIX == "health/dicom_broker"


class TestTypedDicts:
    """Test TypedDict definitions."""

    def test_command_typeddict(self) -> None:
        """Test Command TypedDict structure."""
        cmd: Command = {"action": "subscribe", "topic": "/test/topic"}
        assert cmd["action"] == "subscribe"
        assert cmd["topic"] == "/test/topic"

        cmd2: Command = {"action": "unsubscribe", "topic": None}
        assert cmd2["action"] == "unsubscribe"
        assert cmd2["topic"] is None

    def test_application_entity_typeddict(self) -> None:
        """Test ApplicationEntity TypedDict structure."""
        ae: ApplicationEntity = {"AETitle": "TEST_AE", "IPAddr": "127.0.0.1", "Port": 11112}
        assert ae["AETitle"] == "TEST_AE"
        assert ae["IPAddr"] == "127.0.0.1"
        assert ae["Port"] == 11112


class TestLoadAeConfig:
    """Test load_ae_config function."""

    def test_load_from_default_file(self, tmp_path) -> None:
        """Test loading AE config from default file."""
        import os

        # Create a temporary directory and file
        test_file = tmp_path / "ApplicationEntities.json"
        test_data = [
            {"AETitle": "AE1", "IPAddr": "127.0.0.1", "Port": 11112},
            {"AETitle": "AE2", "IPAddr": "127.0.0.2", "Port": 11113},
        ]
        with open(test_file, "w") as f:
            json.dump(test_data, f)

        # Change to the temporary directory to test default file loading
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = load_ae_config()  # Should load from ApplicationEntities.json in current dir
            expected = {"AE1": ("127.0.0.1", 11112), "AE2": ("127.0.0.2", 11113)}
            assert result == expected
        finally:
            os.chdir(original_cwd)  # Always restore original directory

    def test_load_from_custom_file(self) -> None:
        """Test loading AE config from custom file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                [
                    {"AETitle": "CUSTOM_AE", "IPAddr": "192.168.1.100", "Port": 11114},
                ],
                f,
            )
            temp_file = Path(f.name)

        try:
            result = load_ae_config(str(temp_file))
            expected = {"CUSTOM_AE": ("192.168.1.100", 11114)}
            assert result == expected
        finally:
            temp_file.unlink()

    def test_file_not_found(self) -> None:
        """Test handling of missing configuration file."""
        result = load_ae_config("/non/existent/path.json")
        assert result == {}

    def test_invalid_json(self) -> None:
        """Test handling of invalid JSON in configuration file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_file = Path(f.name)

        try:
            result = load_ae_config(str(temp_file))
            assert result == {}
        finally:
            temp_file.unlink()

    def test_duplicate_ae_titles(self) -> None:
        """Test that duplicate AE titles get overwritten (last wins)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                [
                    {"AETitle": "DUPLICATE", "IPAddr": "127.0.0.1", "Port": 11112},
                    {"AETitle": "DUPLICATE", "IPAddr": "127.0.0.2", "Port": 11113},  # This should win
                ],
                f,
            )
            temp_file = Path(f.name)

        try:
            result = load_ae_config(str(temp_file))
            expected = {"DUPLICATE": ("127.0.0.2", 11113)}  # Last entry wins
            assert result == expected
        finally:
            temp_file.unlink()


class TestConstructMqttTopic:
    """Test construct_mqtt_topic function."""

    def test_worklist_subscription_topic(self) -> None:
        """Test construction of worklist subscription topic."""
        result = construct_mqtt_topic("Workitem", subscription_type="Worklist")
        assert result == "/workitems"

    def test_filtered_worklist_subscription_topic(self) -> None:
        """Test construction of filtered worklist subscription topic."""
        result = construct_mqtt_topic("Workitem", subscription_type="FilteredWorklist")
        assert result == "/workitems"  # Currently returns base topic

    def test_specific_workitem_topic(self) -> None:
        """Test construction of specific workitem topic."""
        result = construct_mqtt_topic("Workitem", workitem_uid="1.2.3.4.5")
        assert result == "/workitems/1.2.3.4.5"

    def test_workitem_topic_with_subtopic(self) -> None:
        """Test construction of workitem topic with subtopic."""
        result = construct_mqtt_topic("Workitem", workitem_uid="1.2.3.4.5", workitem_subtopic="state")
        assert result == "/workitems/1.2.3.4.5/state"

    def test_workitem_topic_with_cancel_request_subtopic(self) -> None:
        """Test construction of workitem topic with cancel request subtopic."""
        result = construct_mqtt_topic("Workitem", workitem_uid="1.2.3.4.5", workitem_subtopic="cancelrequest")
        assert result == "/workitems/1.2.3.4.5/cancelrequest"

    def test_invalid_event_type_raises_value_error(self) -> None:
        """Test that invalid event type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid event type or missing workitem UID"):
            construct_mqtt_topic("InvalidType")

    def test_missing_workitem_uid_raises_value_error(self) -> None:
        """Test that missing workitem UID raises ValueError for Workitem type."""
        with pytest.raises(ValueError, match="Invalid event type or missing workitem UID"):
            construct_mqtt_topic("Workitem")

    def test_empty_workitem_uid_raises_value_error(self) -> None:
        """Test that empty workitem UID raises ValueError for Workitem type."""
        with pytest.raises(ValueError, match="Invalid event type or missing workitem UID"):
            construct_mqtt_topic("Workitem", workitem_uid="")
