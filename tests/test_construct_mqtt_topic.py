# Generated by CodiumAI

import pytest

from dicom_event_broker_adapter.ups_event_mqtt_broker_adapter import _construct_mqtt_topic


class Test_ConstructMqttTopic:
    # Constructs base topic for "Worklist" subscription type
    def test_constructs_base_topic_for_worklist_subscription(self):
        result = _construct_mqtt_topic(event_type="Workitem", subscription_type="Worklist")
        assert result == "/workitems"

    # Raises ValueError for invalid event type
    def test_raises_value_error_for_invalid_event_type(self):
        with pytest.raises(ValueError, match="Invalid event type or missing workitem UID"):
            _construct_mqtt_topic(event_type="InvalidType")
