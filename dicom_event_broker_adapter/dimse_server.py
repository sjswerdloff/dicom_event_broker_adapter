"""DICOM DIMSE server module for DICOM Event Broker Adapter."""

import logging

from pydicom import Dataset, dcmread
from pynetdicom import AE, evt
from pynetdicom.events import Event
from pynetdicom.sop_class import (
    UnifiedProcedureStepEvent,
    UnifiedProcedureStepPush,
    UnifiedProcedureStepWatch,
    UPSFilteredGlobalSubscriptionInstance,
    UPSGlobalSubscriptionInstance,
    Verification,
)
from pynetdicom.transport import ThreadedAssociationServer

from . import mqtt_client
from .config import ACTION_TYPE_DICT, load_ae_config


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
    from .subscriber_manager import register_subscriber, unregister_subscriber

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
            logging.info(f"MQTT Event Type: {mqtt_event_type}")
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
    print(f"ActionTypeID = {action_type_id} == {ACTION_TYPE_DICT[action_type_id]}")
    action_information = dcmread(naction_primitive.ActionInformation, force=True)
    requesting_ae = event.assoc.requestor.ae_title
    receiving_ae = requesting_ae  # only as a fallback.
    if "ReceivingAE" in action_information:
        receiving_ae = action_information.ReceivingAE
    known_aes = load_ae_config()
    if receiving_ae not in known_aes:
        reloaded_aes = load_ae_config()
        if receiving_ae not in reloaded_aes:
            # Table CC.2.3-3. N-ACTION Response Status Values for Subscribe/Unsubscribe to Receive UPS EventReports
            return 0xC308  # Failure, don't recognize the receiving AE.

    # Using a simplified version of topic construction that will be moved to config module
    if subscription_type == "Worklist":
        topic = "/workitems"
    elif subscription_type == "FilteredWorklist":
        topic = "/workitems"  # needs work for filtering
    elif workitem_uid:
        topic = f"/workitems/{workitem_uid}"
    else:
        topic = "/workitems"

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
    """Handle N-EVENT-REPORT requests from DICOM devices."""
    from .config import construct_mqtt_topic
    from .mqtt_client import mqtt_publishing_client

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
    from .config import EVENT_TYPE_DICT

    print(EVENT_TYPE_DICT[nevent_type_id])
    if nevent_type_id == 2:
        workitem_subtopic = "cancelrequest"
    nevent_information.AffectedSOPInstanceUID = affected_sop_instance_uid
    nevent_information.AffectedSOPClassUID = UnifiedProcedureStepPush  # force it to UPS Push
    nevent_information.EventTypeID = nevent_type_id
    json_payload = nevent_information.to_json()
    mqtt_topic = construct_mqtt_topic(
        mqtt_event_type,
        subscription_type=subscription_type,
        workitem_uid=affected_sop_instance_uid,
        workitem_subtopic=workitem_subtopic,
    )

    if not mqtt_publishing_client or not mqtt_publishing_client.is_connected():
        print("Not connected. Waiting for reconnection...")
        while not mqtt_publishing_client or not mqtt_publishing_client.is_connected():
            import time

            time.sleep(1)
    result = mqtt_publishing_client.publish(mqtt_topic, json_payload)
    if result.rc != mqtt_client.MQTT_ERR_SUCCESS:
        print(f"Failed to send message: {mqtt_client.error_string(result.rc)}")
    else:
        print(f"Published event to MQTT topic: {mqtt_topic}")
        print(f"{json_payload}")
    yield 0
    yield 0


def start_dimse_server(ae: AE, listening_port: int) -> ThreadedAssociationServer:
    """Start the DIMSE server with the specified AE and port."""
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
