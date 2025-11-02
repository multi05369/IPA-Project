import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()

def get_router_info():
    mongo_uri  = os.environ.get("MONGODB_URI")
    db_name    = os.environ.get("DB_NAME")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    routers = db["devices"]
    print(mongo_uri)
    print(db_name)
    router_data = routers.find()
    return router_data

if __name__=='__main__':
    get_router_info()
