#!/bin/bash

# Script to start/stop Mosquitto for local testing

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
MOSQUITTO_CONFIG="$REPO_ROOT/tests/config/mosquitto.conf"
CONTAINER_NAME="mqtt-test-broker"
PID_FILE="/tmp/mqtt-test-broker.pid"

is_port_in_use() {
    if command -v nc &> /dev/null; then
        nc -z localhost 1883 &> /dev/null
        return $?
    elif command -v lsof &> /dev/null; then
        lsof -i:1883 &> /dev/null
        return $?
    else
        # Default to assuming port is not in use if we can't check
        return 1
    fi
}

start_mosquitto() {
    echo "Starting Mosquitto broker for testing..."

    # Check if mosquitto is already running on port 1883
    if is_port_in_use; then
        echo "⚠️  Port 1883 is already in use. A Mosquitto broker might already be running."
        echo "✅ Using existing broker on localhost:1883"
        return 0
    fi

    # Try Docker first
    if command -v docker &> /dev/null; then
        echo "Using Docker to run Mosquitto..."

        # Check if container already exists
        if docker ps -a --format '{{.Names}}' | grep -q "^$CONTAINER_NAME$"; then
            echo "Mosquitto container already exists, stopping and removing it first..."
            docker stop "$CONTAINER_NAME" &> /dev/null
            docker rm "$CONTAINER_NAME" &> /dev/null
        fi

        # Start new container
        # Ensure config file exists
        if [ ! -f "$MOSQUITTO_CONFIG" ]; then
            echo "⚠️ Config file not found: $MOSQUITTO_CONFIG"
            exit 1
        fi

        echo "Using config from: $MOSQUITTO_CONFIG"

        # Create a directory to hold the config if needed
        CONFIG_DIR=$(dirname "$MOSQUITTO_CONFIG")

        docker run -d --name "$CONTAINER_NAME" \
            -p 1883:1883 \
            -v "$MOSQUITTO_CONFIG:/mosquitto/config/mosquitto.conf:ro" \
            eclipse-mosquitto:2.0

        echo "Waiting for Mosquitto to start..."
        sleep 2

        if docker ps | grep -q "$CONTAINER_NAME"; then
            echo "✅ Mosquitto broker is running on localhost:1883 via Docker"
            return 0
        else
            echo "⚠️  Failed to start Mosquitto via Docker"
            docker logs "$CONTAINER_NAME" 2>/dev/null || true
            # Fall through to try local mosquitto
        fi
    else
        echo "Docker is not available. Checking for local Mosquitto installation..."
    fi

    # Try local Mosquitto as fallback
    if command -v mosquitto &> /dev/null; then
        echo "Found local Mosquitto installation, launching directly..."

        # Simpler approach - just start mosquitto as a daemon
        # Check if config file exists and is readable
        if [ -f "$MOSQUITTO_CONFIG" ] && [ -r "$MOSQUITTO_CONFIG" ]; then
            echo "Configuration file exists and is readable"
            # Display config file content for debugging
            echo "Configuration file content:"
            cat "$MOSQUITTO_CONFIG"
        else
            echo "⚠️  Configuration file not found or not readable, will use default config"
            MOSQUITTO_CONFIG=""
        fi

        # Kill any existing Mosquitto processes first to avoid port conflicts
        pkill mosquitto 2>/dev/null || true
        sleep 1

        # Start Mosquitto with the config file if it's valid
        if [ -n "$MOSQUITTO_CONFIG" ]; then
            echo "Starting with config file: $MOSQUITTO_CONFIG"
            mosquitto -c "$MOSQUITTO_CONFIG" -d
        else
            echo "Starting with default config"
            mosquitto -d
        fi

        echo "Waiting for Mosquitto to start..."
        sleep 2

        # Check if mosquitto is running by checking the port
        if is_port_in_use; then
            # Find the PID of the mosquitto process
            MOSQUITTO_PID=$(pgrep mosquitto)
            if [ -n "$MOSQUITTO_PID" ]; then
                echo $MOSQUITTO_PID > "$PID_FILE"
                echo "✅ Mosquitto broker is running on localhost:1883 (PID: $MOSQUITTO_PID)"
                return 0
            else
                echo "⚠️  Port is open but couldn't find Mosquitto PID"
                return 0  # Still return success as broker is running
            fi
        else
            echo "❌ Failed to start local Mosquitto"
            return 1
        fi
    else
        echo "❌ Neither Docker nor local Mosquitto installation found."
        echo "Please install Docker or Mosquitto to run integration tests."
        return 1
    fi
}

stop_mosquitto() {
    echo "Stopping Mosquitto broker..."

    # Try to stop Docker container if it exists
    if command -v docker &> /dev/null && docker ps | grep -q "$CONTAINER_NAME" 2>/dev/null; then
        echo "Stopping Docker container..."
        docker stop "$CONTAINER_NAME" &> /dev/null
        docker rm "$CONTAINER_NAME" &> /dev/null
        echo "✅ Mosquitto Docker container stopped"
        return 0
    fi

    # First check for any Mosquitto process running locally
    if pgrep mosquitto >/dev/null; then
        echo "Found running Mosquitto process(es), stopping them..."

        # Use PID file if it exists
        if [ -f "$PID_FILE" ]; then
            MOSQUITTO_PID=$(cat "$PID_FILE")
            if kill -0 "$MOSQUITTO_PID" 2>/dev/null; then
                echo "Stopping local Mosquitto process (PID: $MOSQUITTO_PID)..."
                kill "$MOSQUITTO_PID" 2>/dev/null
            fi
            rm -f "$PID_FILE"
        fi

        # Use pkill as a fallback to kill all mosquitto processes
        pkill mosquitto 2>/dev/null
        sleep 1

        # Verify it's stopped
        if pgrep mosquitto >/dev/null; then
            echo "⚠️  Failed to stop Mosquitto gracefully, trying SIGKILL..."
            pkill -9 mosquitto 2>/dev/null
            sleep 1
        fi

        # Final check
        if ! pgrep mosquitto >/dev/null; then
            echo "✅ Local Mosquitto process(es) stopped"
            return 0
        else
            echo "⚠️  Some Mosquitto processes could not be stopped. You may need to stop them manually."
        fi
    elif [ -f "$PID_FILE" ]; then
        echo "⚠️  PID file exists but no Mosquitto process is running"
        rm -f "$PID_FILE"
    else
        echo "No Mosquitto processes found"
    fi

    # Check if port 1883 is still in use
    if is_port_in_use; then
        echo "⚠️  Port 1883 is still in use by another process."
        echo "You may need to stop it manually."
    else
        echo "✅ No MQTT broker running on port 1883"
    fi
}

case "$1" in
    start)
        if ! start_mosquitto; then
            echo "Failed to start Mosquitto. Integration tests requiring MQTT will be skipped."
            exit 1
        fi
        ;;
    stop)
        stop_mosquitto
        ;;
    restart)
        stop_mosquitto
        if ! start_mosquitto; then
            echo "Failed to restart Mosquitto. Integration tests requiring MQTT will be skipped."
            exit 1
        fi
        ;;
    status)
        if is_port_in_use; then
            echo "✅ Mosquitto broker is running on localhost:1883"
            exit 0
        else
            echo "❌ No Mosquitto broker is running on localhost:1883"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
