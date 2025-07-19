import os
import asyncio
import subprocess
import json
import yaml
import random
import time
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
START_TIME = time.time()
# Set a safe exit margin (53 minutes in seconds) before the hard 55-min timeout
WORKFLOW_TIMEOUT_SECONDS = 53 * 60

def is_approaching_timeout():
    """Checks if the script is approaching the GitHub Actions timeout."""
    return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS

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
    """Main function to run the liveness check process using stateful random sampling and a graceful exit."""
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
        print("No configs found to test. Exiting.")
        return
        
    total_configs = len(all_configs)
    print(f"Loaded {total_configs} total configs.")

    state = load_state()
    tested_indices_in_cycle = set(state.get("tested_indices", []))
    
    # This will hold all live configs found *in this specific run*
    live_configs_this_run = []

    while True:
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Saving state and exiting gracefully.")
            break

        all_indices = set(range(total_configs))
        available_indices = list(all_indices - tested_indices_in_cycle)

        if not available_indices:
            print("Cycle complete. All configs tested. Resetting cycle.")
            tested_indices_in_cycle = set()
            available_indices = list(all_indices)

        print(f"\n{len(available_indices)} configs remaining in this cycle. Processing a new batch.")

        sample_size = min(LIVENESS_CHUNK_SIZE, len(available_indices))
        if sample_size == 0:
            break # Should not happen if logic is correct, but as a safeguard.
            
        sampled_indices = random.sample(available_indices, sample_size)
        configs_to_test_chunk = [all_configs[i] for i in sampled_indices]

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
        
        if valid_targets:
            live_in_batch = await process_batch(valid_targets)
            live_configs_this_run.extend(live_in_batch)
        else:
            print("No valid targets could be extracted from the current random sample.")

        tested_indices_in_cycle.update(set(sampled_indices))
        # Save state after every batch to ensure progress is not lost
        save_state({"tested_indices": list(tested_indices_in_cycle)})
        print(f"State saved. {len(tested_indices_in_cycle)} configs tested in this cycle so far.")

    # Write all candidates found in this entire run to the output file
    if live_configs_this_run:
        print(f"\nFound a total of {len(live_configs_this_run)} live candidates in this run. Writing to '{CANDIDATES_OUTPUT_FILE}'.")
        with open(CANDIDATES_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(live_configs_this_run))
    else:
        print(f"\nNo live candidates found in this run. Clearing '{CANDIDATES_OUTPUT_FILE}'.")
        open(CANDIDATES_OUTPUT_FILE, 'w').close()

    print("Liveness check process finished.")

if __name__ == "__main__":
    asyncio.run(main())