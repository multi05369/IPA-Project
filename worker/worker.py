# worker.py
import pika
import json
import dotenv
import os
import time
import connection as conn
import database as db
from netmiko import NetmikoTimeoutException, NetmikoAuthenticationException

dotenv.load_dotenv()


def iso_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def get_commands(device_type: str):
    dt = (device_type or "").lower()
    cmds = {
        "show_version": "show version",
        "show_ip_int_brief": "show ip interface brief",
        "show_running_config": "show running-config",
    }

    return cmds


def normalize_output(out):
    if out is None:
        return ""
    if isinstance(out, str):
        return out
    try:
        return json.dumps(out, ensure_ascii=False, indent=2)
    except Exception:
        return str(out)


def parse_show_version_basic(output):
    hostname = "unknown"
    version = "unknown"
    uptime = "unknown"

    # If TextFSM gave structured data
    if isinstance(output, list) and output and isinstance(output[0], dict):
        o = output[0]
        hostname = o.get("hostname", hostname)
        version = o.get("version", o.get("os_version", version))
        uptime = o.get("uptime", uptime)
        return hostname or "unknown", version or "unknown", uptime or "unknown"

    if isinstance(output, dict):
        hostname = output.get("hostname", hostname)
        version = output.get("version", output.get("os_version", version))
        uptime = output.get("uptime", uptime)
        return hostname or "unknown", version or "unknown", uptime or "unknown"

    # Fallback: plain text regex
    if isinstance(output, str):
        import re

        m = re.search(r"[Hh]ostname\s*[: ]\s*([^\s]+)", output)
        if m:
            hostname = m.group(1)
        m = re.search(r"[Vv]ersion\s+([\w.\(\)-]+)", output)
        if m:
            version = m.group(1)
        m = re.search(r"[Uu]ptime\s+is\s+([^\n]+)", output)
        if m:
            uptime = m.group(1).strip()

    return hostname or "unknown", version or "unknown", uptime or "unknown"


def save_command_output(ip, command, output):
    # Store a simple document per command, like your save_interface_status style
    db.set_device_info(
        {
            "ip_address": ip,
            "command": command,
            "time": iso_utc(),
            "output": output,
        }
    )


def process_job(ip, username, password, device_type):
    net_connect = None
    visited_at = iso_utc()
    try:
        print(f"Connecting to {ip} as {username} ({device_type})...")
        net_connect = conn.connect(ip, username, password, device_type)
        print("Connected.")

        cmds = get_commands(device_type)

        sv = conn.run_command(net_connect, cmds["show_version"])
        sib = conn.run_command(net_connect, cmds["show_ip_int_brief"])
        srun = conn.run_command(net_connect, cmds["show_running_config"])

        print(f"[{ip}] show version:\n{normalize_output(sv)[:2000]}")
        print(f"[{ip}] show ip interface brief:\n{normalize_output(sib)[:2000]}")
        print(f"[{ip}] show running-config:\n{normalize_output(srun)[:2000]}")

        # Save summary doc
        hostname, version, uptime = parse_show_version_basic(sv)
        summary_doc = {
            "ip": ip,
            "username": username,
            "device_type": device_type,
            "hostname": hostname,
            "firmware": version,
            "uptime": uptime,
            "timestamp": visited_at,
        }
        db.set_device_info(summary_doc)
        print(f"[{ip}] Saved device summary")

        # Save raw outputs as separate docs
        save_command_output(ip, cmds["show_version"], normalize_output(sv))
        save_command_output(ip, cmds["show_ip_int_brief"], normalize_output(sib))
        save_command_output(ip, cmds["show_running_config"], normalize_output(srun))
        print(f"[{ip}] Saved raw command outputs")

    except NetmikoAuthenticationException as e:
        print(f"[{ip}] Authentication failed: {e}")
    except NetmikoTimeoutException as e:
        print(f"[{ip}] Connection timed out: {e}")
    except Exception as e:
        print(f"[{ip}] Unexpected error: {e}")
    finally:
        if net_connect:
            try:
                net_connect.disconnect()
            except Exception:
                pass
            print(f"[{ip}] Disconnected")


def main():
    def callback(ch, method, properties, body):
        try:
            data = json.loads(body)
            print("Decoded JSON:", data)
            ip = data.get("ip_address") or data.get("ip")
            username = data.get("username")
            password = data.get("password")
            device_type = "cisco_ios"

            if not ip or not username or not password:
                raise ValueError("ip/username/password missing in message")

            process_job(ip, username, password, device_type)

        except Exception as e:
            print("Failed to process message:", e)

    credentials = pika.PlainCredentials(
        os.getenv("RABBITMQ_USER"), os.getenv("RABBITMQ_PASSWORD")
    )

    # Retry loop like your example
    for _ in range(10):
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=os.getenv("RABBITMQ_HOST", "localhost"),
                    port=int(os.getenv("RABBITMQ_PORT", "5672")),
                    credentials=credentials,
                )
            )
            break
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ not ready, retrying in 5 seconds...")
            time.sleep(5)
    else:
        print("Failed to connect to RabbitMQ after several attempts.")
        exit(1)

    channel = connection.channel()
    queue_name = os.getenv("RABBITMQ_QUEUE", "router_jobs")
    channel.queue_declare(queue=queue_name)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)

    print(f"Waiting for messages on queue '{queue_name}'...")
    channel.start_consuming()


if __name__ == "__main__":
    main()
