import os
import yaml
import random
from database import get_configs_by_country, get_countries_with_config_counts, get_all_db_configs

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
OUTPUT_DIR = config['paths']['output_dir']
CHUNK_SIZE = config['settings']['create_rotating_sub']['chunk_size']
ALL_CONFIGS_FILE = config['paths']['merged_configs']

def create_subscription_files():
    """
    Creates final subscription files.
    - Full list: All live configs for a country.
    - Sized list: A random sample of live configs.
    - Merged list: All live configs from all countries.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("--- Creating Final Subscription Files ---")

    # --- 1. Generate merged file for all configs ---
    all_configs_from_db = get_all_db_configs()
    if all_configs_from_db:
        # Sort configs for consistent output
        all_configs_from_db.sort()
        with open(ALL_CONFIGS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_configs_from_db))
        print(f"✅ Saved {len(all_configs_from_db)} total configs to {ALL_CONFIGS_FILE}")
    else:
        # Create an empty file if no configs are found
        open(ALL_CONFIGS_FILE, 'w').close()
        print("🟡 No configs found in database. Created an empty merged file.")


    # --- 2. Generate per-country subscription files ---
    countries_from_db = get_countries_with_config_counts()

    if not countries_from_db:
        print("🟡 No countries with configs found in database. Skipping per-country file creation.")
        return

    for country_code, total_count in countries_from_db:
        print(f"\nProcessing country: {country_code}")
        
        all_configs = get_configs_by_country(country_code)
        
        if not all_configs:
            continue

        # --- Save the full subscription file ---
        full_sub_filename = f"{country_code.upper()}_sub.txt"
        full_sub_path = os.path.join(OUTPUT_DIR, full_sub_filename)
        # Sort for consistent output
        all_configs.sort()
        with open(full_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_configs))
        print(f"✅ Saved {len(all_configs)} live configs to {full_sub_filename}")

        # --- Save the random sample subscription file ---
        random.shuffle(all_configs)
        sample_configs = all_configs[:CHUNK_SIZE]
        
        rotating_sub_filename = f"{country_code.upper()}_sub_{CHUNK_SIZE}.txt"
        rotating_sub_path = os.path.join(OUTPUT_DIR, rotating_sub_filename)
        with open(rotating_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(sample_configs))
        print(f"✅ Saved a random sample of {len(sample_configs)} configs to {rotating_sub_filename}")

if __name__ == "__main__":
    create_subscription_files()
    print("\nAll subscription files created successfully.")
