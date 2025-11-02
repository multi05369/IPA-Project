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
    result = db['devices'].find_one({"ip": ip}, {"device_type": 1, "hostname": 1})
    print(f"Device info result: {result}")  # Debug print
    return result


def get_latest_running_config(ip):
    db = get_db()
    try:
        result = db['running_configs'].find_one(
            {"ip": ip},
            {"config": 1}
        )
        if result and 'config' in result:
            return result['config']
        return "No configuration found"
    except Exception as e:
        print(f"Error fetching running config: {e}")
        return "Error fetching configuration"


def get_latest_device_details(ip):
    db = get_db()
    result = db['device_details'].find_one({"ip": ip}, {"firmware": 1, "uptime": 1, "device_type": 1, "mac": 1, "model": 1, "firmware": 1})
    return result if result else {}


def get_latest_interface_status(ip):
    db = get_db()
    result = db['interface_status'].find_one({"ip_parent": ip}, {"interfaces": 1})
    return result.get("interfaces", []) if result else []


def get_latest_vrf_details(ip):
    db = get_db()
    result = db['devices'].find_one({"ip": ip}, {"vrfs": 1})
    return result.get("vrfs", []) if result else []
