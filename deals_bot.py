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
    "+EA1nJVHLfPw0YzQ1",
    "powerloot"
]

INR_ID = "ayu679055639"
INR_KEY = "none"
HISTORY_FILE = "posted_deals.txt"

MAX_DEAL_AGE_HOURS = 3

ALLOWED_DOMAINS = [
    "flipkart", "fkrt.it", "fkrt.co", "shopsy",
    "myntra", "myntr.it", "ajio", "tatacliq", "meesho",
    "bit.ly", "cutt.ly", "fpkrt.cc", "tinyurl.com", "swiggy", "fktr.in", "zomato", "cuttli.in", "jio"
]
# ==============================================================================

def resolve_short_url(url):
    """Unshortens competitor redirect links using a full browser simulation to bypass blocks."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        # Use GET instead of HEAD to bypass Flipkart/EarnKaro anti-bot protections
        with requests.get(url, headers=headers, allow_redirects=True, timeout=8, stream=True) as res:
            return res.url
    except Exception:
        return url

def normalize_product_url(url):
    """Strips affiliate and session tags to isolate the core product ID."""
    try:
        parsed = urllib.parse.urlparse(url)
        query_dict = urllib.parse.parse_qs(parsed.query)
        clean_query = {}
        
        for key in ['pid', 'id', 'item', 'productId', 'p']:
            if key in query_dict:
                clean_query[key] = query_dict[key]
        
        normalized_query = urllib.parse.urlencode(clean_query, doseq=True)
        clean_path = parsed.path.rstrip('/')
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), clean_path, '', normalized_query, ''))
    except Exception:
        return url.split('?')[0].rstrip('/').lower()

def get_inrdeals_link(original_url):
    """Generates direct INRDeals affiliate tracking link."""
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
    """Removes competitor watermarks, promo phrases, and handles."""
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
    """Strictly checks if message was posted within the last 1.5 hours."""
    time_elem = msg_elem.find('time', class_='time')
    if not time_elem or not time_elem.get('datetime'):
        return True

    try:
        dt_str = time_elem['datetime']
        post_time = datetime.fromisoformat(dt_str)
        now_utc = datetime.now(timezone.utc)
        if (now_utc - post_time) > timedelta(hours=MAX_DEAL_AGE_HOURS):
            return False
    except Exception:
        pass

    return True

def process_channel(source_channel, posted_history):
    print(f"[*] Scanning: {source_channel}...")
    url = f"https://t.me/s/{source_channel}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"[!] Failed to fetch {source_channel}: {e}")
        return

    all_messages = soup.find_all('div', class_='tgme_widget_message')
    recent_messages = all_messages[-30:]

    for msg in recent_messages:
        raw_post_id = msg.get('data-post')
        if not raw_post_id:
            continue

        msg_id_num = raw_post_id.split('/')[-1]
        unique_id = f"{source_channel}_{msg_id_num}"

        if unique_id in posted_history:
            continue

        if not is_deal_fresh(msg):
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            posted_history.add(unique_id)
            continue

        text_elem = msg.find('div', class_='tgme_widget_message_text')
        if not text_elem:
            continue

        embedded_links = [a.get('href') for a in text_elem.find_all('a') if a.get('href')]
        raw_text = text_elem.get_text(separator='\n')
        regex_links = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', raw_text)
        all_links = list(set(embedded_links + regex_links))

        valid_deal_links = []
        normalized_product_urls = []
        is_amazon = False
        is_duplicate_product = False
        msg_text_lower = raw_text.lower()

        for link in all_links:
            if "t.me" in link:
                continue

            resolved = resolve_short_url(link)
            res_lower = resolved.lower()
            orig_lower = link.lower()

            # 1. Block Amazon if found in URL OR the message text
            if "amazon" in res_lower or "amzn" in res_lower or "amazon" in orig_lower or "amazon" in msg_text_lower:
                is_amazon = True
                break

            # 2. Accept if domain is allowed OR if store name is explicitly mentioned in the text
            is_valid_url = any(domain in res_lower for domain in ALLOWED_DOMAINS) or any(domain in orig_lower for domain in ALLOWED_DOMAINS)
            is_store_mentioned = any(store in msg_text_lower for store in ["flipkart", "shopsy", "myntra", "ajio", "tatacliq"])

            if is_valid_url or is_store_mentioned:
                normalized = normalize_product_url(resolved)
                
                if normalized in posted_history:
                    is_duplicate_product = True
                    break

                valid_deal_links.append((link, resolved))
                normalized_product_urls.append(normalized)

        if is_amazon or is_duplicate_product or not valid_deal_links:
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            posted_history.add(unique_id)
            continue

        image_url = None
        photo_wrap = msg.find(class_=re.compile('tgme_widget_message_photo_wrap'))
        if photo_wrap and photo_wrap.has_attr('style'):
            style_str = photo_wrap['style']
            img_match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", style_str)
            if img_match:
                raw_img = img_match.group(1).strip().strip("'\"")
                if raw_img.startswith("//"):
                    image_url = "https:" + raw_img
                elif raw_img.startswith("http"):
                    image_url = raw_img

        final_text = raw_text
        for original_link in all_links:
            final_text = final_text.replace(original_link, "")

        clean_text = clean_branding(final_text)

        buy_links_html = []
        for _, resolved_link in valid_deal_links:
            affiliate_link = get_inrdeals_link(resolved_link)
            buy_links_html.append(f"👉 <a href='{affiliate_link}'><b>Click Here To Buy</b></a>")

        if buy_links_html:
            clean_text += "\n\n🛍️ <b>BUY NOW:</b>\n" + "\n".join(buy_links_html)

        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        posted_successfully = False

        if image_url:
            try:
                img_res = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if img_res.status_code == 200:
                    payload = {
                        "chat_id": DESTINATION_CHANNEL,
                        "caption": clean_text[:1024],
                        "parse_mode": "HTML"
                    }
                    files = {
                        "photo": ("image.jpg", img_res.content, "image/jpeg")
                    }
                    res = requests.post(f"{bot_api_url}/sendPhoto", data=payload, files=files, timeout=15)
                    if res.status_code == 200:
                        posted_successfully = True
            except Exception as e:
                print(f"[!] Direct image upload failed: {e}")

        if not posted_successfully:
            try:
                payload = {
                    "chat_id": DESTINATION_CHANNEL,
                    "text": clean_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
                res = requests.post(f"{bot_api_url}/sendMessage", json=payload, timeout=10)
                if res.status_code == 200:
                    posted_successfully = True
            except Exception as e:
                pass

        if posted_successfully:
            print(f"[+] Successfully posted fresh deal from {source_channel}!")
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
                for norm_url in normalized_product_urls:
                    f.write(f"{norm_url}\n")
            posted_history.add(unique_id)
            for norm_url in normalized_product_urls:
                posted_history.add(norm_url)

        time.sleep(3)

def run():
    print("[✓] Fresh deduplicated deals cycle started!")
    if not os.path.exists(HISTORY_FILE):
        open(HISTORY_FILE, 'w').close()

    with open(HISTORY_FILE, 'r') as f:
        posted_history = set(line.strip() for line in f if line.strip())

    for channel in SOURCE_CHANNELS:
        process_channel(channel, posted_history)
        time.sleep(2)

    print("[✓] Cycle complete. History saved.")

if __name__ == "__main__":
    run()

if __name__ == "__main__":
    run()
