import os
import glob
from datetime import datetime
import pytz
import jdatetime

# ====================================================================
# تنظیمات اسکریپت
# ====================================================================
SUB_DIR = "subscription"
REPO_NAME = "MEHR1DAD/V2RayAggregator"
ALL_CONFIGS_FILE = "merged_configs.txt"

# لینک دانلود جدید از بخش Releases
ALL_CONFIGS_URL = f"https://github.com/{REPO_NAME}/releases/latest/download/{ALL_CONFIGS_FILE}"

COUNTRY_NAMES = {
    "us": ("ایالات متحده", "🇺🇸"), "ae": ("امارات", "🇦🇪"), "ca": ("کانادا", "🇨🇦"),
    "de": ("آلمان", "🇩🇪"), "fr": ("فرانسه", "🇫🇷"), "gb": ("بریتانیا", "🇬🇧"),
    "ir": ("ایران", "🇮🇷"), "nl": ("هلند", "🇳🇱"), "se": ("سوئد", "🇸🇪"),
    "tr": ("ترکیه", "🇹🇷")
}

# ====================================================================

def count_connections(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return 0

def get_jalali_update_time():
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_tehran = now_utc.astimezone(tehran_tz)
    jalali_date = jdatetime.datetime.fromgregorian(datetime=now_tehran)
    day_name = jalali_date.strftime("%A")
    day = jalali_date.day
    month_name = jalali_date.strftime('%B')
    year = jalali_date.year
    time_str = now_tehran.strftime("%H:%M")
    return f"{day_name} {day} {month_name} {year} - ساعت {time_str}"

def generate_readme():
    country_data = []
    for file_path in glob.glob(os.path.join(SUB_DIR, "*_sub.txt")):
        file_name = os.path.basename(file_path)
        country_code = file_name.replace('_sub.txt', '').lower()
        if country_code in COUNTRY_NAMES:
            full_sub_count = count_connections(file_path)
            sub_100_path = file_path.replace('_sub.txt', '_sub_100.txt')
            sub_100_count = count_connections(sub_100_path)
            country_data.append({
                'code': country_code, 'name': COUNTRY_NAMES[country_code][0],
                'flag': COUNTRY_NAMES[country_code][1], 'full_count': full_sub_count,
                '100_count': sub_100_count,
                'full_link': f"https://raw.githubusercontent.com/{REPO_NAME}/master/subscription/{file_name}",
                '100_link': f"https://raw.githubusercontent.com/{REPO_NAME}/master/subscription/{os.path.basename(sub_100_path)}"
            })

    country_data.sort(key=lambda x: x['name'])
    all_connections_count = count_connections(ALL_CONFIGS_FILE)
    update_time_str = get_jalali_update_time()

    readme_content = f"""
<div dir="rtl" align="center">

# V2RayAggregator | تجمیع‌کننده کانفیگ‌های V2Ray
این پروژه به صورت خودکار کانفیگ‌های فعال V2Ray را از منابع عمومی مختلف جمع‌آوری، تست و دسته‌بندی می‌کند.
**آخرین به‌روزرسانی:** {update_time_str} (به وقت تهران)
[![Update Subscriptions](https://github.com/{REPO_NAME}/actions/workflows/update_all_proxies.yml/badge.svg)](https://github.com/{REPO_NAME}/actions/workflows/update_all_proxies.yml)
---
## 订阅链接 | Subscription Links
برای استفاده، یکی از لینک‌های زیر را کپی کرده و در کلاینت خود (مانند V2RayNG, Nekoray, Hiddify) وارد کنید.
### 综合订阅 | All-in-One Subscription
این لینک شامل **{all_connections_count:,}** کانفیگ از تمام کشورها است.
```
{ALL_CONFIGS_URL}
```
---
### 按国家/地区分类的订阅 | Country-Specific Subscriptions
- **لینک کامل:** شامل تمام کانفیگ‌های موجود برای آن کشور.
- **لینک ۱۰۰تایی:** یک لیست چرخشی شامل ۱۰۰ کانفیگ رندوم که هر ۵ دقیقه به‌روز می‌شود. (**پیشنهاد شده**)
| پرچم | کشور | تعداد کل | لینک کامل | لینک ۱۰۰تایی |
|:---:|:---:|:---:|:---:|:---:|
"""
    for country in country_data:
        readme_content += (
            f"| {country['flag']} | **{country['name']}** | `{country['full_count']:,}` "
            f"| [Full]({country['full_link']}) "
            f"| [100 Configs]({country['100_link']}) |\n"
        )
    readme_content += "</div>"
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ README.md generated successfully.")

if __name__ == "__main__":
    generate_readme()
