import json
import os
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import load_ae_config


class TestLoadAEConfig:
    def test_load_ae_config_with_default_path(self, tmp_path):
        # Create a temporary test file
        test_data = [
            {"AETitle": "TEST_AE1", "IPAddr": "127.0.0.1", "Port": 11112},
            {"AETitle": "TEST_AE2", "IPAddr": "192.168.1.1", "Port": 11113},
        ]
        mock_file = mock_open(read_data=json.dumps(test_data))

        with patch("builtins.open", mock_file):
            result = load_ae_config()

        # Verify the results
        assert len(result) == 2
        assert result["TEST_AE1"] == ("127.0.0.1", 11112)
        assert result["TEST_AE2"] == ("192.168.1.1", 11113)

    def test_load_ae_config_with_custom_path(self, tmp_path):
        # Create a temporary test file
        test_path = tmp_path / "custom_ae.json"
        test_data = [{"AETitle": "CUSTOM_AE", "IPAddr": "10.0.0.1", "Port": 12345}]
        with open(test_path, "w") as f:
            json.dump(test_data, f)

        # Call the function with custom path
        result = load_ae_config(test_path)

        # Verify the results
        assert len(result) == 1
        assert result["CUSTOM_AE"] == ("10.0.0.1", 12345)

    def test_load_ae_config_duplicate_ae_titles(self, tmp_path):
        # Create a test file with duplicate AE titles
        test_data = [
            {"AETitle": "DUPLICATE_AE", "IPAddr": "192.168.1.1", "Port": 11112},
            {"AETitle": "DUPLICATE_AE", "IPAddr": "192.168.1.2", "Port": 11113},
        ]
        mock_file = mock_open(read_data=json.dumps(test_data))

        with patch("builtins.open", mock_file):
            result = load_ae_config()

        # The last entry should win
        assert len(result) == 1
        assert result["DUPLICATE_AE"] == ("192.168.1.2", 11113)
