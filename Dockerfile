FROM ghcr.io/astral-sh/uv:python3.12-alpine

# Install git for fetching dependencies
RUN apk add --no-cache git

# Set the working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml LICENSE README.md ./

# Copy application code
COPY dicom_event_broker_adapter/ ./dicom_event_broker_adapter/

# Install dependencies
RUN uv pip install --system .

# Create a directory for the ApplicationEntities.json file
RUN mkdir -p /app/config

# Create a non-root user to run the application
RUN adduser -D appuser && chown -R appuser:appuser /app
USER appuser

# Expose the DIMSE port
EXPOSE 11119

# Set environment variables
ENV PYTHONPATH="/app:$PYTHONPATH"

# Run the application with default settings
ENTRYPOINT ["dicom_event_broker_adapter"]
CMD ["--broker-address", "host.docker.internal", "--broker-port", "1883", "--server-listening-port", "11119"]
