"""Main application module for DICOM Event Broker Adapter."""

import argparse
import os
import sys
import textwrap
import time
from typing import Optional

from pynetdicom import AE
from pynetdicom.transport import ThreadedAssociationServer

from .config import (
    ADAPTER_AE_TITLE,
    DEFAULT_BROKER_ADDRESS,
    DEFAULT_BROKER_PORT,
    DEFAULT_LISTENING_PORT,
    HEALTH_CHECK_TOPIC_PREFIX,
)
from .dimse_server import start_dimse_server
from .health_check import MQTTHealthChecker
from .mqtt_client import initialize_mqtt_publisher
from .subscriber_manager import cleanup_subscribers


def main():
    """Main entry point for the DICOM Event Broker Adapter."""
    # Parse command line arguments
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
    parser.add_argument(
        "--broker-address", type=str, default=DEFAULT_BROKER_ADDRESS, help="MQTT broker address (default: 127.0.0.1)"
    )
    parser.add_argument("--broker-port", type=int, default=DEFAULT_BROKER_PORT, help="MQTT broker port (default: 1883)")
    parser.add_argument(
        "--server-ae-title", type=str, default=ADAPTER_AE_TITLE, help=f"Server AE title (default: {ADAPTER_AE_TITLE})"
    )
    parser.add_argument(
        "--server-listening-port", type=int, default=DEFAULT_LISTENING_PORT, help="Server listening port (default: 11119)"
    )
    parser.add_argument("--health-check-interval", type=int, default=30, help="Health check interval in seconds (default: 30)")
    parser.add_argument(
        "--health-check-topic",
        type=str,
        default=HEALTH_CHECK_TOPIC_PREFIX,
        help=f"Health check topic prefix (default: {HEALTH_CHECK_TOPIC_PREFIX})",
    )
    parser.add_argument("--disable-health-check", action="store_true", help="Disable the health check system")

    args = parser.parse_args()

    # Initialize components
    broker_address = args.broker_address
    broker_port = args.broker_port
    server_ae_title = args.server_ae_title
    server_listening_port = args.server_listening_port

    print(f"Broker address: {broker_address}")
    print(f"Broker port: {broker_port}")
    print(f"Server AE title: {server_ae_title}")
    print(f"Server listening port: {server_listening_port}")
    print(f"Health check topic: {args.health_check_topic}")

    # Initialize MQTT publishing client
    mqtt_publishing_client = initialize_mqtt_publisher(
        client_id=server_ae_title, broker_address=broker_address, broker_port=broker_port
    )

    time.sleep(2)
    if mqtt_publishing_client.is_connected():
        print("Publishing Client is connected")
    else:
        print("Failed to connect to Broker, Publishing client is not connected")

    # Initialize DIMSE server
    server_application_entity = AE(server_ae_title)
    dimse_server: Optional[ThreadedAssociationServer] = None

    try:
        dimse_server = start_dimse_server(ae=server_application_entity, listening_port=server_listening_port)
        print(f"DICOM Server running on: {dimse_server.server_address}")
    except Exception as e:
        print(f"Failed to start DIMSE server: {e}")
        sys.exit(1)

    # Initialize health checker
    health_checker: Optional[MQTTHealthChecker] = None
    if not args.disable_health_check and dimse_server:
        health_checker = MQTTHealthChecker(
            mqtt_client=mqtt_publishing_client,
            dimse_server=dimse_server,
            check_interval=args.health_check_interval,
            topic_prefix=args.health_check_topic,
            qos=1,
            retained=True,
        )
        health_checker.start()

    # Main application loop
    try:
        run_forever = True
        while run_forever:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error in main loop: {e}")
        raise  # Re-raise the exception so tests can catch it
    finally:
        # Cleanup
        if health_checker:
            health_checker.stop()

        cleanup_subscribers()

        if dimse_server:
            dimse_server.shutdown()

        if mqtt_publishing_client:
            mqtt_publishing_client.loop_stop()
            mqtt_publishing_client.disconnect()

        print("Application shutdown complete.")


if __name__ == "__main__":
    main()
