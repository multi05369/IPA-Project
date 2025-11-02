FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /worker

COPY requirements.txt .

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-u", "worker.py"]