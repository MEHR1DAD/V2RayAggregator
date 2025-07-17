import os
import yaml
from database import get_configs_by_country, get_countries_with_config_counts

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
OUTPUT_DIR = config['paths']['output_dir']
CHUNK_SIZE = config['settings']['create_rotating_sub']['chunk_size']
# --- End of Constants ---

def create_subscription_files():
    """
    Fetches configs from the database and creates final subscription files for
    the full list and the top 100 fastest configs for each discovered country.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("--- Creating Final Subscription Files ---")

    # Get the list of countries dynamically from the database
    countries_from_db = get_countries_with_config_counts()

    if not countries_from_db:
        print("🟡 No countries with configs found in database. Skipping file creation.")
        return

    for country_code, total_count in countries_from_db:
        print(f"\nProcessing country: {country_code}")
        
        all_configs = get_configs_by_country(country_code)
        
        if not all_configs:
            print(f"🟡 No configs found in database for {country_code}. Skipping.")
            continue

        # --- Save the full subscription file ---
        full_sub_filename = f"{country_code.upper()}_sub.txt"
        full_sub_path = os.path.join(OUTPUT_DIR, full_sub_filename)
        with open(full_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_configs))
        print(f"✅ Saved {len(all_configs)} configs to {full_sub_filename}")

        # --- Save the rotating (top 100) subscription file ---
        top_configs = all_configs[:CHUNK_SIZE]
        
        rotating_sub_filename = f"{country_code.upper()}_sub_100.txt"
        rotating_sub_path = os.path.join(OUTPUT_DIR, rotating_sub_filename)
        with open(rotating_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(top_configs))
        print(f"✅ Saved Top {len(top_configs)} fastest configs to {rotating_sub_filename}")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        create_subscription_files()
        print("\nAll subscription files created successfully.")