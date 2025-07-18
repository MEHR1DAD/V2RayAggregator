import os
import asyncio
import subprocess
import time
import json
import yaml
from utils import extract_ip_from_connection

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
INPUT_DIR = "protocol_configs"
CANDIDATES_OUTPUT_FILE = "candidates.txt"
STATE_FILE = "liveness_state.json"
CONNECTION_TIMEOUT = config['settings']['check_liveness']['connection_timeout']
LIVENESS_CHUNK_SIZE = config['settings']['check_liveness']['chunk_size']
TOTAL_TIMEOUT_SECONDS = 50 * 60  # 50 minutes
START_TIME = time.time()

def is_timeout():
    """Checks if the global script timeout has been reached."""
    return (time.time() - START_TIME) > TOTAL_TIMEOUT_SECONDS

def load_state():
    """Loads the last tested index from the state file."""
    if not os.path.exists(STATE_FILE):
        return {"last_tested_index": 0}
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"last_tested_index": 0}

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
    
    # Create tasks for all targets in the batch
    tasks = [check_port_open_curl(target['host'], target['port']) for target in batch_of_targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        target = batch_of_targets[i]
        # Check if the task completed successfully and returned True
        if isinstance(result, bool) and result:
            live_configs_in_batch.append(target['config'])
            print(f"✅ Live | {target['config'][:60]}...")
        # Optional: uncomment to see failed checks
        # else:
        #     print(f"❌ Dead | {target['config'][:60]}...")
            
    return live_configs_in_batch

async def main():
    """Main function to run the liveness check process."""
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        return

    # 1. Load all configs from files into a single list
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
    print(f"Loaded {total_configs} total configs from '{INPUT_DIR}'.")

    # 2. Load the last tested index
    state = load_state()
    last_index = state.get("last_tested_index", 0)

    # Ensure last_index is within bounds
    if last_index >= total_configs:
        last_index = 0

    print(f"Starting check from index {last_index}. Chunk size: {LIVENESS_CHUNK_SIZE}.")

    # 3. Determine the chunk of configs to test in this run
    start_index = last_index
    end_index = start_index + LIVENESS_CHUNK_SIZE
    
    configs_to_test_chunk = all_configs[start_index:end_index]

    # Handle wrap-around if the end_index goes past the list end
    if end_index > total_configs:
        print("Wrapping around to the beginning of the list.")
        remaining_count = end_index - total_configs
        configs_to_test_chunk.extend(all_configs[:remaining_count])
        next_index = remaining_count
    else:
        next_index = end_index
    
    # Update next_index for the case where it perfectly matches the total
    if next_index == total_configs:
        next_index = 0
        
    print(f"This run will test {len(configs_to_test_chunk)} configs (from index {start_index} to {end_index % total_configs or total_configs}).")

    # 4. Prepare valid targets for the batch
    valid_targets = []
    for config in configs_to_test_chunk:
        host_port_str = extract_ip_from_connection(config)
        if host_port_str and ':' in host_port_str:
            try:
                # rsplit is safer for IPv6 addresses in brackets
                host, port_str = host_port_str.rsplit(':', 1)
                port = int(port_str)
                # Basic validation for host and port
                if host and 1 <= port <= 65535:
                    valid_targets.append({'config': config, 'host': host, 'port': port})
            except (ValueError, IndexError):
                # Handles cases where splitting or int conversion fails
                continue
    
    if not valid_targets:
        print("No valid targets could be extracted from the current chunk.")
        # Still save the state to advance the pointer
        save_state({"last_tested_index": next_index})
        return

    # 5. Process the batch and get live configs
    live_configs = await process_batch(valid_targets)
    
    # 6. Write the live configs to the candidates file
    if live_configs:
        print(f"\nFound {len(live_configs)} live candidates. Writing to '{CANDIDATES_OUTPUT_FILE}'.")
        with open(CANDIDATES_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(live_configs))
    else:
        print(f"\nNo live candidates found in this chunk. Clearing '{CANDIDATES_OUTPUT_FILE}'.")
        # Create an empty file if no live configs are found
        open(CANDIDATES_OUTPUT_FILE, 'w').close()

    # 7. Save the new index for the next run
    save_state({"last_tested_index": next_index})
    print(f"State saved. Next run will start from index {next_index}.")
    print("Liveness check process finished successfully.")

if __name__ == "__main__":
    asyncio.run(main())