FROM python:3.12-slim-bookworm@sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "pytest==8.4.2" -r /tmp/requirements.txt
WORKDIR /workspace
