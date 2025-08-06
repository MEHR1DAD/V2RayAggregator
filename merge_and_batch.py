import os
import argparse
from collections import defaultdict

def merge_partial_configs(input_dir, output_dir):
    """
    Merges configuration files from multiple partial directories into a single output directory.

    This script walks through the input directory, finds all protocol-specific config files
    (e.g., vless_configs.txt) from various worker outputs, and merges them into
    single, unified files in the output directory.
    """
    print("--- Starting Config Merge and Batch Process ---")

    if not os.path.exists(input_dir):
        print(f"Warning: Input directory '{input_dir}' not found. No partial configs to merge.")
        return

    # A dictionary to hold all configs, with protocol as key and a set of configs as value
    # Using a set automatically handles duplicates.
    configs_by_protocol = defaultdict(set)

    print(f"Scanning for partial config files in '{input_dir}'...")
    
    # Walk through all subdirectories and files in the input directory
    for root, _, files in os.walk(input_dir):
        for filename in files:
            if filename.endswith("_configs.txt"):
                protocol = filename.replace("_configs.txt", "")
                file_path = os.path.join(root, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        # Read all lines, strip whitespace, and filter out empty lines
                        lines = {line.strip() for line in f if line.strip()}
                        if lines:
                            configs_by_protocol[protocol].update(lines)
                            print(f"  -> Found {len(lines)} configs for protocol '{protocol}' in {filename}")
                except Exception as e:
                    print(f"  -> Error reading file {file_path}: {e}")

    if not configs_by_protocol:
        print("No valid config files were found to merge.")
        # Create the output directory anyway to prevent downstream errors
        os.makedirs(output_dir, exist_ok=True)
        return

    # Ensure the final output directory exists
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nMerging collected configs into '{output_dir}'...")

    total_merged = 0
    # Save the merged configs into their respective final files
    for protocol, configs in sorted(configs_by_protocol.items()):
        output_filename = os.path.join(output_dir, f"{protocol}_configs.txt")
        
        try:
            # Sort the configs for consistent output
            sorted_configs = sorted(list(configs))
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write("\n".join(sorted_configs))
            
            print(f"✅ Saved {len(sorted_configs)} unique configs to {output_filename}")
            total_merged += len(sorted_configs)
        except Exception as e:
            print(f"❌ Error saving file {output_filename}: {e}")

    print(f"\n--- Merge process finished. Total unique configs merged: {total_merged} ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge partial configuration files from worker artifacts into a final directory."
    )
    parser.add_argument(
        '--input-dir',
        required=True,
        help="The root directory containing subdirectories of partial configs from workers."
    )
    parser.add_argument(
        '--output-dir',
        required=True,
        help="The final directory where merged protocol configs will be saved."
    )
    
    args = parser.parse_args()
    
    merge_partial_configs(args.input_dir, args.output_dir)
