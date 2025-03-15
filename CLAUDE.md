# DICOM Event Broker Adapter Development Guide

## Commands
- Install dependencies: `poetry install`
- Run unit tests: `poetry run pytest tests -m "no mqtt_integration"`
- Run integration tests: `poetry run pytest -m mqtt_integration -v`
- Run tests with specific marker: `poetry run pytest -m mqtt_integration`
- Run all tests: `poetry run pytest tests`
- Run specific test: `poetry run pytest tests/test_file.py::TestClass::test_method`
- Lint code: `poetry run flake8 dicom_event_broker_adapter`
- Format code: `poetry run black dicom_event_broker_adapter`
- Sort imports: `poetry run isort dicom_event_broker_adapter`
- Start Mosquitto for testing: `./scripts/run_mosquitto.sh start`
- Stop Mosquitto after testing: `./scripts/run_mosquitto.sh stop`

## Code Style
- Follow Black formatting (line length: 127)
- Use type hints for all function parameters and return values
- Follow snake_case naming for variables and functions
- Use descriptive docstrings for modules, classes, and functions
- Structure imports: stdlib → third-party → local
- Use explicit exception handling with specific exception classes
- Follow pytest patterns for testing with fixtures in conftest.py
- Make use of pynetdicom and paho-mqtt idioms where appropriate

This is a Python package that bridges DICOM UPS events to MQTT messaging. Tests rely heavily on mocking of DICOM objects and MQTT clients.
