"""worker/worker.py"""
import dotenv
import os
import time
import connection as conn
import database as db
from netmiko import NetmikoTimeoutException, NetmikoAuthenticationException

dotenv.load_dotenv()


def main():
    ip = os.getenv("DEVICE_IP", "10.70.38.3")
    username = os.getenv("DEVICE_USERNAME", "admin")
    password = os.getenv("DEVICE_PASSWORD", "cisco")
    device_type = os.getenv("DEVICE_TYPE", "cisco_ios")

    connection = None
    try:
        print(f"Connecting to {ip} as {username} ({device_type})...")
        connection = conn.connect(ip, username, password, device_type)
        print("Connected.")

        # Run commands
        output = conn.run_command(connection, "show version")
        print("show version:")
        print(output)

        # Save to DB
        device_info = {
            "ip": ip,
            "username": username,
            "device_type": device_type,
            "hostname": output[0].get("hostname", "unknown"),
            "firmware": output[0].get("version", "unknown"),
            "uptime": output[0].get("uptime", "unknown"),
        }
        db.set_device_info(device_info)
        print("Device info saved to DB.")


    except NetmikoAuthenticationException as e:
        print(f"Authentication failed: {e}")
    except NetmikoTimeoutException as e:
        print(f"Connection timed out: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if connection:
            connection.disconnect()
            print("Disconnected.")


if __name__ == "__main__":
    main()