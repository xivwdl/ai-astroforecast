import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError
from urllib.parse import urlsplit

from astronomy import calculate, publication_date
from photos import select_photo
from upstream import get_json

DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()
EPHE_DIR = Path(os.environ.get("EPHE_DIR", "ephe")).resolve()
DEFAULT_MODEL = "glm-4.7-flash"
SECTIONS = ("overview", "moon", "advice")
PROMPT = """
Write one short astrology column from the supplied calculated facts. Write the
Russian version and a natural English translation with the same claims. Return
a JSON object with two keys, "en" and "ru". Each language must have exactly three
non-empty plain-text strings with the keys "overview", "moon", and "advice".
Each string is one paragraph, with no heading, list, line break, or markup.
Use about 120–160 words total per language.

Overview: connect the most relevant facts to ordinary situations.
Moon: describe the traditional astrological interpretation of the given sign.
Advice: give one practical suggestion that follows from the overview.
Never invent degrees, sign changes, aspects, eclipses or planet positions.
Present interpretations as astrology, without scientific or categorical claims.
Avoid giving medical, legal or financial directions. Do not mention the format.
"""


def latest_edition(directory=DATA_DIR):
    try:
        with (directory / "latest.json").open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return None


def generate(day, facts, model, api_key):
    data = {
        "date": day.isoformat(),
        "reference": facts["reference"],
        "moon_sign": facts["moon_sign"][0],
        "moon_phase": facts["moon_phase"][0],
        "eclipses": [item[0] for item in facts["eclipses"]],
        "retrograde": [item[0] for item in facts["retrograde"]],
    }
    result = get_json(
        "https://api.z.ai/api/paas/v4/chat/completions",
        payload={
            "model": model,
            "messages": [
                {"role": "system", "content": PROMPT.strip()},
                {"role": "user", "content": json.dumps(data)},
            ],
            "temperature": 0.7,
            "max_tokens": 1800,
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        },
        token=api_key,
        timeout=75,
    )
    choice = result["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Z.ai did not finish the forecast")
    return validate_forecast(json.loads(choice["message"]["content"]))


def validate_forecast(forecast):
    if not isinstance(forecast, dict) or set(forecast) != {"en", "ru"}:
        raise ValueError("The forecast must contain both languages")
    for language, sections in forecast.items():
        if not isinstance(sections, dict) or set(sections) != set(SECTIONS):
            raise ValueError(f"Invalid forecast sections for {language}")
        for key, value in sections.items():
            if not isinstance(value, str) or not 20 <= len(value.strip()) <= 1400:
                raise ValueError(f"Invalid forecast paragraph for {language}/{key}")
            sections[key] = " ".join(value.split())
        if language == "ru" and not any("а" <= char.lower() <= "я" for char in sections["overview"]):
            raise ValueError("The Russian forecast is missing")
    return forecast


def write_atomic(path, content):
    handle = NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def publish(now=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (DATA_DIR / ".publish.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another publication is running")
            return

        day = publication_date(now or datetime.now(UTC))
        previous = latest_edition(DATA_DIR) or {}
        if previous.get("date", "") >= day.isoformat():
            print(f"Edition {day} already published")
            return

        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set ZAI_API_KEY in the runtime environment")
        model = os.environ.get("ZAI_MODEL", DEFAULT_MODEL)
        facts = calculate(day, EPHE_DIR)
        photo, image = select_photo(day, previous.get("photo", {}))
        forecast = generate(day, facts, model, api_key)

        images = DATA_DIR / "photos"
        images.mkdir(exist_ok=True)
        write_atomic(images / photo["file"], image)
        edition = {
            "date": day.isoformat(), "facts": facts, "forecast": forecast,
            "photo": photo, "model": model,
        }
        payload = json.dumps(edition, ensure_ascii=False).encode()
        # The page switches editions only after its immutable photo is on disk.
        write_atomic(DATA_DIR / "latest.json", payload)
        print(f"Published {day} with {photo['source']}")


def describe_http_error(error):
    host = urlsplit(error.url).hostname
    service = {"api.z.ai": "Z.ai", "science.nasa.gov": "NASA APOD"}.get(host, "Upstream")
    message = f"{service} returned HTTP {error.code}"
    if service == "Z.ai":
        try:
            payload = json.loads(error.read(8192))
            code = payload["error"]["code"]
            if isinstance(code, (str, int)) and str(code).isascii() and str(code).isdigit() and len(str(code)) <= 8:
                message += f" (Z.ai code {code})"
        except (OSError, ValueError, KeyError, TypeError):
            pass
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if retry_after and retry_after.isascii() and retry_after.isdigit() and len(retry_after) <= 8:
        message += f", retry after {retry_after} seconds"
    return message


if __name__ == "__main__":
    try:
        publish()
    except HTTPError as error:
        raise SystemExit(f"Publication failed: {describe_http_error(error)}") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as error:
        raise SystemExit(f"Publication failed: {error}") from None
