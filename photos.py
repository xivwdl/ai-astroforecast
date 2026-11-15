import re
from hashlib import sha256
from html import unescape
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image, ImageOps

from upstream import get_json, request_bytes

APOD = "https://science.nasa.gov"
ARTICLE_HOSTS = {"science.nasa.gov", "apod.nasa.gov"}
PHOTO_HOSTS = {"assets.science.nasa.gov", "science.nasa.gov", "apod.nasa.gov"}
IMAGE_LIMIT = 20 * 1024 * 1024


def clean_text(value):
    return " ".join(unescape(re.sub(r"<[^>]+>", "", value or "")).split())


def nasa_url(value, hosts):
    if not isinstance(value, str):
        return False
    url = urlsplit(value)
    return url.scheme == "https" and url.netloc in hosts


def apod_entries(day):
    fields = "date,media_type,hdurl,title,alt,permalink,credit,copyright"
    entries = get_json(f"{APOD}/wp-json/wp/v2/apod-basic?per_page=14&_fields={fields}")
    day = day.isoformat()
    today = next((entry for entry in entries if entry["date"] == day), None)
    if today is None:
        raise RuntimeError(f"NASA APOD has not published {day} yet")
    if today["media_type"] == "image":
        return [today]
    return sorted(
        (entry for entry in entries if entry["date"] < day and entry["media_type"] == "image"),
        key=lambda entry: entry["date"],
        reverse=True,
    )[:5]


def prepare_image(url):
    raw = request_bytes(url, limit=IMAGE_LIMIT, redirect_hosts=PHOTO_HOSTS)
    with Image.open(BytesIO(raw)) as source:
        if source.format not in {"JPEG", "PNG", "GIF", "WEBP"}:
            raise ValueError("Unsupported NASA image format")
        if source.width * source.height > 30_000_000:
            raise ValueError("NASA image is too large")
        source.thumbnail((1800, 1800))
        image = ImageOps.exif_transpose(source).convert("RGB")
    result = BytesIO()
    image.save(result, format="JPEG", quality=87, optimize=True)
    return result.getvalue(), image.size


def select_photo(day, previous):
    entries = apod_entries(day)
    for entry in entries:
        url = entry.get("hdurl")
        link = entry.get("permalink")
        if not nasa_url(url, PHOTO_HOSTS) or not nasa_url(link, ARTICLE_HOSTS):
            continue
        if entry["date"] != day.isoformat() and url == previous.get("url"):
            continue
        try:
            data, (width, height) = prepare_image(url)
        except (OSError, ValueError, Image.DecompressionBombError):
            continue
        filename = f"{sha256(data).hexdigest()}.jpg"
        if entry["date"] != day.isoformat() and filename == previous.get("file"):
            continue

        title = clean_text(entry.get("title")) or "NASA Astronomy Picture of the Day"
        credit = clean_text(entry.get("credit"))
        copyright_notice = clean_text(entry.get("copyright"))
        attribution = " · ".join(dict.fromkeys(filter(None, (credit, copyright_notice))))
        return {
            "url": url, "link": link, "source": "NASA APOD", "credit": attribution,
            "date": entry["date"], "title": title, "file": filename,
            "alt": (clean_text(entry.get("alt")) or title, f"Фото NASA APOD — {title}"),
            "width": width, "height": height,
        }, data

    raise RuntimeError(f"No usable NASA APOD image is available for {day}")
