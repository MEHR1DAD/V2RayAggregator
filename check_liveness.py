import os
import asyncio
import subprocess
import yaml
import time
import argparse

from utils import extract_ip_from_connection

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
INPUT_DIR = config['paths']['protocol_configs_dir']
CONNECTION_TIMEOUT = config['settings']['check_liveness']['connection_timeout']
LIVENESS_CHUNK_SIZE = config['settings']['check_liveness']['chunk_size']
TASK_TIMEOUT = 15
START_TIME = time.time()
# UPDATED: Set timeout to 170 minutes for the 3-hour cycle
WORKFLOW_TIMEOUT_SECONDS = 170 * 60

def is_approaching_timeout():
    """Checks if the script is approaching the GitHub Actions timeout."""
    return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS

async def check_port_open_curl(host, port):
    command = ['curl', '--connect-timeout', str(CONNECTION_TIMEOUT), '-v', f'telnet://{host}:{port}']
    process = await asyncio.create_subprocess_exec(
        *command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    await process.wait()
    return process.returncode == 0

async def process_batch(batch_of_targets):
    live_configs_in_batch = []
    tasks = []
    for target in batch_of_targets:
        task = asyncio.wait_for(
            check_port_open_curl(target['host'], target['port']),
            timeout=TASK_TIMEOUT
        )
        tasks.append(task)
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, result in enumerate(results):
        target = batch_of_targets[i]
        if isinstance(result, bool) and result:
            live_configs_in_batch.append(target['config'])
            print(f"✅ Live | {target['config'][:60]}...")
    return live_configs_in_batch

async def main(output_path):
    """
    Main function to run liveness check on all configs found in the protocol_configs directory.
    """
    if not os.path.exists(INPUT_DIR):
        print(f"Input directory '{INPUT_DIR}' not found. Exiting.")
        open(output_path, 'w').close()
        return

    all_configs = []
    for filename in sorted(os.listdir(INPUT_DIR)):
        if filename.endswith("_configs.txt"):
            file_path = os.path.join(INPUT_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                all_configs.extend(f.read().strip().splitlines())

    if not all_configs:
        print("No configs found to test. Exiting.")
        open(output_path, 'w').close()
        return
        
    print(f"Processing {len(all_configs)} total configs...")
    
    live_configs_this_run = []
    
    for i in range(0, len(all_configs), LIVENESS_CHUNK_SIZE):
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Stopping liveness checks.")
            break
            
        chunk = all_configs[i:i+LIVENESS_CHUNK_SIZE]
        
        valid_targets = []
        for config in chunk:
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

    if live_configs_this_run:
        print(f"\nFound {len(live_configs_this_run)} live candidates. Writing to '{output_path}'.")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(live_configs_this_run))
    else:
        print(f"\nFound no live candidates. Creating empty output file '{output_path}'.")
        open(output_path, 'w').close()

    print("Liveness check process finished successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run liveness check on all configs from the configs directory.")
    # No --input argument needed for this version
    parser.add_argument('--output', required=True, help="Path to the output file to save live candidates.")
    args = parser.parse_args()
    asyncio.run(main(args.output))
