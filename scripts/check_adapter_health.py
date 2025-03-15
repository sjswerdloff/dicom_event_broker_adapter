#!/usr/bin/env python3
"""
Script to check DICOM MQTT Broker Adapter health via MQTT.
"""

import argparse
import json
import signal
import sys
import time
from datetime import datetime

import paho.mqtt.client as mqtt

# ANSI colors for terminal output
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
NC = "\033[0m"  # No Color

# Health status topics
DEFAULT_TOPIC_PREFIX = "health/dicom_broker"
TIMEOUT = 10  # seconds to wait for responses

# Global variables
received_messages = {}
client = None


def on_connect(client, userdata, flags, rc, properties=None):
    """Called when the client connects to the broker."""
    if rc == 0:
        print(f"{GREEN}Connected to MQTT broker{NC}")
        # Subscribe to all health topics
        topic = f"{args.topic_prefix}/#"
        client.subscribe(topic, qos=1)
        print(f"Subscribed to {topic}")
    else:
        print(f"{RED}Failed to connect to MQTT broker, return code {rc}{NC}")
        sys.exit(1)


def on_message(client, userdata, msg):
    """Called when a message is received from the broker."""
    topic = msg.topic
    try:
        payload = json.loads(msg.payload.decode())
        received_messages[topic] = payload
    except json.JSONDecodeError:
        print(f"{RED}Error: Could not parse JSON from topic {topic}: {msg.payload.decode()}{NC}")


def format_time(timestamp):
    """Format a Unix timestamp as a human-readable string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def print_status(topic, status):
    """Pretty print a status message."""
    if topic.endswith("/status"):
        print(f"\n{BLUE}Overall Health Status:{NC}")
        print(f"  Status: {colorize_status(status.get('status', 'unknown'))}")
        print(f"  Timestamp: {format_time(status.get('timestamp', 0))}")
        print(f"  Node ID: {status.get('node_id', 'unknown')}")

        if "components" in status:
            components = status["components"]
            print(f"\n{BLUE}Component Status:{NC}")

            if "mqtt" in components:
                mqtt_status = components["mqtt"]
                print(f"  MQTT: {colorize_status(mqtt_status.get('status', 'unknown'))}")
                print(f"    Last Check: {format_time(mqtt_status.get('last_check', 0))}")

            if "dimse" in components:
                dimse_status = components["dimse"]
                print(f"  DIMSE: {colorize_status(dimse_status.get('status', 'unknown'))}")
                print(f"    Last Check: {format_time(dimse_status.get('last_check', 0))}")

    elif topic.endswith("/mqtt"):
        print(f"\n{BLUE}MQTT Health:{NC}")
        print(f"  Status: {colorize_status(status.get('status', 'unknown'))}")
        print(f"  Timestamp: {format_time(status.get('timestamp', 0))}")
        print(f"  Node ID: {status.get('node_id', 'unknown')}")

    elif topic.endswith("/dimse"):
        print(f"\n{BLUE}DIMSE Health:{NC}")
        print(f"  Status: {colorize_status(status.get('status', 'unknown'))}")
        print(f"  Timestamp: {format_time(status.get('timestamp', 0))}")
        print(f"  Node ID: {status.get('node_id', 'unknown')}")

    elif topic.endswith("/heartbeat"):
        print(f"\n{BLUE}Heartbeat:{NC}")
        print(f"  Timestamp: {format_time(status.get('timestamp', 0))}")
        print(f"  Count: {status.get('count', 0)}")
        print(f"  Node ID: {status.get('node_id', 'unknown')}")


def colorize_status(status):
    """Add color to a status string."""
    if status == "healthy":
        return f"{GREEN}{status}{NC}"
    elif status == "degraded":
        return f"{YELLOW}{status}{NC}"
    elif status in ["error", "offline"]:
        return f"{RED}{status}{NC}"
    else:
        return status


def signal_handler(sig, frame):
    """Handle Ctrl+C by disconnecting cleanly."""
    print("\nDisconnecting from MQTT broker...")
    if client:
        client.disconnect()
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check DICOM MQTT Broker Adapter health via MQTT")
    parser.add_argument("--broker", type=str, default="localhost", help="MQTT broker address (default: localhost)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument(
        "--topic-prefix",
        type=str,
        default=DEFAULT_TOPIC_PREFIX,
        help=f"Health check topic prefix (default: {DEFAULT_TOPIC_PREFIX})",
    )
    parser.add_argument("--timeout", type=int, default=TIMEOUT, help=f"Timeout in seconds (default: {TIMEOUT})")
    parser.add_argument("--continuous", action="store_true", help="Continuously monitor health status")

    args = parser.parse_args()

    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)

    # Connect to MQTT broker
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.broker, args.port, 60)
    except Exception as e:
        print(f"{RED}Error connecting to MQTT broker: {e}{NC}")
        sys.exit(1)

    # Start the MQTT client loop
    client.loop_start()

    print(f"Waiting up to {args.timeout} seconds for health status messages...")

    # Wait for messages to arrive
    start_time = time.time()
    while time.time() - start_time < args.timeout and f"{args.topic_prefix}/status" not in received_messages:
        time.sleep(0.1)


    # Print received statuses
    if not received_messages:
        print(f"{RED}No health status messages received within timeout.{NC}")
        print("Check if the broker is running and health checks are enabled.")
        client.disconnect()
        sys.exit(1)

    # Print all received messages in a meaningful order
    topics_order = [
        f"{args.topic_prefix}/status",
        f"{args.topic_prefix}/mqtt",
        f"{args.topic_prefix}/dimse",
        f"{args.topic_prefix}/heartbeat",
    ]

    for topic in topics_order:
        if topic in received_messages:
            print_status(topic, received_messages[topic])

    # Check for any other topics we received
    for topic, payload in received_messages.items():
        if topic not in topics_order:
            print(f"\n{BLUE}Additional Topic: {topic}{NC}")
            print(json.dumps(payload, indent=2))

    # Determine overall status
    overall_status = "unknown"
    status_topic = f"{args.topic_prefix}/status"
    if status_topic in received_messages:
        overall_status = received_messages[status_topic].get("status", "unknown")

    # Print summary
    print(f"\n{BLUE}Summary:{NC}")
    print(f"Overall Health: {colorize_status(overall_status)}")

    # For continuous monitoring
    if args.continuous:
        print("\nContinuously monitoring health status. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping health monitor...")

    # Clean up
    client.disconnect()

    # Exit with status code based on health
    if overall_status == "error":
        sys.exit(2)
    elif overall_status == "degraded":
        sys.exit(1)
    else:
        sys.exit(0)
