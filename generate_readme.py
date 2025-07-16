import os
from datetime import datetime
import pytz
import jdatetime
from urllib.parse import quote
import yaml
import json
# توابع دیتابیس را وارد می‌کنیم
from database import get_configs_by_country

# --- Load Configuration ---
with open("config.yml", "r") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
REPO_OWNER = config['project']['repo_owner']
REPO_NAME = config['project']['repo_name']
ALL_CONFIGS_FILE = config['paths']['merged_configs']
COUNTRIES = config['countries']

BASE_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/master"
ALL_CONFIGS_URL = f"{BASE_URL}/{ALL_CONFIGS_FILE}"
SUBSCRIPTION_URL_BASE = f"{BASE_URL}/subscription"

def get_jalali_update_time():
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_tehran = now_utc.astimezone(tehran_tz)
    web_display = now_tehran.isoformat() # For summary.json
    jalali_date = jdatetime.datetime.fromgregorian(datetime=now_tehran)
    readme_display = f"{jalali_date.strftime('%A %d %B %Y، ساعت %H:%M')}" # For README
    return readme_display, web_display

def generate_files():
    country_data = []
    total_configs_count = 0
    
    print("--- Generating Final Output Files ---")
    print("Fetching data from database...")

    for code, info in COUNTRIES.items():
        configs = get_configs_by_country(code)
        count = len(configs)
        total_configs_count += count
        
        if count > 0:
            country_data.append({
                'code': code.lower(),
                'name': info['name'],
                'flag': info['flag'],
                'count': count,
                'full_link': f"{SUBSCRIPTION_URL_BASE}/{info['sub_file']}",
                'link_100': f"{SUBSCRIPTION_URL_BASE}/{info['sub_file'].replace('_sub.txt', '_sub_100.txt')}"
            })
    
    country_data.sort(key=lambda x: x['count'], reverse=True)
    
    readme_update_time, web_update_time = get_jalali_update_time()

    # --- 1. Generate summary.json for Web UI ---
    summary_data = {
        "last_update": web_update_time,
        "merged_configs_url": ALL_CONFIGS_URL,
        "merged_configs_count": total_configs_count,
        "countries": country_data
    }
    with open("summary.json", "w", encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=4)
    print("✅ summary.json generated successfully.")

    # --- 2. Generate Full README.md ---
    encoded_date = quote(readme_update_time)
    readme_content = f"""
<div dir="rtl" align="center">

# تجمیع‌کننده کانفیگ‌های V2Ray

<p>این پروژه به صورت خودکار کانفیگ‌های فعال V2Ray را از منابع عمومی مختلف جمع‌آوری، تست و دسته‌بندی می‌کند.</p>

</div>

<div align="center">

[![Update-Status](https://img.shields.io/github/actions/workflow/status/{REPO_OWNER}/{REPO_NAME}/update_all_proxies.yml?style=for-the-badge&logo=githubactions&logoColor=white&label=Update%20Status)](https://github.com/{REPO_OWNER}/{REPO_NAME}/actions/workflows/update_all_proxies.yml)
[![Configs-Count](https://img.shields.io/badge/Configs-{total_configs_count:,}-blueviolet?style=for-the-badge&logo=server&logoColor=white)]({ALL_CONFIGS_URL})
[![Last-Update](https://img.shields.io/badge/Last%20Update-{encoded_date}-informational?style=for-the-badge&logo=clock&logoColor=white)](https://github.com/{REPO_OWNER}/{REPO_NAME}/commits/main)

</div>

<div dir="rtl">

---

### 💡 ویژگی‌ها

- **تجمیع خودکار:** جمع‌آوری روزانه کانفیگ از ده‌ها منبع عمومی.
- **تست و فیلتر هوشمند:** تست واقعی کانفیگ‌ها و حذف موارد کند یا از کار افتاده.
- **تفکیک جغرافیایی:** دسته‌بندی کانفیگ‌ها بر اساس کشور برای دسترسی آسان.
- **لینک‌های چرخشی:** ارائه لیست‌های ۱۰۰تایی که **هر ساعت** به‌روز می‌شوند تا همیشه کانفیگ تازه در دسترس باشد.
- **آپدیت مداوم:** کل فرآیند به صورت خودکار و ساعتی توسط GitHub Actions اجرا می‌شود.

---

## 📥 لینک‌های اشتراک (Subscription Links)

<div align="center">

### 🌐 لینک جامع (همه کانفیگ‌ها)
<p dir="rtl">این لینک شامل **{total_configs_count:,}** کانفیگ از تمام کشورها است. (ممکن است برای برخی کلاینت‌ها سنگین باشد)</p>

```
{ALL_CONFIGS_URL}
```

---

### 🌍 لینک‌های تفکیک شده بر اساس کشور
<p dir="rtl">
برای مشاهده لینک‌ها، روی نام هر کشور کلیک کنید.
</p>
</div>
"""

    for country in country_data:
        readme_content += f"""
<details>
<summary>
  <div dir="rtl" align="right">
    <b>{country['flag']} {country['name']}</b> (تعداد کل: {country['count']:,})
  </div>
</summary>

<div dir="rtl">
<br>

<p>
- **لینک کامل:** شامل تمام کانفیگ‌های موجود برای این کشور.<br>
- **لینک ۱۰۰تایی:** یک لیست چرخشی شامل ۱۰۰ کانفیگ رندوم که هر ساعت به‌روز می‌شود. (<b>پیشنهاد شده</b>)
</p>

<p><b>لینک کامل:</b></p>
<div align="center">

```
{country['full_link']}
```
</div>

<p><b>لینک ۱۰۰تایی:</b></p>
<div align="center">

```
{country['link_100']}
```
</div>

</div>
</details>
"""

    readme_content += """
<div dir="rtl">

---

## ✅ نرم‌افزارهای پیشنهادی

<div align="center">

### لیست کلاینت‌های موبایل (Mobile Clients)

| iOS/iPadOS | Android | توضیحات مختصر |
| :---: | :---: | :---: |
| <b>[Hiddify](https://apps.apple.com/us/app/hiddify-next/id6476113229)</b> | <b>[Hiddify](https://play.google.com/store/apps/details?id=app.hiddify.com)</b> | <p dir="rtl">رایگان، چند پلتفرمی و با پشتیبانی از تمام پروتکل‌ها.</p> |
| [V2Box](https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690) | [v2rayNG](https://github.com/2dust/v2rayNG/releases) | <p dir="rtl">کلاینت‌های محبوب و قدرتمند برای هر پلتفرم.</p> |
| [Shadowrocket](https://apps.apple.com/us/app/shadowrocket/id932747118) | [NekoBox](https://github.com/MatsuriDayo/NekoBoxForAndroid/releases) | <p dir="rtl">پشتیبانی از پروتکل‌های متنوع، نیازمند خرید یا تنظیمات پیشرفته.</p> |
| [Streisand](https://apps.apple.com/us/app/streisand/id6450534064) | [Clash For Android](https://github.com/Kr328/ClashForAndroid/releases) | <p dir="rtl">بر پایه Clash با قابلیت‌های مدیریت پروکسی حرفه‌ای.</p> |

<br>

### لیست کلاینت‌های دسکتاپ (Desktop Clients)

| Windows | macOS | Linux | توضیحات مختصر |
| :---: | :---: | :---: | :---: |
| <b>[Hiddify](https://github.com/hiddify/hiddify-next/releases)</b> | <b>[Hiddify](https://github.com/hiddify/hiddify-next/releases)</b> | <b>[Hiddify](https://github.com/hiddify/hiddify-next/releases)</b> | <p dir="rtl">رایگان، چند پلتفرمی و با کاربری آسان. (پیشنهاد اصلی)</p> |
| [Nekoray](https://github.com/MatsuriDayo/nekoray/releases) | [V2Box](https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690) | [Nekoray](https://github.com/MatsuriDayo/nekoray/releases) | <p dir="rtl">ابزارهای قدرتمند با قابلیت‌های پیشرفته برای مدیریت پروکسی.</p> |
| [v2rayN](https://github.com/2dust/v2rayN/releases) | [FoXray](https://github.com/Fndroid/Foxray/releases) | [Clash Verge](https://github.com/zzzgydi/clash-verge/releases) | <p dir="rtl">کلاینت‌های محبوب با جامعه کاربری بزرگ و پشتیبانی گسترده.</p> |

</div>

---

### ⚠️ سلب مسئولیت

- این کانفیگ‌ها به صورت عمومی و خودکار جمع‌آوری شده‌اند و امنیت آن‌ها تضمین نمی‌شود.
- مسئولیت استفاده از این کانفیگ‌ها بر عهده کاربر است.
- این پروژه صرفاً برای اهداف آموزشی و تحقیقاتی ایجاد شده است.

</div>
    """

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ README.md generated successfully.")


if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        generate_files()
