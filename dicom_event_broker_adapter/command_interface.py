"""Command interface module for DICOM Event Broker Adapter."""

from queue import Empty, Queue
from typing import Dict

from .config import Command


def parent_process(command_queues: Dict[str, Queue]) -> None:
    """Parent process that handles user commands for subscriber management."""
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
        except EOFError:
            print("\nExiting...")
            break


def process_commands(command_queue: Queue) -> None:
    """Process commands from a command queue."""
    try:
        command: Command = command_queue.get_nowait()
        print("received command")
        if command["action"] == "subscribe":
            # Handle subscribe action
            print(f"Processing subscribe command for topic: {command['topic']}")
        elif command["action"] == "unsubscribe":
            # Handle unsubscribe action
            print(f"Processing unsubscribe command for topic: {command['topic']}")
    except Empty:
        pass  # No command to process
