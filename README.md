# dicom_event_broker_adapter
Adapter between DICOM UPS Watch and Event and Event Brokers, such as mosquitto and solace (at this point, any MQTT broker supporting 3.1.1)

The first adapter is for DIMSE and MQTT over TCP using python.

Future adapters will hopefully include adaptation for DICOM Web (UPS-RS) and to other event protocols (like AMQP and SMF), and using other languages (rust, for better performance, if that seems necessary).

## Installation

    poetry install

## Command-Line Interface

The DICOM Event Broker Adapter can be run from the command line after installation. Here's how to use it:

### Basic Usage

To run the adapter with default settings:

```
dicom_event_broker_adapter
```

This will start the adapter with the following default configuration:
- MQTT Broker Address: 127.0.0.1
- MQTT Broker Port: 1883
- Server AE Title: UPSEventBroker01
- Server Listening Port: 11119

### Command-Line Options

You can customize the adapter's behavior using the following command-line options:

- `--broker-address`: Set the MQTT broker address (default: 127.0.0.1)
- `--broker-port`: Set the MQTT broker port (default: 1883)
- `--server-ae-title`: Set the Server AE title (default: UPSEventBroker01)
- `--server-listening-port`: Set the Server listening port (default: 11119)

### Examples

1. Using a different MQTT broker:
   ```
   dicom_event_broker_adapter --broker-address 192.168.1.100 --broker-port 1884
   ```

2. Changing the server AE title and listening port:
   ```
   dicom_event_broker_adapter --server-ae-title MyCustomAETitle --server-listening-port 11120
   ```

3. Combining multiple options:
   ```
   dicom_event_broker_adapter --broker-address mqtt.example.com --broker-port 8883 --server-ae-title CustomAE --server-listening-port 11121
   ```

### Viewing Help

To see all available options and their descriptions, use the `--help` flag:

```
dicom_event_broker_adapter --help
```

This will display a help message with a description of the adapter and all available command-line options.

### Note

Make sure you have the necessary DICOM configuration in place, including the `ApplicationEntities.json` file in your working directory, before running the adapter. This file should contain the necessary information about the Application Entities that the adapter will interact with.
If you did not use poetry install, but have cloned the repository, the command line is

python dicom_event_broker_adapter/ups_event_mqtt_broker_adapter.py
