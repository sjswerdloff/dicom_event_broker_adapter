"""Subscriber management module for DICOM Event Broker Adapter."""

import time
from multiprocessing import Process, Queue

from .config import Command
from .mqtt_client import command_queues, mqtt_client_process, subscriber_clients, subscriber_processes


def register_subscriber(ae_title: str, topic: str = None):
    """Register a new subscriber and start its MQTT client process."""
    client_name = ae_title
    if ae_title not in subscriber_clients:
        command_queues[client_name] = Queue()
        process = Process(
            target=mqtt_client_process,
            args=(client_name, "127.0.0.1", 1883, command_queues[client_name]),  # Using default broker values for now
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


def unregister_subscriber(ae_title: str, topic: str = None):
    """Unregister a subscriber and stop its MQTT client process."""
    if ae_title in subscriber_clients:
        client_name = ae_title
        if topic is None:
            topic = "/workitems/#"
        command_dict: Command = {"action": "unsubscribe", "topic": topic}
        command_queues[client_name].put(command_dict)
        print(f"MQTT client: {ae_title} is no longer subscribed to {topic}")
    else:
        print(f"Subscriber not found: {ae_title}")


def cleanup_subscribers():
    """Clean up all subscriber processes."""
    for process in subscriber_processes:
        if process.is_alive():
            process.terminate()

    # Wait for all processes to complete
    for process in subscriber_processes:
        process.join()

    print("All subscriber processes have been terminated.")
