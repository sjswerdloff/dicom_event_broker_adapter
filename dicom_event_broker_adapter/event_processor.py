"""Event processing module for DICOM Event Broker Adapter."""

from pydicom import Dataset
from pynetdicom import AE
from pynetdicom.presentation import build_context
from pynetdicom.sop_class import UnifiedProcedureStepPush

from .config import load_ae_config


def send_event_report(dataset: Dataset, client_ae_title: str, subscriber_ae_title: str):
    """Send a DICOM N-EVENT-REPORT to a subscriber."""
    print(dataset)
    ae_title = client_ae_title
    contexts = [build_context(UnifiedProcedureStepPush)]
    send_event_scu = AE(ae_title)

    # Load AE configuration
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
