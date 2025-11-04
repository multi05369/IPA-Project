import os
import pika
import json
from dotenv import load_dotenv
load_dotenv()

def publish_interface_update_job(ip, updates):
    """
    Publishes an interface update job to RabbitMQ for the worker to process.
    Args:
        ip (str): Device IP address
        updates (list): List of dicts, e.g. [{"name": "GigabitEthernet0/1", "enabled": True}]
    """
    rabbitmq_user = os.getenv("RABBITMQ_USER") or os.getenv("RABBITMQ_DEFAULT_USER")
    rabbitmq_pass = os.getenv("RABBITMQ_PASSWORD") or os.getenv("RABBITMQ_DEFAULT_PASS")
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", 5672))

    credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
    parameters = pika.ConnectionParameters(rabbitmq_host, rabbitmq_port, '/', credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.exchange_declare(exchange="jobs", exchange_type="direct")
    channel.queue_declare(queue="router_jobs")
    channel.queue_bind(queue="router_jobs", exchange="jobs", routing_key="update_interface_state")

    job = {
        "job_type": "update_interface_state",
        "ip": ip,
        "updates": updates
    }
    body = json.dumps(job).encode("utf-8")
    channel.basic_publish(exchange="jobs", routing_key="update_interface_state", body=body)
    connection.close()
