FROM nvcr.io/nvidia/tritonserver-pb24h2:24.08.07-py3-min as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git git-lfs wget libpq-dev rustc cargo cmake pkg-config libssl-dev unzip python3 python3-pip python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Rust and Cargo
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Create Python symlinks
RUN ln -sf /usr/bin/python3 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip

# Install uv globally first
RUN pip install --upgrade pip uv

# Copy ALL requirements needed for final stage venv installation
COPY requirements.txt /tmp/requirements.txt
COPY llm-router/requirements.txt /tmp/llm_router_requirements.txt
# Need AgentIQ pyproject.toml for uv sync later
COPY AgentIQ/pyproject.toml /tmp/agentiq_pyproject.toml

# Set up WORKDIR and copy application code (needed for context in final stage)
WORKDIR /app
COPY AgentIQ/ /app/AgentIQ/
COPY llm-router/ /app/llm-router/
COPY scripts/ /app/scripts/

# Build the router-controller in the builder stage
WORKDIR /app/llm-router/src/router-controller
RUN cargo build --release && find target/release -type f -executable -not -path "*/deps/*" | grep -v "\.d$"

# Prepare the binary for final stage copy *before* cleaning up
RUN mkdir -p /app/llm-router/target/release/ && \
    cp /app/llm-router/src/router-controller/target/release/llm-router-gateway-api /app/llm-router/target/release/router-controller

# Clean up large build artifacts before final stage copy
RUN rm -rf /app/llm-router/src/router-controller/target

# --- Final Stage ---
FROM nvcr.io/nvidia/tritonserver-pb24h2:24.08.07-py3-min

# Add NVIDIA package repositories and GPG key
RUN curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
    && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install uv, git, and NVIDIA container toolkit in final stage
RUN sed -i 's#http://archive.ubuntu.com/ubuntu/#http://us.archive.ubuntu.com/ubuntu/#' /etc/apt/sources.list && \
    sed -i 's#http://security.ubuntu.com/ubuntu/#http://us.archive.ubuntu.com/ubuntu/#' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    python3-pip git nvidia-container-toolkit wget \
    && pip install --no-cache-dir uv \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install NATS Server
ARG NATS_VERSION=2.10.17
RUN wget https://github.com/nats-io/nats-server/releases/download/v${NATS_VERSION}/nats-server-v${NATS_VERSION}-linux-amd64.tar.gz -O nats-server.tar.gz \
    && tar -xzf nats-server.tar.gz \
    && mv nats-server-v${NATS_VERSION}-linux-amd64/nats-server /usr/local/bin/ \
    && rm -rf nats-server.tar.gz nats-server-v${NATS_VERSION}-linux-amd64 \
    && chmod +x /usr/local/bin/nats-server

# Create app user in final stage
RUN useradd -m -u 1000 appuser

# Copy the application code from builder (including the pre-placed binary)
COPY --chown=appuser:appuser --from=builder /app /app

# Copy the requirements files from builder's /tmp into the final image's /app locations
COPY --chown=appuser:appuser --from=builder /tmp/requirements.txt /app/requirements.txt
COPY --chown=appuser:appuser --from=builder /tmp/llm_router_requirements.txt /app/llm-router/requirements.txt
# AgentIQ pyproject.toml was copied with /app from builder

# Set WORKDIR
WORKDIR /app

# Setup Python virtual environment as root first - this fixes permissions issues
RUN cd /app/AgentIQ && \
    if [ ! -d .venv ]; then \
    python3 -m venv .venv; \
    fi && \
    chmod -R 755 .venv && \
    chown -R appuser:appuser .venv

# Switch to appuser for remaining operations
USER appuser
RUN cd /app/AgentIQ && \
    . .venv/bin/activate && \
    # Install base requirements first
    pip install --no-cache-dir -r /app/requirements.txt && \
    # Install LLM Router requirements
    pip install --no-cache-dir -r /app/llm-router/requirements.txt && \
    # Install AgentIQ dependencies from pyproject.toml using uv
    # (Skip direct pip install which requires newer setuptools)
    uv sync --all-groups --all-extras

# Verify Python paths and permissions
RUN ls -la /app/AgentIQ/.venv/bin/python && \
    /app/AgentIQ/.venv/bin/python --version

# Set WORKDIR back to /app
WORKDIR /app

# Set Environment Variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app:/app/llm-router:/app/AgentIQ" \
    PATH="/app/AgentIQ/.venv/bin:/opt/tritonserver/bin:/usr/local/bin:/usr/bin:${PATH}" \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all \
    LD_LIBRARY_PATH="/usr/local/cuda/compat/lib:/usr/local/nvidia/lib:/usr/local/nvidia/lib64:${LD_LIBRARY_PATH}"

# Create a fix for the example.simple.app import error
RUN mkdir -p /app/AgentIQ/examples/simple && \
    echo "# This file provides the entry point for the container startup script\nfrom aiq_simple.register import main\n\nif __name__ == '__main__':\n    main()" > /app/AgentIQ/examples/simple/app.py && \
    chmod +x /app/AgentIQ/examples/simple/app.py

# Expose ports
EXPOSE 8000 8001 8002 8080 4222 9090 8084 8100

# Set Entrypoint
ENTRYPOINT ["/app/scripts/simple_start.sh"] 