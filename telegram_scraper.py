import os
import re
import json
import asyncio
import time
from datetime import datetime
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, MessageEntityCode, MessageEntityPre, Channel
from telethon.tl.functions.channels import GetForumTopicsRequest
from telethon.errors.rpcerrorlist import FloodWaitError

# --- تنظیمات اصلی ---
TARGET_ENTITIES_FILE = "telegram_targets.txt"
DIRECT_CONFIGS_FILE = "telegram_direct_configs.txt"
SOURCE_LINKS_FILE = "telegram_source_links.txt"
STATE_FILE = "telegram_scraper_state.json"
DELAY_BETWEEN_CHANNELS = 30

# --- متغیرهای استخراج شده از گیت‌هاب سکرت ---
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
SESSION_STRING = os.getenv('TELEGRAM_SESSION')

# --- عبارات منظم (Regex) ---
CONFIG_REGEX = re.compile(r'(vmess|vless|ss|ssr|trojan|hysteria2?)://[^\s"`<]+')
SOURCE_LINK_REGEX = re.compile(r'https?://[^\s"`<]+')
TELEGRAM_CHANNEL_REGEX = re.compile(r't\.me/([a-zA-Z0-9_]{5,})')

# =================================================================
# *** بخش جدید: منطق فیلترینگ هوشمند لینک‌ها ***
# =================================================================
START_TIME = time.time()
# مهلت زمانی برای تست سریع در شاخه develop
WORKFLOW_TIMEOUT_SECONDS = 55 * 60 

# دامنه‌هایی که همیشه اولویت بالایی دارند
GITHUB_DOMAINS = ("raw.githubusercontent.com", "github.io")

# پسوندهایی که حتی در دامنه‌های گیت‌هاب هم باید نادیده گرفته شوند
GITHUB_BAD_EXTENSIONS = (
    ".apk", ".exe", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".dmg", ".pkg", # اضافه شدن پسوندهای مک
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".mp3", ".mp4", ".avi", ".mkv", ".mov"
)

# لیست سیاه دامنه‌هایی که به احتمال زیاد حاوی کانفیگ نیستند
GENERAL_BLACKLIST_DOMAINS = (
    "youtube.com", "youtu.be", "instagram.com", "twitter.com", "x.com",
    "google.com", "facebook.com", "t.me/proxy", "spotify.com",
    "aparat.com", "mediafire.com", "play.google.com", "apps.apple.com",
    "zoomit.ir", "digikala.com", "varzesh3.com", "virustotal.com",
    "snappfood.ir", "torob.com", "myket.ir"
)

def is_valid_source_link(url: str) -> bool:
    """
    یک لینک را بر اساس قوانین هوشمند فیلتر می‌کند.
    """
    try:
        # پاکسازی اولیه لینک از کاراکترهای اضافی در انتها
        url = url.strip(')*[]')

        # قانون ۱: اولویت با فایل‌های .txt
        if url.endswith('.txt'):
            return True

        # قانون ۲: اولویت با دامنه‌های گیت‌هاب (با در نظر گرفتن لیست سیاه پسوندها)
        if any(domain in url for domain in GITHUB_DOMAINS):
            if not any(url.endswith(ext) for ext in GITHUB_BAD_EXTENSIONS):
                return True
            else:
                return False # لینک گیت‌هاب است اما پسوند نامعتبر دارد

        # قانون ۳: اعمال لیست سیاه عمومی
        if any(domain in url for domain in GENERAL_BLACKLIST_DOMAINS):
            return False

        # اگر لینک از هیچ‌کدام از فیلترهای بالا رد نشد، آن را به عنوان یک منبع بالقوه بپذیر
        return True
    except:
        return False

def is_approaching_timeout():
    elapsed_time = time.time() - START_TIME
    return elapsed_time >= WORKFLOW_TIMEOUT_SECONDS
# =================================================================

# ... (بقیه توابع بدون تغییر باقی می‌مانند) ...
def load_targets(filename):
    if not os.path.exists(filename):
        print(f"Warning: Target file '{filename}' not found. No channels to process.")
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        targets = {line.strip() for line in f if line.strip() and not line.startswith('#')}
    return list(targets)

def save_targets(filename, targets):
    with open(filename, 'w', encoding='utf-8') as f:
        for target in sorted(list(set(targets))):
            f.write(target + '\n')

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

async def process_messages(messages_iterator):
    found_configs, found_sources, discovered_channels = set(), set(), set()
    last_message_id = 0

    async for message in messages_iterator:
        if not message: continue
        if message.id > last_message_id:
            last_message_id = message.id

        text_to_process = ""
        if message.text:
            text_to_process += message.text + "\n"
        if message.entities:
            for ent in message.entities:
                if isinstance(ent, (MessageEntityCode, MessageEntityPre)):
                    code_text = message.text[ent.offset : ent.offset + ent.length]
                    text_to_process += code_text + "\n"
                elif isinstance(ent, (MessageEntityTextUrl, MessageEntityUrl)):
                    url = ent.url if isinstance(ent, MessageEntityTextUrl) else message.text[ent.offset:ent.offset+ent.length]
                    text_to_process += url + "\n"
        
        found_configs.update(CONFIG_REGEX.findall(text_to_process))
        
        # *** تغییر: استفاده از فیلتر هوشمند برای لینک‌ها ***
        potential_links = SOURCE_LINK_REGEX.findall(text_to_process)
        for link in potential_links:
            if is_valid_source_link(link):
                found_sources.add(link)

        discovered_channels.update(TELEGRAM_CHANNEL_REGEX.findall(text_to_process))

        if message.file and message.file.name and (message.file.name.endswith('.txt') or message.file.name.endswith('.json')):
            print(f"  -> Found attachment: {message.file.name}. Downloading...")
            try:
                content = await message.download_media(file=bytes)
                file_text = content.decode('utf-8', errors='ignore')
                found_configs.update(CONFIG_REGEX.findall(file_text))
                
                # *** تغییر: استفاده از فیلتر هوشمند برای لینک‌های داخل فایل ***
                potential_links_in_file = SOURCE_LINK_REGEX.findall(file_text)
                for link in potential_links_in_file:
                    if is_valid_source_link(link):
                        found_sources.add(link)

            except Exception as e:
                print(f"   -> Could not download or process attachment: {e}")

    return found_configs, found_sources, discovered_channels, last_message_id

async def main():
    if not all([API_ID, API_HASH, SESSION_STRING]):
        print("FATAL ERROR: Telegram API credentials or session string not found in environment variables.")
        return
        
    target_entities = load_targets(TARGET_ENTITIES_FILE)
    if not target_entities: return

    print("--- Starting Advanced Telegram Scraper (with Smart Filtering) ---")
    
    total_found_configs, total_found_sources, total_discovered_channels = set(), set(), set()
    state = load_state()

    try:
        async with TelegramClient(StringSession(SESSION_STRING), int(API_ID), API_HASH) as client:
            me = await client.get_me()
            print(f"Successfully logged in as: {me.first_name}")

            for i, entity_name in enumerate(target_entities):
                if is_approaching_timeout():
                    print("\n⏰ Approaching workflow timeout. Saving state and exiting gracefully...")
                    break 

                print(f"\nProcessing entity: {entity_name} ({i+1}/{len(target_entities)})")
                try:
                    entity = await client.get_entity(entity_name)
                    
                    if isinstance(entity, Channel) and entity.megagroup and entity.forum:
                        print(f"  -> This is a Supergroup with Topics. Fetching topics...")
                        topics_result = await client(GetForumTopicsRequest(channel=entity, offset_date=datetime.now(), offset_id=0, offset_topic=0, limit=100))
                        
                        for topic in topics_result.topics:
                            topic_id = topic.id
                            state_key = f"{entity.id}_{topic_id}"
                            last_message_id = state.get(state_key, 0)
                            print(f"   -> Processing Topic: '{topic.title}' since message ID: {last_message_id}")
                            
                            messages_iterator = client.iter_messages(entity, reply_to=topic_id, min_id=last_message_id)
                            configs, sources, channels, new_last_id = await process_messages(messages_iterator)
                            
                            total_found_configs.update(configs)
                            total_found_sources.update(sources)
                            total_discovered_channels.update(channels)
                            if new_last_id > last_message_id:
                                state[state_key] = new_last_id
                    else:
                        state_key = str(entity.id)
                        last_message_id = state.get(state_key, 0)
                        print(f"  -> This is a standard channel/group. Processing since message ID: {last_message_id}")
                        
                        messages_iterator = client.iter_messages(entity, min_id=last_message_id)
                        configs, sources, channels, new_last_id = await process_messages(messages_iterator)
                        
                        total_found_configs.update(configs)
                        total_found_sources.update(sources)
                        total_discovered_channels.update(channels)
                        if new_last_id > last_message_id:
                            state[state_key] = new_last_id
                
                except FloodWaitError as e:
                    print(f"  -> FLOOD WAIT: Telegram asked us to wait for {e.seconds} seconds. Waiting...")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"  -> Could not process entity '{entity_name}'. Error: {e}")

                print(f"  -> Checkpoint: Saving progress after processing '{entity_name}'...")
                save_state(state)

                if i < len(target_entities) - 1:
                    print(f"\n--- Waiting for {DELAY_BETWEEN_CHANNELS} seconds before next channel to avoid flood limits ---")
                    await asyncio.sleep(DELAY_BETWEEN_CHANNELS)

    except ValueError as e:
        print(f"FATAL ERROR: The session string is invalid or corrupted. Please regenerate it. Error: {e}")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    
    finally:
        print("\n--- Finalizing process ---")
        if total_found_configs:
            with open(DIRECT_CONFIGS_FILE, "a", encoding="utf-8") as f:
                for config in sorted(list(total_found_configs)): f.write(config + "\n")
            print(f"✅ Appended {len(total_found_configs)} new direct configs to '{DIRECT_CONFIGS_FILE}'")

        if total_found_sources:
            with open(SOURCE_LINKS_FILE, "a", encoding="utf-8") as f:
                for source in sorted(list(total_found_sources)): f.write(source + "\n")
            print(f"✅ Appended {len(total_found_sources)} new source links to '{SOURCE_LINKS_FILE}'")
        
        if total_discovered_channels:
            current_targets = set(load_targets(TARGET_ENTITIES_FILE))
            newly_discovered = set()
            for channel in total_discovered_channels:
                if not channel.lower().endswith('bot') and channel not in current_targets:
                    newly_discovered.add(channel)

            if newly_discovered:
                print(f"\n🔎 Discovered {len(newly_discovered)} new channels. Appending to target file...")
                updated_targets = list(current_targets.union(newly_discovered))
                save_targets(TARGET_ENTITIES_FILE, updated_targets)
                print(f"✅ Successfully updated '{TARGET_ENTITIES_FILE}'.")
        
        save_state(state)
        print("✅ Final state saved.")
        print("\n--- Telegram Scraper Finished ---")

if __name__ == "__main__":
    asyncio.run(main())
