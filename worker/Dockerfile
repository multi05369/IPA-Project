FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /worker

COPY requirements.txt .
COPY . .

RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get update \
    && apt-get install -y --no-install-recommends ansible sshpass \
    && ansible-galaxy collection install cisco.ios \
    && rm -rf /var/lib/apt/lists/*

CMD ["python", "-u", "worker.py"]