from pymongo import MongoClient
import os
from dotenv import load_dotenv

client = None
db = None

load_dotenv()

def init_db(app):
    global client, db
    mongo_uri = os.environ.get('MONGODB_URI')
    db_name = os.environ.get('DB_NAME')
    print(f"Initializing MongoDB connection to {mongo_uri}, database: {db_name}")


    if not mongo_uri:
        print("WARNING: MONGODB_URI not set in env. Using default localhost connection.")
        mongo_uri = "mongodb://localhost:27017/"

    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]

        client.admin.command('ping')
        print(f"👌Connected to MongoDB at {mongo_uri}, using database '{db_name}'")

    except Exception as e:  
        print(f"Error connecting to MongoDB: {e}")
        client = None
        db = None

def get_db():
    """
    Returns the database instance. Call init_db first.
    """
    if db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db

def close_db(e=None):
    """
    Closes the MongoDB connection when the app context ends.
    """
    global client, db
    if client:
        client.close()
        client = None
        db = None

# Functions for the website
def add_router(ip, username, password, device_type):
    """
    Adds a router to the 'routers' collection.
    Returns True if added, False if already exists.
    """
    database = get_db()
    routers_collection = database['routers']

    # Check if router with same IP already exists
    if routers_collection.find_one({"ip": ip}):
        return False  # Already exists

    router_data = {
        "ip": ip,
        "username": username,
        "password": password,
        "device_type": device_type
    }
    routers_collection.insert_one(router_data)
    return True