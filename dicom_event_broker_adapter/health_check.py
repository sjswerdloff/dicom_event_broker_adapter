"""Health check module for DICOM Event Broker Adapter."""

import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt_client
from pynetdicom.transport import ThreadedAssociationServer


class MQTTHealthChecker:
    """Health checker for MQTT and DIMSE components."""

    def __init__(
        self,
        mqtt_client: mqtt_client.Client,
        dimse_server: ThreadedAssociationServer,
        check_interval: int = 30,
        topic_prefix: str = "health/dicom_broker",
        qos: int = 1,
        retained: bool = True,
    ):
        """Initialize the MQTT health checker.

        Args:
            mqtt_client: The MQTT client to check
            dimse_server: The DIMSE server to check
            check_interval: Interval between health checks in seconds
            topic_prefix: Prefix for health check topics
            qos: Quality of Service level for health messages
            retained: Whether to retain health messages
        """
        self.mqtt_client = mqtt_client
        self.dimse_server = dimse_server
        self.check_interval = check_interval
        self.topic_prefix = topic_prefix
        self.qos = qos
        self.retained = retained
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _health_check_loop(self):
        """Main health check loop that runs in a separate thread."""
        while self._running:
            try:
                # Check MQTT connection status
                mqtt_connected = self.mqtt_client.is_connected() if self.mqtt_client else False

                # Check DIMSE server status
                dimse_running = hasattr(self.dimse_server, "server") and self.dimse_server.server is not None

                # Prepare health status
                health_status = {
                    "timestamp": time.time(),
                    "mqtt_connected": mqtt_connected,
                    "dimse_running": dimse_running,
                    "overall_status": mqtt_connected and dimse_running,
                }

                # Publish health status
                if mqtt_connected:
                    import json

                    health_topic = f"{self.topic_prefix}/status"
                    health_payload = json.dumps(health_status)
                    self.mqtt_client.publish(health_topic, health_payload, qos=self.qos, retain=self.retained)

                # Sleep for the specified interval
                time.sleep(self.check_interval)

            except Exception as e:
                print(f"Error in health check loop: {e}")
                time.sleep(self.check_interval)

    def start(self):
        """Start the health checker in a separate thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._health_check_loop, daemon=True)
            self._thread.start()
            print("Health checker started")

    def stop(self):
        """Stop the health checker."""
        if self._running:
            self._running = False
            if self._thread:
                self._thread.join()
            print("Health checker stopped")
