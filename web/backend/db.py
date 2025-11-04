from flask import g
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

def get_db():
    if 'db' not in g:
        mongo_uri = os.getenv('MONGODB_URI')
        db_name = os.getenv('DB_NAME')

        client = MongoClient(mongo_uri)
        g.mongo_client = client
        g.db = client[db_name]
        print(f"✅ Connected to MongoDB at {mongo_uri}, using database '{db_name}'")

    return g.db


def close_db(e=None):
    client = getattr(g, 'mongo_client', None)
    if client is not None:
        client.close()
        print("❌ MongoDB connection closed.")
        g.pop('mongo_client', None)
        g.pop('db', None)


def add_device(ip, username, password, device_type):
    db = get_db()
    devices = db['devices']

    # Prevent duplicates
    if devices.find_one({"ip": ip}):
        return False

    device_data = {
        "ip": ip,
        "username": username,
        "password": password,
        "device_type": device_type,
        "hostname": "",
        "firmware": "",
        "running_config": "",
        "uptime": "",
        "interfaces": [],
        "vrfs": []
    }
    devices.insert_one(device_data)
    return True


def get_all_devices():
    db = get_db()
    devices = db['devices']

    routers = list(devices.find({"device_type": "router"}))
    switches = list(devices.find({"device_type": "switch"}))
    others = list(devices.find({"device_type": {"$nin": ["router", "switch"]}}))

    return {
        "routers": routers,
        "switches": switches,
        "others": others
    }


def get_device_info(ip):
    db = get_db()
    result = db['devices'].find_one({"ip": ip})  # Return all fields
    return result


def get_latest_running_config(ip):
    db = get_db()
    try:
        # Fetch latest output for 'show running-config' from outputs collection
        result = db['outputs'].find_one(
            {"ip_address": ip, "command": "show running-config", "success": True},
            sort=[("time", -1)]
        )
        if result and 'output' in result:
            return result['output']
        return "No configuration found"
    except Exception as e:
        print(f"Error fetching running config: {e}")
        return "Error fetching configuration"


def get_latest_device_details(ip):
    db = get_db()
    # Fetch latest output for 'show version' from outputs collection
    result = db['outputs'].find_one(
        {"ip_address": ip, "command": "show version", "success": True},
        sort=[("time", -1)]
    )
    if result and 'output' in result and isinstance(result['output'], list) and result['output']:
        # Return the first dict in the output list (as per worker format)
        return result['output'][0]
    return {}


def get_latest_interface_status(ip):
    db = get_db()
    # Fetch latest output for 'show ip interface brief' from outputs collection
    result = db['outputs'].find_one(
        {"ip_address": ip, "command": "show ip interface brief", "success": True},
        sort=[("time", -1)]
    )
    if result and 'output' in result and isinstance(result['output'], list):
        # Convert to expected frontend format: list of dicts with keys name, status, ip, vrf, enabled
        interfaces = []
        for iface in result['output']:
            interfaces.append({
                'name': iface.get('interface', ''),
                'status': iface.get('status', ''),
                'ip': iface.get('ip_address', ''),
                'vrf': iface.get('vrf', ''),  # vrf may not exist
                'enabled': iface.get('status', '').lower() == 'up',
            })
        return interfaces
    return []


def get_latest_vrf_details(ip):
    db = get_db()
    result = db['devices'].find_one({"ip": ip}, {"vrfs": 1})
    return result.get("vrfs", []) if result else []

# Add this new function to db.py
def update_interface_statuses(ip, updates):
    """
    Updates the 'enabled' status for multiple interfaces on a single device.
    'updates' should be a list of dicts, e.g.,
    [ {"name": "eth01", "enabled": True}, {"name": "eth03", "enabled": False} ]
    """
    db = get_db()
    devices = db['devices']
    
    try:
        # Loop through each update provided from the frontend
        for update in updates:
            iface_name = update.get('name')
            is_enabled = update.get('enabled')
            
            if not iface_name:
                continue

            # This command finds the document by IP,
            # then finds the element in the 'interfaces' array with the matching name,
            # and sets its 'enabled' field to the new value.
            devices.update_one(
                {"ip": ip, "interfaces.name": iface_name},
                {"$set": {"interfaces.$.enabled": is_enabled}}
            )
        return True
    except Exception as e:
        print(f"Error updating interface statuses in DB: {e}")
        return False
