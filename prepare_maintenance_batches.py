import os
import sqlite3
import math

DB_FILE = "aggregator_data.db"
OUTPUT_BATCH_DIR = "ci_batches"
NUM_BATCHES = 20

def create_maintenance_batches():
    """
    Reads all existing configs from the main database, shuffles them,
    and divides them into batches for parallel re-testing.
    """
    print("--- Starting Maintenance Batch Preparation ---")
    if not os.path.exists(DB_FILE):
        print(f"Main database '{DB_FILE}' not found. Exiting.")
        return

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT config FROM configs")
        all_configs = [row[0] for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        print(f"Error reading from database: {e}")
        return

    if not all_configs:
        print("No configs found in the database to create batches. Exiting.")
        return

    print(f"Loaded a total of {len(all_configs)} configs for re-testing.")
    
    os.makedirs(OUTPUT_BATCH_DIR, exist_ok=True)

    batch_size = math.ceil(len(all_configs) / NUM_BATCHES)
    
    for i in range(NUM_BATCHES):
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch_configs = all_configs[start_index:end_index]
        
        if not batch_configs:
            continue

        batch_filename = os.path.join(OUTPUT_BATCH_DIR, f"batch_{i}.txt")
        with open(batch_filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(batch_configs))
        
        print(f"✅ Created {batch_filename} with {len(batch_configs)} configs.")

    print(f"\n--- Maintenance batch preparation finished. Created {NUM_BATCHES} batches. ---")

if __name__ == "__main__":
    create_maintenance_batches()
