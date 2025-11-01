from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import os

client = None
db = None

def init_db(app):
    global client, db
    mongo_uri = app.config.get('MONGO_URI')

    db_name = app.config.get('MONGO_DBNAME', 'ipa_project_db')


    if not mongo_uri:
        print("WARNING: MONGO_URI not set in app config. Using default localhost connection.")
        mongo_uri = 'mongodb://localhost:27017/'
    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]

        client.admin.command('ping')
        print(f"Connected to MongoDB at {mongo_uri}, using database '{db_name}'")

    except Exception as e:  
        print(f"Error connecting to MongoDB: {e}")
        client = None
        db = None

