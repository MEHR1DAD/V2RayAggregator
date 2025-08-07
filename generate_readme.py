import os
from datetime import datetime
import pytz
import jdatetime
from urllib.parse import quote
import yaml
import json
import pycountry
import sqlite3

# --- دیکشنری کامل برای ترجمه‌های فارسی ---
PERSIAN_COUNTRY_NAMES = {
    "AF": "افغانستان", "AX": "جزایر آلند", "AL": "آلبانی", "DZ": "الجزایر",
    "AS": "ساموآی آمریکا", "AD": "آندورا", "AO": "آنگولا", "AI": "آنگویلا",
    "AQ": "جنوبگان", "AG": "آنتیگوآ و باربودا", "AR": "آرژانتین", "AM": "ارمنستان",
    "AW": "آروبا", "AU": "استرالیا", "AT": "اتریش", "AZ": "آذربایجان",
    "BS": "باهاما", "BH": "بحرین", "BD": "بنگلادش", "BB": "باربادوس",
    "BY": "بلاروس", "BE": "بلژیک", "BZ": "بلیز", "BJ": "بنین",
    "BM": "برمودا", "BT": "بوتان", "BO": "بولیوی", "BQ": "جزایر کارائیب هلند",
    "BA": "بوسنی و هرزگوین", "BW": "بوتسوانا", "BV": "جزیره بووه", "BR": "برزیل",
    "IO": "قلمرو اقیانوس هند بریتانیا", "BN": "برونئی", "BG": "بلغارستان", "BF": "بورکینافاسو",
    "BI": "بوروندی", "CV": "کیپ ورد", "KH": "کامبوج", "CM": "کامرون",
    "CA": "کانادا", "KY": "جزایر کیمن", "CF": "جمهوری آفریقای مرکزی", "TD": "چاد",
    "CL": "شیلی", "CN": "چین", "CX": "جزیره کریسمس", "CC": "جزایر کوکوس",
    "CO": "کلمبیا", "KM": "کومور", "CG": "جمهوری کنگو", "CD": "جمهوری دموکراتیک کنگو",
    "CK": "جزایر کوک", "CR": "کاستاریکا", "CI": "ساحل عاج", "HR": "کرواسی",
    "CU": "کوبا", "CW": "کوراسائو", "CY": "قبرس", "CZ": "جمهوری چک",
    "DK": "دانمارک", "DJ": "جیبوتی", "DM": "دومینیکا", "DO": "جمهوری دومینیکن",
    "EC": "اکوادور", "EG": "مصر", "SV": "السالوادور", "GQ": "گینه استوایی",
    "ER": "اریتره", "EE": "استونی", "SZ": "اسواتینی", "ET": "اتیوپی",
    "FK": "جزایر فالکلند", "FO": "جزایر فارو", "FJ": "فیجی", "FI": "فنلاند",
    "FR": "فرانسه", "GF": "گویان فرانسه", "PF": "پلی‌نزی فرانسه", "TF": "سرزمین‌های جنوبی و جنوبگانی فرانسه",
    "GA": "گابن", "GM": "گامبیا", "GE": "گرجستان", "DE": "آلمان",
    "GH": "غنا", "GI": "جبل‌الطارق", "GR": "یونان", "GL": "گرینلند",
    "GD": "گرنادا", "GP": "گوادلوپ", "GU": "گوام", "GT": "گواتمالا",
    "GG": "گرنزی", "GN": "گینه", "GW": "گینه بیسائو", "GY": "گویان",
    "HT": "هائیتی", "HM": "جزیره هرد و جزایر مک‌دونالد", "VA": "واتیکان", "HN": "هندوراس",
    "HK": "هنگ کنگ", "HU": "مجارستان", "IS": "ایسلند", "IN": "هند",
    "ID": "اندونزی", "IR": "ایران", "IQ": "عراق", "IE": "ایرلند",
    "IM": "جزیره من", "IL": "اسرائیل", "IT": "ایتالیا", "JM": "جامائیکا",
    "JP": "ژاپن", "JE": "جرزی", "JO": "اردن", "KZ": "قزاقستان",
    "KE": "کنیا", "KI": "کیریباتی", "KP": "کره شمالی", "KR": "کره جنوبی",
    "KW": "کویت", "KG": "قرقیزستان", "LA": "لائوس", "LV": "لتونی",
    "LB": "لبنان", "LS": "لسوتو", "LR": "لیبریا", "LY": "لیبی",
    "LI": "لیختن‌اشتاین", "LT": "لیتوانی", "LU": "لوکزامبورگ", "MO": "ماکائو",
    "MG": "ماداگاسکار", "MW": "مالاوی", "MY": "مالزی", "MV": "مالدیو",
    "ML": "مالی", "MT": "مالت", "MH": "جزایر مارشال", "MQ": "مارتینیک",
    "MR": "موریتانی", "MU": "موریس", "YT": "مایوت", "MX": "مکزیک",
    "FM": "ایالات فدرال میکرونزی", "MD": "مولداوی", "MC": "موناکو", "MN": "مغولستان",
    "ME": "مونته‌نگرو", "MS": "مونتسرات", "MA": "مراکش", "MZ": "موزامبیک",
    "MM": "میانمار", "NA": "نامیبیا", "NR": "نائورو", "NP": "نپال",
    "NL": "هلند", "NC": "کالدونیای جدید", "NZ": "نیوزلند", "NI": "نیکاراگوئه",
    "NE": "نیجر", "NG": "نیجریه", "NU": "نیووی", "NF": "جزیره نورفک",
    "MK": "مقدونیه شمالی", "MP": "جزایر ماریانای شمالی", "NO": "نروژ", "OM": "عمان",
    "PK": "پاکستان", "PW": "پالائو", "PS": "فلسطین", "PA": "پاناما",
    "PG": "پاپوآ گینه نو", "PY": "پاراگوئه", "PE": "پرو", "PH": "فیلیپین",
    "PN": "جزایر پیت‌کرن", "PL": "لهستان", "PT": "پرتغال", "PR": "پورتوریکو",
    "QA": "قطر", "RE": "رئونیون", "RO": "رومانی", "RU": "روسیه",
    "RW": "رواندا", "BL": "سن بارتلمی", "SH": "سنت هلن", "KN": "سنت کیتس و نویس",
    "LC": "سنت لوسیا", "MF": "سنت مارتین", "PM": "سن پیر و میکلن", "VC": "سنت وینسنت و گرنادین‌ها",
    "WS": "ساموآ", "SM": "سن مارینو", "ST": "سائوتومه و پرنسیپ", "SA": "عربستان سعودی",
    "SN": "سنگال", "RS": "صربستان", "SC": "سیشل", "SL": "سیرالئون",
    "SG": "سنگاپور", "SX": "سینت مارتن", "SK": "اسلواکی", "SI": "اسلوونی",
    "SB": "جزایر سلیمان", "SO": "سومالی", "ZA": "آفریقای جنوبی", "GS": "جزایر جورجیای جنوبی و ساندویچ جنوبی",
    "SS": "سودان جنوبی", "ES": "اسپانیا", "LK": "سری‌لانکا", "SD": "سودان",
    "SR": "سورینام", "SJ": "اسوالبارد و یان ماین", "SE": "سوئد", "CH": "سوئیس",
    "SY": "سوریه", "TW": "تایوان", "TJ": "تاجیکستان", "TZ": "تانزانیا",
    "TH": "تایلند", "TL": "تیمور شرقی", "TG": "توگو", "TK": "توکلائو",
    "TO": "تونگا", "TT": "ترینیداد و توباگو", "TN": "تونس", "TR": "ترکیه",
    "TM": "ترکمنستان", "TC": "جزایر تورکس و کایکوس", "TV": "تووالو", "UG": "اوگاندا",
    "UA": "اوکراین", "AE": "امارات متحده عربی", "GB": "بریتانیا", "US": "ایالات متحده",
    "UY": "اروگوئه", "UZ": "ازبکستان", "VU": "وانواتو", "VE": "ونزوئلا",
    "VN": "ویتنام", "VG": "جزایر ویرجین بریتانیا", "VI": "جزایر ویرجین ایالات متحده", "WF": "والیس و فوتونا",
    "EH": "صحرای غربی", "YE": "یمن", "ZM": "زامبیا", "ZW": "زیمباوه",
    "XX": "مکان نامشخص"
}

# --- فایل‌های ورودی و خروجی ---
DB_FILE = "aggregator_data.db"
TELEGRAM_TARGETS_FILE = "telegram_targets.txt"
GITHUB_CRAWLED_URLS_FILE = "crawled_urls.txt"
SUMMARY_OUTPUT_FILE = "summary.json"
REPORT_OUTPUT_FILE = "report_data.json"

def get_country_flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "🏴‍☠️"
    country_code = country_code.upper()
    return "".join(chr(ord(c) + 127397) for c in country_code)

def get_country_info(country_code):
    country_code = country_code.upper()
    flag = get_country_flag_emoji(country_code)
    
    name = PERSIAN_COUNTRY_NAMES.get(country_code)
    if not name:
        try:
            country = pycountry.countries.get(alpha_2=country_code)
            name = country.name if country else country_code
        except (AttributeError, KeyError):
            name = country_code

    if country_code == "XX":
        name = "مکان نامشخص"
        flag = "🏴‍☠️"
        
    return {"name": name, "flag": flag}

def get_line_count(filename):
    """تعداد خطوط غیرخالی یک فایل را می‌شمارد."""
    if not os.path.exists(filename):
        return 0
    with open(filename, 'r', encoding='utf-8') as f:
        return len([line for line in f if line.strip()])

def get_db_stats(db_path):
    """آمار را از دیتابیس استخراج می‌کند."""
    if not os.path.exists(db_path):
        return {
            "total_active_configs": 0,
            "configs_by_protocol": {},
            "countries_with_counts": [],
            "top_10_countries": []
        }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM configs")
    total_configs = cursor.fetchone()[0]

    cursor.execute("SELECT config FROM configs")
    all_configs = [row[0] for row in cursor.fetchall()]
    
    configs_by_protocol = {}
    for config in all_configs:
        try:
            protocol = config.split("://")[0]
            configs_by_protocol[protocol] = configs_by_protocol.get(protocol, 0) + 1
        except IndexError:
            continue
    
    cursor.execute("""
        SELECT country_code, COUNT(config) as count
        FROM configs
        WHERE country_code IS NOT NULL AND country_code != ''
        GROUP BY country_code
        ORDER BY count DESC
    """)
    countries_with_counts = cursor.fetchall()
    top_10_countries = countries_with_counts[:10]

    conn.close()

    return {
        "total_active_configs": total_configs,
        "configs_by_protocol": dict(sorted(configs_by_protocol.items(), key=lambda item: item[1], reverse=True)),
        "countries_with_counts": countries_with_counts,
        "top_10_countries": top_10_countries
    }

def main():
    print("--- Generating All Final Output Files (Summary and Report) ---")
    
    with open("config.yml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    REPO_OWNER = config['project']['repo_owner']
    REPO_NAME = config['project']['repo_name']
    SUBSCRIPTION_URL_BASE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/raw/refs/heads/master/subscription"

    tehran_tz = pytz.timezone('Asia/Tehran')
    update_time_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    update_time_tehran = update_time_utc.astimezone(tehran_tz).isoformat()

    # --- ۱. جمع‌آوری تمام آمار مورد نیاز ---
    db_stats = get_db_stats(DB_FILE)
    telegram_targets_count = get_line_count(TELEGRAM_TARGETS_FILE)
    github_crawled_urls_count = get_line_count(GITHUB_CRAWLED_URLS_FILE)
    
    # --- ۲. ساخت و ذخیره فایل summary.json ---
    country_data_for_summary = []
    for code, count in db_stats["countries_with_counts"]:
        info = get_country_info(code)
        country_data_for_summary.append({
            'code': code.upper(),
            'name': info['name'],
            'flag': info['flag'],
            'count': count,
            'full_link': f"{SUBSCRIPTION_URL_BASE}/{code.upper()}_sub.txt",
            'link_100': f"{SUBSCRIPTION_URL_BASE}/{code.upper()}_sub_100.txt"
        })

    summary_data = {
        "last_update": update_time_tehran,
        "merged_configs_count": db_stats["total_active_configs"],
        "countries": country_data_for_summary
    }
    with open(SUMMARY_OUTPUT_FILE, "w", encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=4)
    print(f"✅ {SUMMARY_OUTPUT_FILE} generated successfully.")

    # --- ۳. ساخت و ذخیره فایل report_data.json ---
    report_data = {
        "report_generated_at": update_time_utc.isoformat(),
        "stats": {
            "total_active_configs": db_stats["total_active_configs"],
            "configs_by_protocol": db_stats["configs_by_protocol"],
            "top_10_countries": db_stats["top_10_countries"],
            "telegram_stats": {
                "total_targets": telegram_targets_count
            },
            "github_stats": {
                "total_crawled_urls": github_crawled_urls_count
            }
        }
    }
    with open(REPORT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=4)
    print(f"✅ {REPORT_OUTPUT_FILE} generated successfully.")

    print("\nSkipping README.md generation for security.")

if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        main()
