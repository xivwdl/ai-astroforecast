from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import swisseph as swe

MOSCOW = ZoneInfo("Europe/Moscow")
NEW_YORK = ZoneInfo("America/New_York")
WEEKDAYS = (
    ("Monday", "понедельник"), ("Tuesday", "вторник"), ("Wednesday", "среда"),
    ("Thursday", "четверг"), ("Friday", "пятница"), ("Saturday", "суббота"),
    ("Sunday", "воскресенье"),
)

SIGNS = (
    ("Aries", "Овен"), ("Taurus", "Телец"), ("Gemini", "Близнецы"),
    ("Cancer", "Рак"), ("Leo", "Лев"), ("Virgo", "Дева"),
    ("Libra", "Весы"), ("Scorpio", "Скорпион"), ("Sagittarius", "Стрелец"),
    ("Capricorn", "Козерог"), ("Aquarius", "Водолей"), ("Pisces", "Рыбы"),
)
PLANETS = (
    (swe.MERCURY, "Mercury", "Меркурий"), (swe.VENUS, "Venus", "Венера"),
    (swe.MARS, "Mars", "Марс"), (swe.JUPITER, "Jupiter", "Юпитер"),
    (swe.SATURN, "Saturn", "Сатурн"),
)
PHASES = {
    "new": ("Near new moon", "Близко к новолунию"),
    "waxing": ("Waxing Moon", "Растущая Луна"),
    "full": ("Near full moon", "Близко к полнолунию"),
    "waning": ("Waning Moon", "Убывающая Луна"),
}


def publication_date(now):
    moscow_date = now.astimezone(MOSCOW).date()
    apod_day = (now.astimezone(NEW_YORK) - timedelta(minutes=15)).date()
    return min(moscow_date, apod_day)


def julian_day(when):
    utc = when.astimezone(UTC)
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    return swe.julday(utc.year, utc.month, utc.day, hour)


def position(jd, body):
    values, flags = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED)
    if not flags & swe.FLG_SWIEPH:
        raise RuntimeError("Swiss Ephemeris data files are missing or unreadable")
    return values


def lunar_phase(elongation):
    if elongation <= 5 or elongation >= 355:
        return "new"
    if abs(elongation - 180) <= 5:
        return "full"
    return "waxing" if elongation < 180 else "waning"


def calculate(day, ephemeris_path):
    swe.set_ephe_path(str(ephemeris_path))
    start = datetime.combine(day, time.min, MOSCOW)
    end = datetime.combine(day + timedelta(days=1), time.min, MOSCOW)
    reference = datetime.combine(day, time(12), MOSCOW)
    start_jd, end_jd, reference_jd = map(julian_day, (start, end, reference))

    start_sign = int((position(start_jd, swe.MOON)[0] % 360) // 30)
    next_sign = (start_sign + 1) % len(SIGNS)
    crossing_jd = swe.mooncross_ut(next_sign * 30, start_jd, swe.FLG_SWIEPH)
    moon_transition = None
    if start_jd <= crossing_jd < end_jd:
        crossing = start.astimezone(UTC) + timedelta(days=crossing_jd - start_jd)
        moon_transition = {
            "from": SIGNS[start_sign], "to": SIGNS[next_sign],
            "at": crossing.astimezone(MOSCOW).isoformat(timespec="seconds"),
        }

    moon = position(reference_jd, swe.MOON)[0] % 360
    sun = position(reference_jd, swe.SUN)[0]
    retrograde = [
        (en, ru) for body, en, ru in PLANETS if position(reference_jd, body)[3] < 0
    ]
    eclipses = []
    for search, en, ru in (
        (swe.sol_eclipse_when_glob, "Solar eclipse", "Солнечное затмение"),
        (swe.lun_eclipse_when, "Lunar eclipse", "Лунное затмение"),
    ):
        flags, times = search(start_jd - 1 / 86400, swe.FLG_SWIEPH)
        if flags > 0 and start_jd <= times[0] < end_jd:
            eclipses.append((en, ru))

    return {
        "reference": reference.isoformat(),
        "weekday": WEEKDAYS[day.weekday()],
        "moon_sign": SIGNS[int(moon // 30)],
        "moon_transition": moon_transition,
        "moon_phase": PHASES[lunar_phase((moon - sun) % 360)],
        "eclipses": eclipses,
        "retrograde": retrograde,
    }
