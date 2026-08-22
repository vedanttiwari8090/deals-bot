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
    "flipkart", "fkrt", "shopsy", "myntra", "myntr", "ajio", "tatacliq", 
    "meesho", "swiggy", "zomato", "jio", "croma", "myntr.it", "fkrt.cc",
    "ern.li", "extp.in", "spndeals", "bit.ly", "cutt.ly", "cuttli.in", "tinyurl", 
    "oia.bio", "openinapp", "halfoffer", "wishlink", "fktr.in", "telegram"
]
# ==============================================================================

def resolve_short_url(url):
    """Advanced unshortener that reads hidden JavaScript redirects."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, allow_redirects=True, timeout=8)
        final_url = res.url
        
        js_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', res.text)
        if js_match:
            final_url = js_match.group(1).replace('\\/', '/')
            
        meta_match = re.search(r'content=["\']\d+;url=([^"\']+)["\']', res.text, re.IGNORECASE)
        if meta_match:
            final_url = meta_match.group(1).replace('\\/', '/')

        if final_url != res.url and final_url.startswith("http"):
            res2 = requests.get(final_url, headers=headers, allow_redirects=True, timeout=5)
            return res2.url

        return final_url
    except Exception:
        return url

def get_inrdeals_link(original_url):
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
    if not text: return ""
    text = re.sub(r'(?i)extra\s*pe', '', text)
    text = re.sub(r'(?i)earnkaro', '', text)
    text = re.sub(r'(?i)inrdeals', '', text)
    text = re.sub(r'https?://t\.me/[a-zA-Z0-9_+]+', f'https://t.me/{CHANNEL_USERNAME}', text)
    text = re.sub(r't\.me/[a-zA-Z0-9_+]+', f't.me/{CHANNEL_USERNAME}', text)
    text = re.sub(r'@[a-zA-Z0-9_]+', DESTINATION_CHANNEL, text)

    filler_phrases = ["Join our backup channel", "Join fast", "Loot fast", "Share with friends", "Join our discussion group", "Channel link:"]
    for phrase in filler_phrases:
        text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)

    text = html.escape(text.strip())
    text += f"\n\n🔥 <b>Join {DESTINATION_CHANNEL} for verified loot deals!</b>"
    return text

def is_deal_fresh(msg_elem):
    time_elem = msg_elem.find('time', class_='time')
    if not time_elem or not time_elem.get('datetime'): return True
    try:
        post_time = datetime.fromisoformat(time_elem['datetime'])
        if (datetime.now(timezone.utc) - post_time) > timedelta(hours=MAX_DEAL_AGE_HOURS):
            return False
    except: pass
    return True

def process_channel(source_channel, posted_history):
    print(f"\n==========================================")
    print(f"[*] SCANNING CHANNEL: {source_channel}")
    print(f"==========================================")
    url = f"https://t.me/s/{source_channel}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"[!] Failed to fetch {source_channel}: {e}")
        return

    all_messages = soup.find_all('div', class_='tgme_widget_message')
    recent_messages = all_messages[-30:] # Checking last 30 messages

    for msg in recent_messages:
        raw_post_id = msg.get('data-post')
        if not raw_post_id: continue

        msg_id_num = raw_post_id.split('/')[-1]
        unique_id = f"{source_channel}_{msg_id_num}"

        if unique_id in posted_history:
            print(f"[-] SKIPPED {unique_id}: Already in posted_deals.txt memory.")
            continue

        if not is_deal_fresh(msg):
            print(f"[-] SKIPPED {unique_id}: Deal is older than {MAX_DEAL_AGE_HOURS} hours.")
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            posted_history.add(unique_id)
            continue

        text_elem = msg.find('div', class_='tgme_widget_message_text')
        raw_text = text_elem.get_text(separator='\n') if text_elem else ""

        embedded_links = [a.get('href') for a in msg.find_all('a') if a.get('href')]
        regex_links = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', raw_text)
        all_links = list(set(embedded_links + regex_links))

        valid_deal_links = []
        is_amazon_link = False
        msg_text_lower = raw_text.lower()

        print(f"\n[?] Checking Message {unique_id}...")
        
        for link in all_links:
            if "t.me" in link or "telegram.org" in link: continue

            resolved = resolve_short_url(link)
            print(f"    -> Found Link: {link}")
            print(f"    -> Traced To: {resolved}")
            
            res_lower = resolved.lower()
            orig_lower = link.lower()

            if "amazon" in res_lower or "amzn" in res_lower or "amazon" in orig_lower:
                is_amazon_link = True
                print(f"    -> 🚫 STATUS: Rejected (Amazon Link Detected)")
                break

            is_valid_url = any(domain in res_lower for domain in ALLOWED_DOMAINS) or any(domain in orig_lower for domain in ALLOWED_DOMAINS)
            is_store_mentioned = any(store in msg_text_lower for store in ["flipkart", "shopsy", "myntra", "ajio", "tatacliq"])

            if is_valid_url or is_store_mentioned:
                valid_deal_links.append((link, resolved))
                print(f"    -> ✅ STATUS: Approved for posting!")
            else:
                print(f"    -> 🚫 STATUS: Rejected (Not a recognized store or domain)")

        if is_amazon_link or not valid_deal_links:
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            posted_history.add(unique_id)
            continue

        image_url = None
        photo_wrap = msg.find(class_=re.compile('tgme_widget_message_photo_wrap'))
        if photo_wrap and photo_wrap.has_attr('style'):
            img_match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", photo_wrap['style'])
            if img_match:
                raw_img = img_match.group(1).strip().strip("'\"")
                image_url = "https:" + raw_img if raw_img.startswith("//") else raw_img

        final_text = raw_text
        for original_link in all_links: final_text = final_text.replace(original_link, "")
        clean_text = clean_branding(final_text)

        buy_links_html = []
        for _, resolved_link in valid_deal_links:
            affiliate_link = get_inrdeals_link(resolved_link)
            buy_links_html.append(f"👉 <a href='{affiliate_link}'><b>Click Here To Buy</b></a>")

        if buy_links_html: clean_text += "\n\n🛍️ <b>BUY NOW:</b>\n" + "\n".join(buy_links_html)

        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        posted_successfully = False

        if image_url:
            try:
                img_res = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if img_res.status_code == 200:
                    payload = {"chat_id": DESTINATION_CHANNEL, "caption": clean_text[:1024], "parse_mode": "HTML"}
                    res = requests.post(f"{bot_api_url}/sendPhoto", data=payload, files={"photo": ("image.jpg", img_res.content, "image/jpeg")}, timeout=15)
                    if res.status_code == 200: posted_successfully = True
            except: pass

        if not posted_successfully:
            try:
                payload = {"chat_id": DESTINATION_CHANNEL, "text": clean_text, "parse_mode": "HTML"}
                res = requests.post(f"{bot_api_url}/sendMessage", json=payload, timeout=10)
                if res.status_code == 200: posted_successfully = True
            except: pass

        if posted_successfully:
            print(f"[+] 🚀 SUCCESS: Deal {unique_id} posted to Telegram!")
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            posted_history.add(unique_id)
        
        time.sleep(3)

def run():
    if not os.path.exists(HISTORY_FILE): open(HISTORY_FILE, 'w').close()
    with open(HISTORY_FILE, 'r') as f: posted_history = set(line.strip() for line in f if line.strip())

    for channel in SOURCE_CHANNELS:
        process_channel(channel, posted_history)
        time.sleep(2)

if __name__ == "__main__":
    run()
