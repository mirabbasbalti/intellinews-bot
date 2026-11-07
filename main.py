import os
import re
import json
import random
from datetime import datetime
from io import BytesIO
import feedparser
import requests
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "")
FB_ACCESS_TOKEN = os.environ.get("FB_ACCESS_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

RSS_FEEDS = {
    "Local": [
        "https://www.dawn.com/feeds/pakistan",
        "https://tribune.com.pk/feed/pakistan",
        "https://www.nation.com.pk/rss/national"
    ],
    "Politics": [
        "https://www.dawn.com/feeds/home",
        "https://tribune.com.pk/feed/home",
        "https://www.nation.com.pk/rss/politics"
    ],
    "Sports": [
        "https://www.dawn.com/feeds/sport",
        "https://tribune.com.pk/feed/cricket",
        "https://feeds.bbci.co.uk/sport/rss.xml"
    ],
    "World News": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://www.dawn.com/feeds/world"
    ],
    "Tech News": [
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://tribune.com.pk/feed/sci-tech",
        "https://www.dawn.com/feeds/tech"
    ]
}

FONT_URLS = [
    "https://cdn.jsdelivr.net/gh/julietulanova/montserrat@master/fonts/ttf/Montserrat-ExtraBold.ttf",
    "https://raw.githubusercontent.com/julietulanova/montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf"
]
FONT_PATH = "Montserrat-ExtraBold.ttf"

def get_font(size):
    if not os.path.exists(FONT_PATH) or os.path.getsize(FONT_PATH) < 10000:
        for url in FONT_URLS:
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200 and len(r.content) > 10000:
                    with open(FONT_PATH, "wb") as f:
                        f.write(r.content)
                    break
            except Exception:
                continue
    for candidate in [
        FONT_PATH,
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default(size=size)

def clean_html(raw_html):
    text = re.sub(r"<[^>]+>", " ", raw_html or "")
    return re.sub(r"\s+", " ", text).strip()

def upgrade_image_url(url):
    if not url:
        return None
    url = url.replace("&amp;", "&").strip()
    if "ichef.bbci.co.uk" in url:
        url = re.sub(r"/(standard|news)/\d+/", r"/\1/1024/", url)
    if "i.dawn.com/thumbnail/" in url:
        url = url.replace("i.dawn.com/thumbnail/", "i.dawn.com/large/")
    return url

def extract_source_image_url(entry, article_url):
    candidates = []

    if hasattr(entry, "media_content"):
        for m in entry.media_content:
            if m.get("url"):
                candidates.append(m["url"])

    if hasattr(entry, "media_thumbnail"):
        for m in entry.media_thumbnail:
            if m.get("url"):
                candidates.append(m["url"])

    if hasattr(entry, "links"):
        for link in entry.links:
            if "image" in link.get("type", "") and link.get("href"):
                candidates.append(link["href"])

    raw_summary = getattr(entry, "summary", "")
    if hasattr(entry, "content") and entry.content:
        raw_summary += " " + entry.content[0].get("value", "")
    img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', raw_summary, re.I)
    candidates.extend(img_matches)

    try:
        r = requests.get(article_url, headers=HEADERS, timeout=12)
        html = r.text
        for prop in ["og:image", "twitter:image"]:
            m1 = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            m2 = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{prop}["\']', html, re.I)
            if m1:
                candidates.insert(0, m1.group(1))
            elif m2:
                candidates.insert(0, m2.group(1))
    except Exception:
        pass

    for c in candidates:
        u = upgrade_image_url(c)
        if u and u.startswith("http"):
            return u
    return None

def download_source_image(img_url):
    if not img_url:
        return None
    try:
        r = requests.get(img_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        if len(r.content) < 4000:
            return None
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:
        return None

def fetch_news_with_source_image():
    categories = list(RSS_FEEDS.keys())
    random.shuffle(categories)

    for category in categories:
        feeds = list(RSS_FEEDS[category])
        random.shuffle(feeds)
        for feed_url in feeds:
            try:
                resp = requests.get(feed_url, headers=HEADERS, timeout=15)
                feed = feedparser.parse(resp.content)
                entries = feed.entries[:8]
                random.shuffle(entries)
                for entry in entries:
                    img_url = extract_source_image_url(entry, entry.link)
                    src_img = download_source_image(img_url)
                    if src_img:
                        summary = clean_html(getattr(entry, "summary", entry.title))
                        return category, entry.title, entry.link, summary, src_img, img_url
            except Exception:
                continue
    raise RuntimeError("No news article with a valid source image could be fetched.")

def split_headline_5_lines(title, category):
    clean_t = re.sub(r"\s+", " ", title).strip()
    parts = re.split(r"\s*[:\-–—|]\s*", clean_t, maxsplit=1)

    if len(parts) == 2 and len(parts[0].split()) <= 4:
        line1 = parts[0]
        rest_words = parts[1].split()
    else:
        words = clean_t.split()
        line1 = " ".join(words[:2]) if len(words) >= 4 else category
        rest_words = words[2:] if len(words) >= 4 else words

    n = len(rest_words)
    if n >= 9:
        c1 = max(2, n // 4)
        c2 = max(2, (n - c1) // 3)
        c3 = max(2, (n - c1 - c2) // 2)
        line2 = " ".join(rest_words[:c1])
        line3 = " ".join(rest_words[c1:c1 + c2])
        line4 = "— " + " ".join(rest_words[c1 + c2:c1 + c2 + c3])
        line5 = " ".join(rest_words[c1 + c2 + c3:])
    elif n >= 6:
        line2 = " ".join(rest_words[:2])
        line3 = " ".join(rest_words[2:4])
        line4 = "— " + " ".join(rest_words[4:6])
        line5 = " ".join(rest_words[6:])
    else:
        line2 = " ".join(rest_words[:2])
        line3 = " ".join(rest_words[2:]) if len(rest_words) > 2 else "Latest Update"
        line4 = ""
        line5 = ""

    return {
        "line1_yellow": line1,
        "line2_white": line2,
        "line3_yellow": line3,
        "line4_white": line4,
        "line5_white": line5
    }

def generate_ai_content(category, title, summary):
    if GEMINI_API_KEY and GEMINI_API_KEY != "PASTE_YOUR_GEMINI_KEY_HERE":
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
            prompt = (
                f"You are the chief editor for IntelliNews. Format this {category} story:\n"
                f"Title: {title}\nSummary: {summary}\n\n"
                "Return ONLY valid JSON with these exact keys:\n"
                '{"line1_yellow": "1 to 2 words (location or key subject, e.g. Islamabad\'s)", '
                '"line2_white": "2 to 4 words (main subject)", '
                '"line3_yellow": "2 to 3 words (key action/outcome)", '
                '"line4_white": "2 to 4 words starting with —", '
                '"line5_white": "2 to 4 words concluding the headline", '
                '"caption": "Attractive Facebook post with a strong title, engaging summary, tags, and 8 trending hashtags"}'
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            res = requests.post(url, json=payload, timeout=25)
            res.raise_for_status()
            text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as e:
            print("Using built-in headline formatter:", e)

    lines = split_headline_5_lines(title, category)
    cat_tag = category.replace(" ", "")
    lines["caption"] = (
        f"🚨 {title}\n\n"
        f"{summary}\n\n"
        f"Follow @IntelliNews for verified updates.\n\n"
        f"#IntelliNews #{cat_tag} #PakistanNews #BreakingNews #WorldNews #LatestNews #Headlines #Trending"
    )
    return lines

def transform_source_image(src_img):
    # Make the source photo unique with a 6% zoom crop and cinematic editorial color grading
    w, h = src_img.size
    crop_margin_x = int(w * 0.03)
    crop_margin_y = int(h * 0.03)
    src_img = src_img.crop((crop_margin_x, crop_margin_y, w - crop_margin_x, h - crop_margin_y))

    # Fill upper image area and extend to 1080x1350 (4:5 vertical)
    fitted = ImageOps.fit(src_img, (1080, 1350), method=Image.Resampling.LANCZOS, centering=(0.5, 0.35))
    fitted = ImageEnhance.Contrast(fitted).enhance(1.25)
    fitted = ImageEnhance.Color(fitted).enhance(1.15)
    fitted = ImageEnhance.Sharpness(fitted).enhance(1.3)
    return fitted.convert("RGBA")

def fit_text_font(draw, text, target_size=78, max_width=980):
    size = target_size
    while size > 36:
        font = get_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font, bbox
        size -= 2
    font = get_font(36)
    return font, draw.textbbox((0, 0), text, font=font)

def draw_social_footer(draw, y_center):
    yellow = (255, 204, 0)
    white = (255, 255, 255)
    black = (10, 10, 10)

    # Left and right yellow horizontal bars
    draw.rectangle([(45, y_center - 2), (265, y_center + 3)], fill=yellow)
    draw.rectangle([(815, y_center - 2), (1035, y_center + 3)], fill=yellow)

    icon_font = get_font(42)
    # 1. Facebook 'f'
    draw.text((315, y_center - 26), "f", fill=white, font=icon_font)

    # 2. Instagram rounded square + lens circle
    ig_x, ig_y = 405, y_center - 20
    draw.rounded_rectangle([(ig_x, ig_y), (ig_x + 42, ig_y + 42)], radius=10, outline=white, width=4)
    draw.ellipse([(ig_x + 11, ig_y + 11), (ig_x + 31, ig_y + 31)], outline=white, width=4)
    draw.ellipse([(ig_x + 31, ig_y + 6), (ig_x + 36, ig_y + 11)], fill=white)

    # 3. X icon
    draw.text((515, y_center - 25), "X", fill=white, font=icon_font)

    # 4. LinkedIn 'in'
    draw.text((615, y_center - 25), "in", fill=white, font=icon_font)

    # 5. YouTube rounded play button
    yt_x, yt_y = 720, y_center - 18
    draw.rounded_rectangle([(yt_x, yt_y), (yt_x + 52, yt_y + 38)], radius=10, fill=white)
    draw.polygon([(yt_x + 20, yt_y + 10), (yt_x + 20, yt_y + 28), (yt_x + 36, yt_y + 19)], fill=black)

def build_poster(data, src_img):
    base_img = transform_source_image(src_img)

    # Top-left dark vignette for IntelliNews logo readability + bottom gradient for text
    gradient = Image.new("RGBA", (1080, 1350), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)
    for y in range(0, 220):
        alpha = int(max(0, (1 - (y / 220)) * 140))
        g_draw.line([(0, y), (450, y)], fill=(0, 0, 0, alpha))

    for y in range(480, 1350):
        alpha = int(min(252, ((y - 480) / 580) * 252))
        g_draw.line([(0, y), (1080, y)], fill=(5, 5, 8, alpha))

    canvas = Image.alpha_composite(base_img, gradient).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # Top-left IntelliNews branding with yellow underline
    logo_font = get_font(44)
    draw.text((45, 45), "IntelliNews", fill=(255, 255, 255), font=logo_font)
    logo_bbox = draw.textbbox((45, 45), "IntelliNews", font=logo_font)
    draw.rectangle([(45, logo_bbox[3] + 8), (logo_bbox[2], logo_bbox[3] + 15)], fill=(255, 204, 0))

    raw_lines = [
        (data.get("line1_yellow", ""), True, 68),
        (data.get("line2_white", ""), False, 82),
        (data.get("line3_yellow", ""), True, 76),
        (data.get("line4_white", ""), False, 74),
        (data.get("line5_white", ""), False, 74)
    ]

    rendered = []
    total_h = 0
    for text, is_yellow, target_sz in raw_lines:
        if not text:
            continue
        font, bbox = fit_text_font(draw, text, target_size=target_sz, max_width=980)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        step = (h + 44) if is_yellow else (h + 26)
        rendered.append((text, is_yellow, font, bbox, w, h, step))
        total_h += step

    y_cursor = max(640, 1215 - total_h)
    for text, is_yellow, font, bbox, w, h, step in rendered:
        x = (1080 - w) // 2
        if is_yellow:
            pad_x, pad_y = 26, 15
            draw.rectangle(
                [(x - pad_x, y_cursor - pad_y), (x + w + pad_x, y_cursor + h + pad_y)],
                fill=(255, 204, 0)
            )
            draw.text((x - bbox[0], y_cursor - bbox[1]), text, fill=(10, 10, 10), font=font)
        else:
            draw.text((x - bbox[0] + 4, y_cursor - bbox[1] + 4), text, fill=(0, 0, 0), font=font)
            draw.text((x - bbox[0], y_cursor - bbox[1]), text, fill=(255, 255, 255), font=font)
        y_cursor += step

    draw_social_footer(draw, 1280)

    out_path = "news_graphic.jpg"
    canvas.save(out_path, quality=95)
    return out_path

def post_to_facebook(caption, image_path, link):
    url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos"
    full_caption = f"{caption}\n\nSource: {link}"
    with open(image_path, "rb") as img:
        res = requests.post(
            url,
            data={"caption": full_caption, "access_token": FB_ACCESS_TOKEN},
            files={"source": img},
            timeout=30
        )
    print("Facebook Response:", res.json())
    res.raise_for_status()

if __name__ == "__main__":
    category, title, link, summary, src_img, img_url = fetch_news_with_source_image()
    print(f"1. Fetched [{category}]: {title}")
    print(f"2. Downloaded Original Source Image: {img_url}")
    ai_data = generate_ai_content(category, title, summary)
    img_path = build_poster(ai_data, src_img)
    print(f"3. Generated Poster with Source Image: {img_path}")
    if FB_PAGE_ID and FB_ACCESS_TOKEN:
        post_to_facebook(ai_data["caption"], img_path, link)
