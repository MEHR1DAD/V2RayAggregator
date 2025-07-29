import os
import re
import json
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

# --- تنظیمات اصلی ---
# لیست اولیه کانال‌ها و گروه‌های عمومی برای شروع
# ربات به صورت خودکار کانال‌های جدیدی که در این کانال‌ها معرفی شوند را پیدا می‌کند
TARGET_ENTITIES = [
    'wbnet',
    # 'کانال_دوم',
    # 'گروه_سوم'
]

# --- نام فایل‌های خروجی و فایل وضعیت ---
DIRECT_CONFIGS_FILE = "telegram_direct_configs.txt"
SOURCE_LINKS_FILE = "telegram_source_links.txt"
STATE_FILE = "telegram_scraper_state.json" # فایل برای ذخیره آخرین پیام خوانده شده

# --- متغیرهای استخراج شده از گیت‌هاب سکرت ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_STRING = os.getenv('TELEGRAM_SESSION')

# --- عبارات منظم (Regex) ---
CONFIG_REGEX = re.compile(r'(vmess|vless|ss|ssr|trojan|hysteria2?)://[^\s"`<]+')
SOURCE_LINK_REGEX = re.compile(r'https?://[^\s"`<]+')
TELEGRAM_CHANNEL_REGEX = re.compile(r't\.me/([a-zA-Z0-9_]+)')

def load_state():
    """فایل وضعیت را برای خواندن آخرین ID پیام‌ها بارگذاری می‌کند"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    """آخرین ID پیام‌های پردازش شده را در فایل وضعیت ذخیره می‌کند"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

async def main():
    if not all([API_ID, API_HASH, SESSION_STRING]):
        print("FATAL ERROR: Telegram API credentials not found in environment variables.")
        return

    print("--- Starting Advanced Telegram Scraper ---")
    
    found_configs = set()
    found_sources = set()
    discovered_channels = set()
    
    state = load_state()

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Successfully logged in as: {me.first_name}")

        for entity_name in TARGET_ENTITIES:
            last_message_id = state.get(entity_name, 0)
            print(f"\nProcessing entity: {entity_name} (since message ID: {last_message_id})")
            
            try:
                entity = await client.get_entity(entity_name)
                
                # خواندن پیام‌های جدیدتر از آخرین پیام ذخیره شده
                async for message in client.iter_messages(entity, min_id=last_message_id):
                    # به‌روزرسانی آخرین ID پیام دیده شده در این اجرا
                    if message.id > last_message_id:
                        last_message_id = message.id

                    # ۱. پردازش متن پیام (کانفیگ مستقیم، لینک، هایپرلینک و کانال جدید)
                    text_to_process = ""
                    if message.text:
                        text_to_process += message.text + "\n"
                    if message.entities:
                        for ent in message.entities:
                            if isinstance(ent, (MessageEntityTextUrl, MessageEntityUrl)):
                                # استخراج URL از هایپرلینک‌ها
                                url = ent.url if isinstance(ent, MessageEntityTextUrl) else message.text[ent.offset:ent.offset+ent.length]
                                text_to_process += url + "\n"
                    
                    found_configs.update(CONFIG_REGEX.findall(text_to_process))
                    found_sources.update(SOURCE_LINK_REGEX.findall(text_to_process))
                    discovered_channels.update(TELEGRAM_CHANNEL_REGEX.findall(text_to_process))

                    # ۲. پردازش فایل‌های ضمیمه شده
                    if message.file and message.file.name and (message.file.name.endswith('.txt') or message.file.name.endswith('.json')):
                        print(f"  -> Found attachment: {message.file.name}. Downloading...")
                        content = await client.download_media(message, file=bytes)
                        file_text = content.decode('utf-8', errors='ignore')
                        found_configs.update(CONFIG_REGEX.findall(file_text))
                        found_sources.update(SOURCE_LINK_REGEX.findall(file_text))
                
                # ذخیره آخرین ID برای اجرای بعدی
                state[entity_name] = last_message_id
                print(f"  -> Finished. Next time will start from message ID: {last_message_id}")

            except Exception as e:
                print(f"  -> Could not process entity '{entity_name}'. Error: {e}")

    # --- ذخیره نتایج ---
    if found_configs:
        with open(DIRECT_CONFIGS_FILE, "a", encoding="utf-8") as f:
            for config in sorted(list(found_configs)):
                f.write(config + "\n")
        print(f"\n✅ Appended {len(found_configs)} direct configs to '{DIRECT_CONFIGS_FILE}'")

    if found_sources:
        with open(SOURCE_LINKS_FILE, "a", encoding="utf-8") as f:
            for source in sorted(list(found_sources)):
                f.write(source + "\n")
        print(f"✅ Appended {len(found_sources)} source links to '{SOURCE_LINKS_FILE}'")
    
    if discovered_channels:
        print("\n🔎 Discovered new potential Telegram channels (please review and add them manually to TARGET_ENTITIES):")
        for channel in discovered_channels:
            print(f"  - {channel}")
    
    save_state(state)
    print("\n--- Advanced Telegram Scraper Finished ---")

if __name__ == "__main__":
    asyncio.run(main())
