import os
import re
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl

# --- تنظیمات اصلی ---
# لطفاً لیست کانال‌های عمومی مورد نظر خود را در اینجا وارد کنید
# مثال: ['durov', 'telegram']
TARGET_CHANNELS = [
    'wbnet' 
]

# --- نام فایل‌های خروجی ---
DIRECT_CONFIGS_FILE = "telegram_direct_configs.txt"
SOURCE_LINKS_FILE = "telegram_source_links.txt"

# --- متغیرهای استخراج شده از گیت‌هاب سکرت ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_STRING = os.getenv('TELEGRAM_SESSION')

# --- عبارات منظم برای پیدا کردن کانفیگ و لینک ---
CONFIG_REGEX = re.compile(r'(vmess|vless|ss|ssr|trojan|hysteria2?)://[^\s"`<]+')
SOURCE_LINK_REGEX = re.compile(r'https?://[^\s"`<]+')

async def main():
    if not all([API_ID, API_HASH, SESSION_STRING]):
        print("FATAL ERROR: Telegram API credentials not found in environment variables.")
        return

    print("--- Starting Telegram Scraper ---")
    
    found_configs = set()
    found_sources = set()

    # اتصال به تلگرام با استفاده از session string
    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Successfully logged in as: {me.first_name}")

        for channel in TARGET_CHANNELS:
            print(f"\nProcessing channel: @{channel}")
            try:
                # خواندن ۱۰۰ پیام آخر کانال
                async for message in client.iter_messages(channel, limit=100):
                    # ۱. پیدا کردن کانفیگ‌های مستقیم در متن پیام
                    if message.text:
                        for match in CONFIG_REGEX.finditer(message.text):
                            found_configs.add(match.group(0))

                    # ۲. پیدا کردن لینک‌های هایپرلینک شده
                    if message.entities:
                        for entity in message.entities:
                            if isinstance(entity, MessageEntityTextUrl):
                                found_sources.add(entity.url)
                
                print(f"  -> Found {len(found_configs)} unique direct configs so far.")
                print(f"  -> Found {len(found_sources)} unique source links so far.")

            except Exception as e:
                print(f"  -> Could not process channel @{channel}. Error: {e}")

    # ذخیره کانفیگ‌های مستقیم
    if found_configs:
        with open(DIRECT_CONFIGS_FILE, "w", encoding="utf-8") as f:
            for config in sorted(list(found_configs)):
                f.write(config + "\n")
        print(f"\n✅ Saved {len(found_configs)} direct configs to '{DIRECT_CONFIGS_FILE}'")

    # ذخیره لینک‌های منابع
    if found_sources:
        with open(SOURCE_LINKS_FILE, "w", encoding="utf-8") as f:
            for source in sorted(list(found_sources)):
                f.write(source + "\n")
        print(f"✅ Saved {len(found_sources)} source links to '{SOURCE_LINKS_FILE}'")
        
    print("\n--- Telegram Scraper Finished ---")


if __name__ == "__main__":
    asyncio.run(main())
