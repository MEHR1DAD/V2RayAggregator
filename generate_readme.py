import os
from datetime import datetime
import pytz
import jdatetime
from urllib.parse import quote
import yaml
import json
import pycountry

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

def get_country_flag_emoji(country_code):
    if not country_code or len(country_code) != 2:
        return "🏴‍☠️"
    country_code = country_code.upper()
    return "".join(chr(ord(c) + 127397) for c in country_code)

def get_country_info(country_code):
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

with open("config.yml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

REPO_OWNER = config['project']['repo_owner']
REPO_NAME = config['project']['repo_name']
SUBSCRIPTION_URL_BASE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/raw/refs/heads/master/subscription"

def get_iso_update_time():
    tehran_tz = pytz.timezone('Asia/Tehran')
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    return now_utc.astimezone(tehran_tz).isoformat()

def generate_summary_file():
    country_data = []
    total_configs_count = 0
    
    print("--- Generating Final Output File (summary.json only) ---")
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
    
    web_update_time = get_iso_update_time()

    summary_data = {
        "last_update": web_update_time,
        "merged_configs_count": total_configs_count,
        "countries": country_data
    }
    with open("summary.json", "w", encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=4)
    print("✅ summary.json generated successfully.")
    print("Skipping README.md generation for security.")


if __name__ == "__main__":
    if not os.path.exists('config.yml'):
        print("FATAL: config.yml not found.")
    else:
        generate_summary_file()
