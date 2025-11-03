"""worker/connection.py"""
import os
import subprocess
from dotenv import load_dotenv
from netmiko import ConnectHandler

load_dotenv()


def get_ssh_connection(device):
    return ConnectHandler(**device)


def run_command(connection, command):
    # If TextFSM templates are available, this returns structured data
    return connection.send_command(command, use_textfsm=True)


def connect(ip: str, username: str, password: str, device_type: str):
    device = {
        "device_type": device_type,  # e.g., "cisco_ios"
        "host": ip,
        "username": username,
        "password": password,
        "use_keys": False,
        "allow_agent": False,
        "fast_cli": True,
    }
    return get_ssh_connection(device)
