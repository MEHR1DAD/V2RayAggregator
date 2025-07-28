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
CONNECTION_TIMEOUT = config['settings']['check_liveness']['connection_timeout']
LIVENESS_CHUNK_SIZE = config['settings']['check_liveness']['chunk_size']
TASK_TIMEOUT = 15
START_TIME = time.time()
WORKFLOW_TIMEOUT_SECONDS = config['settings']['global_timeout_minutes'] * 60

def is_approaching_timeout():
    """Checks if the script is approaching the GitHub Actions timeout."""
    return (time.time() - START_TIME) >= WORKFLOW_TIMEOUT_SECONDS

async def check_port_open_curl(host, port):
    """
    Checks if a TCP port is open on a host using curl's telnet feature.
    """
    command = ['curl', '--connect-timeout', str(CONNECTION_TIMEOUT), '-v', f'telnet://{host}:{port}']
    process = await asyncio.create_subprocess_exec(
        *command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    await process.wait()
    return process.returncode == 0

async def process_batch(batch_of_targets):
    """Processes a batch of targets concurrently to check for liveness."""
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
            print(f"✅ Live (TCP Check) | {target['config'][:60]}...")
            
    return live_configs_in_batch

async def main(input_path, output_path):
    """Main function to read configs, check liveness, and write live ones to output."""
    if not os.path.exists(input_path):
        print(f"Input file '{input_path}' not found. Creating empty output.")
        open(output_path, 'w').close()
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        configs_to_test = f.read().strip().splitlines()
        
    if not configs_to_test:
        print("No configs to test. Creating empty output.")
        open(output_path, 'w').close()
        return

    print(f"Worker processing {len(configs_to_test)} configs from '{input_path}'.")
    
    live_configs_this_run = []
    
    for i in range(0, len(configs_to_test), LIVENESS_CHUNK_SIZE):
        if is_approaching_timeout():
            print("⏰ Approaching workflow timeout. Stopping liveness checks for this worker.")
            break
            
        chunk = configs_to_test[i:i+LIVENESS_CHUNK_SIZE]
        tcp_targets = []
        
        for config in chunk:
            # --- START OF HYSTERIA2 FIX ---
            # Automatically consider hysteria2 configs as "live" for the next stage
            if config.strip().startswith("hysteria2://"):
                live_configs_this_run.append(config)
                print(f"✅ Live (UDP Bypass) | {config[:60]}...")
                continue
            # --- END OF HYSTERIA2 FIX ---

            host_port_str = extract_ip_from_connection(config)
            if host_port_str and ':' in host_port_str:
                try:
                    host, port_str = host_port_str.rsplit(':', 1)
                    port = int(port_str)
                    if host and 1 <= port <= 65535:
                        tcp_targets.append({'config': config, 'host': host, 'port': port})
                except (ValueError, IndexError):
                    continue
                    
        if tcp_targets:
            live_in_batch = await process_batch(tcp_targets)
            live_configs_this_run.extend(live_in_batch)

    if live_configs_this_run:
        print(f"\nWorker found {len(live_configs_this_run)} live candidates. Writing to '{output_path}'.")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(live_configs_this_run))
    else:
        print(f"\nWorker found no live candidates. Creating empty output file '{output_path}'.")
        open(output_path, 'w').close()
        
    print("Liveness check worker finished successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run liveness check on a specific batch of configs.")
    parser.add_argument('--input', required=True, help="Path to the input file containing configs.")
    parser.add_argument('--output', required=True, help="Path to the output file to write live configs.")
    args = parser.parse_args()
    asyncio.run(main(args.input, args.output))
