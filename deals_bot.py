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

def clean_store_url(url):
    """Safely cleans store URLs without breaking schemes or vital parameters."""
    if not url or not isinstance(url, str):
        return url

    # 1. Ensure scheme is present
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url.lstrip('/')

    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()

        # If netloc is missing (e.g. was just a path), fallback
        if not netloc:
            return url

        # Flipkart & Shopsy: Keep core identifiers
        if "flipkart.com" in netloc or "shopsy" in netloc:
            qs = urllib.parse.parse_qs(parsed.query)
            allowed = ['pid', 'lid', 'marketplace', 'spotlightTagId', 'offer']
            clean_qs = {k: v for k, v in qs.items() if k in allowed}
            
            # If query had parameters but none matched allowed, keep original query to prevent 404s
            if qs and not clean_qs:
                new_query = parsed.query
            else:
                new_query = urllib.parse.urlencode(clean_qs, doseq=True)

            return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', new_query, ''))

        # Myntra & Ajio: Clean tracking parameters safely
        if "myntra.com" in netloc or "ajio.com" in netloc:
            clean_path = parsed.path.rstrip('/')
            return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, clean_path, '', '', ''))

    except Exception:
        pass
        
    return url

def resolve_short_url(url):
    """Unshortens redirects and ensures a fully qualified HTTPS destination."""
    if not url:
        return ""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    current_url = url
    
    for _ in range(8):
        try:
            res = requests.get(current_url, headers=headers, allow_redirects=False, timeout=6)
            next_url = None
            
            if res.status_code in (301, 302, 303, 307, 308):
                next_url = res.headers.get('Location')
            elif res.status_code == 200:
                js_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', res.text)
                if js_match:
                    next_url = js_match.group(1).replace('\\/', '/')
                else:
                    meta_match = re.search(r'content=["\']\d+;url=([^"\']+)["\']', res.text, re.IGNORECASE)
                    if meta_match:
                        next_url = meta_match.group(1).replace('\\/', '/')

            if not next_url:
                break

            # Reconstruct relative paths into absolute URLs
            if next_url.startswith('/'):
                parsed_cur = urllib.parse.urlparse(current_url)
                next_url = f"{parsed_cur.scheme or 'https'}://{parsed_cur.netloc}{next_url}"

            current_url = next_url
            
            # Stop if we reached a canonical product page
            if "flipkart.com" in current_url.lower() and ("/p/" in current_url.lower() or "pid=" in current_url.lower()):
                break
        except Exception:
            break

    return clean_store_url(current_url)

def clean_product_fingerprint(url, raw_text):
    """Creates unique identifier to prevent cross-channel duplicate posts."""
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        for key in ['pid', 'id', 'productId', 'item', 'p']:
            if key in query:
                return f"PROD_{query[key][0]}"
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) > 0 and len(path_parts[-1]) >= 4:
            return f"PROD_{path_parts[-1]}"
    except Exception:
        pass
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', raw_text[:40]).lower()
    return f"TITLE_{clean_title}" if len(clean_title) > 8 else None

def get_inrdeals_link_direct(resolved_url):
    """Validates destination URL before passing to INRDeals to prevent server crashes."""
    clean_url = clean_store_url(resolved_url)
    
    # Defensive check: Must be a full valid HTTP/HTTPS link
    if not clean_url or not clean_url.startswith(('http://', 'https://')):
        return resolved_url

    encoded_url = urllib.parse.quote(clean_url, safe='')

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
    """Strips watermarks and handles from competitor posts."""
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

    return text.strip()

def is_deal_fresh(msg_elem):
    """Verifies that the deal timestamp is within the configured window."""
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        res = requests.get(f"https://t.me/s/{source_channel}", headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        messages = soup.find_all('div', class_='tgme_widget_message')[-35:]
    except Exception as e:
        print(f"[!] Error loading {source_channel}: {e}")
        return

    for msg in messages:
        raw_post_id = msg.get('data-post')
        if not raw_post_id:
            continue
        unique_id = f"{source_channel}_{raw_post_id.split('/')[-1]}"

        if unique_id in posted_history:
            continue

        if not is_deal_fresh(msg):
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            continue

        text_elem = msg.find('div', class_='tgme_widget_message_text')
        if text_elem:
            for br in text_elem.find_all("br"):
                br.replace_with("\n")
        
        raw_text = text_elem.get_text() if text_elem else ""
        msg_text_lower = raw_text.lower()

        inline_links = []
        if text_elem:
            for a_tag in text_elem.find_all('a'):
                href = a_tag.get('href')
                if href and not href.startswith(('mailto:', 'tel:')):
                    inline_links.append({"url": href, "text": a_tag.get_text()})

        valid_deal_links = []
        primary_link = None
        
        for link_obj in inline_links:
            href = link_obj['url']
            display_text = link_obj['text']
            
            if "t.me" in href or "telegram.org" in href:
                continue
                
            resolved = resolve_short_url(href)
            res_lower = resolved.lower()
            
            if "amazon" in res_lower or "amzn" in res_lower:
                valid_deal_links.append((display_text, ""))
                continue
                
            is_valid = any(d in res_lower for d in ALLOWED_DOMAINS) or any(s in msg_text_lower for s in ["flipkart", "shopsy", "myntra", "ajio", "tatacliq", "croma", "meesho"])
            
            if is_valid:
                if not primary_link:
                    primary_link = resolved
                aff_link = get_inrdeals_link_direct(resolved)
                new_html = f"<a href='{aff_link}'><b>👉 Click Here To Buy</b></a>"
                valid_deal_links.append((display_text, new_html))
            else:
                valid_deal_links.append((display_text, ""))

        if not primary_link:
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            continue

        fingerprint = clean_product_fingerprint(primary_link, raw_text)
        if fingerprint and fingerprint in posted_history:
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f:
                f.write(f"{unique_id}\n")
            continue

        final_text = html.escape(raw_text)
        
        for old_display_text, new_html_button in valid_deal_links:
            escaped_display = html.escape(old_display_text)
            if escaped_display:
                final_text = final_text.replace(escaped_display, new_html_button, 1)

        clean_text = clean_branding(final_text)
        clean_text += f"\n\n🔥 <b>Join {DESTINATION_CHANNEL} for verified loot deals!</b>"

        image_url = None
        photo_wrap = msg.find(class_=re.compile('tgme_widget_message_photo_wrap'))
        if photo_wrap and photo_wrap.has_attr('style'):
            img_match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", photo_wrap['style'])
            if img_match:
                raw_img = img_match.group(1).strip().strip("'\"")
                image_url = "https:" + raw_img if raw_img.startswith("//") else raw_img

        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        posted_successfully = False

        if image_url:
            try:
                img_res = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if img_res.status_code == 200:
                    payload = {"chat_id": DESTINATION_CHANNEL, "caption": clean_text[:1020], "parse_mode": "HTML"}
                    files = {"photo": ("image.jpg", img_res.content, "image/jpeg")}
                    res = requests.post(f"{bot_api_url}/sendPhoto", data=payload, files=files, timeout=15)
                    if res.status_code == 200:
                        posted_successfully = True
            except Exception:
                pass

        if not posted_successfully:
            try:
                payload = {"chat_id": DESTINATION_CHANNEL, "text": clean_text[:4000], "parse_mode": "HTML"}
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
