from pymongo import MongoClient

# --- 1️⃣ Connection URIs ---
source_uri = "mongodb+srv://dlovej009:Dheeraj2006@cluster0.dnu8vna.mongodb.net/iped_system_v2"
target_uri = "mongodb+srv://study:Dheeraj2006@studies.global.mongocluster.cosmos.azure.com/iped_system_v2"

# --- 2️⃣ Connect to both databases ---
source_client = MongoClient(source_uri)
target_client = MongoClient(target_uri)

source_db = source_client.get_default_database()
target_db = target_client.get_default_database()

# --- 3️⃣ Copy all collections ---
for collection_name in source_db.list_collection_names():
    print(f"Transferring collection: {collection_name}")
    
    source_collection = source_db[collection_name]
    target_collection = target_db[collection_name]
    
    # Clear existing data in target (optional)
    target_collection.delete_many({})
    
    # Fetch all documents
    documents = list(source_collection.find())
    
    if documents:
        target_collection.insert_many(documents)
        print(f"  ✅ {len(documents)} documents copied.")
    else:
        print("  ⚠️ No documents found.")

print("\n🎉 Database transfer completed successfully!")

# --- 4️⃣ Close connections ---
source_client.close()
target_client.close()
