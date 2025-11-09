"""Configuration module for DICOM Event Broker Adapter."""

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple, TypedDict, Union

# Constants
ADAPTER_AE_TITLE = "UPSEventBroker01"
DEFAULT_BROKER_ADDRESS = "127.0.0.1"
DEFAULT_BROKER_PORT = 1883
DEFAULT_LISTENING_PORT = 11119

# Event and action type mappings
EVENT_TYPE_DICT = {
    1: "UPS State Report",
    2: "UPS Cancel Request",
    3: "UPS Progress Report",
    4: "SCP Status Change",
    5: "UPS Assigned",
}

ACTION_TYPE_DICT = {
    3: "Subscribe to Receive UPS Event Reports",
    4: "Unsubscribe from Receiving UPS Event Reports",
    5: "Suspend Global Subscription",
}

# Health check settings
HEALTH_CHECK_TOPIC_PREFIX = "health/dicom_broker"


class Command(TypedDict):
    action: Literal["subscribe", "unsubscribe"]
    topic: Optional[str]


class ApplicationEntity(TypedDict):
    AETitle: str
    IPAddr: str
    Port: int


def load_ae_config(path_to_ae_config: Union[str, Path] = None) -> Dict[str, Tuple[str, int]]:
    """Returns a dictionary of AEs, with the values being the IPAddr, Port tuple.

    The AE file is expected to be json, as an array of (AETitle:str,IPAddr:str,Port:int).
    It is possible for there to be duplicate AE Titles in the list with varying IPAddr and/or Port.
    Last entry wins (the dict is just overwritten).

    Returns:
        Dict[str,(str,int)]: The dict of AEs with key being the AE Title and the value being a
        (str,int) Tuple of IPAddr,Port
    """
    dict_of_tuple: Dict[str, Tuple[str, int]] = {}
    if path_to_ae_config is not None:
        ae_config_file = path_to_ae_config
    else:
        ae_config_file = "ApplicationEntities.json"

    try:
        with open(ae_config_file, "r") as f:
            ae_config_list: List[ApplicationEntity] = json.load(f)
        for ae in ae_config_list:
            dict_of_tuple[ae["AETitle"]] = (ae["IPAddr"], ae["Port"])
    except FileNotFoundError:
        print(f"Warning: AE configuration file {ae_config_file} not found. Using empty configuration.")
    except json.JSONDecodeError:
        print(f"Warning: AE configuration file {ae_config_file} contains invalid JSON. Using empty configuration.")

    return dict_of_tuple


# Topic construction utilities
def construct_mqtt_topic(
    event_type,
    subscription_type: Optional[str] = None,
    workitem_uid: Optional[str] = None,
    workitem_subtopic: Optional[str] = None,
    subscriber_ae_title: Optional[str] = None,
    dicom_topic_filter=None,
):
    """Construct MQTT topic from DICOM event parameters."""
    base_topic = "/workitems"
    if subscription_type == "Worklist":
        return f"{base_topic}"
    elif subscription_type == "FilteredWorklist":
        # TODO: Apply filter for topic construction
        return f"{base_topic}"  # needs some work.  see above for topic hierarchy
    if event_type == "Workitem" and workitem_uid:
        workitem_topic = f"{base_topic}/{workitem_uid}"
        if workitem_subtopic is not None:
            workitem_topic = f"{workitem_topic}/{workitem_subtopic}"
        return f"{workitem_topic}"
    else:
        raise ValueError("Invalid event type or missing workitem UID")
