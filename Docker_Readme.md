# DICOM DIMSE UPS Event to MQTT Broker Adapter - Docker Setup

This document describes how to build and run the DICOM DIMSE UPS Event to MQTT Broker Adapter in a Docker container.

## Prerequisites

- Docker
- Docker Compose (optional but recommended)

## Project Structure

Your project already has the correct structure. Just add these Docker-related files:

```
project/
├── Dockerfile              # Add this
├── docker-compose.yml      # Add this
├── .dockerignore           # Add this
├── ApplicationEntities.json
├── dicom_event_broker_adapter/
│   ├── __init__.py
│   └── ups_event_mqtt_broker_adapter.py
├── pyproject.toml
├── uv.lock
├── README.md
├── tests/
│   └── config/
│       └── mosquitto.conf
└── mosquitto/              # Create this directory
    ├── data/               # Create this directory
    └── log/                # Create this directory
```

## Building and Running the Docker Image

### Automated Script (Recommended)

A convenience script is provided to build and run the Docker container:

```bash
# Make the script executable
chmod +x docker-build-run.sh

# Run the script
./docker-build-run.sh
```

### Manual Setup

#### Option 1: Using Docker CLI

```bash
# Build the image
docker build -t dicom-mqtt-adapter .

# Run the container
docker run -p 11119:11119 -v $(pwd)/ApplicationEntities.json:/app/ApplicationEntities.json dicom-mqtt-adapter
```

#### Option 2: Using Docker Compose

```bash
# Create directories for Mosquitto
mkdir -p mosquitto/data mosquitto/log

# Build and start the services
docker compose up -d

# For older Docker Compose versions
docker-compose up -d

# View logs
docker compose logs -f
```

## Configuration

### ApplicationEntities.json

This file contains the list of DICOM Application Entities that the adapter can communicate with. Make sure to update it with your actual AE Titles, IP addresses, and ports.

### Environment Variables

You can configure the adapter by setting environment variables in the docker-compose.yml file:

- `BROKER_ADDRESS`: The MQTT broker address (default: host.docker.internal)
- `BROKER_PORT`: The MQTT broker port (default: 1883)
- `SERVER_AE_TITLE`: The AE title for the adapter (default: UPSEventBroker01)
- `SERVER_LISTENING_PORT`: The port on which the adapter listens for DICOM connections (default: 11119)

## Networking

When running the adapter in Docker, be aware of the following networking considerations:

1. The container exposes port 11119 for DICOM communication
2. The adapter attempts to connect to the MQTT broker at the specified address and port
3. For communication between containers, use the service name (e.g., "mqtt-broker")
4. For communication with the host, use "host.docker.internal" (on macOS and Windows) or the host's IP address

## Troubleshooting

### Cannot connect to MQTT broker

Check that:
- The broker is running
- The broker address and port are correct
- Network connectivity between the containers is working

### DICOM associations failing

Check that:
- The ApplicationEntities.json file contains the correct information
- The firewall allows connections on port 11119
- The AE titles match between the systems

## Security Considerations

This setup is intended for development and testing. For production use, consider:

1. Adding authentication to the MQTT broker
2. Using TLS/SSL for MQTT and DICOM communications
3. Implementing network segmentation
4. Running the container with a non-root user (already configured in the Dockerfile)
