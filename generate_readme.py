import os
from datetime import datetime
import pytz
import jdatetime
from urllib.parse import quote
import yaml
import json
import pycountry

# --- دیکشنری برای ترجمه‌های فارسی با کیفیت بالا (اختیاری) ---
# هر کشوری که در این لیست نباشد، نام انگلیسی آن به صورت خودکار استفاده خواهد شد
PERSIAN_COUNTRY_NAMES = {
    "US": "ایالات متحده", "FR": "فرانسه", "GB": "بریتانیا", "IR": "ایران",
    "KR": "کره جنوبی", "JP": "ژاپن", "HK": "هنگ کنگ", "DE": "آلمان",
    "NL": "هلند", "CA": "کانادا", "SG": "سنگاپور", "TR": "ترکیه",
    "BR": "برزیل", "LV": "لتونی", "SE": "سوئد", "IN": "هند",
    "AU": "استرالیا", "CH": "سوئیس", "AE": "امارات", "AM": "ارمنستان",
    "AR": "آرژانتین", "BG": "بلغارستان", "CL": "شیلی", "CN": "چین",
    "CZ": "جمهوری چک", "ES": "اسپانیا", "FI": "فنلاند", "IL": "اسرائیل",
    "IT": "ایتالیا", "KZ": "قزاقستان", "LT": "لیتوانی", "MD": "مولداوی",
    "PL": "لهستان", "RU": "روسیه", "TW": "تایوان", "UA": "اوکراین",
    "ZA": "آفریقای جنوبی", "CY": "قبرس", "JO": "اردن", "SI": "اسلوونی",
    "ID": "اندونزی", "LU": "لوکزامبورگ", "AT": "اتریش", "PH": "فیلیپین",
    "IM": "جزیره من", "SC": "سیشل", "EE": "استونی", "NZ": "نیوزلند",
    "SA": "عربستان سعودی", "MY": "مالزی", "PT": "پرتغال", "MX": "مکزیک",
    "MT": "مالت", "HR": "کرواسی", "BA": "بوسنی و هرزگوین", "EC": "اکوادور",
    "TH": "تایلند", "RS": "صربستان", "PY": "پاراگوئه", "PR": "پورتوریکو",
    "PE": "پرو", "NO": "نروژ", "MK": "مقدونیه شمالی", "IS": "ایسلند",
    "GT": "گواتمالا", "GR": "یونان", "CR": "کاستاریکا", "CO": "کلمبیا",
    "BZ": "بلیز", "BH": "بحرین", "RO": "رومانی", "VN": "ویتنام",
    "XX": "مکان نامشخص"
}

def get_country_flag_emoji(country_code):
    """
    Converts a two-letter country code to its corresponding flag emoji.
    """
    if not country_code or len(country_code) != 2:
        return "🏴‍☠️"
    
    country_code = country_code.upper()
    return "".join(chr(ord(c) + 127397) for c in country_code)

def get_country_info(country_code):
    """
    اطلاعات کشور (نام و پرچم) را به صورت خودکار دریافت می‌کند.
    """
    country_code = country_code.upper()
    
    flag = get_country_flag_emoji(country_code)
    
    if country_code in PERSIAN_COUNTRY_NAMES:
        name = PERSIAN_COUNTRY_NAMES[country_code]
    else:
        try:
            country = pycountry.countries.get(alpha_2=country_code)
            name = country.name if country else country_code
        except (AttributeError, KeyError):
            name = country_code

    if country_code == "XX":
        name = "مکان نامشخص"
        flag = "🏴‍☠️"
        
    return {"name": name, "flag": flag}


from database import get_countries_with_config_counts

# --- Load Configuration ---
with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# --- Constants from Config File ---
REPO_OWNER = config['project']['repo_owner']
REPO_NAME = config['project']['repo_name']
ALL_CONFIGS_FILE = config['paths']['merged_configs'] 

BASE_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/raw/refs/heads/master"
ALL_CONFIGS_URL = f"{BASE_URL}/{ALL_CONFIGS_FILE}"
SUBSCRIPTION_URL_BASE = f"{BASE_URL}/subscription"


def get_jalali_update_time():
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_tehran = now_utc.astimezone(tehran_tz)
    web_display = now_tehran.isoformat()
    jalali_date = jdatetime.datetime.fromgregorian(datetime=now_tehran)
    readme_display = f"{jalali_date.strftime('%A %d %B %Y، ساعت %H:%M')}"
    return readme_display, web_display

def generate_files():
    country_data = []
    total_configs_count = 0
    
    print("--- Generating Final Output Files ---")
    print("Fetching data from database...")

    countries_from_db = get_countries_with_config_counts()

    for code, count in countries_from_db:
        info = get_country_info(code)
        
        total_configs_count += count

        country_data.append({
            'code': code.upper(),
            'name': info['name'],
            'flag': info['flag'],
            'count': count,
            'full_link': f"{SUBSCRIPTION_URL_BASE}/{code.upper()}_sub.txt",
            'link_100': f"{SUBSCRIPTION_URL_BASE}/{code.upper()}_sub_100.txt"
        })
    
    country_data.sort(key=lambda x: x['count'], reverse=True)
    
    readme_update_time, web_update_time = get_jalali_update_time()

    # --- Generate summary.json for Web UI ---
    summary_data = {
        "last_update": web_update_time,
        "merged_configs_count": total_configs_count,
        "countries": country_data
    }
    with open("summary.json", "w", encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=4)
    print("✅ summary.json generated successfully.")

    # --- Generate Full README.md ---
    encoded_date = quote(readme_update_time)
    
    badge_markdown = f"[![Main Proxy Pipeline](https://github.com/{REPO_OWNER}/{REPO_NAME}/actions/workflows/main-pipeline.yml/badge.svg)](https://github.com/{REPO_OWNER}/{REPO_NAME}/actions/workflows/main-pipeline.yml)"
    
    readme_content = f"""
<div dir="rtl" align="center">

# تجمیع‌کننده کانفیگ‌های V2Ray

<p>این پروژه به صورت خودکار کانفیگ‌های فعال V2Ray را از منابع عمومی مختلف جمع‌آوری، تست و دسته‌بندی می‌کند.</p>

</div>

<div align="center">

{badge_markdown}
[![Configs-Count](https://img.shields.io/badge/Configs-{total_configs_count:,}-blueviolet?style=for-the-badge&logo=server&logoColor=white)](https://github.com/{REPO_OWNER}/{REPO_NAME})
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
