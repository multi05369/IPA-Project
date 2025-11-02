from pymongo import MongoClient
import os

def set_device_info(device_info):
    client = MongoClient(os.getenv("MONGODB_URI", "mongodb://admin:passwd@localhost:27017/ipa_project_db?authSource=admin"))
    db = client[os.getenv("DB_NAME", "ipa_project_db")]
    devices_collection = db.devices
    devices_collection.insert_one(device_info)
    client.close()