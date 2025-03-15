"""Health check module for DICOM MQTT Broker Adapter using MQTT protocol.

This module provides health status monitoring through MQTT topics,
allowing external systems to monitor the application health via MQTT.
"""

import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt_client

# Set up logging
logger = logging.getLogger(__name__)

# Health check topics
HEALTH_TOPIC_BASE = "health/dicom_broker"
HEALTH_TOPIC_STATUS = f"{HEALTH_TOPIC_BASE}/status"
HEALTH_TOPIC_MQTT = f"{HEALTH_TOPIC_BASE}/mqtt"
HEALTH_TOPIC_DIMSE = f"{HEALTH_TOPIC_BASE}/dimse"
HEALTH_TOPIC_HEARTBEAT = f"{HEALTH_TOPIC_BASE}/heartbeat"


class HealthStatus:
    """Class to maintain health status of various components."""

    def __init__(self):
        self.mqtt_status = "unknown"
        self.mqtt_last_check = 0
        self.dimse_status = "unknown"
        self.dimse_last_check = 0
        self.component_statuses: Dict[str, Dict[str, Any]] = {}
        self.overall_status = "unknown"
        self._lock = threading.Lock()

    def update_mqtt_status(self, status: str):
        """Update MQTT connection status."""
        with self._lock:
            self.mqtt_status = status
            self.mqtt_last_check = time.time()
            self._update_overall_status()

    def update_dimse_status(self, status: str):
        """Update DIMSE server status."""
        with self._lock:
            self.dimse_status = status
            self.dimse_last_check = time.time()
            self._update_overall_status()

    def update_component_status(self, component: str, status: str, details: Optional[Dict[str, Any]] = None):
        """Update status of a specific component."""
        with self._lock:
            self.component_statuses[component] = {"status": status, "last_check": time.time(), "details": details or {}}
            self._update_overall_status()

    def _update_overall_status(self):
        """Update the overall health status based on component statuses."""
        if "error" in [self.mqtt_status, self.dimse_status]:
            self.overall_status = "error"
        elif "degraded" in [self.mqtt_status, self.dimse_status]:
            self.overall_status = "degraded"
        elif self.mqtt_status == "healthy" and self.dimse_status == "healthy":
            self.overall_status = "healthy"
        else:
            self.overall_status = "unknown"

        # Also consider component statuses
        component_statuses = [info["status"] for info in self.component_statuses.values()]
        if "error" in component_statuses and self.overall_status != "error":
            self.overall_status = "error"
        elif "degraded" in component_statuses and self.overall_status not in ["error"]:
            self.overall_status = "degraded"

    def get_status(self) -> Dict[str, Any]:
        """Get the complete health status as a dictionary."""
        with self._lock:
            return {
                "status": self.overall_status,
                "timestamp": time.time(),
                "components": {
                    "mqtt": {"status": self.mqtt_status, "last_check": self.mqtt_last_check},
                    "dimse": {"status": self.dimse_status, "last_check": self.dimse_last_check},
                    **self.component_statuses,
                },
            }


class MQTTHealthChecker:
    """Health checker that publishes status via MQTT topics."""

    def __init__(
        self,
        mqtt_client: mqtt_client.Client,
        dimse_server: Optional[Any] = None,
        check_interval: int = 30,
        topic_prefix: str = HEALTH_TOPIC_BASE,
        qos: int = 1,
        retained: bool = True,
    ):
        """Initialize the MQTT health checker.

        Args:
            mqtt_client: MQTT client instance to use for publishing status.
            dimse_server: DIMSE server instance to check.
            check_interval: Interval between health checks in seconds.
            topic_prefix: Prefix for health check topics.
            qos: QoS level for health status messages.
            retained: Whether health status messages should be retained.
        """
        self.mqtt_client = mqtt_client
        self.dimse_server = dimse_server
        self.check_interval = check_interval
        self.topic_prefix = topic_prefix
        self.qos = qos
        self.retained = retained
        self.health_status = HealthStatus()
        self.checker_thread = None
        self.running = False
        self.node_id = str(uuid.uuid4())

        # Define topics
        self.status_topic = f"{topic_prefix}/status"
        self.mqtt_topic = f"{topic_prefix}/mqtt"
        self.dimse_topic = f"{topic_prefix}/dimse"
        self.heartbeat_topic = f"{topic_prefix}/heartbeat"

    def start(self):
        """Start the health checker."""
        if self.running:
            return

        # Start periodic health checks
        self.running = True
        self.checker_thread = threading.Thread(target=self._run_checks)
        self.checker_thread.daemon = True
        self.checker_thread.start()

        logger.info(f"MQTT Health checker started with node ID {self.node_id}")
        logger.info(f"Publishing health status to {self.status_topic}")

    def stop(self):
        """Stop the health checker."""
        if not self.running:
            return

        self.running = False

        if self.checker_thread and self.checker_thread.is_alive():
            self.checker_thread.join(timeout=5)

        # Publish final offline status
        try:
            final_status = {"status": "offline", "timestamp": time.time(), "node_id": self.node_id}
            self.mqtt_client.publish(self.status_topic, json.dumps(final_status), qos=self.qos, retain=self.retained)
            logger.info("Published offline health status")
        except Exception as e:
            logger.error(f"Error publishing offline status: {str(e)}")

        logger.info("Health checker stopped")

    def _run_checks(self):
        """Run periodic health checks."""
        heartbeat_count = 0
        while self.running:
            try:
                # Check MQTT connectivity
                self._check_mqtt()

                # Check DIMSE server
                self._check_dimse()

                # Publish overall status
                self._publish_status()

                # Publish heartbeat
                heartbeat_count += 1
                self._publish_heartbeat(heartbeat_count)

                # Sleep until next check
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in health check: {str(e)}")
                # Try to update the status to error
                try:
                    self.health_status.update_mqtt_status("error")
                    self.health_status.update_dimse_status("error")
                    self._publish_status()
                except Exception as e:
                    logger.error(f"Error in trying to update health status to error! {e}")
                time.sleep(5)  # Sleep a bit before retrying

    def _check_mqtt(self):
        """Check MQTT broker connectivity."""
        try:
            if self.mqtt_client.is_connected():
                # Try publishing a test message to verify the connection is fully functional
                test_topic = f"{self.topic_prefix}/test/{uuid.uuid4()}"
                test_message = json.dumps({"timestamp": time.time(), "node_id": self.node_id})
                result = self.mqtt_client.publish(test_topic, test_message)

                if result.rc == mqtt_client.MQTT_ERR_SUCCESS:
                    self.health_status.update_mqtt_status("healthy")
                else:
                    logger.warning(f"MQTT publish failed with code: {result.rc}")
                    self.health_status.update_mqtt_status("degraded")
            else:
                logger.warning("MQTT client is not connected")
                self.health_status.update_mqtt_status("error")

            # Publish MQTT-specific status
            mqtt_status = {"status": self.health_status.mqtt_status, "timestamp": time.time(), "node_id": self.node_id}
            self.mqtt_client.publish(self.mqtt_topic, json.dumps(mqtt_status), qos=self.qos, retain=self.retained)
        except Exception as e:
            logger.error(f"Error checking MQTT status: {str(e)}")
            self.health_status.update_mqtt_status("error")

    def _check_dimse(self):
        """Check DIMSE server status."""
        try:
            # Check if the server socket is still active
            if self.dimse_server and hasattr(self.dimse_server, "socket") and self.dimse_server.socket:
                self.health_status.update_dimse_status("healthy")
            else:
                if self.dimse_server:
                    logger.warning("DIMSE server socket is not active")
                    self.health_status.update_dimse_status("error")
                else:
                    self.health_status.update_dimse_status("unknown")

            # Publish DIMSE-specific status
            dimse_status = {"status": self.health_status.dimse_status, "timestamp": time.time(), "node_id": self.node_id}
            self.mqtt_client.publish(self.dimse_topic, json.dumps(dimse_status), qos=self.qos, retain=self.retained)
        except Exception as e:
            logger.error(f"Error checking DIMSE status: {str(e)}")
            self.health_status.update_dimse_status("error")

    def _publish_status(self):
        """Publish overall health status to MQTT."""
        try:
            if not self.mqtt_client.is_connected():
                logger.warning("Cannot publish health status: MQTT client not connected")
                return

            status = self.health_status.get_status()
            status["node_id"] = self.node_id

            self.mqtt_client.publish(self.status_topic, json.dumps(status), qos=self.qos, retain=self.retained)
        except Exception as e:
            logger.error(f"Error publishing health status: {str(e)}")

    def _publish_heartbeat(self, count):
        """Publish a heartbeat message."""
        try:
            if not self.mqtt_client.is_connected():
                return

            heartbeat = {"timestamp": time.time(), "count": count, "node_id": self.node_id}

            self.mqtt_client.publish(
                self.heartbeat_topic,
                json.dumps(heartbeat),
                qos=0,  # Use QoS 0 for heartbeats to minimize overhead
                retain=False,  # No need to retain heartbeats
            )
        except Exception as e:
            logger.error(f"Error publishing heartbeat: {str(e)}")
