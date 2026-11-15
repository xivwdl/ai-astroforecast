import os
import re
from datetime import date, datetime

from flask import Flask, make_response, render_template, send_from_directory

from astronomy import WEEKDAYS
from publish import DATA_DIR, latest_edition

app = Flask(__name__, template_folder=".")

SOURCE_URL = "https://github.com/xivwdl/ai-astroforecast"
MONTHS_EN = "January February March April May June July August September October November December".split()
MONTHS_RU = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()


def format_date(iso_date):
    day = date.fromisoformat(iso_date)
    weekday_en, weekday_ru = WEEKDAYS[day.weekday()]
    return (
        f"{weekday_en}, {day.day} {MONTHS_EN[day.month - 1]} {day.year}",
        f"{weekday_ru.capitalize()}, {day.day} {MONTHS_RU[day.month - 1]} {day.year}",
    )


def format_moon_sign(facts):
    transition = facts.get("moon_transition")
    if transition is None:
        return facts["moon_sign"]
    time = datetime.fromisoformat(transition["at"]).strftime("%H:%M")
    return [
        f"{transition['from'][i]} → {transition['to'][i]} ({time} {zone})"
        for i, zone in enumerate(("MSK", "МСК"))
    ]


def format_list(items, empty):
    return [", ".join(item[i] for item in items) or empty[i] for i in range(2)]


@app.get("/")
def home():
    edition = latest_edition()
    if edition is None:
        return "", 503, {"Cache-Control": "no-store", "Retry-After": "900"}

    day = edition["date"]
    facts = edition["facts"]
    revision = os.environ.get("SOURCE_COMMIT", "")
    source = f"{SOURCE_URL}/tree/{revision}" if re.fullmatch(r"[a-f0-9]{40}", revision) else SOURCE_URL
    response = make_response(render_template(
        "index.html", edition=edition, labels=format_date(day), source=source,
        moon_sign=format_moon_sign(facts),
        eclipses=format_list(facts["eclipses"], ("No solar or lunar eclipses", "Солнечных и лунных нет")),
        retrograde=format_list(facts["retrograde"], ("None", "Нет")),
    ))
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/edition")
def current_edition():
    edition = latest_edition()
    if edition is None:
        return "", 200, {"Cache-Control": "no-store"}
    return edition["date"], 200, {
        "Cache-Control": "no-store",
        "X-Edition-Revision": edition.get("published_at", ""),
    }


@app.get("/photos/<filename>")
def photo(filename):
    if not re.fullmatch(r"[a-f0-9]{64}\.jpg", filename):
        return "", 404
    response = send_from_directory(DATA_DIR / "photos", filename, max_age=31_536_000)
    response.cache_control.immutable = True
    return response


@app.get("/health")
def health():
    return "OK"
