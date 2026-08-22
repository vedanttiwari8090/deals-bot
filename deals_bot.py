import requests
from bs4 import BeautifulSoup
import time
import re
import os
import urllib.parse
import html

# ==============================================================================
#                               CONFIGURATIONS
# ==============================================================================
# 1. Telegram Details
BOT_TOKEN = "8671389280:AAFNzf8iWTWIpk_yJJCq62hwALX9NeOmuxc"            # From @BotFather
DESTINATION_CHANNEL = "@GetLoot_Deals"       # Your channel username with @
CHANNEL_USERNAME = "GetLoot_Deals"           # Your channel username without @

# 2. 5 Competitor Channels to Scrape (Without '@' or 't.me/')
SOURCE_CHANNELS = [
    "lootjunctionn",
    "techgurukaka",
    "iamprasadtech",
    "+EA1nJVHLfPw0YzQ1",
    "+YrRAN1v-nr5kZWI1"
]

INR_ID = "ayu679055639"
INR_KEY = "none"
HISTORY_FILE = "posted_deals.txt"

ALLOWED_DOMAINS = [
    "flipkart", "fkrt.it", "fkrt.co", "shopsy",
    "myntra", "myntr.it", "ajio", "tatacliq", "meesho",
    "bit.ly", "cutt.ly", "tinyurl.com", "swiggy", "fktr.in", "zomato", "cuttli.in", "jio"
]
# ==============================================================================

def resolve_short_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=5)
        return response.url
    except Exception:
        return url

def get_inrdeals_link(original_url):
    """Generates the raw tracking URL without external shorteners that block affiliates."""
    real_url = resolve_short_url(original_url)
    encoded_url = urllib.parse.quote(real_url, safe='')

    if INR_KEY and INR_KEY.lower() != "none":
        api_url = f"https://inr.deals/api/request/affiliatelink?id={INR_ID}&key={INR_KEY}&url={encoded_url}"
        try:
            res = requests.get(api_url, timeout=10).json()
            if res.get("status") is True and "url" in res:
                return res.get("url")
        except Exception:
            pass

    return f"https://inr.deals/track?id={INR_ID}&url={encoded_url}"

def clean_branding(text):
    if not text:
        return ""

    text = re.sub(r'(?i)extra\s*pe', '', text)
    text = re.sub(r'(?i)earnkaro', '', text)
    text = re.sub(r'(?i)inrdeals', '', text)
    text = re.sub(r'https?://t\.me/[a-zA-Z0-9_+]+', f'https://t.me/{CHANNEL_USERNAME}', text)
    text = re.sub(r't\.me/[a-zA-Z0-9_+]+', f't.me/{CHANNEL_USERNAME}', text)
    text = re.sub(r'@[a-zA-Z0-9_]+', DESTINATION_CHANNEL, text)

    filler_phrases = ["Join our backup channel", "Join fast", "Loot fast", "Share with friends"]
    for phrase in filler_phrases:
        text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)

    # Convert to safe text for Telegram HTML parsing
    text = html.escape(text.strip())
    text += f"\n\n🔥 <b>Join {DESTINATION_CHANNEL} for verified loot deals!</b>"
    return text

def process_channel(source_channel, posted_ids):
    print(f"[*] Scanning: {source_channel}...")
    url = f"https://t.me/s/{source_channel}"
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception:
        return

    messages = soup.find_all('div', class_='tgme_widget_message')

    for msg in messages:
        raw_post_id = msg.get('data-post')
        if not raw_post_id:
            continue

        msg_id_num = raw_post_id.split('/')[-1]
        unique_id = f"{source_channel}_{msg_id_num}"
        if unique_id in posted_ids:
            continue

        text_elem = msg.find('div', class_='tgme_widget_message_text')
        if not text_elem:
            continue

        embedded_links = [a.get('href') for a in text_elem.find_all('a') if a.get('href')]
        raw_text = text_elem.get_text(separator='\n')
        regex_links = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', raw_text)
        all_links = list(set(embedded_links + regex_links))

        valid_deal_links = []
        is_amazon = False

        for link in all_links:
            if "t.me" in link:
                continue

            resolved = resolve_short_url(link)
            res_lower = resolved.lower()

            if "amazon" in res_lower or "amzn" in res_lower:
                is_amazon = True
                break

            if any(domain in res_lower for domain in ALLOWED_DOMAINS):
                valid_deal_links.append((link, resolved))

        if is_amazon or not valid_deal_links:
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            posted_ids.append(unique_id)
            continue

        # --- IMAGE BYPASS SCRAPER ---
        image_url = None
        photo_wrap = msg.find(class_=re.compile('tgme_widget_message_photo_wrap'))
        if photo_wrap and photo_wrap.has_attr('style'):
            style_str = photo_wrap['style']
            img_match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", style_str)
            if img_match:
                raw_img = img_match.group(1).strip().strip("'\"")
                if raw_img.startswith("//"): image_url = "https:" + raw_img
                elif raw_img.startswith("http"): image_url = raw_img

        # --- TEXT & LINK CLEANUP ---
        final_text = raw_text
        
        # 1. Delete all the ugly raw competitor links from the post entirely
        for original_link in all_links:
            final_text = final_text.replace(original_link, "")
            
        # 2. Clean the branding
        clean_text = clean_branding(final_text)
        
        # 3. Create elegant HTML clickable buttons for your tracking links
        converted_list = []
        for _, resolved_link in valid_deal_links:
            affiliate_link = get_inrdeals_link(resolved_link)
            # This hides the long URL behind clean text
            converted_list.append(f"🔗 <a href='{affiliate_link}'><b>Click Here To Buy</b></a>")

        if converted_list:
            clean_text += "\n\n🛒 <b>Buy Links:</b>\n" + "\n".join(converted_list)

        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        posted_successfully = False

        # --- POSTING WITH IMAGE FALLBACK ---
        if image_url and len(clean_text) <= 1024:
            payload = {
                "chat_id": DESTINATION_CHANNEL,
                "photo": image_url,
                "caption": clean_text,
                "parse_mode": "HTML"
            }
            res = requests.post(f"{bot_api_url}/sendPhoto", json=payload, timeout=10)
            if res.status_code == 200:
                posted_successfully = True

        if not posted_successfully:
            payload = {
                "chat_id": DESTINATION_CHANNEL,
                "text": clean_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
            res = requests.post(f"{bot_api_url}/sendMessage", json=payload, timeout=10)
            if res.status_code == 200:
                posted_successfully = True

        if posted_successfully:
            print(f"[+] Successfully posted deal from {source_channel}!")
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            posted_ids.append(unique_id)

        time.sleep(3)

def run():
    print("[✓] GitHub Action Cycle Started (Image Bypass Active)!")
    if not os.path.exists(HISTORY_FILE):
        open(HISTORY_FILE, 'w').close()

    with open(HISTORY_FILE, 'r') as f:
        posted_ids = f.read().splitlines()

    for channel in SOURCE_CHANNELS:
        process_channel(channel, posted_ids)
        time.sleep(2)
        
    print("[✓] Cycle Complete. Shutting down server until next schedule.")

if __name__ == "__main__":
    run()

