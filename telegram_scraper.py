import os
import re
import json
import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, Channel, Chat
from telethon.tl.functions.channels import GetForumTopicsRequest

# --- تنظیمات اصلی ---
# نام فایلی که لیست کانال‌ها و گروه‌ها از آن خوانده می‌شود
TARGET_ENTITIES_FILE = "telegram_targets.txt"

# --- نام فایل‌های خروجی و فایل وضعیت ---
DIRECT_CONFIGS_FILE = "telegram_direct_configs.txt"
SOURCE_LINKS_FILE = "telegram_source_links.txt"
STATE_FILE = "telegram_scraper_state.json"

# --- متغیرهای استخراج شده از گیت‌هاب سکرت ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_STRING = os.getenv('TELEGRAM_SESSION')

# --- عبارات منظم (Regex) ---
CONFIG_REGEX = re.compile(r'(vmess|vless|ss|ssr|trojan|hysteria2?)://[^\s"`<]+')
SOURCE_LINK_REGEX = re.compile(r'https?://[^\s"`<]+')
TELEGRAM_CHANNEL_REGEX = re.compile(r't\.me/([a-zA-Z0-9_]+)')

def load_targets(filename):
    """لیست کانال‌ها را از فایل متنی می‌خواند."""
    if not os.path.exists(filename):
        print(f"Warning: Target file '{filename}' not found. No channels to process.")
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        # خطوط خالی و خطوطی که با # شروع می‌شوند (کامنت) نادیده گرفته می‌شوند
        targets = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return targets

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

async def process_messages(messages_iterator):
    """یک مجموعه از پیام‌ها را پردازش کرده و کانفیگ‌ها و لینک‌ها را استخراج می‌کند."""
    found_configs = set()
    found_sources = set()
    discovered_channels = set()
    last_message_id = 0

    async for message in messages_iterator:
        if message.id > last_message_id:
            last_message_id = message.id

        text_to_process = ""
        if message.text:
            text_to_process += message.text + "\n"
        if message.entities:
            for ent in message.entities:
                if isinstance(ent, (MessageEntityTextUrl, MessageEntityUrl)):
                    url = ent.url if isinstance(ent, MessageEntityTextUrl) else message.text[ent.offset:ent.offset+ent.length]
                    text_to_process += url + "\n"
        
        found_configs.update(CONFIG_REGEX.findall(text_to_process))
        found_sources.update(SOURCE_LINK_REGEX.findall(text_to_process))
        discovered_channels.update(TELEGRAM_CHANNEL_REGEX.findall(text_to_process))

        if message.file and message.file.name and (message.file.name.endswith('.txt') or message.file.name.endswith('.json')):
            print(f"  -> Found attachment: {message.file.name}. Downloading...")
            try:
                content = await message.download_media(file=bytes)
                file_text = content.decode('utf-8', errors='ignore')
                found_configs.update(CONFIG_REGEX.findall(file_text))
                found_sources.update(SOURCE_LINK_REGEX.findall(file_text))
            except Exception as e:
                print(f"    -> Could not download or process attachment: {e}")

    return found_configs, found_sources, discovered_channels, last_message_id


async def main():
    if not all([API_ID, API_HASH, SESSION_STRING]):
        print("FATAL ERROR: Telegram API credentials not found in environment variables.")
        return
    
    target_entities = load_targets(TARGET_ENTITIES_FILE)
    if not target_entities:
        return

    print("--- Starting Advanced Telegram Scraper (with Topic Support) ---")
    
    total_found_configs = set()
    total_found_sources = set()
    total_discovered_channels = set()
    
    state = load_state()

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        me = await client.get_me()
        print(f"Successfully logged in as: {me.first_name}")

        for entity_name in target_entities:
            print(f"\nProcessing entity: {entity_name}")
            try:
                entity = await client.get_entity(entity_name)
                
                # بررسی اینکه آیا یک سوپرگروه با تاپیک است یا خیر
                if isinstance(entity, Channel) and entity.megagroup and entity.forum:
                    print(f"  -> This is a Supergroup with Topics. Fetching topics...")
                    topics = await client(GetForumTopicsRequest(channel=entity))
                    
                    for topic in topics.topics:
                        topic_id = topic.id
                        state_key = f"{entity_name}_{topic_id}"
                        last_message_id = state.get(state_key, 0)
                        print(f"    -> Processing Topic: '{topic.title}' (ID: {topic_id}) since message ID: {last_message_id}")
                        
                        messages_iterator = client.iter_messages(entity, reply_to=topic_id, min_id=last_message_id)
                        configs, sources, channels, new_last_id = await process_messages(messages_iterator)
                        
                        total_found_configs.update(configs)
                        total_found_sources.update(sources)
                        total_discovered_channels.update(channels)
                        if new_last_id > last_message_id:
                            state[state_key] = new_last_id

                else: # برای کانال‌ها و گروه‌های عادی
                    state_key = entity_name
                    last_message_id = state.get(state_key, 0)
                    print(f"  -> This is a standard channel/group. Processing since message ID: {last_message_id}")
                    
                    messages_iterator = client.iter_messages(entity, min_id=last_message_id)
                    configs, sources, channels, new_last_id = await process_messages(messages_iterator)
                    
                    total_found_configs.update(configs)
                    total_found_sources.update(sources)
                    total_discovered_channels.update(channels)
                    if new_last_id > last_message_id:
                        state[state_key] = new_last_id

            except Exception as e:
                print(f"  -> Could not process entity '{entity_name}'. Error: {e}")

    # --- ذخیره نتایج ---
    if total_found_configs:
        with open(DIRECT_CONFIGS_FILE, "a", encoding="utf-8") as f:
            for config in sorted(list(total_found_configs)):
                f.write(config + "\n")
        print(f"\n✅ Appended {len(total_found_configs)} new direct configs to '{DIRECT_CONFIGS_FILE}'")

    if total_found_sources:
        with open(SOURCE_LINKS_FILE, "a", encoding="utf-8") as f:
            for source in sorted(list(total_found_sources)):
                f.write(source + "\n")
        print(f"✅ Appended {len(total_found_sources)} new source links to '{SOURCE_LINKS_FILE}'")
    
    if total_discovered_channels:
        print("\n🔎 Discovered new potential Telegram channels (please review and add them manually to the target file):")
        for channel in total_discovered_channels - set(target_entities):
            print(f"  - {channel}")
    
    save_state(state)
    print("\n--- Advanced Telegram Scraper Finished ---")

if __name__ == "__main__":
    asyncio.run(main())
