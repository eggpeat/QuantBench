FROM python:3.13-slim-bookworm@sha256:129f9f5d5729767916d79f0021ba4fe56ff113332b08ef1213ecf529a9da7ebb
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
RUN python -m pip install --no-cache-dir pytest==8.4.2
