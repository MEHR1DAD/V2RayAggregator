import os
import yaml
import random
import math

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
INPUT_DIR = config['paths']['protocol_configs_dir']
OUTPUT_BATCH_DIR = "ci_batches"
NUM_BATCHES = 10 # We'll create 10 parallel workers

def create_batches():
    """
    Reads all configs, shuffles them, and divides them into a fixed
    number of batch files for parallel processing in the CI/CD pipeline.
    """
    print("--- Starting Batch Preparation ---")
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return

    all_configs = []
    for filename in sorted(os.listdir(INPUT_DIR)):
        if filename.endswith("_configs.txt"):
            file_path = os.path.join(INPUT_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                all_configs.extend(f.read().strip().splitlines())

    if not all_configs:
        print("No configs found to create batches. Exiting.")
        return

    print(f"Loaded a total of {len(all_configs)} configs.")
    random.shuffle(all_configs)
    print("Shuffled all configs randomly.")
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

    print(f"\n--- Batch preparation finished successfully. Created {NUM_BATCHES} batches. ---")

if __name__ == "__main__":
    create_batches()
