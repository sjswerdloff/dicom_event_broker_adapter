FROM python:3.11-alpine AS builder

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    git \
    curl

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Configure Poetry to not create a virtual environment
ENV PATH="/root/.local/bin:$PATH"
RUN poetry config virtualenvs.create false

# Copy project files
WORKDIR /app
COPY pyproject.toml poetry.lock LICENSE README.md ./

# Copy your application code
COPY dicom_event_broker_adapter/ ./dicom_event_broker_adapter/

# Install dependencies
RUN poetry install --without dev

# Create a slim runtime image
FROM python:3.11-alpine AS runtime

# Copy installed packages and application from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Set the working directory
WORKDIR /app

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
