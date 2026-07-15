FROM python:3.12-slim-bookworm@sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt pytest==8.4.2
WORKDIR /workspace
