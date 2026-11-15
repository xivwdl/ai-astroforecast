import re
from datetime import date, datetime
from hashlib import sha256
from html import unescape
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image, ImageOps

from upstream import get_json, request_bytes

APOD = "https://science.nasa.gov"
EPIC = "https://epic.gsfc.nasa.gov"
PHOTO_HOSTS = {"assets.science.nasa.gov", "apod.nasa.gov", "epic.gsfc.nasa.gov"}
NASA_CREDITS = {"NASA", "NASA/JPL", "NASA/JPL-Caltech", "NASA/GSFC", "NASA Goddard"}
IMAGE_LIMIT = 20 * 1024 * 1024


def clean_text(value):
    return " ".join(unescape(re.sub(r"<[^>]+>", "", value or "")).split())


def nasa_url(value, hosts):
    if not isinstance(value, str):
        return False
    url = urlsplit(value)
    return url.scheme == "https" and url.netloc in hosts


def apod_photo(day):
    fields = "date,media_type,hdurl,title,alt,permalink,credit,copyright"
    entries = get_json(f"{APOD}/wp-json/wp/v2/apod-basic?per_page=7&_fields={fields}")
    for entry in entries:
        credit = clean_text(entry.get("credit"))
        link = entry.get("permalink")
        image = entry.get("hdurl")
        if (
            entry.get("date") == day.isoformat()
            and entry.get("media_type") == "image"
            and not clean_text(entry.get("copyright"))
            and credit in NASA_CREDITS
            and nasa_url(link, {"science.nasa.gov", "apod.nasa.gov"})
            and nasa_url(image, PHOTO_HOSTS)
        ):
            title = clean_text(entry.get("title")) or "NASA Astronomy Picture of the Day"
            return {
                "url": image, "link": link, "source": "NASA APOD", "credit": credit,
                "date": day.isoformat(), "title": title,
                "alt": (clean_text(entry.get("alt")) or title, f"Фото NASA APOD — {title}"),
            }
    return None


def epic_photos(day, previous_url):
    entries = get_json(f"{EPIC}/api/natural")
    candidates = []
    for entry in sorted(entries, key=lambda item: item["date"], reverse=True):
        captured = datetime.fromisoformat(entry["date"]).date()
        image = entry["image"]
        if captured > day or not re.fullmatch(r"epic_1b_\d{14}", image):
            continue
        url = f"{EPIC}/archive/natural/{captured:%Y/%m/%d}/jpg/{image}.jpg"
        if url != previous_url:
            candidates.append((captured, url))
    if not candidates:
        raise RuntimeError("NASA EPIC has no new eligible Earth photo")

    # Spread selections across available views when the archive lags for several days.
    index = (day - date.min).days % len(candidates)
    for captured, url in (candidates[index:] + candidates[:index])[:3]:
        yield {
            "url": url, "link": f"{EPIC}/?date={captured.isoformat()}",
            "source": "NASA EPIC", "credit": "NASA EPIC Team",
            "date": captured.isoformat(), "title": "Earth from DSCOVR",
            "alt": ("Earth seen from DSCOVR", "Земля со спутника DSCOVR"),
        }


def prepare_image(url):
    raw = request_bytes(url, limit=IMAGE_LIMIT, redirect_hosts=PHOTO_HOSTS)
    with Image.open(BytesIO(raw)) as source:
        if source.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Unsupported NASA image format")
        if source.width * source.height > 30_000_000:
            raise ValueError("NASA image is too large")
        source.thumbnail((1800, 1800))
        image = ImageOps.exif_transpose(source).convert("RGB")
    result = BytesIO()
    image.save(result, format="JPEG", quality=87, optimize=True)
    return result.getvalue(), image.size


def select_photo(day, previous):
    previous_url = previous.get("url")
    previous_file = previous.get("file")
    try:
        candidate = apod_photo(day)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"NASA APOD feed unavailable ({type(error).__name__})", flush=True)
        candidate = None

    def prepare(photo):
        if photo["url"] == previous_url:
            return None
        try:
            data, (width, height) = prepare_image(photo["url"])
        except (OSError, ValueError, Image.DecompressionBombError):
            return None
        filename = f"{sha256(data).hexdigest()}.jpg"
        if filename == previous_file:
            return None
        return {**photo, "file": filename, "width": width, "height": height}, data

    if candidate and (result := prepare(candidate)):
        return result
    for photo in epic_photos(day, previous_url):
        if result := prepare(photo):
            return result
    raise RuntimeError("No new NASA image could be downloaded and decoded")
