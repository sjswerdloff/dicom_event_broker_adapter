"""MQTT client module for DICOM Event Broker Adapter."""

import logging
import multiprocessing
import os
import time
from multiprocessing import Process, Queue
from queue import Empty
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt_client
from paho.mqtt.properties import Properties as mqtt_properties

from .config import Command

# Global variables to maintain state
subscriber_clients: List[str] = []
command_queues: Dict[str, Queue] = {}
subscriber_processes: List[Process] = []
mqtt_publishing_client: Optional[mqtt_client.Client] = None


def on_connect(
    client: mqtt_client.Client, userdata: Any, flags: Dict[str, int], rc: int, properties: mqtt_properties = None
) -> None:
    """Handle MQTT client connection events."""
    print("Connected!")
    print(f"Process {multiprocessing.current_process().name}: Connected with result code {rc} and properties {properties}")


def on_disconnect(client: mqtt_client.Client, userdata: Any, rc: int, properties: mqtt_properties = None) -> None:
    """Handle MQTT client disconnection events.

    Args:
        client: The MQTT client that was disconnected
        userdata: User data passed to the client constructor
        rc: The disconnection result code (0 for expected, non-zero for unexpected)
        properties: Properties for MQTT v5 (optional)
    """
    if rc != 0:
        # This is an unexpected disconnection - try to reconnect
        print(
            f"Process {multiprocessing.current_process().name}: Unexpected disconnection (rc={rc}). Attempting to reconnect..."
        )
        try:
            client.reconnect()
        except Exception as e:
            print(f"Failed to reconnect: {e}")
    else:
        # This is an expected/clean disconnection, don't attempt to reconnect
        print(f"Process {multiprocessing.current_process().name}: Clean disconnection (rc=0)")


def on_message(client: mqtt_client.Client, userdata: Any, msg: mqtt_client.MQTTMessage) -> None:
    """Handle incoming MQTT messages."""
    print(f"Received message on topic {msg.topic}: {msg.payload.decode()}")
    process_mqtt_message(this_client=client, userdata=userdata, message=msg)


def process_mqtt_message(this_client: mqtt_client.Client, userdata: Any, message: mqtt_client.MQTTMessage):
    """Process an incoming MQTT message and convert it to DICOM event."""
    from .config import ADAPTER_AE_TITLE
    from .event_processor import send_event_report

    print(f"Processing message on topic {message.topic}")
    topic = message.topic
    payload = message.payload.decode()
    print(f"Process {multiprocessing.current_process().name}: Received message on topic {topic}")
    print(f"Payload: {payload}")

    try:
        parts = topic.split("/")
        print(parts)
        event_type: int = -1
        action_type: int = -1
        subscriber_ae_title: str = multiprocessing.current_process().name
        ups_uid: Optional[str] = None
        if len(parts) < 2:
            print(f"Invalid topic format: {topic}")
            # return
        if len(parts) > 2:
            from pynetdicom.sop_class import UPSFilteredGlobalSubscriptionInstance, UPSGlobalSubscriptionInstance

            uid = parts[2]
            if uid in [UPSGlobalSubscriptionInstance, UPSFilteredGlobalSubscriptionInstance]:
                event_type = 0
                action_type = 4  # unsubscribe - only the last assignment has effect
            else:
                ups_uid = uid
                if len(parts) > 3:
                    if parts[3] == "state":
                        event_type = 1
                    elif parts[3] == "cancelrequest":
                        event_type = 2
        # if len(parts) > 4:
        #     if ups_uid is None:
        #         subscriber_ae_title = parts[4]  # this is not really the right thing.

        # Convert payload to DICOM dataset
        import json

        from pydicom import Dataset

        payload_dict = json.loads(payload)
        print(payload_dict)
        ds = Dataset.from_json(payload_dict)

        # Add necessary attributes for N-EVENT-REPORT
        if "EventTypeID" not in ds:
            ds.EventTypeID = event_type
            print("adding EventTypeID based on topic and context")
        if "AffectedSOPClassUID" not in ds:
            from pynetdicom.sop_class import UnifiedProcedureStepPush

            ds.AffectedSOPClassUID = UnifiedProcedureStepPush
            print("adding UnifiedProcedureStepPush as AffectedSOPClassUID")
        if "AffectedSOPInstanceUID" not in ds:
            ds.AffectedSOPInstanceUID = ups_uid
            print("adding Affected SOP Instance UID based on topic")

        # Send N-EVENT-REPORT to the subscriber
        if event_type > 0:
            send_event_report(ds, client_ae_title=ADAPTER_AE_TITLE, subscriber_ae_title=subscriber_ae_title)
        elif action_type > 0:
            pass
        else:
            return

    except json.JSONDecodeError:
        print(f"Error decoding JSON from MQTT message: {payload}")
    except Exception as e:
        print(f"Error processing MQTT message: {str(e)}")


def mqtt_client_process(process_name: str, broker: str, port: int, command_queue: Queue) -> None:
    """Process function for running an MQTT client."""
    print("mqtt_client_process invoked")
    print(f"process_name: {process_name}")
    print("module name:", __name__)
    print("parent process:", os.getppid())
    print("process id:", os.getpid())
    try:
        client = mqtt_client.Client(client_id=process_name, callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2)
        client.enable_logger()
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        print(f"Connecting client to broker {broker} on port {port}")
        client.connect(broker, port, 60)
        error_code = client.loop_start()
        print(f"MQTT Error Code on client loop_start: {error_code}")
        current_topic: Optional[str] = None
    except BaseException as e:
        print(e)

    def process_commands() -> None:
        nonlocal current_topic
        try:
            command: Command = command_queue.get_nowait()
            print("received command")
            if command["action"] == "subscribe":
                if current_topic:
                    client.unsubscribe(current_topic)
                current_topic = command["topic"]
                if current_topic:
                    client.subscribe(current_topic)
                    print(f"Process {process_name}: Subscribed to {current_topic}")
                    time.sleep(0.5)  # Allow subscription to complete
            elif command["action"] == "unsubscribe":
                if current_topic:
                    client.unsubscribe(current_topic)
                    current_topic = None
                    print(f"Process {process_name}: Unsubscribed from all topics")
        except Empty:
            logging.debug("No command to process, looping")
            pass

    while True:
        logging.debug("processing commands")
        process_commands()
        client.loop(timeout=1.0)  # This allows the client to process incoming messages
        time.sleep(0.1)


def initialize_mqtt_publisher(client_id: str, broker_address: str, broker_port: int) -> mqtt_client.Client:
    """Initialize the MQTT publishing client."""
    global mqtt_publishing_client
    mqtt_publishing_client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id=client_id)
    mqtt_publishing_client.on_connect = on_connect
    mqtt_publishing_client.on_disconnect = on_disconnect
    mqtt_publishing_client.connect(host=broker_address, port=broker_port)
    mqtt_publishing_client.loop_start()
    return mqtt_publishing_client
