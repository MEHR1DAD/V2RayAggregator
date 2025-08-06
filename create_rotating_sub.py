import os
import yaml
import random
# *** تابع جدید را وارد می‌کنیم ***
from database import get_configs_by_country, get_countries_with_config_counts, get_all_db_configs, get_top_configs

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
    - Top 100: The 100 fastest configs regardless of country.
    - Full list: All live configs for a country.
    - Sized list: A random sample of live configs.
    - Merged list: All live configs from all countries.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("--- Creating Final Subscription Files ---")

    # --- ۱. ایجاد فایل ۱۰۰ کانفیگ برتر (پیشنهاد شما) ---
    print("\nGenerating Top 100 subscription file...")
    TOP_100_FILE = os.path.join(OUTPUT_DIR, 'TOP100_sub.txt')
    top_100_configs = get_top_configs(100)
    if top_100_configs:
        with open(TOP_100_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(top_100_configs))
        print(f"✅ Saved {len(top_100_configs)} fastest configs to {TOP_100_FILE}")
    else:
        print("🟡 No configs found in database to create a Top 100 list.")

    # --- ۲. ایجاد فایل کلی شامل تمام کانفیگ‌ها ---
    all_configs_from_db = get_all_db_configs()
    if all_configs_from_db:
        all_configs_from_db.sort()
        with open(ALL_CONFIGS_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_configs_from_db))
        print(f"✅ Saved {len(all_configs_from_db)} total configs to {ALL_CONFIGS_FILE}")
    else:
        open(ALL_CONFIGS_FILE, 'w').close()
        print("🟡 No configs found in database. Created an empty merged file.")


    # --- ۳. ایجاد فایل‌های اشتراک برای هر کشور ---
    countries_from_db = get_countries_with_config_counts()

    if not countries_from_db:
        print("🟡 No countries with configs found in database. Skipping per-country file creation.")
        return

    for country_code, total_count in countries_from_db:
        print(f"\nProcessing country: {country_code}")
        
        all_configs = get_configs_by_country(country_code)
        
        if not all_configs:
            continue

        # --- ذخیره فایل اشتراک کامل ---
        full_sub_filename = f"{country_code.upper()}_sub.txt"
        full_sub_path = os.path.join(OUTPUT_DIR, full_sub_filename)
        all_configs.sort()
        with open(full_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_configs))
        print(f"✅ Saved {len(all_configs)} live configs to {full_sub_filename}")

        # --- ذخیره فایل اشتراک نمونه تصادفی ---
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
