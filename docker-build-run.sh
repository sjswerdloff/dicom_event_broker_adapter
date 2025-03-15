#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}DICOM MQTT Broker Adapter - Docker Build Script${NC}"
echo "========================================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed or not in your PATH${NC}"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null; then
    echo -e "${YELLOW}Warning: Docker Compose V2 not found, trying docker-compose...${NC}"
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}Error: Neither docker compose nor docker-compose found${NC}"
        exit 1
    fi
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

# Create directories for Mosquitto
echo -e "${GREEN}Creating directories for Mosquitto...${NC}"
mkdir -p mosquitto/data mosquitto/log

# Check if ApplicationEntities.json exists
if [ ! -f ApplicationEntities.json ]; then
    echo -e "${YELLOW}ApplicationEntities.json not found, creating a sample one...${NC}"
    cat > ApplicationEntities.json <<EOF
[
  {
    "AETitle": "NEVENT_RECEIVER",
    "IPAddr": "127.0.0.1",
    "Port": 11115
  },
  {
    "AETitle": "UPS_SUBSCRIBER",
    "IPAddr": "172.17.0.1",
    "Port": 11112
  }
]
EOF
fi

# Build and run with Docker Compose
echo -e "${GREEN}Building and starting containers with Docker Compose...${NC}"
$COMPOSE_CMD up --build -d

# Check if containers are running
echo -e "${GREEN}Checking container status...${NC}"
$COMPOSE_CMD ps

echo -e "${GREEN}To view logs, run:${NC} $COMPOSE_CMD logs -f"
echo -e "${GREEN}To stop the containers, run:${NC} $COMPOSE_CMD down"
echo -e "${GREEN}DICOM MQTT Broker Adapter is now running!${NC}"
