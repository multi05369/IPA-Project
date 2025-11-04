import re


def parse_show_version_to_json(text: str):
    """
    Parse the output of 'show version' into a structured dict as specified.
    Returns a list with one dict (to match your requested format).
    """
    # Initialize fields
    result = {
        "software_image": "",
        "version": "",
        "release": "",
        "rommon": "",
        "hostname": "",
        "uptime": "",
        "uptime_years": "",
        "uptime_weeks": "",
        "uptime_days": "",
        "uptime_hours": "",
        "uptime_minutes": "",
        "reload_reason": "",
        "running_image": "",
        "hardware": [],
        "serial": [],
        "config_register": "",
        "mac_address": [],
        "restarted": "",
    }
    lines = text.splitlines()
    # Patterns for extraction
    version_re = re.compile(r"Version ([\d.]+)\(([^)]+)\), RELEASE SOFTWARE.*")
    version_alt_re = re.compile(r"Version ([\d.]+), RELEASE SOFTWARE \(([^)]+)\)")
    hostname_re = re.compile(r"^([\w-]+) uptime is (.+)")
    uptime_re = re.compile(
        r"(\d+) years, (\d+) weeks, (\d+) days, (\d+) hours, (\d+) minutes"
    )
    uptime_simple_re = re.compile(r"(\d+) hours, (\d+) minutes")
    image_re = re.compile(r"System image file is \"(.+?)\"")
    hardware_re = re.compile(r"^cisco (\S+).+processor")
    serial_re = re.compile(r"Processor board ID ([\w\d]+)")
    config_reg_re = re.compile(r"Configuration register is (\S+)")
    reload_re = re.compile(r"^Last reload reason: (.+)")
    mac_re = re.compile(r"(?:address is|MAC Address) ([\w.:-]+)", re.IGNORECASE)
    software_image_re = re.compile(r'System image file is ".*?/([\w-]+)"')
    rommon_re = re.compile(r"ROM: (.+)")
    running_image_re = re.compile(r"Running image: (.+)")
    # Extraction loop
    for line in lines:
        if not result["hostname"]:
            m = hostname_re.match(line)
            if m:
                result["hostname"] = m.group(1)
                result["uptime"] = m.group(2)
                # Try to extract uptime details
                m2 = uptime_re.search(result["uptime"])
                if m2:
                    result["uptime_years"] = m2.group(1)
                    result["uptime_weeks"] = m2.group(2)
                    result["uptime_days"] = m2.group(3)
                    result["uptime_hours"] = m2.group(4)
                    result["uptime_minutes"] = m2.group(5)
                else:
                    m2 = uptime_simple_re.search(result["uptime"])
                    if m2:
                        result["uptime_hours"] = m2.group(1)
                        result["uptime_minutes"] = m2.group(2)
        if not result["version"]:
            m = version_re.search(line)
            if m:
                result["version"] = m.group(1)
                result["release"] = m.group(2)
            else:
                m = version_alt_re.search(line)
                if m:
                    result["version"] = m.group(1)
                    result["release"] = m.group(2)
        if not result["software_image"]:
            m = software_image_re.search(line)
            if m:
                result["software_image"] = m.group(1)
        if not result["rommon"]:
            m = rommon_re.search(line)
            if m:
                result["rommon"] = m.group(1)
        if not result["running_image"]:
            m = running_image_re.search(line)
            if m:
                result["running_image"] = m.group(1)
        if not result["reload_reason"]:
            m = reload_re.search(line)
            if m:
                result["reload_reason"] = m.group(1)
        if not result["config_register"]:
            m = config_reg_re.search(line)
            if m:
                result["config_register"] = m.group(1)
        m = hardware_re.search(line)
        if m:
            hw = m.group(1)
            if hw not in result["hardware"]:
                result["hardware"].append(hw)
        m = serial_re.search(line)
        if m:
            sn = m.group(1)
            if sn not in result["serial"]:
                result["serial"].append(sn)
        for mac in mac_re.findall(line):
            if mac not in result["mac_address"]:
                result["mac_address"].append(mac)
    return [result]


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
        if ln.strip().startswith("Interface"):
            start_idx = i
            break
    if start_idx is None:
        # Try to find a line that contains the two first columns
        for i, ln in enumerate(lines):
            if "Interface" in ln and "IP-Address" in ln:
                start_idx = i
                break
    if start_idx is None:
        return text.strip()
    kept = lines[start_idx:]
    # Optionally stop at the next prompt-looking line (e.g., R1# or R1>)
    stop_idx = None
    for i, ln in enumerate(kept):
        t = ln.strip()
        if t.endswith("#") or t.endswith(">"):
            stop_idx = i
            break
    if stop_idx is not None:
        kept = kept[:stop_idx]
    return "\n".join([ln.rstrip() for ln in kept]).strip()


def parse_show_ip_int_brief_to_json(text: str):
    """
    Parse the output of 'show ip interface brief' into a list of dicts.
    Each dict has keys: interface, ip_address, status, proto.
    """
    # First, crop to the table only
    cropped = crop_show_ip_int_brief(text)
    lines = [ln for ln in cropped.splitlines() if ln.strip()]
    if not lines:
        return []
    # Find header line and column positions
    header = lines[0]
    columns = [col.strip().lower().replace("-", "_") for col in header.split()]
    # Map header names to expected keys
    col_map = {
        "interface": "interface",
        "ip_address": "ip_address",
        "ip-address": "ip_address",
        "status": "status",
        "proto": "proto",
        "protocol": "proto",
    }
    # Find the indices for each expected column
    col_indices = []
    for col in columns:
        mapped = col_map.get(col, col)
        col_indices.append(mapped)
    # Parse each row
    result = []
    seen_interfaces = set()
    for row in lines[1:]:
        # Split by whitespace, but keep 'administratively down' together
        parts = row.split()
        # Heuristic: if 'administratively' is present, join with next part
        if "administratively" in parts:
            idx = parts.index("administratively")
            if idx + 1 < len(parts):
                parts[idx] = "administratively down"
                del parts[idx + 1]
        # Only keep rows with at least 4 columns
        if len(parts) >= 4:
            # Skip header row or any row where interface is 'Interface'
            if parts[0].lower() == "interface":
                continue
            # Skip duplicates
            if parts[0] in seen_interfaces:
                continue
            seen_interfaces.add(parts[0])
            entry = {
                "interface": parts[0],
                "ip_address": parts[1],
                "status": parts[-2],
                "proto": parts[-1],
            }
            result.append(entry)
    return result


def normalize_output(command: str, text: str):
    """Normalize raw/parsed command output per command type.
    For 'show ip interface brief', return a list of dicts (JSON-serializable).
    For 'show version', return a list with one dict as specified.
    For others, return trimmed text.
    """
    c = (command or "").lower().strip()
    if "show ip interface brief" in c:
        return parse_show_ip_int_brief_to_json(text)
    if "show version" in c:
        return parse_show_version_to_json(text)
    return (text or "").strip()


def get_playbooks():
    return {
        "show_ip_int_brief": "show_ip_interface_brief.yml",
        "show_running_config": "show_running_config.yml",
        "show_version": "show_version.yml",
    }


def run_ansible_playbook(playbook, inventory, extra_vars=None):
    cmd = [
        "ansible-playbook",
        playbook,
        "-i",
        inventory,
        "-e",
        f"ansible_python_interpreter=/usr/local/bin/python3",
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

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, env=env
        )
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
        first_brace = s.find("{")
        if first_brace != -1:
            try:
                json_text = s[first_brace:]
                parsed = json.loads(json_text)
                # Walk parsed structure to extract stdout_lines where available
                outputs = []

                plays = parsed.get("plays", []) if isinstance(parsed, dict) else []
                for play in plays:
                    tasks = play.get("tasks", [])
                    for task in tasks:
                        for host, result in task.get("hosts", {}).items():
                            # result may contain 'stdout' or 'stdout_lines' or 'msg'
                            if isinstance(result, dict):
                                if "stdout" in result and result["stdout"]:
                                    outputs.append(
                                        _to_text_from_stdout(result["stdout"])
                                    )
                                if "stdout_lines" in result and result["stdout_lines"]:
                                    outputs.append(
                                        _to_text_from_stdout_lines(
                                            result["stdout_lines"]
                                        )
                                    )
                                if "msg" in result and result["msg"]:
                                    outputs.append(str(result["msg"]))
                if outputs:
                    return "\n---\n".join(outputs)
            except Exception:
                # fall back to text parsing below
                pass

        # Fallback: simple line-based scrape for 'ok:' markers and following indented blocks
        lines = s.splitlines()
        output_lines = []
        capture = False
        for line in lines:
            if line.strip().startswith("ok:") or line.strip().startswith("TASK ["):
                capture = True
                output_lines = []
            elif capture:
                if line.strip() == "":
                    break
                output_lines.append(line)
        output = "\n".join(output_lines).strip()
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

        # Execute a sequence of network show commands via their playbooks
        playbooks = get_playbooks()
        commands = [
            ("show ip interface brief", "show_ip_int_brief"),
            ("show running-config", "show_running_config"),
            ("show version", "show_version"),
        ]

        for command_text, key in commands:
            playbook_file = playbooks.get(key)
            if not playbook_file:
                save_command_output(
                    ip,
                    command_text,
                    "",
                    success=False,
                    error=f"Playbook key '{key}' not found",
                )
                continue

            rc, stdout, stderr = run_ansible_playbook(playbook_file, inventory_path)
            if rc == 0:
                parsed = parse_ansible_output(stdout)
                # If parsing produced nothing, prefer the raw stdout or stderr
                if not parsed or parsed.strip() == "":
                    parsed = (stdout or "").strip() or (stderr or "").strip() or ""

                normalized = normalize_output(command_text, parsed)
                save_command_output(ip, command_text, normalized, success=True)
            else:
                err_text = (
                    stderr or stdout or "ansible-playbook returned non-zero exit code"
                )
                save_command_output(ip, command_text, "", success=False, error=err_text)
    except Exception as e:
        save_command_output(
            ip, "show ip interface brief", "", success=False, error=str(e)
        )


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
