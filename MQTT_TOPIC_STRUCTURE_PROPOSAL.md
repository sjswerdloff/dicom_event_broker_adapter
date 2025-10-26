# MQTT Topic Structure Analysis and Proposal for IHE-RO TDW-II Alignment

## Executive Summary

This document analyzes the current MQTT topic structure used in the DICOM Event Broker Adapter and proposes an improved structure that better aligns with IHE-RO TDW-II profile requirements and DICOM UPS filtering patterns.

## Current Topic Structure

The repository currently implements a simple flat topic hierarchy:

```
/workitems
/workitems/{workitem_uid}
/workitems/{workitem_uid}/state
/workitems/{workitem_uid}/cancelrequest
```

### Current Implementation Details

From `ups_event_mqtt_broker_adapter.py`:
- Base topic: `/workitems`
- Worklist subscription: `/workitems` (global)
- Filtered worklist: `/workitems` (filter not yet applied to topic)
- Specific workitem: `/workitems/{workitem_uid}`
- Workitem with subtopic: `/workitems/{workitem_uid}/{subtopic}`
  - `subtopic` can be: `state`, `cancelrequest`

### Current Limitations

1. **No location/station filtering**: All devices receive all workitems unless they subscribe to specific UIDs
2. **No patient-level subscriptions**: Cannot subscribe to all events for a specific patient
3. **No activity/procedure type filtering**: Cannot filter by treatment type or procedure category
4. **Poor scalability**: Clients must either subscribe to everything (`/workitems/#`) or know specific UIDs in advance
5. **Acknowledged in code**: Lines 301-309 of `ups_event_mqtt_broker_adapter.py` include a comment recognizing these limitations

## IHE-RO TDW-II Profile Context

### Profile Overview

- **TDW-II**: Treatment Delivery Workflow-II Integration Profile
- **Purpose**: Standardizes workflow between Treatment Management Systems (TMS) and Treatment Delivery Devices (TDD)
- **Status**: Trial Implementation
- **Foundation**: Based on DICOM UPS (Unified Procedure Step)

### Key Finding: No Explicit MQTT Specification

The IHE-RO TDW-II profile does **not explicitly mandate MQTT topic structures**. However, it does define:

1. DICOM UPS subscription mechanisms (Global and Filtered Global Subscription)
2. Event types and their semantics
3. Key filtering attributes for workitem subscriptions

### DICOM UPS Filtering Attributes

The TDW-II profile relies on standard DICOM UPS filtering attributes that should inform MQTT topic design:

| DICOM Attribute | Tag | Purpose | Mapping to MQTT |
|----------------|-----|---------|-----------------|
| Scheduled Station Name Code Sequence | (0040,4025) | WHERE the procedure happens | Station/Location level |
| Scheduled Station AE Title | - | WHICH device/system | Station identifier |
| Scheduled Station Geographic Location Code | - | Physical location | Room/Area identifier |
| Patient ID | (0010,0020) | WHO the procedure is for | Patient level |
| Procedure Step State | - | WHAT status (SCHEDULED, IN PROGRESS, etc.) | Event type |
| Scheduled Human Performers Sequence | (0040,4034) | WHO performs it | Optional filtering |
| Procedure Step Label | - | Type of procedure | Activity type |

### TDW-II Event Types

From `ups_event_mqtt_broker_adapter.py` (lines 38-44):
1. UPS State Report (EventTypeID = 1)
2. UPS Cancel Request (EventTypeID = 2)
3. UPS Progress Report (EventTypeID = 3)
4. SCP Status Change (EventTypeID = 4)
5. UPS Assigned (EventTypeID = 5)

## Proposed Topic Structure

### Full Hierarchical Structure (Recommended)

```
workitems/{station_ae_title}/{patient_id}/{procedure_type}/{workitem_uid}/{event_type}
```

#### Topic Level Definitions

1. **station_ae_title**: AE Title of the scheduled station (e.g., `LINAC_01`, `CT_SIM_02`)
   - Source: DICOM `Scheduled Station AE Title` or `Scheduled Station Name Code Sequence`
   - Use `_unknown_` if not specified

2. **patient_id**: Patient identifier
   - Source: DICOM `Patient ID` (0010,0020)
   - Use `_unknown_` if not specified (e.g., for global subscriptions)

3. **procedure_type**: Category of procedure
   - Examples: `treatment_delivery`, `treatment_planning`, `qa_verification`, `imaging`
   - Source: Mapped from `Procedure Step Label` or `Scheduled Procedure Step Description`
   - Use `_general_` if not categorized

4. **workitem_uid**: SOP Instance UID of the UPS workitem
   - Source: DICOM `SOP Instance UID`
   - Always present and unique

5. **event_type**: Type of event notification
   - Values: `state`, `cancelrequest`, `progress`, `assigned`, `scp_status`
   - Maps to DICOM EventTypeID

#### Example Topics

```
# Specific workitem state change on LINAC 1 for patient PAT12345
workitems/LINAC_01/PAT12345/treatment_delivery/1.2.840.113619.2.55.3.2609/state

# Progress report for the same workitem
workitems/LINAC_01/PAT12345/treatment_delivery/1.2.840.113619.2.609/progress

# Cancel request
workitems/LINAC_01/PAT12345/treatment_delivery/1.2.840.113619.2.609/cancelrequest

# UPS Assigned event
workitems/LINAC_01/PAT12345/treatment_delivery/1.2.840.113619.2.609/assigned

# QA verification on a different device
workitems/QA_STATION_01/PAT12345/qa_verification/1.2.840.113619.2.610/state
```

#### Subscription Patterns

```bash
# Station-specific: All events for LINAC_01
workitems/LINAC_01/#

# Patient-specific: All events for a patient across all stations
workitems/+/PAT12345/#

# Activity-specific: All treatment deliveries across all stations and patients
workitems/+/+/treatment_delivery/#

# Event-specific: All state changes across all workitems
workitems/+/+/+/+/state

# Station and activity: All treatment deliveries on LINAC_01
workitems/LINAC_01/+/treatment_delivery/#

# Station and patient: Everything for a patient on a specific station
workitems/LINAC_01/PAT12345/#

# Single workitem, all events
workitems/LINAC_01/PAT12345/treatment_delivery/1.2.840.113619.2.609/#
```

### Alternative Simplified Structure

If the full structure is too complex, a simplified version:

```
workitems/{station_location}/{patient_id}/{workitem_uid}/{event_type}
```

#### Example:
```
workitems/room1/PAT12345/1.2.840.113619.2.609/state
workitems/room1/PAT12345/1.2.840.113619.2.609/progress
```

This removes procedure_type level but maintains station and patient filtering.

## Benefits of Proposed Structure

### 1. Station-Level Routing
Treatment delivery devices can subscribe to only their relevant workitems:
```
workitems/LINAC_01/#
```
This is critical for TDW-II where each TDD should only receive workitems assigned to it.

### 2. Patient-Focused Monitoring
Care coordination systems can track all procedures for a patient:
```
workitems/+/PAT12345/#
```

### 3. Procedure Type Filtering
Analytics and reporting systems can monitor specific procedure types:
```
workitems/+/+/treatment_delivery/#
```

### 4. Reduced Network Traffic
Clients only receive messages relevant to their subscriptions, reducing bandwidth and processing overhead.

### 5. TDW-II Alignment
Maps directly to DICOM UPS Filtered Global Subscription patterns:
- Station Name → Topic Level 1
- Patient ID → Topic Level 2
- Procedure type → Topic Level 3

### 6. Safety and Compliance
Clear station-level routing reduces risk of workitems being displayed on wrong devices.

### 7. Flexible Querying
MQTT wildcards (`+` and `#`) enable powerful filtering without custom application logic.

## Implementation Recommendations

### Phase 1: Enhance Topic Construction

Modify `_construct_mqtt_topic()` in `ups_event_mqtt_broker_adapter.py`:

```python
def _construct_mqtt_topic(
    event_type,
    subscription_type: Optional[str] = None,
    workitem_uid: Optional[UID] = None,
    workitem_subtopic: Optional[str] = None,
    subscriber_ae_title: Optional[str] = None,
    dicom_topic_filter: Optional[Dataset] = None,
    # New parameters for enhanced structure
    station_ae_title: Optional[str] = None,
    patient_id: Optional[str] = None,
    procedure_type: Optional[str] = None,
    use_enhanced_structure: bool = True,  # Feature flag
):
    """Construct MQTT topic with optional enhanced hierarchical structure."""

    if not use_enhanced_structure:
        # Fallback to current simple structure
        return _construct_legacy_topic(...)

    # Enhanced structure implementation
    base_topic = "workitems"

    # Extract attributes from dicom_topic_filter if provided
    if dicom_topic_filter:
        station_ae_title = station_ae_title or _extract_station_ae(dicom_topic_filter)
        patient_id = patient_id or _extract_patient_id(dicom_topic_filter)
        procedure_type = procedure_type or _extract_procedure_type(dicom_topic_filter)

    # Use defaults for unspecified values
    station = station_ae_title or "_unknown_"
    patient = patient_id or "_unknown_"
    proc_type = procedure_type or "_general_"

    if subscription_type in ["Worklist", "FilteredWorklist"]:
        # Global subscriptions use wildcards
        return f"{base_topic}/{station}/{patient}/{proc_type}/#"

    if workitem_uid:
        topic = f"{base_topic}/{station}/{patient}/{proc_type}/{workitem_uid}"
        if workitem_subtopic:
            topic = f"{topic}/{workitem_subtopic}"
        return topic

    raise ValueError("Invalid topic construction parameters")
```

### Phase 2: Extract Attributes from DICOM Datasets

Add helper functions to extract DICOM attributes:

```python
def _extract_station_ae(dataset: Dataset) -> Optional[str]:
    """Extract Scheduled Station AE Title from dataset."""
    # Try Scheduled Station Name Code Sequence first
    if hasattr(dataset, 'ScheduledStationNameCodeSequence'):
        # Extract from code sequence
        pass
    # Fallback to other attributes
    return None

def _extract_patient_id(dataset: Dataset) -> Optional[str]:
    """Extract Patient ID from dataset."""
    return getattr(dataset, 'PatientID', None)

def _extract_procedure_type(dataset: Dataset) -> Optional[str]:
    """Map procedure step label to procedure type category."""
    label = getattr(dataset, 'ProcedureStepLabel', '')
    # Map to categories: treatment_delivery, treatment_planning, etc.
    return _map_to_procedure_category(label)
```

### Phase 3: Backwards Compatibility

Maintain compatibility during transition:

1. **Dual Publishing**: Publish to both old and new topic structures
2. **Configuration Flag**: `--use-enhanced-topics` command-line argument
3. **Gradual Migration**: Allow clients to migrate at their own pace

### Phase 4: Update Subscription Logic

Modify `handle_n_action()` to use enhanced topics when constructing subscriptions:

```python
def handle_n_action(event: Event):
    # ... existing code ...

    # Extract station and patient info from action_information
    station_ae = _extract_station_ae(action_information)
    patient_id = _extract_patient_id(action_information)

    topic = _construct_mqtt_topic(
        event_type=mqtt_event_type,
        subscription_type=subscription_type,
        workitem_uid=workitem_uid,
        dicom_topic_filter=action_information,
        station_ae_title=station_ae,
        patient_id=patient_id,
        use_enhanced_structure=enhanced_topics_enabled,
    )

    # ... rest of handler ...
```

### Phase 5: Update Tests

Add test cases in `test_construct_mqtt_topic.py`:

```python
def test_enhanced_topic_with_all_attributes():
    result = _construct_mqtt_topic(
        event_type="Workitem",
        workitem_uid="1.2.3.4.5",
        workitem_subtopic="state",
        station_ae_title="LINAC_01",
        patient_id="PAT12345",
        procedure_type="treatment_delivery",
    )
    assert result == "workitems/LINAC_01/PAT12345/treatment_delivery/1.2.3.4.5/state"

def test_enhanced_topic_with_wildcards():
    result = _construct_mqtt_topic(
        event_type="Workitem",
        subscription_type="FilteredWorklist",
        station_ae_title="LINAC_01",
    )
    assert result == "workitems/LINAC_01/_unknown_/_general_/#"
```

## Migration Strategy

### For Existing Deployments

1. **Update Broker Adapter**: Deploy new version with enhanced topic support
2. **Enable Dual Publishing**: Publish to both old and new structures
3. **Update Subscribers**: Migrate subscribers to use new topic patterns
4. **Monitor**: Verify no subscribers still using old patterns
5. **Deprecate**: Remove old topic publishing after migration period

### Configuration Options

Add to command-line arguments:

```bash
dicom_event_broker_adapter \
  --broker-address 127.0.0.1 \
  --broker-port 1883 \
  --use-enhanced-topics \
  --dual-publish  # Publish to both old and new during migration
```

## Comparison with Original Comment

The original comment in `ups_event_mqtt_broker_adapter.py` (lines 301-309) suggested:

```
workitems/<location>/<patient_id>/<activity_type>/<work_item_id>
```

Our proposal refines this to:

```
workitems/{station_ae_title}/{patient_id}/{procedure_type}/{workitem_uid}/{event_type}
```

**Key improvements:**
1. More specific station identifier (AE Title rather than generic "location")
2. Added event_type level for finer-grained subscriptions
3. Aligned terminology with DICOM UPS and TDW-II
4. Defined concrete mapping from DICOM attributes to topic levels

## Conclusion

The proposed MQTT topic structure provides:

- ✅ **TDW-II Alignment**: Maps to DICOM UPS filtering patterns
- ✅ **Scalability**: Reduces message traffic through targeted subscriptions
- ✅ **Flexibility**: MQTT wildcards enable powerful filtering
- ✅ **Safety**: Clear station-level routing
- ✅ **Extensibility**: Can add more levels if needed
- ✅ **Backwards Compatibility**: Can maintain old structure during transition

### Recommended Next Steps

1. Review and approve proposed structure
2. Implement Phase 1 (topic construction enhancement)
3. Add comprehensive tests
4. Document new topic patterns for API users
5. Plan migration timeline for existing deployments

## References

- IHE-RO TDW-II Profile: https://wiki.ihe.net/index.php/RT_Treatment_Delivery_Workflow-II
- DICOM PS3.4 Section CC: Unified Procedure Step Service
- DICOM PS3.18 Section 11.10: UPS-RS Subscribe Transaction
- MQTT Topic Best Practices: https://www.hivemq.com/blog/mqtt-essentials-part-5-mqtt-topics-best-practices/
- Current implementation: `dicom_event_broker_adapter/ups_event_mqtt_broker_adapter.py`
