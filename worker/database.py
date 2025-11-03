from pymongo import MongoClient
import os

def set_device_info(device_info):
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("DB_NAME")]
    devices_collection = db.outputs
    devices_collection.insert_one(device_info)
    client.close()