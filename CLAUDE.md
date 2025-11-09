# DICOM Event Broker Adapter Development Guide

## Commands
- Install dependencies: `uv sync`
- Run unit tests: `uv run pytest tests -m "not mqtt_integration"`
- Run integration tests: `uv run pytest -m mqtt_integration -v`
- Run tests with specific marker: `uv run pytest -m mqtt_integration`
- Run all tests: `uv run pytest tests`
- Run specific test: `uv run pytest tests/test_file.py::TestClass::test_method`
- Lint code: `uv run ruff check dicom_event_broker_adapter`
- Format code: `uv run ruff format dicom_event_broker_adapter`
- Start Mosquitto for testing: `./scripts/run_mosquitto.sh start`
- Stop Mosquitto after testing: `./scripts/run_mosquitto.sh stop`

## Code Style
- Follow Ruff formatting (line length: 127)
- Use type hints for all function parameters and return values
- Follow snake_case naming for variables and functions
- Use descriptive docstrings for modules, classes, and functions
- Structure imports: stdlib → third-party → local
- Use explicit exception handling with specific exception classes
- Follow pytest patterns for testing with fixtures in conftest.py
- Make use of pynetdicom and paho-mqtt idioms where appropriate

## Modular Structure
The code has been refactored into the following modules:
- `config.py` - Configuration loading and management
- `mqtt_client.py` - MQTT client implementation and management
- `dimse_server.py` - DICOM DIMSE server implementation
- `event_processor.py` - Event processing and routing logic
- `subscriber_manager.py` - Subscriber registration and management
- `health_check.py` - Health check functionality
- `command_interface.py` - Command processing interface
- `main.py` - Main application entry point

## Testing
Unit tests should focus on individual modules. Integration tests verify the complete flow between DICOM DIMSE events and MQTT messages. Tests rely heavily on mocking of DICOM objects and MQTT clients.

This is a Python package that bridges DICOM UPS events to MQTT messaging through a modular architecture.
