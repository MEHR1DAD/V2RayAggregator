import os
import yaml
# تابع get_configs_by_country از قبل کانفیگ‌ها را بر اساس سرعت مرتب می‌کند
from database import get_configs_by_country

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
OUTPUT_DIR = config['paths']['output_dir']
COUNTRIES = config['countries']
CHUNK_SIZE = config['settings']['create_rotating_sub']['chunk_size']
# --- End of Constants ---

def create_subscription_files():
    """
    Fetches configs from the database and creates final subscription files for
    the full list and the top 100 fastest configs.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("--- Creating Final Subscription Files ---")

    for country_code, country_info in COUNTRIES.items():
        print(f"\nProcessing country: {country_code}")
        
        # ۱. خواندن تمام کانفیگ‌های سالم و مرتب‌شده بر اساس سرعت از دیتابیس
        all_configs = get_configs_by_country(country_code)
        
        if not all_configs:
            print(f"🟡 No configs found in database for {country_code}. Skipping.")
            continue

        # ۲. ذخیره فایل اشتراک کامل
        full_sub_filename = country_info['sub_file']
        full_sub_path = os.path.join(OUTPUT_DIR, full_sub_filename)
        with open(full_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(all_configs))
        print(f"✅ Saved {len(all_configs)} configs to {full_sub_filename}")

        # ۳. ساخت و ذخیره فایل ۱۰۰تایی از پرسرعت‌ترین‌ها
        # چون get_configs_by_country از قبل مرتب می‌کند، کافی است ۱۰۰ تای اول را برداریم
        top_100_configs = all_configs[:CHUNK_SIZE]
        
        rotating_sub_filename = full_sub_filename.replace('_sub.txt', '_sub_100.txt')
        rotating_sub_path = os.path.join(OUTPUT_DIR, rotating_sub_filename)
        with open(rotating_sub_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(top_100_configs))
        print(f"✅ Saved Top {len(top_100_configs)} fastest configs to {rotating_sub_filename}")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        create_subscription_files()
        print("\nAll subscription files created successfully.")
