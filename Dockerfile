# PayloadStash Dockerfile
# Builds a minimal Python image with the PayloadStash CLI installed.

FROM python:3.11-slim AS runtime

# Prevents Python from writing .pyc files and enables consistent stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Work directory inside the container
WORKDIR /app

# System packages required at build/runtime (git not required). Add curl for debugging if needed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency files first to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

# Copy the rest of the project and install the package
COPY . .
RUN pip install .

# Create default bind-mount target dirs (will be overridden by volumes in compose)
RUN mkdir -p /app/config /app/output

# Default workdir is /app; entrypoint is the CLI
ENTRYPOINT ["payloadstash"]
CMD ["--help"]
