import os
import yaml
from database import (
    get_countries_with_config_counts,
    get_average_speed,
    get_configs_above_speed,
    get_configs_by_country, # We still need this for the fastest configs
    get_live_configs_no_speed
)

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants ---
OUTPUT_DIR = config['paths']['output_dir']
CHUNK_SIZE = config['settings']['create_rotating_sub']['chunk_size'] # This is our "Top N" size, e.g., 100

def create_subscription_files():
    """
    Fetches configs from the database and creates final subscription files
    using the "smart list" generation logic.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("--- Creating Final Subscription Files (Smart Logic) ---")

    countries_from_db = get_countries_with_config_counts()

    if not countries_from_db:
        print("🟡 No countries with configs found in database. Skipping file creation.")
        return

    for country_code, total_count in countries_from_db:
        print(f"\nProcessing country: {country_code} ({total_count} total configs)")
        
        # --- 1. Generate the "Full" subscription list (Better than Average) ---
        avg_speed = get_average_speed(country_code)
        print(f"  -> Average speed for {country_code}: {avg_speed:.2f} KB/s")
        
        better_than_average_configs = get_configs_above_speed(country_code, avg_speed)
        
        if not better_than_average_configs:
            print(f"🟡 No configs found above average speed for {country_code}. Skipping full list.")
        else:
            full_sub_filename = f"{country_code.upper()}_sub.txt"
            full_sub_path = os.path.join(OUTPUT_DIR, full_sub_filename)
            with open(full_sub_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(better_than_average_configs))
            print(f"✅ Saved {len(better_than_average_configs)} 'better than average' configs to {full_sub_filename}")

        # --- 2. Generate the "Top 100" hybrid list ---
        fastest_configs = get_configs_by_country(country_code, limit=CHUNK_SIZE)
        
        hybrid_top_list = fastest_configs
        
        # If the list of fastest configs is less than CHUNK_SIZE, top it up
        if len(hybrid_top_list) < CHUNK_SIZE:
            print(f"  -> Fastest list has {len(hybrid_top_list)} configs. Looking for non-speed-tested configs to fill up.")
            needed = CHUNK_SIZE - len(hybrid_top_list)
            
            # Get live configs for which we couldn't measure speed
            no_speed_configs = get_live_configs_no_speed(country_code)
            
            # Add them to the list until it's full
            hybrid_top_list.extend(no_speed_configs[:needed])

        if not hybrid_top_list:
             print(f"🟡 No configs found for hybrid list for {country_code}. Skipping.")
             continue

        rotating_sub_filename = f"{country_code.upper()}_sub_{CHUNK_SIZE}.txt"
        rotating_sub_path = os.path.join(OUTPUT_DIR, rotating_sub_filename)
        with open(rotating_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(hybrid_top_list))
        print(f"✅ Saved {len(hybrid_top_list)} configs to the hybrid list {rotating_sub_filename}")


if __name__ == "__main__":
    create_subscription_files()
    print("\nAll subscription files created successfully using smart logic.")