# filepath: src/bot.py

import os
import re
import asyncio
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import jdatetime

load_dotenv()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
TELETHON_SESSION = os.getenv("TELETHON_SESSION", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

# Importing Telethon components late to prevent initialization side-effects
from telethon import TelegramClient
from telethon.sessions import StringSession

def sanitize_persian_text(text):
    """Converts Persian digits to English, removes commas, and strips layout stretch bars."""
    if not text:
        return ""
    
    # \u0640 is the Tatweel/Kashida character used to stretch words like نــقدی or خــرید
    # Strip this BEFORE any string matching happens
    clean = text.replace('\u0640', '').replace(',', '').replace('\u200c', ' ')
    
    persian_to_eng = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
    clean = clean.translate(persian_to_eng)
    
    # Standardize multiple continuous spaces down to single spaces
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def scrape_tgju_local_assets():
    """Scrapes individual TGJU profile pages for Silver, Emami, and Azadi coins in Tomans."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    def fetch_val(url):
        try:
            resp = session.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            val_str = ""
            
            target = soup.find('span', class_='value')
            if target:
                val_str = target.text
            else:
                h3_target = soup.find('h3')
                if h3_target:
                    val_str = h3_target.text

            if val_str:
                clean = sanitize_persian_text(val_str)
                match = re.search(r'\d+', clean)
                if match:
                    rial_val = float(match.group(0))
                    # Profile pages serve values in Rials -> divide by 10 to get Tomans
                    return rial_val / 10
        except Exception as e:
            print(f"TGJU Profile Scrape Error for {url}: {e}")
        return 0.0

    silver = fetch_val("https://www.tgju.org/profile/silver_999")
    emami = fetch_val("https://www.tgju.org/profile/sekee")
    azadi = fetch_val("https://www.tgju.org/profile/sekeb")
    
    return silver, emami, azadi

async def scrape_telegram():
    """Iterates channel histories to find precise market values for Ounce, 18k, Dollar, and Tether."""
    client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)
    await client.connect()
    
    ounce_val = 0.0
    iran_18k_val = 0.0
    dollar_val = 0.0
    tether_val = 0.0
    
    try:
        # 1. Global Ounce: Look back through latest messages from OUNSGOLD
        async for msg in client.iter_messages('OUNSGOLD', limit=10):
            if not msg.text:
                continue
            clean = sanitize_persian_text(msg.text)
            match = re.search(r'\d+(?:\.\d+)?', clean)
            if match:
                ounce_val = float(match.group(0))
                break
                
        # 2. Iran 18k: Look back through updates from abshdanaghdy
        async for msg in client.iter_messages('abshdanaghdy', limit=30):
            if not msg.text:
                continue
            clean = sanitize_persian_text(msg.text)
            if "آبشده_نقدی" in clean and "خرید" in clean:
                match = re.search(r'#طلا_گرمی\s*(\d+)', clean)
                if match:
                    iran_18k_val = float(match.group(1))
                    break
                    
        # 3. Live Dollar: Handle variant emoji prefixes ([⏳💵]) seamlessly
        fallback_dollar = 0.0
        async for msg in client.iter_messages('dollar_tehran3bze', limit=100):
            if not msg.text:
                continue
            clean = sanitize_persian_text(msg.text)
            
            # Primary Target: Cash rate matching
            if "دلار نقدی تهران" in clean and "خرید" in clean:
                match = re.search(r'[⏳💵]\s*(\d+)', clean)
                if match:
                    dollar_val = float(match.group(1))
                    break
            
            # Backup Target: Paper rate matching as an absolute emergency buffer
            if fallback_dollar == 0.0 and "دلار فردایی تهران" in clean and "خرید" in clean:
                match = re.search(r'[⏳💵]\s*(\d+)', clean)
                if match:
                    fallback_dollar = float(match.group(1))

        if dollar_val == 0.0 and fallback_dollar > 0.0:
            print("Notice: Cash rate not found. Deploying fallback paper rate.")
            dollar_val = fallback_dollar
            
        # 4. Tether Rate: Uses flexible regex to capture digits regardless of spaces or colon variants
        async for msg in client.iter_messages('TetherLand', limit=15):
            if not msg.text:
                continue
            clean = sanitize_persian_text(msg.text)
            
            match = re.search(r'نرخ تتر\D*(\d+)', clean)
            if match:
                tether_val = float(match.group(1))
                break
                
    finally:
        await client.disconnect()
        
    return ounce_val, iran_18k_val, dollar_val, tether_val

def build_message(ounce, iran_18k, dollar, tether, emami, azadi, silver):
    """Calculates bubble metrics and renders them into the client's requested sleek format."""
    global_24k_toman = (ounce / 31.1034) * dollar if dollar else 0
    global_18k_toman = global_24k_toman * 0.75
    
    bubble_pct = 0.0
    diff_val = 0.0
    bubble_str = "0.00 ٪"
    
    if global_18k_toman > 0:
        bubble_pct = ((iran_18k / global_18k_toman) * 100) - 100
        diff_val = iran_18k - global_18k_toman
        
        # Format label strings depending on whether the asset holds a premium or discount
        if diff_val >= 0:
            bubble_str = f"{bubble_pct:,.2f} ٪(مثبت {diff_val:,.0f} تومن)"
        else:
            bubble_str = f"منفی {abs(bubble_pct):,.2f} ٪(منفی {abs(diff_val):,.0f} تومن)"

    months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", 
              "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
    now = jdatetime.datetime.now()
    date_str = f"{now.day} {months[now.month-1]} ماه {now.year}"
    time_str = now.strftime("%H:%M")

    text = f"""نرخ لحظه‌ای ارز و طلا 
⏰ {date_str} - ساعت {time_str} 

🟣💱 شاخص‌های ارزی و جهانی
▫️ اونس جهانی طلا (۲۴ عیار) : {ounce:,.2f} 💵 دلار 
▫️ قیمت دلار تهران : {dollar:,.0f} 💰 تومان 
▫️ قیمت تتر : {tether:,.0f} 💰 تومان 

🟡🥇 طلا و نقره
▫️ قیمت طلا بدون حباب : {global_18k_toman:,.0f} 💰 تومان 
▫️ معامله هر گرم ۱۸ عیار در بازار: {iran_18k:,.0f} 💰 تومان 
▫️   حباب طلا :  {bubble_str}
▫️ نقره ۹۹۹ : {silver:,.0f} 💰 تومان 

🟢🪙 سکه
▫️ سکه امامی : {emami:,.0f} 💰 تومان 
▫️ سکه بهار آزادی : {azadi:,.0f} 💰 تومان 

آدرس: چهارطبقه ؛ بین امام خمینی ۲۲ و ۲۴
روبروی جنت طلای آبشده مشهد
0912-071-0390"""
    return text

def send_message(text):
    """Dispatches the processed layout payload to the target Telegram channel."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()

async def main():
    print("Extracting live feeds from Telegram targets (Ounce, 18k, Cash Dollar, Tether)...")
    ounce, iran_18k, dollar, tether = await scrape_telegram()
    
    print("Gathering market indexes from TGJU individual profiles (Coins, Silver)...")
    silver, emami, azadi = scrape_tgju_local_assets()
    
    print("Formatting template and dispatching...")
    msg = build_message(ounce, iran_18k, dollar, tether, emami, azadi, silver)
    send_message(msg)
    print("Deployment cycle completed successfully.")

if __name__ == "__main__":
    asyncio.run(main())