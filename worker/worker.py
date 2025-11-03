
import pika
import json
import os
import time
import subprocess
import database as db
from dotenv import load_dotenv

load_dotenv()

def iso_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def _to_text_from_stdout(val):
    """Ansible's ios_command returns stdout as list[str] or str.

    Promoted to top-level to avoid nested function definitions and to enable
    reuse in other parsers.
    """
    if isinstance(val, list):
        return "\n".join(str(x) for x in val)
    return str(val)


def _to_text_from_stdout_lines(val):
    """stdout_lines can be list[str] or list[list[str]].

    Promoted to top-level for clarity and testability.
    """
    if isinstance(val, list):
        flat = []
        for item in val:
            if isinstance(item, list):
                flat.extend(str(x) for x in item)
            else:
                flat.append(str(item))
        return "\n".join(flat)
    return str(val)



def crop_show_ip_int_brief(text: str) -> str:
    """Return only the IOS table starting at the 'Interface' header.

    This trims any Ansible noise and device prompts, keeping exactly the
    section users expect to see from the CLI.
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    # Find first header line that starts with 'Interface'
    start_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('Interface'):
            start_idx = i
            break
    if start_idx is None:
        # Try to find a line that contains the two first columns
        for i, ln in enumerate(lines):
            if 'Interface' in ln and 'IP-Address' in ln:
                start_idx = i
                break
    if start_idx is None:
        return text.strip()
    kept = lines[start_idx:]
    # Optionally stop at the next prompt-looking line (e.g., R1# or R1>)
    stop_idx = None
    for i, ln in enumerate(kept):
        t = ln.strip()
        if t.endswith('#') or t.endswith('>'):
            stop_idx = i
            break
    if stop_idx is not None:
        kept = kept[:stop_idx]
    return "\n".join([ln.rstrip() for ln in kept]).strip()


def normalize_output(command: str, text: str) -> str:
    """Normalize raw/parsed command output per command type."""
    c = (command or '').lower().strip()
    if 'show ip interface brief' in c:
        return crop_show_ip_int_brief(text)
    return (text or '').strip()



def get_playbooks():
    return {
        "show_ip_int_brief": "show_ip_interface_brief.yml",
        "show_running_config": "show_running_config.yml",
        "show_cdp_neighbor": "show_cdp_neighbor.yml",
    }




def run_ansible_playbook(playbook, inventory, extra_vars=None):
    cmd = [
        "ansible-playbook",
        playbook,
        "-i", inventory,
        "-e", f"ansible_python_interpreter=/usr/local/bin/python3"
    ]
    if extra_vars:
        for k, v in extra_vars.items():
            cmd.extend(["-e", f"{k}={v}"])
    # Use higher verbosity to capture connection errors and details
    cmd.extend(["-vvv"])
    try:
        env = os.environ.copy()
        # Make ansible emit JSON so parsing is more reliable
        env.setdefault("ANSIBLE_STDOUT_CALLBACK", "json")
        # Reduce noisy deprecation warnings in output
        env.setdefault("ANSIBLE_DEPRECATION_WARNINGS", "False")
        # Disable host key checking for testing/dev environments (optional)
        env.setdefault("ANSIBLE_HOST_KEY_CHECKING", "False")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)




def parse_ansible_output(ansible_stdout):
    try:
        # Try to parse JSON callback output first
        s = ansible_stdout.strip()
        if not s:
            return ""
        # Find the first JSON object in the output (ansible may prefix with text)
        first_brace = s.find('{')
        if first_brace != -1:
            try:
                json_text = s[first_brace:]
                parsed = json.loads(json_text)
                # Walk parsed structure to extract stdout_lines where available
                outputs = []

                plays = parsed.get('plays', []) if isinstance(parsed, dict) else []
                for play in plays:
                    tasks = play.get('tasks', [])
                    for task in tasks:
                        for host, result in task.get('hosts', {}).items():
                            # result may contain 'stdout' or 'stdout_lines' or 'msg'
                            if isinstance(result, dict):
                                if 'stdout' in result and result['stdout']:
                                    outputs.append(_to_text_from_stdout(result['stdout']))
                                if 'stdout_lines' in result and result['stdout_lines']:
                                    outputs.append(_to_text_from_stdout_lines(result['stdout_lines']))
                                if 'msg' in result and result['msg']:
                                    outputs.append(str(result['msg']))
                if outputs:
                    return '\n---\n'.join(outputs)
            except Exception:
                # fall back to text parsing below
                pass

        # Fallback: simple line-based scrape for 'ok:' markers and following indented blocks
        lines = s.splitlines()
        output_lines = []
        capture = False
        for line in lines:
            if line.strip().startswith('ok:') or line.strip().startswith('TASK ['):
                capture = True
                output_lines = []
            elif capture:
                if line.strip() == '':
                    break
                output_lines.append(line)
        output = '\n'.join(output_lines).strip()
        # If we couldn't extract any structured output, fall back to returning
        # the raw ansible stdout so the caller always has something to store.
        if output:
            return output
        # Final fallback: return the raw stdout (or empty string) so we don't
        # drop command results in the DB.
        return ansible_stdout.strip()
    except Exception:
        return ansible_stdout




def save_command_output(ip, command, output, success=True, error=None):
    db.set_device_info(
        {
            "ip_address": ip,
            "command": command,
            "time": iso_utc(),
            "output": output,
            "success": success,
            "error": error,
        }
    )


def process_job(ip, username, password, device_type="cisco_ios"):
    """
    Minimal job runner for a single network device.
    - Creates a temporary inventory with the provided credentials under group [routers]
    - Runs the 'show ip interface brief' playbook
    - Parses output and stores it in MongoDB via save_command_output

    This is a basic implementation to unblock runtime errors. You can extend it
    to select different playbooks or store results into specific collections.
    """
    try:
        # Build a short-lived inventory for this device under group [routers]
        inventory_path = f"/tmp/inventory_{ip.replace('.', '_')}"
        inventory_content = (
            "[routers]\n"
            f"{ip} ansible_host={ip} ansible_user={username} ansible_password={password} "
            "ansible_network_os=cisco.ios.ios ansible_connection=network_cli\n"
        )
        with open(inventory_path, "w") as f:
            f.write(inventory_content)

        # Choose a default playbook to execute (can be extended later)
        playbooks = get_playbooks()
        playbook = playbooks.get("show_ip_int_brief")

        rc, stdout, stderr = run_ansible_playbook(playbook, inventory_path)
        if rc == 0:
            parsed = parse_ansible_output(stdout)
            # If parsing produced nothing, prefer the raw stdout or stderr so
            # the output field contains the command results rather than an
            # empty string. This ensures the UI / DB always keep the result.
            if not parsed or parsed.strip() == "":
                parsed = (stdout or "").strip() or (stderr or "").strip() or ""

            normalized = normalize_output("show ip interface brief", parsed)
            save_command_output(ip, "show ip interface brief", normalized, success=True)
        else:
            err_text = stderr or stdout or "ansible-playbook returned non-zero exit code"
            save_command_output(ip, "show ip interface brief", "", success=False, error=err_text)
    except Exception as e:
        save_command_output(ip, "show ip interface brief", "", success=False, error=str(e))

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

def main():
    # Support both styles of env vars and prefer the ones used in docker-compose
    rabbit_user = os.getenv("RABBITMQ_DEFAULT_USER") or os.getenv("RABBITMQ_USER")
    rabbit_pass = os.getenv("RABBITMQ_DEFAULT_PASS") or os.getenv("RABBITMQ_PASSWORD")
    credentials = pika.PlainCredentials(rabbit_user, rabbit_pass)

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

