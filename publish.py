import fcntl
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlsplit

from astronomy import WEEKDAYS, calculate, publication_date
from photos import select_photo
from upstream import get_json

DATA_DIR = Path(os.environ.get("DATA_DIR", "data")).resolve()
EPHE_DIR = Path(os.environ.get("EPHE_DIR", "ephe")).resolve()
DEFAULT_MODEL = "glm-4.7-flash"
ZAI_URL = "https://api.z.ai/api/paas/v4/chat/completions"
SECTIONS = ("overview", "moon", "advice")
WEEKDAY_WORDS = {
    en.lower(): index for index, (en, _) in enumerate(WEEKDAYS)
}
WEEKDAY_WORDS.update({
    word: index
    for index, forms in enumerate((
        "понедельник понедельника понедельнику понедельником понедельнике",
        "вторник вторника вторнику вторником вторнике",
        "",  # «Среда» also means environment. Match calendar phrases below.
        "четверг четверга четвергу четвергом четверге",
        "пятница пятницы пятницу пятницей пятнице пятницею",
        "суббота субботы субботу субботой субботою субботе",
        "воскресенье воскресенья воскресенью воскресеньем воскресении",
    ))
    for word in forms.split()
})
PROMPT = """
Напиши короткий астрологический прогноз на указанную в данных дату на основе переданных показателей.

**Задача**
Создай цельный, содержательный прогноз на день в стиле современной астрологической колонки. Не перечисляй астрологические показатели механически, а интерпретируй их и объясняй, как они могут проявляться в повседневных ситуациях.

**Структура**

**Обзор дня**
Выдели 1–2 наиболее значимых астрологических фактора и свяжи их в единый прогноз. Учитывай фазу Луны, ретроградность планет и затмения, если они присутствуют в данных. Объясни, какие занятия, решения и формы общения сегодня могут быть более уместны, а какие лучше отложить. Избегай общих фраз, которые подходят для любого дня.

**Луна в знаке**
Объясни, какой эмоциональный фон и характер поведения традиционно связывают с текущим положением Луны. Если в данных есть переход Луны в другой знак, опиши оба знака и различие между частями дня. Время перехода указано по Москве. Если перехода в данных нет, опирайся на знак Луны на момент расчёта. Не придумывай точные градусы и переходы.

**Совет дня**
Дай одну конкретную, практически применимую рекомендацию, которая логически следует из обзора. Не повторяй предыдущие формулировки.

**Правила**
- Используй только предоставленные астрологические данные. Не придумывай аспекты, градусы, положения планет и события.
- Если упоминаешь день недели, используй только день недели из данных и его правильный перевод.
- Расставляй акценты по значимости. Не нужно упоминать каждый показатель, если он не влияет на основную мысль.
- Если данных для какого-то вывода недостаточно, не делай этот вывод.
- Пиши простым, живым и уверенным языком, без эзотерического пафоса, мистики и категоричных предсказаний.
- Формулируй интерпретации как астрологические трактовки, а не научно установленные причинно-следственные связи.
- Избегай штампов вроде «прислушайтесь к себе», «Вселенная подсказывает» и «день идеально подходит для».
- Не используй списки внутри разделов. Каждый раздел — один небольшой связный абзац.
- Общий объём — 120–160 слов на каждом языке.
- Не добавляй вступление, заключение или пояснения о методе.

**Формат ответа**
Сначала напиши прогноз по-русски, затем дай естественный английский перевод с теми же фактами и рекомендациями. Верни один JSON-объект с ключами "ru" и "en". В каждом языке должны быть три строковых поля: "overview" — обзор дня, "moon" — Луна в знаке, "advice" — совет дня. Значение каждого поля — один абзац обычного текста без заголовка и разметки.
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
        "weekday": {"ru": facts["weekday"][1], "en": facts["weekday"][0]},
        "reference_moscow": facts["reference"],
        "moon_sign_at_reference": facts["moon_sign"][1],
        "moon_phase": facts["moon_phase"][1],
        "moon_transition": None,
        "eclipses": [item[1] for item in facts["eclipses"]],
        "retrograde": [item[1] for item in facts["retrograde"]],
    }
    if (transition := facts["moon_transition"]) is not None:
        data["moon_transition"] = {
            "from": transition["from"][1], "to": transition["to"][1],
            "time_moscow": datetime.fromisoformat(transition["at"]).strftime("%H:%M"),
        }
    result = request_forecast(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": PROMPT.strip()},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
            "temperature": 0.7,
            "max_tokens": 1800,
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        },
        api_key,
    )
    choice = result["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Z.ai did not finish the forecast")
    return validate_forecast(json.loads(choice["message"]["content"]), day.weekday())


def validate_forecast(forecast, weekday):
    if not isinstance(forecast, dict) or set(forecast) != {"en", "ru"}:
        raise ValueError("The forecast must contain both languages")
    for language, sections in forecast.items():
        if not isinstance(sections, dict) or set(sections) != set(SECTIONS):
            raise ValueError(f"Invalid forecast sections for {language}")
        for key, value in sections.items():
            if not isinstance(value, str) or not 20 <= len(value.strip()) <= 1400:
                raise ValueError(f"Invalid forecast paragraph for {language}/{key}")
            text = value.casefold()
            words = re.findall(r"[^\W\d_]+", text)
            wrong_wednesday = weekday != 2 and re.search(r"\b(?:в среду|к среде|со среды|сегодня\s*[—–-]?\s*среда)\b", text)
            if wrong_wednesday or any(WEEKDAY_WORDS.get(word, weekday) != weekday for word in words):
                raise ValueError(f"Incorrect weekday in {language}/{key}")
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
        previous_day = previous.get("date", "")
        same_day = previous_day == day.isoformat()
        if previous_day > day.isoformat() or (same_day and "weekday" in previous["facts"]):
            print(f"Edition {day} already published")
            return

        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set ZAI_API_KEY in the runtime environment")
        model = os.environ.get("ZAI_MODEL", DEFAULT_MODEL)
        facts = calculate(day, EPHE_DIR)
        images = DATA_DIR / "photos"
        previous_photo = previous.get("photo", {})
        if same_day and (images / previous_photo.get("file", "")).is_file():
            photo, image = previous_photo, None
        else:
            photo, image = select_photo(day, previous_photo if not same_day else {})
        forecast = generate(day, facts, model, api_key)

        if image is not None:
            images.mkdir(exist_ok=True)
            write_atomic(images / photo["file"], image)
        edition = {
            "date": day.isoformat(), "facts": facts, "forecast": forecast,
            "photo": photo, "model": model, "published_at": datetime.now(UTC).isoformat(),
        }
        payload = json.dumps(edition, ensure_ascii=False).encode()
        # The page switches editions only after its immutable photo is on disk.
        write_atomic(DATA_DIR / "latest.json", payload)
        print(f"Published {day} with {photo['source']}")


def zai_error_code(error):
    try:
        with error:
            code = json.loads(error.read(8192))["error"]["code"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if isinstance(code, (str, int)) and str(code).isascii() and str(code).isdigit() and len(str(code)) <= 8:
        return str(code)
    return None


def retry_after_seconds(error):
    value = error.headers.get("Retry-After") if error.headers else None
    if value and value.isascii() and value.isdigit() and len(value) <= 8:
        return int(value)
    return None


def describe_http_error(error, zai_code=None):
    host = urlsplit(error.url).hostname
    service = {"api.z.ai": "Z.ai", "science.nasa.gov": "NASA APOD"}.get(host, "Upstream")
    message = f"{service} returned HTTP {error.code}"
    if zai_code:
        message += f" (Z.ai code {zai_code})"
    if (retry_after := retry_after_seconds(error)) is not None:
        message += f", retry after {retry_after} seconds"
    return message


def request_forecast(payload, api_key):
    for retry_delay in (3, 8, None):
        try:
            return get_json(ZAI_URL, payload=payload, token=api_key, timeout=75)
        except HTTPError as error:
            code = zai_error_code(error)
            message = describe_http_error(error, code)
            if error.code != 429 or code != "1305" or retry_delay is None:
                raise RuntimeError(message) from None

            delay = max(retry_delay, retry_after_seconds(error) or 0)
            if delay > 15:
                raise RuntimeError(message) from None
            print(f"{message}. Retrying in {delay} seconds.", flush=True)
            sleep(delay)


if __name__ == "__main__":
    try:
        publish()
    except HTTPError as error:
        raise SystemExit(f"Publication failed: {describe_http_error(error)}") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as error:
        raise SystemExit(f"Publication failed: {error}") from None
