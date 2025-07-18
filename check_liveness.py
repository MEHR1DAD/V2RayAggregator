import os
import asyncio
import subprocess
import json
import yaml
import random
from utils import extract_ip_from_connection

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
INPUT_DIR = config['paths']['protocol_configs_dir']
CANDIDATES_OUTPUT_FILE = "candidates.txt"
STATE_FILE = "liveness_state.json"
CONNECTION_TIMEOUT = config['settings']['check_liveness']['connection_timeout']
LIVENESS_CHUNK_SIZE = config['settings']['check_liveness']['chunk_size']

def load_state():
    """Loads the state, which includes indices of already tested configs."""
    if not os.path.exists(STATE_FILE):
        return {"tested_indices": []}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"tested_indices": []}

def save_state(state):
    """Saves the current state to the state file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

async def check_port_open_curl(host, port):
    """Asynchronously checks if a TCP port is open using curl's telnet feature."""
    command = ['curl', '--connect-timeout', str(CONNECTION_TIMEOUT), '-v', f'telnet://{host}:{port}']
    process = await asyncio.create_subprocess_exec(
        *command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    await process.wait()
    return process.returncode == 0

async def process_batch(batch_of_targets):
    """Processes a single batch of configs for liveness and returns live configs."""
    live_configs_in_batch = []
    
    tasks = [check_port_open_curl(target['host'], target['port']) for target in batch_of_targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        target = batch_of_targets[i]
        if isinstance(result, bool) and result:
            live_configs_in_batch.append(target['config'])
            print(f"✅ Live | {target['config'][:60]}...")
            
    return live_configs_in_batch

async def main():
    """Main function to run the liveness check process using stateful random sampling."""
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return

    # 1. Load all configs from files
    all_configs = []
    for filename in sorted(os.listdir(INPUT_DIR)):
        if filename.endswith("_configs.txt"):
            file_path = os.path.join(INPUT_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                all_configs.extend(f.read().strip().splitlines())

    if not all_configs:
        print("No configs found to test. Exiting.")
        return
        
    total_configs = len(all_configs)
    print(f"Loaded {total_configs} total configs.")

    # 2. Load state and determine available configs to test
    state = load_state()
    tested_indices = set(state.get("tested_indices", []))
    
    all_indices = set(range(total_configs))
    available_indices = list(all_indices - tested_indices)

    # If all configs have been tested, start a new cycle
    if not available_indices:
        print("All configs have been tested in this cycle. Starting a new cycle.")
        tested_indices = set()
        available_indices = list(all_indices)

    print(f"{len(available_indices)} configs remaining in this cycle. Taking a random sample of up to {LIVENESS_CHUNK_SIZE}.")

    # 3. Take a random sample from the available configs
    sample_size = min(LIVENESS_CHUNK_SIZE, len(available_indices))
    sampled_indices = random.sample(available_indices, sample_size)
    configs_to_test_chunk = [all_configs[i] for i in sampled_indices]

    # 4. Prepare valid targets for the batch
    valid_targets = []
    for config in configs_to_test_chunk:
        host_port_str = extract_ip_from_connection(config)
        if host_port_str and ':' in host_port_str:
            try:
                host, port_str = host_port_str.rsplit(':', 1)
                port = int(port_str)
                if host and 1 <= port <= 65535:
                    valid_targets.append({'config': config, 'host': host, 'port': port})
            except (ValueError, IndexError):
                continue
    
    # 5. Process the batch
    live_configs = []
    if valid_targets:
        live_configs = await process_batch(valid_targets)
    else:
        print("No valid targets could be extracted from the random sample.")

    # 6. Write live configs to the candidates file
    if live_configs:
        print(f"\nFound {len(live_configs)} live candidates. Writing to '{CANDIDATES_OUTPUT_FILE}'.")
        with open(CANDIDATES_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(live_configs))
    else:
        print(f"\nNo live candidates found in this sample. Clearing '{CANDIDATES_OUTPUT_FILE}'.")
        open(CANDIDATES_OUTPUT_FILE, 'w').close()

    # 7. Update and save the state
    newly_tested_indices = tested_indices.union(set(sampled_indices))
    save_state({"tested_indices": list(newly_tested_indices)})
    print(f"State saved. {len(newly_tested_indices)} configs tested in this cycle so far.")
    print("Liveness check process finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())