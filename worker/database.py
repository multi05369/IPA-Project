from pymongo import MongoClient
import os

def set_device_info(device_info):
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("DB_NAME")]
    devices_collection = db.outputs
    devices_collection.insert_one(device_info)
    client.close()


def set_ping_result(ping_doc):
    """
    Insert a ping result document into the 'pings' collection.
    Expected fields include: ip_address, target_ip, command, output, success, time, error (optional)
    """
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("DB_NAME")]
    db.pings.insert_one(ping_doc)
    client.close()