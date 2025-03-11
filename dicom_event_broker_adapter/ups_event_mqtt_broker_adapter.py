import argparse
import json
import logging
import multiprocessing
import os
import textwrap
import time
from multiprocessing import Process, Queue
from pathlib import Path
from queue import Empty
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict, Union

import paho.mqtt.client as mqtt_client
from paho.mqtt.properties import Properties as mqtt_properties
from pydicom import Dataset, dcmread
from pydicom.uid import UID
from pynetdicom import AE, evt
from pynetdicom.events import Event
from pynetdicom.presentation import build_context
from pynetdicom.sop_class import (
    UnifiedProcedureStepEvent,
    UnifiedProcedureStepPush,
    UnifiedProcedureStepWatch,
    UPSFilteredGlobalSubscriptionInstance,
    UPSGlobalSubscriptionInstance,
    Verification,
)
from pynetdicom.transport import ThreadedAssociationServer

logging.basicConfig()

ADAPTER_AE_TITLE = "UPSEventBroker01"
broker_address: str = "127.0.0.1"  # use loopback as a default
broker_port: int = 1883  # default MQTT port

event_type_dict = {
    1: "UPS State Report",
    2: "UPS Cancel Request",
    3: "UPS Progress Report",
    4: "SCP Status Change",
    5: "UPS Assigned",
}

action_type_dict = {
    3: "Subscribe to Receive UPS Event Reports",
    4: "Unsubscribe from Receiving UPS Event Reports",
    5: "Suspend Global Subscription",
}


mqtt_publishing_client: mqtt_client.Client = None

# Maintain a list of clients by AE Title/name (which will be used for process name and client_id)
subscriber_clients: List[str] = []

# Maintain command queues, one for each client to support subscribing and unsubscribing from topics
command_queues: Dict[str, Queue] = {}

# Maintain list of processes, one for each subscriber client
subscriber_processes: List[Process] = []


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
    with open(ae_config_file, "r") as f:
        ae_config_list: List[str, str, str] = json.load(f)
    for ae in ae_config_list:
        dict_of_tuple[ae["AETitle"]] = (ae["IPAddr"], ae["Port"])
    return dict_of_tuple


known_aes: Dict[str, Tuple[str, int]] = load_ae_config()


class Command(TypedDict):
    action: Literal["subscribe", "unsubscribe"]
    topic: str | None


def on_connect(
    client: mqtt_client.Client, userdata: Any, flags: Dict[str, int], rc: int, properties: mqtt_properties = None
) -> None:
    print("Connected!")
    print(f"Process {multiprocessing.current_process().name}: " f"Connected with result code {rc} and properties {properties}")


def on_disconnect(client: mqtt_client.Client, userdata: Any, rc: int, properties: mqtt_properties = None) -> None:
    """
    Handle MQTT client disconnection events.

    Args:
        client: The MQTT client that was disconnected
        userdata: User data passed to the client constructor
        rc: The disconnection result code (0 for expected, non-zero for unexpected)
        properties: Properties for MQTT v5 (optional)
    """
    if rc != 0:
        # This is an unexpected disconnection - try to reconnect
        print(
            f"Process {multiprocessing.current_process().name}: "
            f"Unexpected disconnection (rc={rc}). Attempting to reconnect..."
        )
        try:
            client.reconnect()
        except Exception as e:
            print(f"Failed to reconnect: {e}")
    else:
        # This is an expected/clean disconnection, don't attempt to reconnect
        print(f"Process {multiprocessing.current_process().name}: Clean disconnection (rc=0)")


def on_message(client: mqtt_client.Client, userdata: Any, msg: mqtt_client.MQTTMessage) -> None:
    print(f"Received message on topic {msg.topic}: {msg.payload.decode()}")
    process_mqtt_message(this_client=client, userdata=userdata, message=msg)


def process_mqtt_message(this_client: mqtt_client.Client, userdata: Any, message: mqtt_client.MQTTMessage):
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
        ups_uid: Optional[UID] = None
        if len(parts) < 2:
            print(f"Invalid topic format: {topic}")
            # return
        if len(parts) > 2:
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
        payload_dict = json.loads(payload)
        print(payload_dict)
        ds = Dataset.from_json(payload_dict)

        # Add necessary attributes for N-EVENT-REPORT
        if "EventTypeID" not in ds:
            ds.EventTypeID = event_type
            print("adding EventTypeID based on topic and context")
        if "AffectedSOPClassUID" not in ds:
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


def send_event_report(dataset: Dataset, client_ae_title: str, subscriber_ae_title: str):
    print(dataset)
    ae_title = client_ae_title
    known_aes = {}
    contexts = [build_context(UnifiedProcedureStepPush)]
    send_event_scu = AE(ae_title)
    if subscriber_ae_title not in known_aes:
        known_aes = load_ae_config()
    if subscriber_ae_title not in known_aes:
        print(f"AE {subscriber_ae_title} not found in Application Entities configuration file")
        return

    ip, port = known_aes[subscriber_ae_title]
    send_event_assoc = send_event_scu.associate(addr=ip, port=port, contexts=contexts, ae_title=subscriber_ae_title)
    if send_event_assoc.is_established:
        status = send_event_assoc.send_n_event_report(
            dataset, dataset.EventTypeID, UnifiedProcedureStepPush, dataset.AffectedSOPInstanceUID
        )
        print(f"N-EVENT-REPORT status: {status}")
        send_event_assoc.release()
    else:
        print(f"Association rejected, aborted or never connected with {subscriber_ae_title}")


def mqtt_client_process(process_name: str, broker: str, port: int, command_queue: Queue) -> None:
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
        current_topic: str | None = None
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


def parent_process(command_queues: Dict[str, Queue]) -> None:
    while True:
        try:
            command = input("Enter command (format: 'client_name action topic'): ")
            parts = command.split()
            if len(parts) < 2:
                print("Invalid command format")
                continue

            client_name, action = parts[0], parts[1]
            topic = parts[2] if len(parts) > 2 else None

            if client_name not in command_queues:
                print(f"Unknown client: {client_name}")
                continue

            if action not in ["subscribe", "unsubscribe"]:
                print(f"Unknown action: {action}")
                continue

            command_dict: Command = {"action": action, "topic": topic}  # type: ignore
            command_queues[client_name].put(command_dict)
            print(f"Sent command to {client_name}: {command_dict}")
        except KeyboardInterrupt:
            print("\nExiting...")
            break


# First pass was to map closely to the REST API spec.
#  But... the following structure would make it easier to address typical filtering
# workitems/<location>/<patient_id>/<activity_type>/<work_item_id>
# e.g. workitems/machine_name/patient_id/treatment_delivery/sop_instance_uid
# that way, something in the particular room would subscribe to workitems/machine_name/#
# to find out what is coming in the future.
# while workitems/+/+/sop_instance_uid would get them just what is happening to the "current" UPS in progress
# and when that's done, it could unsubscribe from the topic
# and if someone wanted to aggregate events to a particular patient workitems/+/patient_id/#


def _construct_mqtt_topic(
    event_type,
    subscription_type: Optional[str] = None,
    workitem_uid: Optional[UID] = None,
    workitem_subtopic: Optional[str] = None,
    subscriber_ae_title: Optional[str] = None,
    dicom_topic_filter: Optional[Dataset] = None,
):
    base_topic = "/workitems"
    if subscription_type == "Worklist":
        return f"{base_topic}"
        # return f"{base_topic}/{UPSGlobalSubscriptionInstance}/subscribers/{subscriber_ae_title}"
    elif subscription_type == "FilteredWorklist":
        warning_message = f"Not applying filter for topic construction yet: {dicom_topic_filter}"
        logging.warning(warning_message)
        return f"{base_topic}"  # needs some work.  see above for topic hierarchy
        # return f"{base_topic}/{UPSFilteredGlobalSubscriptionInstance}/subscribers/{subscriber_ae_title}"
    if event_type == "Workitem" and workitem_uid:
        workitem_topic = f"{base_topic}/{workitem_uid}"
        if workitem_subtopic is not None:
            workitem_topic = f"{workitem_topic}/{workitem_subtopic}"
        return f"{workitem_topic}"
    else:
        raise ValueError("Invalid event type or missing workitem UID")


def handle_echo(event: Event):
    """Optional implementation of the evt.EVT_C_ECHO handler."""
    # Return a Success response to the peer
    # We could also return a pydicom Dataset with a (0000, 0900) Status
    #   element
    requesting_ae = event.assoc.requestor.ae_title
    requestor_address = event.assoc.requestor.address
    requestor_port = event.assoc.requestor.port

    print(f"Received echo request from {requesting_ae} at {requestor_address} on port {requestor_port}")
    return 0x0000


def handle_n_action(event: Event):
    """Handle N-ACTION requests for UPS Watch operations."""
    naction_primitive = event.request
    action_type_id = naction_primitive.ActionTypeID
    action_information = dcmread(naction_primitive.ActionInformation, force=True)
    service_status = 0x0000
    # sub_operations_remaining = 0
    # in case things go wrong
    error_response = Dataset()  # update the Error Comment and service status if things go wrong
    error_response.is_little_endian = True
    error_response.is_implicit_VR = True

    happy_response = Dataset()
    happy_response.Status = service_status
    # happy_response.update(action_information) # apparently not all elements get to go back in a status dataset
    workitem_uid = None
    if action_type_id != 1:
        subscribing_ae_title = None
        deletion_lock = False
        if action_information is not None:
            try:
                logging.info("Action Information:")

                subscribing_ae_title = action_information.ReceivingAE
                deletion_lock = action_information.DeletionLock == "TRUE"
                print(f"Receiving AE: {subscribing_ae_title}")
                print(f"Deletion Lock: {deletion_lock}, although it isn't being used with broker")
                logging.info(action_information)
            except AttributeError as exc:
                logging.error(f"Error in decoding subscriber information: {exc}")
                # TODO... service_status = some error code
        else:
            logging.warn("No action information available!")
            # TODO... service_status = some error code

        # TODO:  use action_type_id to determine if this is subscribe or unsubscribe
        if naction_primitive.RequestedSOPInstanceUID == UPSGlobalSubscriptionInstance:
            logging.info("Request was for (unfiltered) Global UPS")
            mqtt_event_type = "Worklist"
            subscription_type = "Worklist"
            if action_type_id == 3:
                logging.info("Global Subscribe")
            elif action_type_id == 4:
                logging.info("Global Unsubscribe")
        elif naction_primitive.RequestedSOPInstanceUID == UPSFilteredGlobalSubscriptionInstance:
            mqtt_event_type = "FilteredWorklist"
            subscription_type = "FilteredWorklist"
            logging.info("Request was for Filtered Global UPS")
            logging.info(f"Filter contained in action information: {action_information})")
            if action_type_id == 3:
                logging.info("Filtered Subscribe")
            elif action_type_id == 4:
                logging.info("Filtered Unsubscribe")
        else:
            workitem_uid = naction_primitive.RequestedSOPInstanceUID
            logging.info(f"Subscribe to specific UPS: {workitem_uid}")

    action_type = event.action_type
    # action_info = event.action_information
    action_type_id = naction_primitive.ActionTypeID
    print(f"ActionTypeID = {action_type_id} == {action_type_dict[action_type_id]}")
    action_information = dcmread(naction_primitive.ActionInformation, force=True)
    requesting_ae = event.assoc.requestor.ae_title
    receiving_ae = requesting_ae  # only as a fallback.
    if "ReceivingAE" in action_information:
        receiving_ae = action_information.ReceivingAE
    if receiving_ae not in known_aes:
        reloaded_aes = load_ae_config()
        if receiving_ae not in reloaded_aes:
            # Table CC.2.3-3. N-ACTION Response Status Values for Subscribe/Unsubscribe to Receive UPS EventReports
            return 0xC308  # Failure, don't recognize the receiving AE.
    topic = _construct_mqtt_topic(
        event_type=mqtt_event_type,
        subscription_type=subscription_type,
        workitem_uid=workitem_uid,
        dicom_topic_filter=action_information,
    )
    if action_type == 3:  # Subscribe
        register_subscriber(receiving_ae, topic=topic)
        yield service_status
        yield happy_response
        return  # Success
    elif action_type == 4:  # Unsubscribe
        unregister_subscriber(receiving_ae, topic=topic)
        yield service_status
        yield happy_response
        return  # Success
    elif action_type == 5:
        print("Request to Suspend Global Subscription not handled properly yet")
        unregister_subscriber(receiving_ae, topic="/workitems/#")
        yield service_status
        yield happy_response
        return  # Success.  A bit of a white lie.
    else:
        service_status = 0xC304
        error_response.ErrorComment = f"Unrecognized action type: {action_type}"
        error_response.status = service_status
        yield error_response
        yield None
        return  # Failure - Unrecognized action type


def handle_dimse_n_event(event: Event):
    print("Received a DIMSE N-EVENT Message")
    nevent_primitive = event.request
    r"""Represents a N-EVENT-REPORT primitive.

    +------------------------------------------+---------+----------+
    | Parameter                                | Req/ind | Rsp/conf |
    +==========================================+=========+==========+
    | Message ID                               | M       | \-       |
    +------------------------------------------+---------+----------+
    | Message ID Being Responded To            | \-      | M        |
    +------------------------------------------+---------+----------+
    | Affected SOP Class UID                   | M       | U(=)     |
    +------------------------------------------+---------+----------+
    | Affected SOP Instance UID                | M       | U(=)     |
    +------------------------------------------+---------+----------+
    | Event Type ID                            | M       | C(=)     |
    +------------------------------------------+---------+----------+
    | Event Information                        | U       | \-       |
    +------------------------------------------+---------+----------+
    | Event Reply                              | \-      | C        |
    +------------------------------------------+---------+----------+
    | Status                                   | \-      | M        |
    +------------------------------------------+---------+----------+

    | (=) - The value of the parameter is equal to the value of the parameter
    in the column to the left
    | C - The parameter is conditional.
    | M - Mandatory
    | MF - Mandatory with a fixed value
    | U - The use of this parameter is a DIMSE service user option
    | UF - User option with a fixed value

    Attributes
    ----------
    MessageID : int
        Identifies the operation and is used to distinguish this
        operation from other notifications or operations that may be in
        progress. No two identical values for the Message ID shall be used for
        outstanding operations.
    MessageIDBeingRespondedTo : int
        The Message ID of the operation request/indication to which this
        response/confirmation applies.
    AffectedSOPClassUID : pydicom.uid.UID, bytes or str
        For the request/indication this specifies the SOP Class for
        storage. If included in the response/confirmation, it shall be equal
        to the value in the request/indication
    Status : int
        The error or success notification of the operation.
    """
    requestor = event.assoc.requestor
    timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    addr, port = requestor.address, requestor.port
    logging.info(f"Received N-EVENT request from {addr}:{port} at {timestamp}")

    model = event.request.AffectedSOPClassUID
    nevent_type_id = nevent_primitive.EventTypeID
    nevent_information = dcmread(nevent_primitive.EventInformation, force=True)
    nevent_rsp_primitive = nevent_primitive
    nevent_rsp_primitive.Status = 0x0000

    logging.info(f"Event Information: {nevent_information}")

    if model.keyword in ["UnifiedProcedureStepPush", "UnifiedProcedureStepEvent"]:
        # event_response_cb(type_id=nevent_type_id, information_ds=nevent_information, logger=logger)
        logging.warning(f"Received model.keyword = {model.keyword} with AffectedSOPClassUID = {model}")
    else:
        logging.warning(f"Received model.keyword = {model.keyword} with AffectedSOPClassUID = {model}")
        logging.warning("Not a UPS Event")

    logging.info("Finished Processing N-EVENT-REPORT-RQ")

    # affected_sop_class_uid = model
    affected_sop_instance_uid = event.request.AffectedSOPInstanceUID
    if "SOPInstanceUID" in nevent_information:
        affected_sop_instance_uid = nevent_information.SOPInstanceUID  # nevent_information.AffectedSOPInstanceUID

    mqtt_event_type = "Workitem"
    subscription_type = None  # the subscription type takes place in N-ACTION, not N-EVENT
    workitem_subtopic = "state"  # the N-EVENT is used to
    print(event_type_dict[nevent_type_id])
    if nevent_type_id == 2:
        workitem_subtopic = "cancelrequest"
    nevent_information.AffectedSOPInstanceUID = affected_sop_instance_uid
    nevent_information.AffectedSOPClassUID = UnifiedProcedureStepPush  # force it to UPS Push
    nevent_information.EventTypeID = nevent_type_id
    json_payload = nevent_information.to_json()
    mqtt_topic = _construct_mqtt_topic(
        mqtt_event_type,
        subscription_type=subscription_type,
        workitem_uid=affected_sop_instance_uid,
        workitem_subtopic=workitem_subtopic,
    )

    if not mqtt_publishing_client.is_connected():
        print("Not connected. Waiting for reconnection...")
        while not mqtt_publishing_client.is_connected():
            time.sleep(1)
    result = mqtt_publishing_client.publish(mqtt_topic, json_payload)
    if result.rc != mqtt_client.MQTT_ERR_SUCCESS:
        print(f"Failed to send message: {mqtt_client.error_string(result.rc)}")
    else:
        print(f"Published event to MQTT topic: {mqtt_topic}")
        print(f"{json_payload}")
    yield 0
    yield 0


def register_subscriber(ae_title, topic):
    client_name = ae_title
    if ae_title not in subscriber_clients:
        command_queues[client_name] = Queue()
        process = Process(
            target=mqtt_client_process,
            args=(client_name, broker_address, broker_port, command_queues[client_name]),
            name=client_name,
        )
        subscriber_processes.append(process)
        subscriber_clients.append(ae_title)
        process.start()
        print(f"Registered subscriber: {ae_title} and started process for it")
        time.sleep(2)
    if topic is None:
        topic = "/workitems/#"
    else:
        topic += "/#"

    command_dict: Command = {"action": "subscribe", "topic": topic}
    command_queues[client_name].put(command_dict)
    print(f"MQTT client: {client_name} is now subscribed to {topic}")


def unregister_subscriber(ae_title, topic: str = None):
    if ae_title in subscriber_clients:
        client_name = ae_title
        if topic is None:
            topic = "/workitems/#"
        command_dict: Command = {"action": "unsubscribe", "topic": topic}
        command_queues[client_name].put(command_dict)
        print(f"MQTT client: {ae_title} is no longer subscribed to {topic}")
    else:
        print(f"Subscriber not found: {ae_title}")


def start_dimse_server(ae: AE, listening_port: int) -> ThreadedAssociationServer:
    ae.add_supported_context(UnifiedProcedureStepWatch)
    ae.add_supported_context(UnifiedProcedureStepEvent)
    ae.add_supported_context(UnifiedProcedureStepPush)
    ae.add_supported_context(Verification)
    dimse_port = listening_port
    handlers = [
        (evt.EVT_N_ACTION, handle_n_action),
        (evt.EVT_N_EVENT_REPORT, handle_dimse_n_event),
        (evt.EVT_C_ECHO, handle_echo),
    ]
    dimse_server = ae.start_server(("0.0.0.0", dimse_port), evt_handlers=handlers, block=False)
    print(f"DIMSE server started on port {dimse_port}")
    return dimse_server


def main():
    broker_address = "127.0.0.1"
    broker_port = 1883
    server_ae_title: str = ADAPTER_AE_TITLE
    server_listening_port: int = 11119
    script_description = textwrap.dedent(
        """DICOM DIMSE UPS Event to MQTT Broker Adapter
    To interact with this broker adapter, subscribe, e.g. with UPSGlobalSubscriptionInstance
    python watchscu.py 127.0.0.1 11119
    And to publish events that are then sent to all appropriate subscribers:
    python nevent_sender.py --called-aet UPSEventBroker01 127.0.0.1 11119
    Substitute the appropriate IP address for 127.0.0.1 and the appropriate port for 11119.
    For this broker adapter to properly associate with UPS Watch subscribers (receiving AEs)
    Populate the Application Entity information in ApplicationEntities.json in the current working directory
    A minimal ApplicationEntities.json would contain something like:
    [
        {
        "AETitle": "NEVENT_RECEIVER",
        "IPAddr": "127.0.0.1",
        "Port": 11115
        }
    ]
    """
    ).strip()
    script_description = script_description.replace("\n", os.linesep)
    parser = argparse.ArgumentParser(description=script_description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--broker-address", type=str, default="127.0.0.1", help="MQTT broker address (default: 127.0.0.1)")
    parser.add_argument("--broker-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument(
        "--server-ae-title", type=str, default=ADAPTER_AE_TITLE, help=f"Server AE title (default: {ADAPTER_AE_TITLE})"
    )
    parser.add_argument("--server-listening-port", type=int, default=11119, help="Server listening port (default: 11119)")
    args = parser.parse_args()
    # Use the parsed arguments
    broker_address = args.broker_address
    broker_port = args.broker_port
    server_ae_title = args.server_ae_title
    server_listening_port = args.server_listening_port
    # main code here
    print(f"Broker address: {broker_address}")
    print(f"Broker port: {broker_port}")
    print(f"Server AE title: {server_ae_title}")
    print(f"Server listening port: {server_listening_port}")
    # known_aes = load_ae_config()
    mqtt_publishing_client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id=server_ae_title)
    mqtt_publishing_client.on_connect = on_connect
    mqtt_publishing_client.on_disconnect = on_disconnect
    mqtt_publishing_client.connect(host=broker_address, port=broker_port)  # clean_start=True)
    mqtt_publishing_client.loop_start()

    time.sleep(2)
    if mqtt_publishing_client.is_connected():
        print("Publishing Client is connected")
    else:
        print("Failed to connect to Broker, Publishing client is not connected")

    server_application_entity = AE(server_ae_title)
    dimse_server = start_dimse_server(ae=server_application_entity, listening_port=server_listening_port)
    print(f"DICOM Server running on: {dimse_server.server_address}")
    run_forever = True
    while run_forever:
        time.sleep(1)

    # Terminate all child processes
    for process in subscriber_processes:
        process.terminate()

    # Wait for all processes to complete
    for process in subscriber_processes:
        process.join()

    print("All processes have been terminated.")


if __name__ == "__main__":
    main()
