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
    """Manually follows redirects and STOPS before Flipkart's Captcha wall can trigger."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    current_url = url
    
    for _ in range(5):  # Maximum of 5 redirect jumps to prevent endless loops
        try:
            # allow_redirects=False is the secret. We take manual control of the jumps!
            res = requests.get(current_url, headers=headers, allow_redirects=False, timeout=6)
            next_url = None
            
            # 1. Check for standard HTTP redirect (EarnKaro, Bitly, etc.)
            if res.status_code in (301, 302, 303, 307, 308):
                next_url = res.headers.get('Location')
            
            # 2. Check for hidden HTML/JS redirects (ExtraPe, etc.)
            elif res.status_code == 200:
                js_match = re.search(r'window\.location\.(?:replace|href)\s*=\s*["\']([^"\']+)["\']', res.text)
                if js_match:
                    next_url = js_match.group(1).replace('\\/', '/')
                else:
                    meta_match = re.search(r'content=["\']\d+;url=([^"\']+)["\']', res.text, re.IGNORECASE)
                    if meta_match:
                        next_url = meta_match.group(1).replace('\\/', '/')

            if not next_url:
                break  # We reached the final destination
                
            # Fix broken relative URLs
            if next_url.startswith('/'):
                parsed = urllib.parse.urlparse(current_url)
                next_url = f"{parsed.scheme}://{parsed.netloc}{next_url}"
                
            current_url = next_url
            
            # =========================================================
            # THE SMART BRAKE: Stop immediately if we hit a shopping app!
            # =========================================================
            store_domains = ['flipkart.com', 'dl.flipkart.com', 'myntra.com', 'shopsy.in', 'ajio.com']
            if any(store in current_url.lower() for store in store_domains):
                break # Stop the loop before the Captcha triggers!

        except Exception:
            break
            
    return current_url

def clean_product_fingerprint(url, raw_text):
    """Creates a unique ID to prevent cross-channel duplicates, now supporting shortlinks!"""
    try:
        parsed = urllib.parse.urlparse(url)
        
        # 1. Look for standard Product IDs (pid, id, etc.)
        query = urllib.parse.parse_qs(parsed.query)
        for key in ['pid', 'id', 'productId', 'item', 'p']:
            if key in query: 
                return f"PROD_{query[key][0]}"
        
        # 2. Look for Shortlink Unique Codes (e.g., dl.flipkart.com/s/XYZ123)
        # This extracts the 'XYZ123' part from the end of the URL to use as the ID
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) > 0 and path_parts[-1]:
            # Ensure it's not an empty string and grab the last part of the link
            if len(path_parts[-1]) >= 4:
                return f"PROD_{path_parts[-1]}"
                
    except Exception:
        pass
    
    # 3. Fallback: If no link ID is found, use the first few words of the post
    clean_title = re.sub(r'[^a-zA-Z0-9]', '', raw_text[:40]).lower()
    return f"TITLE_{clean_title}" if len(clean_title) > 8 else None
    
def get_inrdeals_link_direct(resolved_url):
    encoded_url = urllib.parse.quote(resolved_url, safe='')
    if INR_KEY and INR_KEY.lower() != "none":
        api_url = f"https://inr.deals/api/request/affiliatelink?id={INR_ID}&key={INR_KEY}&url={encoded_url}"
        try:
            res = requests.get(api_url, timeout=6).json()
            if res.get("status") is True and "url" in res: return res.get("url")
        except: pass
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
    for phrase in filler_phrases: text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)
    return text.strip()

def is_deal_fresh(msg_elem):
    time_elem = msg_elem.find('time', class_='time')
    if not time_elem or not time_elem.get('datetime'): return True
    try:
        post_time = datetime.fromisoformat(time_elem['datetime'])
        if (datetime.now(timezone.utc) - post_time) > timedelta(hours=MAX_DEAL_AGE_HOURS): return False
    except: pass
    return True

def process_channel(source_channel, posted_history):
    if source_channel.startswith("+"): return
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
        if not raw_post_id: continue
        unique_id = f"{source_channel}_{raw_post_id.split('/')[-1]}"

        if unique_id in posted_history: continue

        if not is_deal_fresh(msg):
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            continue

        text_elem = msg.find('div', class_='tgme_widget_message_text')
        
        # Format HTML breaks to newlines before extracting text
        if text_elem:
            for br in text_elem.find_all("br"): br.replace_with("\n")
        
        raw_text = text_elem.get_text() if text_elem else ""
        msg_text_lower = raw_text.lower()

        # 1. EXTRACT REAL LINKS & VISUAL TEXT FROM HTML
        inline_links = []
        if text_elem:
            for a_tag in text_elem.find_all('a'):
                href = a_tag.get('href')
                if href and not href.startswith(('mailto:', 'tel:')):
                    inline_links.append({"url": href, "text": a_tag.get_text()})

        # 2. RESOLVE & VERIFY LINKS
        valid_deal_links = [] # Will hold tuples of (Old Display Text, New HTML Button)
        primary_link = None
        
        for link_obj in inline_links:
            href = link_obj['url']
            display_text = link_obj['text']
            
            if "t.me" in href or "telegram.org" in href: continue
                
            resolved = resolve_short_url(href)
            res_lower = resolved.lower()
            
            # Delete Amazon links entirely
            if "amazon" in res_lower or "amzn" in res_lower:
                valid_deal_links.append((display_text, ""))
                continue
                
            is_valid = any(d in res_lower for d in ALLOWED_DOMAINS) or any(s in msg_text_lower for s in ["flipkart", "shopsy", "myntra", "ajio", "tatacliq", "croma", "meesho"])
            
            if is_valid:
                if not primary_link: primary_link = resolved
                aff_link = get_inrdeals_link_direct(resolved)
                new_html = f"<a href='{aff_link}'><b>👉 Click Here To Buy</b></a>"
                valid_deal_links.append((display_text, new_html))
            else:
                # Erase unknown junk links
                valid_deal_links.append((display_text, ""))

        # 3. VERIFY DEDUPLICATION
        if not primary_link:
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            continue

        fingerprint = clean_product_fingerprint(primary_link, raw_text)
        if fingerprint and fingerprint in posted_history:
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            continue

        # 4. PERFECT INLINE TEXT REPLACEMENT
        final_text = html.escape(raw_text)
        
        # Replace the exact visible text with our new button on the exact same line!
        for old_display_text, new_html_button in valid_deal_links:
            escaped_display = html.escape(old_display_text)
            if escaped_display:
                # replace(..., 1) ensures we only replace the specific link, not normal words
                final_text = final_text.replace(escaped_display, new_html_button, 1)

        clean_text = clean_branding(final_text)
        clean_text += f"\n\n🔥 <b>Join {DESTINATION_CHANNEL} for verified loot deals!</b>"

        # 5. FETCH IMAGE
        image_url = None
        photo_wrap = msg.find(class_=re.compile('tgme_widget_message_photo_wrap'))
        if photo_wrap and photo_wrap.has_attr('style'):
            img_match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", photo_wrap['style'])
            if img_match:
                raw_img = img_match.group(1).strip().strip("'\"")
                image_url = "https:" + raw_img if raw_img.startswith("//") else raw_img

        # 6. POST TO TELEGRAM
        bot_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}"
        posted_successfully = False

        if image_url:
            try:
                img_res = requests.get(image_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if img_res.status_code == 200:
                    payload = {"chat_id": DESTINATION_CHANNEL, "caption": clean_text[:1020], "parse_mode": "HTML"}
                    files = {"photo": ("image.jpg", img_res.content, "image/jpeg")}
                    res = requests.post(f"{bot_api_url}/sendPhoto", data=payload, files=files, timeout=15)
                    if res.status_code == 200: posted_successfully = True
            except: pass

        if not posted_successfully:
            try:
                payload = {"chat_id": DESTINATION_CHANNEL, "text": clean_text[:4000], "parse_mode": "HTML"}
                res = requests.post(f"{bot_api_url}/sendMessage", json=payload, timeout=10)
                if res.status_code == 200: posted_successfully = True
            except: pass

        if posted_successfully:
            print(f"[+] Posted deal: {unique_id}")
            posted_history.add(unique_id)
            with open(HISTORY_FILE, 'a') as f: f.write(f"{unique_id}\n")
            if fingerprint:
                posted_history.add(fingerprint)
                with open(HISTORY_FILE, 'a') as f: f.write(f"{fingerprint}\n")

        time.sleep(2)

def run():
    if not os.path.exists(HISTORY_FILE): open(HISTORY_FILE, 'w').close()
    with open(HISTORY_FILE, 'r') as f: posted_history = set(line.strip() for line in f if line.strip())

    for channel in SOURCE_CHANNELS:
        process_channel(channel, posted_history)
        time.sleep(2)

if __name__ == "__main__":
    run()
