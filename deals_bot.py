import requests
from bs4 import BeautifulSoup
import time
import re
import os
import urllib.parse
import html
from datetime import datetime, timezone, timedelta

# ==============================================================================
#                               CONFIGURATIONS
# ==============================================================================
BOT_TOKEN = "8671389280:AAF4_uvJN6R7nKIC_lJFBMg_xFBa3b8Z8Uo"            # From @BotFather
DESTINATION_CHANNEL = "@GetLoot_Deals"       # Your channel username with @
CHANNEL_USERNAME = "GetLoot_Deals"           # Your channel username without @

SOURCE_CHANNELS = [
    "lootjunctionn",
    "techgurukaka",
    "iamprasadtech",
    "myntra_Ajio_Sale_Deals_offers_li",
    "powerloot"
]

INR_ID = "ayu679055639"
INR_KEY = "none"
HISTORY_FILE = "posted_deals.txt"

MAX_DEAL_AGE_HOURS = 3

ALLOWED_DOMAINS = [
   "flipkart", "fkrt", "shopsy", "myntra", "myntr", "ajio", "tatacliq", 
    "meesho", "swiggy", "zomato", "jio", "croma", "nykaa", "boat-lifestyle",
    "ern.li", "extp.in", "spndeals", "bit.ly", "cutt.ly", "tinyurl", 
    "oia.bio", "openinapp", "halfoffer", "wishlink", "fktr", "cuttli", 
    "affl.io", "linkvertise", "dealssh.in", "mdeal.in", "fkrt.cc", "myntr.it", 
    "cuttli.in", "myntr.in", "fkrt.co", "fkrt.it"
]
# ==============================================================================

def resolve_short_url(url):
    """Unshortens redirect links and parses hidden JavaScript/meta redirects."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, allow_redirects=True, timeout=6)
        final_url = res.url
        
        # Check for JavaScript location replace
        js_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', res.text)
        if js_match:
            final_url = js_match.group(1).replace('\\/', '/')
            
        # Check for HTML meta refresh
        meta_match = re.search(r'content=["\']\d+;url=([^"\']+)["\']', res.text, re.IGNORECASE)
        if meta_match:
            final_url = meta_match.group(1).replace('\\/', '/')

        if final_url != res.url and final_url.startswith("http"):
            res2 = requests.get(final_url, headers=headers, allow_redirects=True, timeout=5)
            return res2.url

        return final_url
    except Exception:
        return url

def clean_product_fingerprint(url, raw_text):
    """Creates a unique ID from product ID or post title to prevent cross-channel duplicates."""
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        for key in ['pid', 'id', 'productId', 'item', 'p']:
            if key in query:
                return f"PROD_{query[key][0]}"
    except Exception:
        pass
    
    # Fallback: clean the first 40 characters of message text
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', raw_text[:45]).lower()
    return f"TITLE_{clean_title}" if len(clean_title) > 8 else None

def get_inrdeals_link_direct(resolved_url):
    """Generates direct INRDeals affiliate link."""
    encoded_url = urllib.parse.quote(resolved_url, safe='')

    if INR_KEY and INR_KEY.lower() != "none":
        api_url = f"https://inr.deals/api/request/affiliatelink?id={INR_ID}&key={INR_KEY}&url={encoded_url}"
        try:
            res = requests.get(api_url, timeout=6).json()
            if res.get("status") is True and "url" in res:
                return res.get("url")
        except Exception:
            pass

    return f"https://inr.deals/track?id={INR_ID}&url={encoded_url}"

def clean_branding(text):
    """Strips watermarks and replaces competitor tags."""
    if not text:
        return ""
    text = re.sub(r'(?i)extra\s*pe', '', text)
    text = re.sub(r'(?i)earnkaro', '', text)
    text = re.sub(r'(?i)inrdeals', '', text)
    text = re.sub(r'https?://t\.me/[a-zA-Z0-9_+]+', f'https://t.me/{CHANNEL_USERNAME}', text)
    text = re.sub(r't\.me/[a-zA-Z0-9_+]+', f't.me/{CHANNEL_USERNAME}', text)
    text = re.sub(r'@[a-zA-Z0-9_]+', DESTINATION_CHANNEL, text)

    filler_phrases = [
        "Join our backup channel", "Join fast", "Loot fast", 
        "Share with friends", "Join our discussion group", "Channel link:"
    ]
    for phrase in filler_phrases:
        text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)

    text = html.escape(text.strip())
    text += f"\n\n🔥 <b>Join {DESTINATION_CHANNEL} for verified loot deals!</b>"
    return text

def is_deal_fresh(msg_elem):
    """Checks if message is within the configured time window."""
    time_elem = msg_elem.find('time', class_='time')
    if not time_elem or not time_elem.get('datetime'):
        return True
    try:
        post_time = datetime.fromisoformat(time_elem['datetime'])
        if (datetime.now(timezone.utc) - post_time) > timedelta(hours=MAX_DEAL_AGE_HOURS):
            return False
    except Exception:
        pass
    return True

def process_channel(source_channel, posted_history):
    if source_channel.startswith("+"):
        return

    print(f"\n[*] Scanning: {source_channel}...")
    url = f"https://t.me/s/{source_channel}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        messages = soup.find_all('div', class_='tgme_widget_message')
    except Exception as e:
        print(f"[!] Error loading {source_channel}: {e}")
        return

    recent_messages = messages[-35:]

    for msg in recent_messages:
        raw_post_id = msg.get('data-post')
        if not raw_post_id:
            continue

        msg_id_num = raw_post_id.split('/')[-1]
        unique_id = f"{source_channel}_{msg_id_num}"

        if unique_id in posted_history:
            continue

        if not is_deal_fresh(msg):
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            continue

        text_elem = msg.find('div', class_='tgme_widget_message_text')
        raw_text = text_elem.get_text(separator='\n') if text_elem else ""

        embedded_links = [a.get('href') for a in msg.find_all('a') if a.get('href')]
        regex_links = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', raw_text)
        all_links = list(set(embedded_links + regex_links))

        valid_deal_links = []
        msg_text_lower = raw_text.lower()

        for link in all_links:
            if "t.me" in link or "telegram.org" in link:
                continue

            resolved = resolve_short_url(link)
            res_lower = resolved.lower()
            orig_lower = link.lower()

            # Skip Amazon products
            if "amazon" in res_lower or "amzn" in res_lower or "amazon" in orig_lower:
                continue

            is_valid_url = any(d in res_lower for d in ALLOWED_DOMAINS) or any(d in orig_lower for d in ALLOWED_DOMAINS)
            is_store_mentioned = any(s in msg_text_lower for s in ["flipkart", "shopsy", "myntra", "ajio", "tatacliq", "croma", "meesho"])

            if is_valid_url or is_store_mentioned:
                valid_deal_links.append((link, resolved))

        if not valid_deal_links:
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            continue

        # Prevent cross-channel duplicate posts of the same item
        primary_link = valid_deal_links[0][1]
        fingerprint = clean_product_fingerprint(primary_link, raw_text)
        if fingerprint and fingerprint in posted_history:
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            continue

        # Extract image if available
        image_url = None
        photo_wrap = msg.find(class_=re.compile('tgme_widget_message_photo_wrap'))
        if photo_wrap and photo_wrap.has_attr('style'):
            img_match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", photo_wrap['style'])
            if img_match:
                raw_img = img_match.group(1).strip().strip("'\"")
                image_url = "https:" + raw_img if raw_img.startswith("//") else raw_img

        # Prepare text & affiliate buttons
        final_text = raw_text
        for original_link in all_links:
            final_text = final_text.replace(original_link, "")
        clean_text = clean_branding(final_text)

        buy_links_html = []
        for _, resolved_link in valid_deal_links:
            affiliate_link = get_inrdeals_link_direct(resolved_link)
            buy_links_html.append(f"👉 <a href='{affiliate_link}'><b>Click Here To Buy</b></a>")

        if buy_links_html:
            clean_text += "\n\n🛍️ <b>BUY NOW:</b>\n" + "\n".join(buy_links_html)

        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        posted_successfully = False

        # Attempt to post with photo
        if image_url:
            try:
                img_res = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if img_res.status_code == 200:
                    payload = {
                        "chat_id": DESTINATION_CHANNEL,
                        "caption": clean_text[:1020],
                        "parse_mode": "HTML"
                    }
                    files = {"photo": ("image.jpg", img_res.content, "image/jpeg")}
                    res = requests.post(f"{bot_api_url}/sendPhoto", data=payload, files=files, timeout=15)
                    if res.status_code == 200:
                        posted_successfully = True
            except Exception:
                pass

        # Text-only fallback (only runs if photo upload was not attempted or failed before sending)
        if not posted_successfully:
            try:
                payload = {
                    "chat_id": DESTINATION_CHANNEL,
                    "text": clean_text[:4000],
                    "parse_mode": "HTML"
                }
                res = requests.post(f"{bot_api_url}/sendMessage", json=payload, timeout=10)
                if res.status_code == 200:
                    posted_successfully = True
            except Exception:
                pass

        if posted_successfully:
            print(f"[+] Posted deal: {unique_id}")
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            if fingerprint:
                posted_history.add(fingerprint)
                with open(HISTORY_FILE, 'a') as f:
                    f.write(f"{fingerprint}\n")

        time.sleep(2)

def run():
    if not os.path.exists(HISTORY_FILE):
        open(HISTORY_FILE, 'w').close()
    with open(HISTORY_FILE, 'r') as f:
        posted_history = set(line.strip() for line in f if line.strip())

    for channel in SOURCE_CHANNELS:
        process_channel(channel, posted_history)
        time.sleep(2)

if __name__ == "__main__":
    run()
