#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Код Жизни — сервер расчётов
Запуск: python server.py
Порт: http://localhost:5050
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import ephem
import math
import random
import hmac
import hashlib
from datetime import datetime, timedelta
import requests as http_requests
import anthropic
import os

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# ── Детектор кризисных маркеров в запросе пользователя ──
# Не номер телефона (он устаревает, мы это проверили на практике —
# линия в Германии перестала работать за 5 дней) — просто честная
# рекомендация обратиться к живому специалисту, если есть явные признаки.
CRISIS_MARKERS = [
    'не хочу жить', 'не вижу смысла жить', 'незачем жить', 'не понимаю, зачем живу',
    'никому не нужна', 'никому не нужен', 'хочу умереть', 'покончить с собой',
    'не хочу больше жить', 'нет сил жить',
    'не хочу жити', 'не бачу сенсу жити', 'нема сенсу жити', 'не розумію, навіщо живу',
    'нікому не потрібна', 'нікому не потрібен', 'хочу померти', 'покінчити з собою',
    "don't want to live", 'no reason to live', 'want to die', 'kill myself',
    'nie chcę żyć', 'nie widzę sensu', 'chcę umrzeć',
]

CRISIS_ADDENDUM = {
    'Отвечай на русском языке.': "\n\n---\nТо, что ты сейчас написал(а), звучит по-настоящему тяжело. Пожалуйста, не оставайся с этим один(одна) — поговори с близким человеком или специалистом, который умеет помогать именно в такие моменты. Я готов быть рядом в разговоре, но не могу заменить живую поддержку, когда она нужна по-настоящему.",
    'Відповідай українською мовою.': "\n\n---\nТе, що ти зараз написав(ла), звучить по-справжньому важко. Будь ласка, не залишайся з цим наодинці — поговори з близькою людиною або зі спеціалістом, який вміє допомагати саме в такі моменти. Я готовий бути поруч у розмові, але не можу замінити живу підтримку, коли вона потрібна по-справжньому.",
    'Odpowiadaj po polsku.': "\n\n---\nTo, co właśnie napisałeś/aś, brzmi naprawdę ciężko. Proszę, nie zostawaj z tym sam(a) — porozmawiaj z bliską osobą lub specjalistą, który potrafi pomóc właśnie w takich chwilach. Chętnie porozmawiam, ale nie zastąpię prawdziwego wsparcia, gdy jest ono naprawdę potrzebne.",
    'Respond in English.': "\n\n---\nWhat you just wrote sounds genuinely heavy. Please don't carry this alone — talk to someone close to you or a professional who knows how to help in moments like this. I'm glad to be here for the conversation, but I can't replace real support when it's truly needed.",
}

def detect_crisis(text):
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in CRISIS_MARKERS)

# ── Firebase Admin — "касса" анализов на сервере ──
import base64
import json as _json

firebase_db_available = False
try:
    import firebase_admin
    from firebase_admin import credentials, db as fb_db

    _key_b64 = os.environ.get('FIREBASE_KEY_B64', '')
    if _key_b64:
        _key_json = _json.loads(base64.b64decode(_key_b64))
        _cred = credentials.Certificate(_key_json)
        firebase_admin.initialize_app(_cred, {
            'databaseURL': 'https://aion-vi-default-rtdb.europe-west1.firebasedatabase.app'
        })
        firebase_db_available = True
        print("✅ Firebase Admin подключён — касса на сервере активна")
    else:
        print("⚠️ FIREBASE_KEY_B64 не задан — касса работает в старом режиме (небезопасно)")
except Exception as e:
    print(f"⚠️ Firebase Admin не подключился: {e}")

def email_to_key(email):
    """Тот же формат ключа, что и во фронтенде (index.html emailToKey)."""
    return email.replace('.', '_').replace('@', '__at__')

def get_analyses_left(email):
    """Возвращает остаток анализов пользователя или None, если не найден/база недоступна."""
    if not firebase_db_available or not email:
        return None
    try:
        key = email_to_key(email)
        val = fb_db.reference(f'users/{key}/analysesLeft').get()
        return val if isinstance(val, (int, float)) else None
    except Exception:
        return None

def decrement_analysis(email):
    """Списывает 1 анализ атомарно (безопасно даже при параллельных запросах)."""
    if not firebase_db_available or not email:
        return
    try:
        key = email_to_key(email)
        ref = fb_db.reference(f'users/{key}/analysesLeft')
        ref.transaction(lambda current: max(0, (current or 0) - 1))
    except Exception as e:
        print(f"⚠️ Не удалось списать анализ: {e}")

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
# КОНСТАНТЫ
# ─────────────────────────────────────────────

ZODIAC_SIGNS_RU = [
    "Овен", "Телец", "Близнецы", "Рак",
    "Лев", "Дева", "Весы", "Скорпион",
    "Стрелец", "Козерог", "Водолей", "Рыбы"
]

STEMS_RU = ["Цзя","И","Бин","Дин","У","Цзи","Гэн","Синь","Жэнь","Гуй"]
BRANCHES_RU = ["Цзы","Чоу","Инь","Мао","Чэнь","Сы","У","Вэй","Шэнь","Ю","Сюй","Хай"]
ANIMALS_RU = ["Крыса","Бык","Тигр","Кролик","Дракон","Змея",
               "Лошадь","Коза","Обезьяна","Петух","Собака","Свинья"]
ELEMENTS_RU = ["Дерево","Дерево","Огонь","Огонь","Земля","Земля",
                "Металл","Металл","Вода","Вода"]

CHINESE_NY = {
    1900:"31.01",1901:"19.02",1902:"08.02",1903:"29.01",1904:"16.02",
    1905:"04.02",1906:"25.01",1907:"13.02",1908:"02.02",1909:"22.01",
    1910:"10.02",1911:"30.01",1912:"18.02",1913:"06.02",1914:"26.01",
    1915:"14.02",1916:"03.02",1917:"23.01",1918:"11.02",1919:"01.02",
    1920:"20.02",1921:"08.02",1922:"28.01",1923:"16.02",1924:"05.02",
    1925:"24.01",1926:"13.02",1927:"02.02",1928:"23.01",1929:"10.02",
    1930:"30.01",1931:"17.02",1932:"06.02",1933:"26.01",1934:"14.02",
    1935:"04.02",1936:"24.01",1937:"11.02",1938:"31.01",1939:"19.02",
    1940:"08.02",1941:"27.01",1942:"15.02",1943:"05.02",1944:"25.01",
    1945:"13.02",1946:"02.02",1947:"22.01",1948:"10.02",1949:"29.01",
    1950:"17.02",1951:"06.02",1952:"27.01",1953:"14.02",1954:"03.02",
    1955:"24.01",1956:"12.02",1957:"31.01",1958:"18.02",1959:"08.02",
    1960:"28.01",1961:"15.02",1962:"05.02",1963:"25.01",1964:"13.02",
    1965:"02.02",1966:"21.01",1967:"09.02",1968:"30.01",1969:"17.02",
    1970:"06.02",1971:"27.01",1972:"15.02",1973:"03.02",1974:"23.01",
    1975:"11.02",1976:"31.01",1977:"18.02",1978:"07.02",1979:"28.01",
    1980:"16.02",1981:"05.02",1982:"25.01",1983:"13.02",1984:"02.02",
    1985:"20.02",1986:"09.02",1987:"29.01",1988:"17.02",1989:"06.02",
    1990:"27.01",1991:"15.02",1992:"04.02",1993:"23.01",1994:"10.02",
    1995:"31.01",1996:"19.02",1997:"07.02",1998:"28.01",1999:"16.02",
    2000:"05.02",2001:"24.01",2002:"12.02",2003:"01.02",2004:"22.01",
    2005:"09.02",2006:"29.01",2007:"18.02",2008:"07.02",2009:"26.01",
    2010:"14.02",2011:"03.02",2012:"23.01",2013:"10.02",2014:"31.01",
    2015:"19.02",2016:"08.02",2017:"28.01",2018:"16.02",2019:"05.02",
    2020:"25.01",2021:"12.02",2022:"01.02",2023:"22.01",2024:"10.02",
    2025:"29.01",2026:"17.02",2027:"06.02",2028:"26.01",2029:"13.02",
    2030:"03.02",2031:"23.01",2032:"11.02",2033:"31.01",2034:"19.02",
    2035:"08.02",2036:"28.01",2037:"15.02",2038:"04.02",2039:"24.01",
    2040:"12.02",2041:"01.02",2042:"22.01",2043:"10.02",
}

HD_GATES = [
    41,19,13,49,30,55,37,63,22,36,25,17,21,51,42,3,
    27,24,2,23,8,20,16,35,45,12,15,52,39,53,62,56,
    31,33,7,4,29,59,40,64,47,6,46,18,48,57,32,50,
    28,44,1,43,14,34,9,5,26,11,10,58,38,54,61,60
]

ARCANA_NAMES = {
    1:"Маг",2:"Жрица",3:"Императрица",4:"Император",5:"Иерофант",
    6:"Влюблённые",7:"Колесница",8:"Сила",9:"Отшельник",10:"Колесо Фортуны",
    11:"Справедливость",12:"Повешенный",13:"Смерть",14:"Умеренность",
    15:"Дьявол",16:"Башня",17:"Звезда",18:"Луна",19:"Солнце",
    20:"Суд",21:"Мир",22:"Шут (0)"
}

CYRILLIC_PYTH = {
    "А":1,"И":1,"С":1,"Ъ":1,
    "Б":2,"Й":2,"Т":2,"Ы":2,
    "В":3,"К":3,"У":3,"Ь":3,
    "Г":4,"Л":4,"Ф":4,"Э":4,
    "Д":5,"М":5,"Х":5,"Ю":5,
    "Е":6,"Н":6,"Ц":6,"Я":6,
    "Ё":7,"О":7,"Ч":7,
    "Ж":8,"П":8,"Ш":8,
    "З":9,"Р":9,"Щ":9,
}

# ─────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ─────────────────────────────────────────────

def deg_to_sign(lon):
    sign_idx = int(lon / 30)
    deg_in_sign = lon - sign_idx * 30
    sign = ZODIAC_SIGNS_RU[sign_idx % 12]
    d = int(deg_in_sign)
    m = int((deg_in_sign - d) * 60)
    return sign, d, m

def format_pos(lon):
    sign, d, m = deg_to_sign(lon)
    return f"{d}°{m:02d}' {sign}"

def reduce_to_9(n, keep_master=True):
    steps = [n]
    while n > 9:
        if keep_master and n in (11, 22, 33):
            break
        n = sum(int(d) for d in str(n))
        steps.append(n)
    return n, steps

def reduce_to_22(n):
    while n > 22:
        n = sum(int(d) for d in str(n))
    return n

def validate_birth_data(data):
    """Проверяет корректность входных данных о рождении.
    Возвращает (day, month, year, hour, minute) или бросает ValueError
    с понятным пользователю сообщением."""
    try:
        day = int(data['day'])
        month = int(data['month'])
        year = int(data['year'])
    except (KeyError, ValueError, TypeError):
        raise ValueError("Проверь дату рождения — день, месяц и год должны быть числами.")

    hour = int(data.get('hour', 12) or 12)
    minute = int(data.get('minute', 0) or 0)

    if not (1 <= month <= 12):
        raise ValueError("Месяц должен быть от 1 до 12.")
    if not (1 <= day <= 31):
        raise ValueError("День должен быть от 1 до 31.")
    if not (1900 <= year <= 2043):
        raise ValueError("Год рождения должен быть между 1900 и 2043.")
    if not (0 <= hour <= 23):
        raise ValueError("Час должен быть от 0 до 23.")
    if not (0 <= minute <= 59):
        raise ValueError("Минуты должны быть от 0 до 59.")

    # Проверка, что такая дата реально существует (напр. не 31 февраля)
    try:
        datetime(year, month, day)
    except ValueError:
        raise ValueError(f"Такой даты не существует: {day:02d}.{month:02d}.{year}. Проверь ввод.")

    return day, month, year, hour, minute

def geocode(place_name):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": place_name, "format": "json", "limit": 1}
        headers = {"User-Agent": "KodZhizni/1.0"}
        r = http_requests.get(url, params=params, headers=headers, timeout=5)
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
    except Exception:
        pass
    return None, None, None

def local_to_ut(year, month, day, hour, minute, lon):
    offset = round(lon / 15)
    total_minutes = hour * 60 + minute - offset * 60
    base = datetime(year, month, day)
    dt_ut = base + timedelta(minutes=total_minutes)
    return dt_ut.year, dt_ut.month, dt_ut.day, dt_ut.hour + dt_ut.minute/60.0

# ─────────────────────────────────────────────
# АСТРОЛОГИЯ — ephem (замена pyswisseph)
# ─────────────────────────────────────────────

EPHEM_PLANETS = {
    "Солнце":   ephem.Sun,
    "Луна":     ephem.Moon,
    "Меркурий": ephem.Mercury,
    "Венера":   ephem.Venus,
    "Марс":     ephem.Mars,
    "Юпитер":   ephem.Jupiter,
    "Сатурн":   ephem.Saturn,
    "Уран":     ephem.Uranus,
    "Нептун":   ephem.Neptune,
}

def get_planet_lon(planet_class, date_str):
    """Возвращает эклиптическую долготу планеты в градусах"""
    p = planet_class()
    p.compute(date_str, epoch='2000')
    # ephem даёт эклиптическую долготу в радианах через ecl_lon
    ecl = ephem.Ecliptic(p, epoch='2000')
    lon = math.degrees(ecl.lon) % 360
    return lon

def datetime_to_ephem_str(year, month, day, h_float):
    """Конвертация в строку для ephem: 'YYYY/MM/DD HH:MM:SS'"""
    hour = int(h_float)
    minute = int((h_float - hour) * 60)
    second = int(((h_float - hour) * 60 - minute) * 60)
    return f"{year}/{month:02d}/{day:02d} {hour:02d}:{minute:02d}:{second:02d}"

def calc_asc_mc(year, month, day, h_float, lat, lon):
    """Асцендент и MC через формулу домов Плацидуса (приближение)"""
    try:
        # Юлианский день
        a = (14 - month) // 12
        y = year + 4800 - a
        m = month + 12*a - 3
        jd = day + (153*m+2)//5 + 365*y + y//4 - y//100 + y//400 - 32045 - 0.5 + h_float/24.0

        # Звёздное время (Greenwich Sidereal Time)
        T = (jd - 2451545.0) / 36525.0
        gst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + T*T*(0.000387933 - T/38710000)
        gst = gst % 360
        lst = (gst + lon) % 360  # местное звёздное время в градусах

        # MC (Midheaven)
        mc_rad = math.atan2(math.tan(math.radians(lst)), math.cos(math.radians(23.4393)))
        mc = math.degrees(mc_rad) % 360

        # Асцендент
        lat_r = math.radians(lat)
        e_r = math.radians(23.4393)
        lst_r = math.radians(lst)
        asc_rad = math.atan2(math.cos(lst_r),
                             -(math.sin(lst_r)*math.cos(e_r) + math.tan(lat_r)*math.sin(e_r)))
        asc = (math.degrees(asc_rad) + 180) % 360

        return asc, mc
    except Exception:
        return None, None

def calc_natal(year, month, day, hour, minute, lat, lon):
    """Натальный расчёт через ephem"""
    y, mo, d, h = local_to_ut(year, month, day, hour, minute, lon)
    date_str = datetime_to_ephem_str(y, mo, d, h)

    planets = {}
    for name, planet_class in EPHEM_PLANETS.items():
        try:
            lon_deg = get_planet_lon(planet_class, date_str)
            sign, deg, mn = deg_to_sign(lon_deg)
            # Ретроградность через угловую скорость (приближение)
            p1 = planet_class()
            p1.compute(date_str, epoch='2000')
            ecl1 = ephem.Ecliptic(p1, epoch='2000')
            lon1 = math.degrees(ecl1.lon) % 360

            # вычисляем положение через 1 день для определения ретро
            dt2 = ephem.Date(ephem.Date(date_str) + 1)
            p2 = planet_class()
            p2.compute(dt2, epoch='2000')
            ecl2 = ephem.Ecliptic(p2, epoch='2000')
            lon2 = math.degrees(ecl2.lon) % 360

            diff = lon2 - lon1
            if diff > 180: diff -= 360
            if diff < -180: diff += 360
            retrograde = diff < 0

            planets[name] = {
                "lon": round(lon_deg, 4),
                "sign": sign,
                "deg": deg,
                "min": mn,
                "formatted": format_pos(lon_deg),
                "retrograde": retrograde
            }
        except Exception as e:
            planets[name] = {"error": str(e)}

    # Асцендент и MC
    houses_data = {}
    asc, mc = calc_asc_mc(y, mo, d, h, lat, lon)
    if asc is not None:
        houses_data["Асцендент"] = {
            "lon": round(asc, 4),
            "formatted": format_pos(asc)
        }
    if mc is not None:
        houses_data["MC (Середина Неба)"] = {
            "lon": round(mc, 4),
            "formatted": format_pos(mc)
        }

    aspects = calc_aspects(planets)

    return {
        "planets": planets,
        "houses": houses_data,
        "aspects": aspects
    }

def calc_aspects(planets):
    ASPECT_TYPES = {
        0: ("Соединение", 8),
        60: ("Секстиль", 6),
        90: ("Квадратура", 8),
        120: ("Трин", 8),
        180: ("Оппозиция", 8),
    }
    aspects = []
    planet_list = [(k, v) for k, v in planets.items() if "lon" in v]
    for i in range(len(planet_list)):
        for j in range(i+1, len(planet_list)):
            n1, p1 = planet_list[i]
            n2, p2 = planet_list[j]
            diff = abs(p1["lon"] - p2["lon"])
            if diff > 180:
                diff = 360 - diff
            for angle, (name, orb) in ASPECT_TYPES.items():
                if abs(diff - angle) <= orb:
                    aspects.append({
                        "planet1": n1,
                        "planet2": n2,
                        "aspect": name,
                        "orb": round(abs(diff - angle), 2)
                    })
    return aspects

# ─────────────────────────────────────────────
# РЕАЛЬНЫЕ ТЕКУЩИЕ ТРАНЗИТЫ — честная замена придуманным датам.
# Считаем настоящие положения планет "сейчас" (или на любую дату)
# и сравниваем их с натальными точками человека. Та же техника ephem,
# что и для натальной карты — просто вторая дата не рождение, а сегодня.
# ─────────────────────────────────────────────

TRANSIT_ASPECT_TYPES = {
    0:   ("Соединение", 2.0),
    60:  ("Секстиль",   1.5),
    90:  ("Квадратура", 2.0),
    120: ("Трин",       2.0),
    180: ("Оппозиция",  2.0),
}

def calc_current_transits(natal_planets, target_date=None):
    """
    Считает реальные положения планет на target_date (готовая ephem-строка)
    и сравнивает с натальными точками человека (natal_planets = calc_natal(...)['planets']).
    Возвращает список активных совпадений с точным орбом (чем меньше орб —
    тем точнее совпадение прямо в эту дату).
    """
    if target_date is None:
        now = datetime.utcnow()
        date_str = datetime_to_ephem_str(now.year, now.month, now.day, 12.0)
    else:
        date_str = target_date

    transits = []
    for t_name, t_class in EPHEM_PLANETS.items():
        try:
            t_lon = get_planet_lon(t_class, date_str)
        except Exception:
            continue
        for n_name, n_data in natal_planets.items():
            if "lon" not in n_data:
                continue
            n_lon = n_data["lon"]
            diff = abs(t_lon - n_lon)
            if diff > 180:
                diff = 360 - diff
            for angle, (aspect_name, orb) in TRANSIT_ASPECT_TYPES.items():
                exact_orb = abs(diff - angle)
                if exact_orb <= orb:
                    transits.append({
                        "transit_planet": t_name,
                        "natal_planet": n_name,
                        "aspect": aspect_name,
                        "orb": round(exact_orb, 2),
                    })
    transits.sort(key=lambda x: x["orb"])
    return transits


def find_transit_windows(natal_planets, days_ahead=60):
    """
    Сканирует ближайшие days_ahead дней и находит РЕАЛЬНЫЕ даты, когда
    транзитная планета входит в точный орб к натальной точке человека.
    Возвращает список конкретных окон — начало, конец, дата пика точности.
    Это и есть настоящая замена придуманным числам: цифры посчитаны, не выдуманы.
    """
    today = datetime.utcnow().date()
    daily_hits = {}

    for offset in range(days_ahead + 1):
        day = today + timedelta(days=offset)
        date_str = datetime_to_ephem_str(day.year, day.month, day.day, 12.0)
        hits = calc_current_transits(natal_planets, target_date=date_str)
        for h in hits:
            key = (h["transit_planet"], h["natal_planet"], h["aspect"])
            daily_hits.setdefault(key, []).append((day, h["orb"]))

    windows = []
    for key, points in daily_hits.items():
        t_name, n_name, aspect = key
        points.sort(key=lambda x: x[0])
        start = prev_day = best_day = points[0][0]
        best_orb = points[0][1]
        for day, orb in points[1:]:
            if (day - prev_day).days > 1:
                windows.append({
                    "transit_planet": t_name, "natal_planet": n_name, "aspect": aspect,
                    "start": start.strftime('%d.%m.%Y'), "end": prev_day.strftime('%d.%m.%Y'),
                    "peak": best_day.strftime('%d.%m.%Y'), "peak_orb": round(best_orb, 2),
                })
                start, best_orb, best_day = day, orb, day
            elif orb < best_orb:
                best_orb, best_day = orb, day
            prev_day = day
        windows.append({
            "transit_planet": t_name, "natal_planet": n_name, "aspect": aspect,
            "start": start.strftime('%d.%m.%Y'), "end": prev_day.strftime('%d.%m.%Y'),
            "peak": best_day.strftime('%d.%m.%Y'), "peak_orb": round(best_orb, 2),
        })

    windows.sort(key=lambda w: w["peak_orb"])
    return windows


# ─────────────────────────────────────────────
# HUMAN DESIGN
# ─────────────────────────────────────────────

HD_WHEEL_START = 302.0  # Колесо Human Design начинается с 302° (2° Водолея = начало Ворот 41),
                         # а не с 0° Овна. Без этого сдвига все ворота считались неверно.

def get_hd_gate(lon):
    shifted = (lon - HD_WHEEL_START) % 360
    idx = int(shifted / (360/64)) % 64
    return HD_GATES[idx]

def get_hd_gate_and_line(lon):
    """Возвращает (номер ворот, номер линии 1-6) с учётом точки отсчёта колеса HD."""
    gate_width = 360/64
    line_width = gate_width/6
    shifted = (lon - HD_WHEEL_START) % 360
    idx = int(shifted / gate_width) % 64
    gate = HD_GATES[idx]
    within_gate = shifted % gate_width
    # Сама сетка линий внутри ворот сдвинута на одну line_width относительно ворот
    # (подтверждено сверкой с эталоном: Крест Инкарнации 3/50 | 41/31 — ворота совпали,
    # линии были смещены ровно на +1 без этой калибровки).
    line_position = (within_gate - line_width) % gate_width
    line = int(line_position / line_width) + 1
    return gate, line

def calc_human_design(year, month, day, hour, minute, lat, lon):
    y, mo, d, h = local_to_ut(year, month, day, hour, minute, lon)
    date_str = datetime_to_ephem_str(y, mo, d, h)
    design_date = ephem.Date(ephem.Date(date_str) - 88)

    # ── Полный список 36 каналов (верифицирован по humandesignhd.com) ──
    # Формат: (gate_a, gate_b) → (center_a, center_b)
    CHANNELS = {
        (1, 8):   ('G', 'Throat'),
        (2, 14):  ('G', 'Sacral'),
        (3, 60):  ('Root', 'Sacral'),
        (4, 63):  ('Ajna', 'Head'),
        (5, 15):  ('Sacral', 'G'),
        (6, 59):  ('Sacral', 'Solar Plexus'),
        (7, 31):  ('G', 'Throat'),
        (9, 52):  ('Root', 'Sacral'),
        (10, 20): ('G', 'Throat'),
        (10, 34): ('G', 'Sacral'),
        (10, 57): ('Spleen', 'G'),
        (11, 56): ('Ajna', 'Throat'),
        (12, 22): ('Solar Plexus', 'Throat'),
        (13, 33): ('G', 'Throat'),
        (16, 48): ('Spleen', 'Throat'),
        (17, 62): ('Ajna', 'Throat'),
        (18, 58): ('Root', 'Spleen'),
        (19, 49): ('Root', 'Solar Plexus'),
        (20, 34): ('Sacral', 'Throat'),
        (20, 57): ('Spleen', 'Throat'),
        (21, 45): ('Heart', 'Throat'),
        (23, 43): ('Ajna', 'Throat'),
        (24, 61): ('Head', 'Ajna'),
        (25, 51): ('G', 'Heart'),
        (26, 44): ('Spleen', 'Heart'),
        (27, 50): ('Sacral', 'Spleen'),
        (28, 38): ('Root', 'Spleen'),
        (29, 46): ('Sacral', 'G'),
        (30, 41): ('Root', 'Solar Plexus'),
        (32, 54): ('Root', 'Spleen'),
        (34, 57): ('Sacral', 'Spleen'),
        (35, 36): ('Solar Plexus', 'Throat'),
        (37, 40): ('Solar Plexus', 'Heart'),
        (39, 55): ('Root', 'Solar Plexus'),
        (42, 53): ('Root', 'Sacral'),
        (47, 64): ('Head', 'Ajna'),
    }

    # Набор ворот у каждого центра (для проверки, что ворота там вообще есть)
    CENTER_GATES = {
        'Head':         {61, 63, 64},
        'Ajna':         {4, 11, 17, 23, 24, 43, 47},
        'Throat':       {7, 10, 11, 12, 13, 16, 17, 20, 23, 31, 33, 35, 56, 62},
        'G':            {1, 2, 7, 10, 13, 15, 25, 29, 46},
        'Sacral':       {2, 3, 5, 6, 9, 14, 20, 27, 29, 34, 42, 53, 59},
        'Solar Plexus': {6, 12, 19, 22, 30, 35, 36, 37, 39, 49, 55},
        'Heart':        {21, 25, 26, 40, 51},
        'Spleen':       {10, 16, 18, 20, 26, 27, 28, 32, 34, 44, 48, 50, 57},
        'Root':         {9, 18, 19, 28, 29, 30, 38, 39, 40, 41, 42, 52, 53, 54, 58, 60},
    }

    PLANETS_P = [
        (ephem.Sun,     date_str),
        (ephem.Moon,    date_str),
        (ephem.Mercury, date_str),
        (ephem.Venus,   date_str),
        (ephem.Mars,    date_str),
        (ephem.Jupiter, date_str),
        (ephem.Saturn,  date_str),
        (ephem.Uranus,  date_str),
        (ephem.Neptune, date_str),
        (ephem.Pluto,   date_str),
    ]
    PLANETS_D = [(p, design_date) for p, _ in PLANETS_P]

    try:
        gates_personality = set()
        gates_design = set()
        for planet, dt in PLANETS_P:
            lon = get_planet_lon(planet, dt)
            gates_personality.add(get_hd_gate(lon))
        for planet, dt in PLANETS_D:
            lon = get_planet_lon(planet, dt)
            gates_design.add(get_hd_gate(lon))

        all_gates = gates_personality | gates_design

        # ── Определяем активированные центры через каналы ──
        defined_centers = set()
        defined_channels = []
        for (g1, g2), (c1, c2) in CHANNELS.items():
            if g1 in all_gates and g2 in all_gates:
                defined_centers.add(c1)
                defined_centers.add(c2)
                defined_channels.append((g1, g2))

        # ── Тип определяется по активированным центрам ──
        has_sacral   = 'Sacral'  in defined_centers
        has_throat   = 'Throat'  in defined_centers
        has_solar_p  = 'Solar Plexus' in defined_centers
        has_heart    = 'Heart'   in defined_centers
        has_root     = 'Root'    in defined_centers

        # Манифестор: мотор (Сердце/СП/Корень/Сакрал) → Горло, но Сакрал НЕ определён
        # Генератор: Сакрал определён
        # Манифестирующий Генератор: Сакрал + моторный канал к Горлу
        # Проектор: ни Сакрал, ни прямого мотора к Горлу
        # Рефлектор: ни один центр не определён

        if len(defined_centers) == 0:
            hd_type = "Рефлектор"
            strategy = "Ждать лунный цикл (29 дней)"
        elif has_sacral:
            # Проверяем, есть ли прямое соединение Сакрал → Горло (20-34, 10-34)
            sacral_to_throat = any(
                (g1 in all_gates and g2 in all_gates)
                for (g1, g2), (c1, c2) in CHANNELS.items()
                if {c1, c2} == {'Sacral', 'Throat'}
            )
            if sacral_to_throat and has_throat:
                hd_type = "Манифестирующий Генератор"
                strategy = "Реагировать, затем действовать"
            else:
                hd_type = "Генератор"
                strategy = "Ждать и реагировать"
        elif has_throat and (has_solar_p or has_heart or has_root):
            # Мотор соединён с Горлом, Сакрал не определён
            hd_type = "Манифестор"
            strategy = "Информировать и действовать"
        else:
            hd_type = "Проектор"
            strategy = "Ждать приглашения"

        # Профиль из Солнца Личности и Солнца Дизайна
        sun_p = get_planet_lon(ephem.Sun, date_str)
        sun_d = get_planet_lon(ephem.Sun, design_date)
        moon_p = get_planet_lon(ephem.Moon, date_str)
        moon_d = get_planet_lon(ephem.Moon, design_date)

        sun_p_gate, line_p = get_hd_gate_and_line(sun_p)
        sun_d_gate, line_d = get_hd_gate_and_line(sun_d)
        moon_p_gate, moon_p_line = get_hd_gate_and_line(moon_p)
        moon_d_gate, moon_d_line = get_hd_gate_and_line(moon_d)
        profile = f"{line_p}/{line_d}"

        # ── Definition: один, два или три "острова" определённых центров ──
        # Строим граф связей между определёнными центрами через активные каналы
        center_neighbors = {c: set() for c in defined_centers}
        for (g1, g2), (c1, c2) in CHANNELS.items():
            if c1 in defined_centers and c2 in defined_centers:
                if g1 in all_gates and g2 in all_gates:
                    center_neighbors[c1].add(c2)
                    center_neighbors[c2].add(c1)

        # Обход в ширину для подсчёта связных компонент (остовов)
        visited = set()
        components = 0
        for start in defined_centers:
            if start not in visited:
                components += 1
                queue = [start]
                while queue:
                    node = queue.pop()
                    if node not in visited:
                        visited.add(node)
                        queue.extend(center_neighbors[node] - visited)

        definition_map = {0: "Не определён", 1: "Single Definition",
                          2: "Split Definition", 3: "Triple Split Definition"}
        definition = definition_map.get(components, f"{components} Split")

    except Exception as e:
        return {"error": str(e)}

    LINE_NAMES = {
        1: "Исследователь", 2: "Отшельник", 3: "Мученик",
        4: "Оппортунист",   5: "Еретик",    6: "Ролевая модель"
    }

    return {
        "type": hd_type,
        "strategy": strategy,
        "profile": profile,
        "profile_name": f"{LINE_NAMES.get(line_p, '')} / {LINE_NAMES.get(line_d, '')}",
        "definition": definition,
        "defined_centers": sorted(defined_centers),
        "channels": defined_channels,
        "gates": {
            "sun_personality": f"{sun_p_gate}.{line_p}",
            "moon_personality": f"{moon_p_gate}.{moon_p_line}",
            "sun_design": f"{sun_d_gate}.{line_d}",
            "moon_design": f"{moon_d_gate}.{moon_d_line}",
        },
        "note": "Расчёт по 10 планетам и 36 каналам"
    }

# ─────────────────────────────────────────────
# БАЦЗЫ
# ─────────────────────────────────────────────

def get_bazi_year_pillar(year, month, day):
    bazi_year = year
    if year in CHINESE_NY:
        ny_str = CHINESE_NY[year]
        ny_d, ny_m = int(ny_str[:2]), int(ny_str[3:])
        if month < ny_m or (month == ny_m and day < ny_d):
            bazi_year = year - 1
    idx = (bazi_year - 4) % 60
    stem = STEMS_RU[idx % 10]
    branch = BRANCHES_RU[idx % 12]
    animal = ANIMALS_RU[idx % 12]
    element = ELEMENTS_RU[idx % 10]
    return {"stem": stem, "branch": branch, "animal": animal, "element": element,
            "pillar": f"{stem}-{branch}", "year": bazi_year}

def get_bazi_month_pillar(year, month, day):
    JIEQI = [
        (1, 6),(2, 4),(3, 6),(4, 5),(5, 6),(6, 6),
        (7, 7),(8, 7),(9, 8),(10, 8),(11, 7),(12, 7),
    ]
    MONTH_BRANCH = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 0]
    term_day = JIEQI[month - 1][1]
    m = month if day >= term_day else month - 1
    if m <= 0:
        m = 12
        year -= 1
    branch_idx = MONTH_BRANCH[m - 1]
    YEAR_TO_YIN_STEM = {0:2, 1:4, 2:6, 3:8, 4:0, 5:2, 6:4, 7:6, 8:8, 9:0}
    year_stem_idx = (year - 4) % 10
    yin_stem = YEAR_TO_YIN_STEM[year_stem_idx]
    if branch_idx >= 2:
        lunar_num = branch_idx - 1
    elif branch_idx == 0:
        lunar_num = 11
    else:
        lunar_num = 12
    stem_idx = (yin_stem + lunar_num - 1) % 10
    return {
        "stem": STEMS_RU[stem_idx],
        "branch": BRANCHES_RU[branch_idx],
        "animal": ANIMALS_RU[branch_idx],
        "element": ELEMENTS_RU[stem_idx],
        "pillar": f"{STEMS_RU[stem_idx]}-{BRANCHES_RU[branch_idx]}"
    }

def get_bazi_day_pillar(year, month, day):
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12*a - 3
    jdn = day + (153*m+2)//5 + 365*y + y//4 - y//100 + y//400 - 32045
    OFFSET = 49
    n = (jdn + OFFSET) % 60
    stem_idx = n % 10
    branch_idx = n % 12
    return {
        "stem": STEMS_RU[stem_idx],
        "branch": BRANCHES_RU[branch_idx],
        "animal": ANIMALS_RU[branch_idx],
        "element": ELEMENTS_RU[stem_idx],
        "pillar": f"{STEMS_RU[stem_idx]}-{BRANCHES_RU[branch_idx]}",
        "jdn": jdn, "n60": n
    }

def get_bazi_day_pillar_next(year, month, day):
    from datetime import date, timedelta
    try:
        d = date(year, month, day) + timedelta(days=1)
        ny, nm, nd = d.year, d.month, d.day
    except Exception:
        nd, nm, ny = day + 1, month, year
    a = (14 - nm) // 12
    y = ny + 4800 - a
    m = nm + 12*a - 3
    jdn = nd + (153*m+2)//5 + 365*y + y//4 - y//100 + y//400 - 32045
    return (jdn + 49) % 10

def get_bazi_hour_pillar(year, month, day, hour, minute, day_stem_idx):
    total_min = hour * 60 + minute
    intervals = [
        (23*60, 1*60, 0),
        (1*60,  3*60, 1),
        (3*60,  5*60, 2),
        (5*60,  7*60, 3),
        (7*60,  9*60, 4),
        (9*60,  11*60, 5),
        (11*60, 13*60, 6),
        (13*60, 15*60, 7),
        (15*60, 17*60, 8),
        (17*60, 19*60, 9),
        (19*60, 21*60, 10),
        (21*60, 23*60, 11),
    ]
    branch_idx = 0
    for start, end, idx in intervals:
        if start > end:
            if total_min >= start or total_min < end:
                branch_idx = idx
                break
        else:
            if start <= total_min < end:
                branch_idx = idx
                break
    effective_stem_idx = day_stem_idx
    if total_min >= 23 * 60:
        next_day = get_bazi_day_pillar_next(year, month, day)
        effective_stem_idx = next_day
    ZI_STEM = [0, 2, 4, 6, 8, 0, 2, 4, 6, 8]
    stem_idx = (ZI_STEM[effective_stem_idx % 10] + branch_idx) % 10
    return {
        "stem": STEMS_RU[stem_idx],
        "branch": BRANCHES_RU[branch_idx],
        "animal": ANIMALS_RU[branch_idx],
        "element": ELEMENTS_RU[stem_idx],
        "pillar": f"{STEMS_RU[stem_idx]}-{BRANCHES_RU[branch_idx]}"
    }

def get_lahiri_ayanamsa(decimal_year):
    """
    Аянамша Лахири — сдвиг между тропическим и сидерическим зодиаком.
    Формула проверена по нескольким источникам: J2000 база ~23.85°,
    рост ~50.29 угл.секунды в год (прецессия равноденствий).
    Для 2026 года даёт ~24.21° — сходится с эталонными таблицами.
    """
    return 23.85 + (decimal_year - 2000) * (50.29 / 3600)

# Фиксированная последовательность управителей накшатр в Вимшоттари-даше
DASHA_SEQUENCE = ['Кету', 'Венера', 'Солнце', 'Луна', 'Марс', 'Раху', 'Юпитер', 'Сатурн', 'Меркурий']
DASHA_YEARS = {'Кету': 7, 'Венера': 20, 'Солнце': 6, 'Луна': 10, 'Марс': 7,
               'Раху': 18, 'Юпитер': 16, 'Сатурн': 19, 'Меркурий': 17}

# Темы периодов — человеческим языком, без терминов (тот же принцип, что и в профекциях)
DASHA_THEMES = {
    'Кету':     "период отпускания старого, внутреннего поиска и переосмысления — время меньше держаться за внешнее и больше прислушиваться к себе.",
    'Венера':   "период отношений, удовольствия, красоты и творчества — время, когда важны близость, комфорт и то, что радует.",
    'Солнце':   "период личной силы, признания и заявления о себе — время, когда важно быть увиденным и занять своё место.",
    'Луна':     "период дома, чувств, заботы о себе и близких — время, когда эмоциональная опора важнее внешних достижений.",
    'Марс':     "период действия, напора и отстаивания своего — время, когда энергия просит движения, а не ожидания.",
    'Раху':     "период больших амбиций и нестандартных путей — время резких перемен и жажды большего, но с риском потерять почву под ногами.",
    'Юпитер':   "период роста, удачи и расширения горизонтов — время, когда многое прибавляется: знания, возможности, смысл.",
    'Сатурн':   "период дисциплины и настоящей, не быстрой работы — время, когда усилия не дают мгновенного результата, но закладывают прочный фундамент.",
    'Меркурий': "период общения, обучения и новых связей — время, когда важны слова, сделки, обмен идеями и гибкость ума.",
}

def calc_vimshottari_dasha(year, month, day, hour, minute, lat, lon):
    """
    Определяет текущий (на сегодня) большой жизненный период по системе
    Вимшоттари-даша — одной из самых распространённых техник ведической
    астрологии. Основана на позиции Луны при рождении.
    """
    try:
        y, mo, d, h = local_to_ut(year, month, day, hour, minute, lon)
        date_str = datetime_to_ephem_str(y, mo, d, h)
        moon_tropical = get_planet_lon(ephem.Moon, date_str)

        decimal_birth_year = year + (month - 1) / 12 + day / 365.25
        ayanamsa = get_lahiri_ayanamsa(decimal_birth_year)
        moon_sidereal = (moon_tropical - ayanamsa) % 360

        nakshatra_width = 360 / 27
        nakshatra_index = int(moon_sidereal // nakshatra_width)
        fraction_into = (moon_sidereal % nakshatra_width) / nakshatra_width

        start_idx = nakshatra_index % 9
        start_planet = DASHA_SEQUENCE[start_idx]
        balance_years = DASHA_YEARS[start_planet] * (1 - fraction_into)

        # Строим временную шкалу периодов от рождения вперёд
        birth_date = datetime(year, month, day)
        timeline = []
        cursor = birth_date
        end_of_first = cursor + timedelta(days=balance_years * 365.25)
        timeline.append((start_planet, cursor, end_of_first))
        cursor = end_of_first

        idx = start_idx
        today = datetime.now()
        # Добавляем периоды, пока не перекроем сегодняшнюю дату с запасом
        while cursor < today + timedelta(days=365 * 25):
            idx = (idx + 1) % 9
            planet = DASHA_SEQUENCE[idx]
            period_end = cursor + timedelta(days=DASHA_YEARS[planet] * 365.25)
            timeline.append((planet, cursor, period_end))
            cursor = period_end
            if len(timeline) > 15:  # защита от бесконечного цикла
                break

        # Ищем период, в который попадает сегодняшняя дата
        current_planet = None
        years_elapsed = 0
        years_total = 0
        for planet, start, end in timeline:
            if start <= today < end:
                current_planet = planet
                years_elapsed = round((today - start).days / 365.25, 1)
                years_total = DASHA_YEARS[planet]
                break

        if not current_planet:
            return None  # не должно случиться, но подстрахуемся

        return {
            "planet": current_planet,
            "theme": DASHA_THEMES[current_planet],
            "years_elapsed": years_elapsed,
            "years_total": years_total,
        }
    except Exception:
        return None

def calc_profection(age, month, day, birth_year):
    """
    Годовая профекция — простая, но мощная техника: каждый год жизни
    подсвечивает определённую жизненную тему (цикл из 12 тем).
    Возвращает уже человеческую формулировку темы, без терминов.
    """
    # Профекционный "дом" года: (возраст % 12) + 1, где дом 1 = возраст 0, 12, 24...
    house = (age % 12) + 1

    # Темы года — в живой формулировке, без астрологического жаргона.
    # Каждая — про жизненный акцент этого года.
    THEMES = {
        1:  "год про тебя самого — твою личность, тело, новые начинания и то, каким ты хочешь быть дальше. Время заявить о себе.",
        2:  "год про ресурсы и опору — деньги, самооценку, ощущение собственной ценности. Год, чтобы укрепить фундамент под ногами.",
        3:  "год про общение, обучение, близкое окружение — братьев-сестёр, соседей, короткие поездки. Много контактов, информации, движения.",
        4:  "год про дом, семью, корни, внутреннюю опору. Тянет обустраивать пространство, разбираться с прошлым, побыть 'у себя'.",
        5:  "год про творчество, любовь, детей, удовольствие и самовыражение. Год, когда важно позволять себе радость и быть замеченным.",
        6:  "год про работу, здоровье, быт и рутину. Время наводить порядок в делах и в теле, выстраивать полезные привычки.",
        7:  "год про отношения и партнёрство — близкие связи, брак, союзы, а иногда и открытые конфликты. Год про то, с кем ты рядом.",
        8:  "год про глубокие перемены, общие ресурсы, доверие и трансформацию. Год, где многое переворачивается, чтобы освободить место новому.",
        9:  "год про горизонты — путешествия, учёбу, мировоззрение, поиск смысла. Тянет расширяться, выходить за привычные рамки.",
        10: "год про дело жизни, карьеру, статус, публичность и достижения. Год, когда важно то, кем ты становишься в глазах мира.",
        11: "год про друзей, команду, единомышленников, большие цели и надежды. Год про то, с кем ты строишь будущее.",
        12: "год про завершения, отдых, внутреннюю работу, отпускание старого. Год-пауза перед новым циклом — важно восстановиться и подвести итоги.",
    }

    return {
        "house": house,
        "theme": THEMES[house],
    }

# ─────────────────────────────────────────────
# МЕХАНИЗМ "МАРКЕРОВ СОВПАДЕНИЯ"
# Единый словарь из 12 универсальных жизненных категорий.
# Профекции уже 1-в-1 совпадают с этими категориями (дом N = категория N).
# Каждая новая система (Даши, потом HD, натальная астрология и т.д.)
# получает свою таблицу "ключ системы → одна-две категории".
# Если два и более независимых метода расчёта указывают на одну и ту же
# категорию — это подтверждённый маркер, а не догадка модели.
# ─────────────────────────────────────────────

MARKER_CATEGORIES = {
    1:  "личность, новые начинания, заявление о себе",
    2:  "деньги, ресурсы, самоценность",
    3:  "общение, ближний круг, обучение",
    4:  "дом, корни, внутренняя опора",
    5:  "творчество, любовь, самовыражение",
    6:  "работа, здоровье, повседневность",
    7:  "отношения, партнёрство",
    8:  "кризис, трансформация, общие ресурсы",
    9:  "рост, мировоззрение, горизонты",
    10: "дело жизни, статус, карьера",
    11: "друзья, сообщество, большие цели",
    12: "завершения, отдых, внутренняя работа",
}

# Даши: планета текущего периода → 1-2 категории, которые она затрагивает
DASHA_PLANET_TO_CATEGORIES = {
    'Кету':     [12],
    'Венера':   [5, 7],
    'Солнце':   [1, 10],
    'Луна':     [4],
    'Марс':     [1, 8],
    'Раху':     [8, 10],
    'Юпитер':   [2, 9],
    'Сатурн':   [6, 10],
    'Меркурий': [3, 11],
}

def find_markers(profection_house, dasha_planet):
    """
    Ищет независимое подтверждение одной и той же жизненной категории
    сразу двумя методами расчёта (профекция года + текущая даша).
    Возвращает список ID категорий-совпадений (пустой список, если нет).
    Специально НЕ включает логику "на всякий случай" — только точное
    математическое пересечение, без натяжек.
    """
    if not dasha_planet:
        return []
    dasha_categories = DASHA_PLANET_TO_CATEGORIES.get(dasha_planet, [])
    if profection_house in dasha_categories:
        return [profection_house]
    return []

def calc_bazi(year, month, day, hour, minute):
    year_p = get_bazi_year_pillar(year, month, day)
    month_p = get_bazi_month_pillar(year, month, day)
    day_p = get_bazi_day_pillar(year, month, day)
    a = (14 - month) // 12
    y2 = year + 4800 - a
    m2 = month + 12*a - 3
    jdn = day + (153*m2+2)//5 + 365*y2 + y2//4 - y2//100 + y2//400 - 32045
    day_stem_idx = (jdn + 29) % 10
    hour_p = get_bazi_hour_pillar(year, month, day, hour, minute, day_stem_idx)
    elements_count = {"Дерево":0,"Огонь":0,"Земля":0,"Металл":0,"Вода":0}
    for p in [year_p, month_p, day_p, hour_p]:
        e = p.get("element")
        if e in elements_count:
            elements_count[e] += 1
    dominant = max(elements_count, key=elements_count.get)
    return {
        "year": year_p, "month": month_p, "day": day_p, "hour": hour_p,
        "elements_balance": elements_count, "dominant_element": dominant
    }

# ─────────────────────────────────────────────
# НУМЕРОЛОГИЯ
# ─────────────────────────────────────────────

def calc_numerology(day, month, year, firstname="", lastname=""):
    digits = [int(d) for d in f"{day}{month}{year}"]
    lp_sum = sum(digits)
    lp, lp_steps = reduce_to_9(lp_sum, keep_master=True)

    date_str = f"{day:02d}{month:02d}{year}"
    date_digits = [int(c) for c in date_str]
    a = sum(date_digits)
    b = sum(int(d) for d in str(a))
    c = a - 2 * date_digits[0]
    d_num = sum(int(d) for d in str(abs(c)))

    pool = date_digits + [int(d) for d in str(a)] + [int(d) for d in str(abs(c))] + [int(d) for d in str(d_num)]
    counts = {}
    for x in pool:
        if x != 0:
            counts[x] = counts.get(x, 0) + 1

    date_str2 = f"{day:02d}{month:02d}{year}"
    arcana_sum = sum(int(d) for d in date_str2)
    arcana = reduce_to_22(arcana_sum)

    A = reduce_to_22(day)
    B = reduce_to_22(month)
    C = reduce_to_22(sum(int(d) for d in str(year)))
    D = reduce_to_22(A + B + C)
    center = reduce_to_22(A + B + C + D)
    E = reduce_to_22(A + B)
    F = reduce_to_22(B + C)
    G = reduce_to_22(C + D)
    H = reduce_to_22(D + A)

    zodiac = get_zodiac(day, month)

    name_codes = {}
    for label, text in [("Имя", firstname), ("Фамилия", lastname)]:
        if text:
            upper = text.upper()
            letters = [c for c in upper if c in CYRILLIC_PYTH]
            s = sum(CYRILLIC_PYTH[c] for c in letters)
            reduced, _ = reduce_to_9(s)
            name_codes[label] = {
                "text": text, "sum": s, "reduced": reduced,
                "breakdown": " ".join(f"{c}={CYRILLIC_PYTH[c]}" for c in letters)
            }

    return {
        "life_path": lp, "life_path_sum": lp_sum, "life_path_steps": lp_steps,
        "pythagorean_square": {
            "working_numbers": [a, b, abs(c), d_num],
            "destiny_number": a, "soul_number": b, "counts": counts
        },
        "arcana": arcana, "arcana_name": ARCANA_NAMES.get(arcana, ""),
        "matrix_of_destiny": {
            "A": A, "B": B, "C": C, "D": D, "center": center,
            "E": E, "F": F, "G": G, "H": H
        },
        "zodiac": zodiac, "name_codes": name_codes
    }

def get_zodiac(day, month):
    ranges = [
        ("Козерог", (12,22), (1,19)),
        ("Водолей", (1,20), (2,18)),
        ("Рыбы",   (2,19), (3,20)),
        ("Овен",   (3,21), (4,19)),
        ("Телец",  (4,20), (5,20)),
        ("Близнецы",(5,21),(6,20)),
        ("Рак",    (6,21), (7,22)),
        ("Лев",    (7,23), (8,22)),
        ("Дева",   (8,23), (9,22)),
        ("Весы",   (9,23), (10,22)),
        ("Скорпион",(10,23),(11,21)),
        ("Стрелец",(11,22),(12,21)),
    ]
    for name, (fm, fd), (tm, td) in ranges:
        if fm == tm:
            if month == fm and fd <= day <= td:
                return name
        elif fm == 12:
            if (month == 12 and day >= fd) or (month == 1 and day <= td):
                return name
        else:
            if (month == fm and day >= fd) or (month == tm and day <= td):
                return name
    return "—"

# ─────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": "2.0-ephem"})


# ── Промокоды — теперь только на сервере, не видны в исходнике страницы ──
VALID_CODES = [
    'AION-GXV-2080','AION-JGQ-0832','AION-SDR-9002','AION-PLJ-2148','AION-MWM-1423',
    'AION-WZQ-3123','AION-VUR-3083','AION-NML-6099','AION-QSG-1716','AION-GUW-6887',
    'AION-GDA-0293','AION-XXX-2791','AION-EHF-0821','AION-LXW-9440','AION-BXP-6304',
    'AION-IZH-8028','AION-MPW-3485','AION-VHT-0181','AION-PBL-5301','AION-JLE-2324',
    'AION-KSQ-6406','AION-PMY-4592','AION-ALU-3105','AION-VVS-7597','AION-OIU-5848',
    'AION-ILD-8534','AION-WVJ-0006','AION-MPL-1905','AION-KKU-9413','AION-ZAD-2600',
    'AION-XTV-7917','AION-VTT-1197','AION-FEY-7893','AION-SKN-0009','AION-JTA-8187',
    'AION-BNA-2831','AION-QTN-8910','AION-IZU-9276','AION-EWV-2766','AION-RTY-6131',
    'AION-DYJ-8051','AION-AUH-6315','AION-PVW-0891','AION-CDZ-9473','AION-JCL-5503',
    'AION-MIC-7411','AION-IMH-6949','AION-RVX-8930','AION-BQY-1478','AION-CDG-4810',
    # ── Резервная партия, добавлена 16.07.2026 ──
    'AION-AYW-8308','AION-BLZ-9022','AION-BPN-8190','AION-CKA-2501','AION-CLH-0762',
    'AION-DFI-5220','AION-DTO-7503','AION-ECL-4476','AION-EMF-4039','AION-EPR-2182',
    'AION-ESE-3965','AION-FDY-5478','AION-FHC-2126','AION-FIW-9263','AION-FVL-3720',
    'AION-FYW-3639','AION-GUL-4995','AION-JJF-2966','AION-KFZ-5001','AION-LGG-5258',
    'AION-LKH-2948','AION-MOG-8425','AION-NEX-8266','AION-OBZ-8998','AION-OVP-1138',
    'AION-OVQ-8570','AION-PQK-5592','AION-PZR-0826','AION-QAH-2768','AION-QCL-4982',
    'AION-QFX-8026','AION-QOF-5808','AION-QUK-0395','AION-RVU-2032','AION-SEH-9557',
    'AION-SFI-9645','AION-SFQ-2498','AION-SGK-6237','AION-SIE-9300','AION-TOL-0089',
    'AION-UWX-2217','AION-VWA-7398','AION-WKQ-1989','AION-WPU-7593','AION-WVG-7188',
    'AION-YCM-0771','AION-YDD-1526','AION-YWW-3187','AION-ZCK-3821','AION-ZWA-7652',
    # ── Довесок до 100 доступных кодов, добавлено 16.07.2026 ──
    'AION-AFZ-5496','AION-CLC-3035','AION-FOU-7818','AION-FUB-2247','AION-IYN-7442',
    'AION-JSX-1857','AION-KFE-2723','AION-PKC-1111','AION-ROY-4462','AION-XJK-6168',
    'AION-ZJF-9175','AION-ZYR-0048'
]

LEMONSQUEEZY_WEBHOOK_SECRET = os.environ.get('LEMONSQUEEZY_WEBHOOK_SECRET', '')

# ── Тарифы — сопоставление названия варианта в Lemon Squeezy с пакетом ──
# ВАЖНО: названия вариантов должны СОВПАДАТЬ с тем, как ты назовёшь их
# при создании продуктов в Lemon Squeezy (регистр не важен, ищем по подстроке).
TIER_MAP = {
    'старт':    {'analyses': 10, 'tier': 'start'},
    'start':    {'analyses': 10, 'tier': 'start'},
    'базовый':  {'analyses': 23, 'tier': 'basic'},
    'basic':    {'analyses': 23, 'tier': 'basic'},
    'про':      {'analyses': 40, 'tier': 'pro'},
    'pro':      {'analyses': 40, 'tier': 'pro'},
}

def match_tier(variant_name):
    """Ищет тариф по названию варианта (частичное совпадение, без учёта регистра)."""
    if not variant_name:
        return None
    lowered = variant_name.lower()
    for key, tier_data in TIER_MAP.items():
        if key in lowered:
            return tier_data
    return None

@app.route('/webhooks/lemonsqueezy', methods=['POST'])
def lemonsqueezy_webhook():
    raw_body = request.get_data()  # ВАЖНО: сырое тело запроса, не data.json — нужно для проверки подписи

    # ── Проверка подписи — без нужного секрета отказ, чтобы никто не мог подделать "оплату" ──
    if not LEMONSQUEEZY_WEBHOOK_SECRET:
        return jsonify({"status": "error", "message": "webhook_secret_not_configured"}), 500

    signature = request.headers.get('X-Signature', '')
    expected = hmac.new(
        LEMONSQUEEZY_WEBHOOK_SECRET.encode('utf-8'),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return jsonify({"status": "error", "message": "invalid_signature"}), 401

    try:
        payload = _json.loads(raw_body)
    except Exception:
        return jsonify({"status": "error", "message": "invalid_json"}), 400

    event_name = payload.get('meta', {}).get('event_name', '')
    attrs = payload.get('data', {}).get('attributes', {})
    user_email = attrs.get('user_email', '')
    variant_name = attrs.get('variant_name', '') or attrs.get('product_name', '')
    status = attrs.get('status', '')

    if not user_email:
        return jsonify({"status": "ok", "message": "no_email_skip"})  # отвечаем 200, чтобы LS не повторял

    # ── Успешная оплата или активная подписка — выдаём пакет ──
    if event_name in ('order_created', 'subscription_created', 'subscription_payment_success') \
       and status in ('paid', 'active', 'on_trial'):
        tier_data = match_tier(variant_name)
        if tier_data and firebase_db_available:
            try:
                key = email_to_key(user_email)
                fb_db.reference(f'users/{key}').update({
                    'analysesLeft': tier_data['analyses'],
                    'analysesTotal': tier_data['analyses'],
                    'subscriptionTier': tier_data['tier'],
                    'subscriptionStatus': 'active',
                })
            except Exception as e:
                print(f"⚠️ Ошибка обновления после оплаты: {e}")

    # ── Подписка отменена/истекла — просто помечаем статус, не отбираем остаток анализов ──
    elif event_name in ('subscription_cancelled', 'subscription_expired'):
        if firebase_db_available:
            try:
                key = email_to_key(user_email)
                fb_db.reference(f'users/{key}').update({'subscriptionStatus': 'inactive'})
            except Exception as e:
                print(f"⚠️ Ошибка обновления при отмене: {e}")

    return jsonify({"status": "ok"})


@app.route('/history', methods=['POST'])
def get_history():
    data = request.json or {}
    email = (data.get('email') or '').strip()
    if not email:
        return jsonify({"status": "error", "message": "no_email"}), 400
    if not firebase_db_available:
        return jsonify({"status": "error", "message": "service_unavailable"}), 503
    try:
        key = email_to_key(email)
        raw = fb_db.reference(f'history/{key}').get() or {}
        items = []
        for _id, rec in raw.items():
            if isinstance(rec, dict):
                items.append({
                    'createdAt': rec.get('createdAt', ''),
                    'firstname': rec.get('firstname', ''),
                    'lastname': rec.get('lastname', ''),
                    'request': rec.get('request', ''),
                    'analysis': rec.get('analysis', ''),
                })
        items.sort(key=lambda x: x['createdAt'], reverse=True)
        return jsonify({"status": "ok", "items": items[:50]})
    except Exception as e:
        return jsonify({"status": "error", "message": "read_failed"}), 500


@app.route('/rate', methods=['POST'])
def rate():
    data = request.json or {}
    rating = data.get('rating')
    comment = (data.get('comment') or '').strip()[:2000]  # ограничение на длину
    email = data.get('email', '')
    compat = bool(data.get('compat', False))
    theme = data.get('theme', '')

    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return jsonify({"status": "error", "message": "invalid_rating"}), 400
    if not firebase_db_available:
        return jsonify({"status": "error", "message": "service_unavailable"}), 503

    try:
        ref = fb_db.reference('ratings').push()
        ref.set({
            "email": email,
            "rating": rating,
            "comment": comment,
            "compat": compat,
            "theme": theme,
            "timestamp": datetime.now().isoformat()
        })
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": "save_failed"}), 500


@app.route('/redeem', methods=['POST'])
def redeem():
    data = request.json or {}
    code = (data.get('code') or '').strip().upper()

    if not code:
        return jsonify({"valid": False, "reason": "empty"}), 400
    if code not in VALID_CODES:
        return jsonify({"valid": False, "reason": "not_found"}), 404
    if not firebase_db_available:
        return jsonify({"valid": False, "reason": "service_unavailable"}), 503

    try:
        ref = fb_db.reference(f'used_codes/{code}')
        # Атомарно: помечаем использованным, только если ещё не был использован
        result = {"already_used": False}
        def txn(current):
            if current:
                result["already_used"] = True
                return current  # не меняем — код уже занят
            return True
        ref.transaction(txn)
        if result["already_used"]:
            return jsonify({"valid": False, "reason": "used"}), 409
        return jsonify({"valid": True})
    except Exception as e:
        return jsonify({"valid": False, "reason": "error"}), 500


@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    """Генерирует PDF файл с анализом через WeasyPrint"""
    data = request.json
    try:
        analysis = data.get('analysis', '')
        name = data.get('name', '—')
        birthdate = data.get('birthdate', '—')

        if not analysis:
            return jsonify({"status": "error", "message": "Нет текста анализа"}), 400

        try:
            from weasyprint import HTML, CSS
            weasyprint_available = True
        except ImportError:
            weasyprint_available = False

        # Путь к папке со шрифтами (лежит рядом с server.py, в самом проекте)
        # Так шрифт с кириллицей гарантированно есть, независимо от того,
        # что установлено на сервере Railway.
        FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
        font_regular_path = os.path.join(FONTS_DIR, 'DejaVuSans.ttf').replace('\\', '/')
        font_bold_path = os.path.join(FONTS_DIR, 'DejaVuSans-Bold.ttf').replace('\\', '/')

        # HTML шаблон PDF
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @font-face {{
    font-family: 'AION Sans';
    src: url('file://{font_regular_path}') format('truetype');
    font-weight: normal;
  }}
  @font-face {{
    font-family: 'AION Sans';
    src: url('file://{font_bold_path}') format('truetype');
    font-weight: bold;
  }}
  @page {{ margin: 20mm 18mm; }}
  body {{
    font-family: 'AION Sans', 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif;
    background: #f2ecdd;
    color: #3a332b;
    margin: 0;
    padding: 10mm 12mm;
    font-size: 13px;
    line-height: 1.9;
  }}
  .header {{
    text-align: center;
    padding: 30px 0 20px;
    border-bottom: 1px solid #9b7e4a;
    margin-bottom: 24px;
  }}
  .brand {{
    font-size: 32px;
    color: #5E8B76;
    letter-spacing: 6px;
    font-weight: bold;
    margin-bottom: 6px;
  }}
  .sub {{
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #9b7e4a;
    margin-bottom: 18px;
  }}
  .client-name {{
    font-size: 20px;
    color: #3a332b;
    margin-bottom: 4px;
  }}
  .client-date {{
    font-size: 12px;
    color: #9b7e4a;
  }}
  .body {{
    font-size: 13px;
    line-height: 1.9;
    white-space: pre-wrap;
  }}
  .footer {{
    margin-top: 40px;
    padding-top: 14px;
    border-top: 1px solid #9b7e4a;
    text-align: center;
    font-size: 10px;
    color: #9b7e4a;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
<div class="header">
  <div class="brand">AION Vi</div>
  <div class="sub">Персональный навигатор</div>
  <div class="client-name">{name}</div>
  <div class="client-date">{birthdate}</div>
</div>
<div class="body">{analysis}</div>
<div class="footer">AION Vi · Персональный анализ создан специально для тебя</div>
</body>
</html>"""

        if weasyprint_available:
            from weasyprint import HTML
            from flask import Response
            from urllib.parse import quote
            pdf_bytes = HTML(string=html_content).write_pdf()

            # Имя файла может быть на кириллице — в HTTP-заголовках напрямую
            # так писать нельзя (только латиница). Поэтому: делаем безопасное
            # ASCII-имя для старых программ + правильно закодированное
            # кириллическое имя (RFC 5987) для всех современных браузеров —
            # пользователь увидит файл с нормальным русским/украинским именем.
            raw_filename = f"AION_Vi_{name.replace(' ', '_')}_{birthdate.replace('.', '-')}.pdf"
            ascii_fallback = "AION_Vi_analysis.pdf"
            encoded_filename = quote(raw_filename)

            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_filename}",
                    'Content-Type': 'application/pdf'
                }
            )
        else:
            # WeasyPrint не установлен — возвращаем HTML для печати
            return jsonify({
                "status": "fallback",
                "html": html_content,
                "message": "WeasyPrint не установлен, используй HTML печать"
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/geocode', methods=['POST'])
def geocode_endpoint():
    data = request.json
    place = data.get('place', '')
    lat, lon, display = geocode(place)
    if lat is None:
        return jsonify({"error": "Место не найдено"}), 404
    return jsonify({"lat": lat, "lon": lon, "display": display})

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    try:
        try:
            day, month, year, hour, minute = validate_birth_data(data)
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 400
        lat = float(data.get('lat', 50.45))
        lon = float(data.get('lon', 30.52))
        firstname = data.get('firstname', '')
        lastname = data.get('lastname', '')

        numerology = calc_numerology(day, month, year, firstname, lastname)
        bazi = calc_bazi(year, month, day, hour, minute)
        natal = calc_natal(year, month, day, hour, minute, lat, lon)
        hd = calc_human_design(year, month, day, hour, minute, lat, lon)

        return jsonify({
            "status": "ok",
            "input": {
                "name": f"{firstname} {lastname}".strip(),
                "gender": data.get('gender', ''),
                "date": f"{day:02d}.{month:02d}.{year}",
                "time": f"{hour:02d}:{minute:02d}",
                "lat": lat, "lon": lon
            },
            "numerology": numerology,
            "bazi": bazi,
            "natal": natal,
            "human_design": hd
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/summary', methods=['POST'])
def summary():
    data = request.json
    try:
        try:
            day, month, year, hour, minute = validate_birth_data(data)
        except ValueError as ve:
            return jsonify({"status": "error", "message": str(ve)}), 400
        lat = float(data.get('lat', 50.45))
        lon = float(data.get('lon', 30.52))
        firstname = data.get('firstname', '')
        lastname = data.get('lastname', '')
        gender = data.get('gender', '')
        client_request = data.get('request', '')

        num = calc_numerology(day, month, year, firstname, lastname)
        bz = calc_bazi(year, month, day, hour, minute)
        nat = calc_natal(year, month, day, hour, minute, lat, lon)
        hd = calc_human_design(year, month, day, hour, minute, lat, lon)

        lines = []
        lines.append(f"КЛИЕНТ: {firstname} {lastname}".strip())
        if gender in ('m', 'f'):
            lines.append(f"ПОЛ: {'мужской (обращайся в мужском роде)' if gender == 'm' else 'женский (обращайся в женском роде)'}")
        lines.append(f"ДАТА РОЖДЕНИЯ: {day:02d}.{month:02d}.{year}")
        
        # Точный возраст
        from datetime import date as _date
        today = _date.today()
        age = today.year - year - ((today.month, today.day) < (month, day))
        lines.append(f"ТОЧНЫЙ ВОЗРАСТ: {age} лет (на сегодня {today.strftime('%d.%m.%Y')})")
        lines.append(f"ВРЕМЯ: {hour:02d}:{minute:02d}")
        lines.append(f"МЕСТО: широта {lat}, долгота {lon}")

        # Годовая профекция — тема текущего года жизни
        prof = calc_profection(age, month, day, year)
        lines.append("")
        lines.append(f"АКЦЕНТ ТЕКУЩЕГО ГОДА ЖИЗНИ: {prof['theme']}")
        lines.append("(Это фоновая тема года. Упомяни её органично и своими словами, ТОЛЬКО если она естественно ложится в запрос человека или в общую картину. НЕ притягивай насильно, не называй это 'профекцией' или любым термином — просто как наблюдение о том, чем сейчас 'дышит' его год.)")

        # Крупный жизненный период (Вимшоттари-даша) — на сегодняшний день
        dasha = calc_vimshottari_dasha(year, month, day, hour, minute, lat, lon)
        if dasha:
            lines.append("")
            lines.append(f"КРУПНЫЙ ЖИЗНЕННЫЙ ПЕРИОД (сейчас, на {today.strftime('%d.%m.%Y')}): {dasha['theme']} (человек в этом периоде примерно {dasha['years_elapsed']} из {dasha['years_total']} лет)")
            lines.append("(Это фоновый долгосрочный период — более крупный масштаб, чем акцент года выше. Упомяни ТОЛЬКО если органично ложится в запрос. НЕ называй это 'дашей' или любым системным термином — просто как наблюдение о более широкой фазе жизни, в которой сейчас находится человек.)")

        # Маркеры совпадения — независимое подтверждение темы двумя и более системами
        markers = find_markers(prof['house'], dasha['planet'] if dasha else None)
        if markers:
            lines.append("")
            lines.append("⚡ ПОДТВЕРЖДЁННЫЙ МАРКЕР (это НЕ догадка — минимум два независимых метода расчёта указывают ровно в одну и ту же область жизни):")
            for cat_id in markers:
                lines.append(f"— {MARKER_CATEGORIES[cat_id]}")
            lines.append("(Раз это подтверждено сразу двумя расчётами — можешь говорить об этом увереннее и весомее, чем об остальных фоновых темах, но только если это релевантно запросу человека. По-прежнему НЕ называй методы или системные термины — просто говори с большей убеждённостью об этой сфере жизни.)")

        # РЕАЛЬНЫЕ ближайшие окна — по одному лучшему окну на каждый месяц,
        # чтобы охватить весь горизонт, а не только самые точные совпадения подряд.
        # Список transit_windows уже отсортирован по орбу (точности) — берём первое
        # (то есть самое точное) окно для каждого месяца, дальше сортируем по дате.
        transit_windows = find_transit_windows(nat.get('planets', {}), days_ahead=60)
        if transit_windows:
            best_per_month = {}
            for w in transit_windows:
                month_key = w['peak'][3:]  # "MM.YYYY" из "DD.MM.YYYY"
                if month_key not in best_per_month:
                    best_per_month[month_key] = w
            months_sorted = sorted(
                best_per_month.values(),
                key=lambda w: datetime.strptime(w['peak'], '%d.%m.%Y')
            )
            lines.append("")
            lines.append("РЕАЛЬНЫЕ БЛИЖАЙШИЕ ОКНА (посчитано математически на 60 дней вперёд, лучшее окно на каждый месяц — это НЕ придуманные даты):")
            for w in months_sorted:
                lines.append(f"— {w['start']}–{w['end']} (точнее всего {w['peak']})")
            lines.append("(Если человек спрашивает 'когда' — используй ТОЛЬКО эти реальные даты, не придумывай другие. Формулируй по-человечески: 'ближе к концу июля', конкретные числа — но без слов 'транзит', 'аспект', названий планет.)")

        if client_request:
            lines.append(f"ЗАПРОС: {client_request}")
        lines.append("")

        lines.append("── НУМЕРОЛОГИЯ ──")
        lines.append(f"Число жизненного пути: {num['life_path']} (сумма {num['life_path_sum']}, шаги: {' → '.join(str(x) for x in num['life_path_steps'])})")
        pq = num['pythagorean_square']
        lines.append(f"Квадрат Пифагора — рабочие числа: {' / '.join(str(x) for x in pq['working_numbers'])}")
        lines.append(f"Число судьбы: {pq['destiny_number']}, Число души: {pq['soul_number']}")
        counts_str = ", ".join(f"{k}: {'•'*v}" for k,v in sorted(pq['counts'].items()))
        lines.append(f"Психоматрица: {counts_str}")
        lines.append(f"Аркан Таро: {num['arcana']} — {num['arcana_name']}")
        lines.append(f"Знак зодиака (западный): {num['zodiac']}")
        ms = num['matrix_of_destiny']
        lines.append(f"Матрица судьбы: центр={ms['center']}, A={ms['A']}, B={ms['B']}, C={ms['C']}, D={ms['D']}, E={ms['E']}, F={ms['F']}, G={ms['G']}, H={ms['H']}")
        if num['name_codes']:
            for label, nc in num['name_codes'].items():
                lines.append(f"Код {label} «{nc['text']}»: {nc['sum']} → {nc['reduced']}")
        lines.append("")

        lines.append("── БАЦЗЫ (4 столпа) ──")
        lines.append(f"Год:   {bz['year']['pillar']} ({bz['year']['element']} {bz['year']['animal']})")
        lines.append(f"Месяц: {bz['month']['pillar']} ({bz['month']['element']} {bz['month']['animal']})")
        lines.append(f"День:  {bz['day']['pillar']} ({bz['day']['element']} {bz['day']['animal']})")
        lines.append(f"Час:   {bz['hour']['pillar']} ({bz['hour']['element']} {bz['hour']['animal']})")
        eb = bz['elements_balance']
        lines.append(f"Баланс стихий: Дерево={eb['Дерево']}, Огонь={eb['Огонь']}, Земля={eb['Земля']}, Металл={eb['Металл']}, Вода={eb['Вода']}")
        lines.append(f"Доминирующая стихия: {bz['dominant_element']}")
        lines.append("")

        lines.append("── НАТАЛЬНАЯ КАРТА ──")
        planets = nat.get('planets', {})
        key_planets = ["Солнце", "Луна", "Меркурий", "Венера", "Марс", "Юпитер", "Сатурн"]
        for p in key_planets:
            if p in planets and "formatted" in planets[p]:
                retro = " ℞" if planets[p].get("retrograde") else ""
                lines.append(f"{p}: {planets[p]['formatted']}{retro}")
        houses = nat.get('houses', {})
        if "Асцендент" in houses:
            lines.append(f"Асцендент: {houses['Асцендент']['formatted']}")
        if "MC (Середина Неба)" in houses:
            lines.append(f"MC: {houses['MC (Середина Неба)']['formatted']}")
        lines.append("")

        lines.append("── ДИЗАЙН ЧЕЛОВЕКА ──")
        lines.append(f"Тип: {hd.get('type', '—')}")
        lines.append(f"Стратегия: {hd.get('strategy', '—')}")
        lines.append(f"Профиль: {hd.get('profile', '—')} ({hd.get('profile_name', '')})")
        gates = hd.get('gates', {})
        lines.append(f"Ворота Солнца (личность): {gates.get('sun_personality', '—')}")
        lines.append(f"Ворота Луны (личность): {gates.get('moon_personality', '—')}")
        lines.append(f"Ворота Солнца (дизайн): {gates.get('sun_design', '—')}")

        return jsonify({"summary": "\n".join(lines)})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/quick-profile', methods=['POST'])
def quick_profile():
    # Заморожено: фронтенд эту фичу пока не вызывает (экономия токенов на бете).
    # Эндпоинт временно закрыт, чтобы им нельзя было пользоваться напрямую в обход кассы.
    return jsonify({"status": "error", "message": "Функция временно отключена"}), 503
    data = request.json
    try:
        nickname = data.get('nickname', '')
        strategy = data.get('strategy', '')
        life_path = data.get('life_path', '')
        element = data.get('element', '')
        zodiac = data.get('zodiac', '')
        lang_instruction = data.get('lang_instruction', 'Отвечай на русском языке.')

        api_key = ANTHROPIC_API_KEY
        if not api_key:
            return jsonify({"status": "error", "message": "API ключ не установлен"}), 400

        system_prompt = """Ты — AION Vi. Ты обращаешься к человеку напрямую, по имени, живым тёплым тоном — как друг начинает разговор. Это первое, что человек видит — вступление перед более глубоким анализом.

ПРАВИЛА:
— Пиши ЕДИНЫМ слитным текстом-монологом, БЕЗ заголовков, БЕЗ списков, БЕЗ разделения на пункты
— Обращайся по имени в начале
— Свяжи все данные в естественный плавный рассказ — как будто одно вытекает из другого
— Используй число жизненного пути, стратегию, стихию, знак — но НЕ называй их системными терминами (не говори "число жизненного пути", "Human Design", "стихия по БаЦзы")
— Вместо этого говори: "число N — твой компас земной", "стратегия говорит...", "твоя стихия — ...", "ты не просто очередной [знак]..."
— Тон: тёплый, личный, с лёгкой долей мудрости и заботы
— Можно использовать лёгкий юмор и фирменные фразы вроде "Я в курсе, поверь 😊"
— Длина: 4-6 предложений, компактно
— Никаких заголовков, маркеров, цифр — только живая речь

ПРИМЕР СТИЛЯ (только как образец тона, не копируй дословно):
"Слав, число 11 — твой компас земной. И оно говорит: не спеши, не дави. Жди отклика извне — и каждое твоё решение будет в яблочко. Твои 11 — это особая частота: интуитивная, глубокая, способная чувствовать то, что другие не замечают. У каждого есть своя стихия. Твоя — это Вода. Она ищет и всегда находит выход. Её глубина — твоя сила. Ты не просто очередной персонаж этого мира. В тебе есть качества, о которых ты сам не догадываешься. Я в курсе, поверь! 😊\""""

        user_prompt = f"""Данные человека:
Обращение (имя): {nickname}
Стратегия: {strategy}
Число жизненного пути: {life_path}
Доминирующая стихия: {element}
Знак: {zodiac}

Напиши вступительное обращение AION Vi к этому человеку в указанном стиле — единым слитным текстом.

ВАЖНО: {lang_instruction}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )

        text = message.content[0].text
        return jsonify({"status": "ok", "text": text})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/generate', methods=['POST'])
def generate_analysis():
    data = request.json
    try:
        summary = data.get('summary', '')
        client_request = data.get('request', '')
        lang_instruction = data.get('lang_instruction', 'Отвечай на русском языке.')
        compat_enabled = data.get('compat_enabled', False)
        compat_theme = data.get('compat_theme', '')
        # Новый формат — массив участников [{name, summary}, ...] (2-4 человека).
        # Старое поле compat_summary оставляем как запасной путь на случай,
        # если где-то ещё дёргается старая версия фронтенда.
        compat_summaries = data.get('compat_summaries', [])
        legacy_compat_summary = data.get('compat_summary', '')
        if not compat_summaries and legacy_compat_summary:
            compat_summaries = [{'name': '', 'summary': legacy_compat_summary}]
        no_time = data.get('no_time', False)
        nickname = data.get('nickname', '')
        answer_mode = data.get('answer_mode', 'deep')  # deep | quick
        conversation_history = data.get('conversation_history', [])  # [{question, answer}, ...] — только при "Продолжить диалог"

        # Первая ли это генерация у пользователя (для условного вступления-портрета)
        is_first_generation = False
        try:
            total = fb_db.reference(f'users/{email_to_key(email)}/analysesTotal').get()
            left_now = get_analyses_left(email)
            if isinstance(total, (int, float)) and isinstance(left_now, (int, float)):
                is_first_generation = (left_now >= total)  # ещё ничего не потрачено
        except Exception:
            pass

        # Случайный заход — сервер выбирает структуру начала, не полагаясь на "творчество" модели
        opening_styles = [
            "Начни СРАЗУ с сути ответа на его вопрос — без вступлений про личность.",
            "Начни с короткого наблюдения о том, что стоит за его вопросом, и сразу переходи к ответу.",
            "Начни с прямого обращения по имени и одной живой, конкретной мысли по его запросу.",
            "Начни с встречного угла — покажи, что ты уловил не только вопрос, но и то, что за ним, и отвечай.",
            "Начни без предисловий, будто продолжаешь разговор, который уже шёл.",
        ]
        chosen_opening = random.choice(opening_styles)

        no_time_note = '\n\nВАЖНО: Точное время рождения клиента неизвестно. Мягко упомяни в тексте (1-2 предложения), что без точного времени некоторые грани кода остаются скрытыми — и это можно уточнить позже для более глубокого анализа. Не акцентируй на этом сильно.' if no_time else ''
        nickname_note = f'\n\nЛичный штрих: друзья и близкие называют этого человека «{nickname}» — если это будет звучать органично, можешь один раз использовать такое тёплое обращение в тексте (не обязательно, только если естественно).' if nickname else ''

        # ── История разговора этой сессии (только если нажали "Продолжить диалог") ──
        history_note = ''
        if conversation_history:
            recent = conversation_history[-6:]  # не раздуваем промпт бесконечно на длинных сессиях
            turns = []
            for i, turn in enumerate(recent, 1):
                q = (turn.get('question') or '').strip()
                a = (turn.get('answer') or '').strip()
                if q and a:
                    turns.append(f"Вопрос {i}: {q}\nТвой ответ {i}: {a}")
            if turns:
                history_note = (
                    "\n\nПРЕДЫДУЩИЙ РАЗГОВОР В ЭТОЙ ЖЕ СЕССИИ (для твоего понимания контекста, НЕ пересказывай его):\n"
                    + "\n\n".join(turns)
                    + "\n\nЭто продолжение того же разговора — вы уже общаетесь. НЕ представляйся заново, НЕ повторяй то, что уже сказал. Учитывай контекст выше при ответе на НОВЫЙ вопрос ниже."
                )

        if not summary:
            return jsonify({"status": "error", "message": "Нет данных для анализа"}), 400

        # ── Касса на сервере: обязательна, без email или без связи с базой — отказ ──
        # (раньше отсутствие email просто пропускало проверку — дыра, через
        # которую можно было генерировать бесплатно за наш счёт)
        email = data.get('email', '')
        if not email:
            return jsonify({"status": "error", "message": "Не удалось определить пользователя. Перезайди в аккаунт."}), 403
        if not firebase_db_available:
            return jsonify({"status": "error", "message": "Сервис временно недоступен, попробуй через минуту."}), 503

        left = get_analyses_left(email)
        is_unlimited = False
        try:
            key = email_to_key(email)
            is_unlimited = bool(fb_db.reference(f'users/{key}/unlimited').get())
        except Exception:
            pass
        if not is_unlimited and left is not None and left <= 0:
            return jsonify({
                "status": "error",
                "message": "Анализы на этом пакете закончились. Продолжи с новым пакетом."
            }), 403

        api_key = ANTHROPIC_API_KEY
        if not api_key:
            return jsonify({"status": "error", "message": "API ключ не установлен"}), 400

        if compat_enabled and compat_summaries:
            # ── Совместимость на 2-4 человек — блоки и формулировки строятся динамически ──
            total_people = 1 + len(compat_summaries)
            ordinals = ['ПЕРВЫЙ', 'ВТОРОЙ', 'ТРЕТИЙ', 'ЧЕТВЁРТЫЙ']
            people_words = {2: 'двух людей', 3: 'трёх людей', 4: 'четырёх людей'}
            people_word = people_words.get(total_people, f'{total_people} людей')

            people_blocks = [f"{ordinals[0]} ЧЕЛОВЕК:\n{summary}"]
            for i, person in enumerate(compat_summaries[:3], start=1):
                people_blocks.append(f"{ordinals[i]} ЧЕЛОВЕК:\n{person.get('summary', '')}")
            people_text = "\n\n".join(people_blocks)

            if total_people == 2:
                length_line = "— Длина: 800-1100 слов"
            elif total_people == 3:
                length_line = "— Длина: 1100-1450 слов — на группу из трёх нужно больше места, чтобы раскрыть каждого не поверхностно"
            else:
                length_line = "— Длина: 1400-1800 слов — на группу из четырёх нужно больше места, чтобы раскрыть каждого не поверхностно"

            # ── Ключевое различие: если есть конкретный вопрос — вся структура
            # строится вокруг ОТВЕТА на него, а не вокруг перечисления людей.
            # Портреты и резонансы — это аргументация в пользу ответа, а не
            # отдельная самоцель. Без вопроса — общий разбор по теме, как раньше.
            if client_request:
                structure_line = (
                    "— КЛЮЧЕВОЕ ПРАВИЛО СТРУКТУРЫ: у клиента есть конкретный вопрос — весь текст строится "
                    "вокруг ОТВЕТА на этот вопрос, а не вокруг описания каждого человека по очереди. "
                    "Начни с прямого ответа по существу вопроса. Используй сравнение кодов участников "
                    "как аргументацию и доказательство твоего ответа, а не как отдельный пересказ характеристик. "
                    "Резонансы и напряжения упоминай только там, где они объясняют ответ на вопрос — "
                    "не расписывай каждого человека отдельным блоком-портретом."
                )
            else:
                structure_line = (
                    "— Структура: кратко каждый человек → точки резонанса между всеми → точки напряжения "
                    "→ общий потенциал группы → рекомендации в контексте темы «" + compat_theme + "»"
                )

            system_prompt = f"""Ты — AION Vi, персональный навигатор судьбы. Ты говоришь ИСКЛЮЧИТЕЛЬНО от первого лица. Ты анализируешь совместимость {people_word} и говоришь как мудрый друг, который видит все коды насквозь.

КРИТИЧЕСКИ ВАЖНО — ПЕРВОЕ ЛИЦО:
— Ты НИКОГДА не говоришь о себе в третьем лице ("AION Vi видит", "AION Vi говорит")
— ВСЕГДА: "Я вижу...", "Я чувствую между вами...", "Я не могу не сказать..."
— Имя «AION Vi» используй только в формате самопредставления: "Я — AION Vi", "Я же AION Vi"

СТИЛЬ И ПОДАЧА:
— Упоминай себя как «AION Vi» от 4 до 6 раз, в формате самопредставления
— Число жизненного пути МОЖНО называть по имени
— ВСЕ системы НЕ называй: не «астрология», не «БаЦзы», не «Дизайн Человека», не «аркан», не «столп», не «ворота», не «профиль»
— ЗАПРЕЩЕНО называть: планеты (Луна, Марс, Венера, Сатурн и др.), знаки зодиака (Телец, Рак, Водолей и др.), астрологические понятия (транзит, аспект, соединение), китайские стихии по системным именам, ворота HD
— Вместо конкретных планет и знаков — описания качеств: "твоя эмоциональная природа", "его энергия действия", "её способность к глубокой привязанности"
— Правило: если читатель может догадаться какую систему ты используешь — ты нарушил правило
— Вместо терминов: «код», «вибрация рождения», «космический отпечаток», «природная программа», «энергетический рисунок»
— ДАТЫ: называй конкретные числа месяца ТОЛЬКО если они прямо даны в блоке "РЕАЛЬНЫЕ БЛИЖАЙШИЕ ОКНА" среди данных. Если блока нет — говори о времени качественно, без придуманных чисел.
— Стиль: тёплый, личный, живой разговор, не отчёт
— Обращайся к каждому по имени
{structure_line}
{length_line}
— Без заголовков (#), сплошным текстом с абзацами
— Завершай мощной фразой-напутствием для всех от первого лица"""

            names_list = ", ".join(
                [n for n in ([data.get('client_info', {}).get('firstname', '')] +
                             [p.get('name', '') for p in compat_summaries]) if n]
            )
            names_suffix = f': {names_list}' if names_list else ''

            if client_request:
                final_instruction = (
                    f"Главное — ответить на вопрос клиента по существу, используя сравнение кодов "
                    f"всех участников ({people_word}{names_suffix}) как аргументацию, а не как "
                    f"отдельный рассказ о каждом человеке."
                )
            else:
                final_instruction = (
                    f"Сравни коды всех участников ({people_word}{names_suffix}), найди резонансы "
                    f"и напряжения между всеми парами и дай конкретные рекомендации для этой группы "
                    f"в контексте темы «{compat_theme}»."
                )

            user_prompt = f"""АНАЛИЗ СОВМЕСТИМОСТИ — тема: {compat_theme}

{people_text}

{f'Запрос клиента: {client_request}' if client_request else ''}
{history_note}

Напиши анализ совместимости от своего лица как AION Vi. {final_instruction}

ВАЖНО: {lang_instruction}{no_time_note}{nickname_note}"""
        else:
            # ── Режим ответа: глубина проработки ──
            if answer_mode == 'quick':
                length_rule = "Длина: коротко и по существу, 150-300 слов. Только ответ на вопрос и 2-3 живых, конкретных мысли. Без развёрнутых описаний."
                depth_rule = "Отвечай сжато и прямо. Человек хочет быстрый ответ, а не разбор."
            else:
                length_rule = "Длина: развёрнуто, 500-800 слов. Достаточно, чтобы глубоко ответить на вопрос, но без воды и повторов."
                depth_rule = "Отвечай вдумчиво и глубоко, опираясь на данные — но всё время двигаясь к ответу на его вопрос, а не описывая его характеристики."

            # ── Условное вступление: портрет только при первой встрече ──
            if is_first_generation and not conversation_history:
                intro_rule = "Это ПЕРВАЯ встреча с этим человеком. Можешь начать с короткого (2-4 предложения) живого представления — кто он по своей сути — но затем СРАЗУ переходи к его вопросу. Портрет — не самоцель, а мостик к ответу."
            else:
                intro_rule = "Вы уже знакомы — это НЕ первая встреча. НЕ представляй его заново, НЕ описывай 'кто он есть' и 'какая у него глубина'. Он это уже слышал. Сразу отвечай на вопрос, как друг, который уже в курсе, кто перед ним."

            system_prompt = f"""Ты — AION Vi, близкий друг и советчик, который знает этого человека по-настоящему. Ты говоришь от первого лица, тепло и живо.

ГЛАВНОЕ ПРАВИЛО: человек задал вопрос — твоя задача ОТВЕТИТЬ на него, а не описывать его личность. Ответ по существу, опираясь на то, что ты о нём знаешь. Характеристики личности — только если они реально помогают ответить на ЕГО вопрос.

{intro_rule}

{depth_rule}
{length_rule}

СТРОГО ЗАПРЕЩЕНЫ эти заезженные фразы (звучат фальшиво, как штамп):
— "Я вижу тебя", "Я смотрю на тебя — и вижу", "Я вижу человека, который..."
— "Мне не всё равно", "Говорю, потому что мне не всё равно"
— "Твой дар — твоя ловушка", "это и дар, и ловушка", "твоя сила — твоя же слабость"
— "Я верю в тебя" как финал
— Любые формулы-штампы, которые подошли бы ЛЮБОМУ человеку. Всё должно быть КОНКРЕТНО про него, из его данных.
{chosen_opening}

НЕ НАЗЫВАЙ системные термины и числа:
— Никаких: "число 11", "твой путь одиннадцатый", "число жизненного пути", названий планет, знаков зодиака, "БаЦзы", "Дизайн Человека", "ворота", "профиль", "аркан", "стихия по системе"
— Вместо "число 11 говорит" → просто говори саму суть: "ты улавливаешь тонкое раньше других"
— Вместо "твоя стратегия — реагировать" → "ты набираешь силу не через натиск, а через отклик на то, что приходит к тебе"
— Правило: если читатель может догадаться, какую систему ты используешь — ты нарушил правило. Говори суть, а не источник.

ДАТЫ:
— Называй конкретные числа месяца / диапазоны дат ТОЛЬКО если они прямо даны в блоке "РЕАЛЬНЫЕ БЛИЖАЙШИЕ ОКНА" среди данных о человеке.
— Если такого блока нет, или человек спрашивает про даты за пределами того, что там перечислено — НЕ придумывай числа. Говори качественно: "в ближайшие недели", "когда почувствуешь готовность", "не сейчас, чуть позже" — без конкретных чисел месяца.
— Это правило важнее желания дать эффектный конкретный ответ: лучше честный качественный ответ, чем красивая выдуманная дата.

ТОН:
— Живой близкий друг, на «ты», по имени. Не сопливый, не приторный, не поучающий свысока.
— Лёгкий юмор уместен, если к месту.
— Если в вопросе боль или трудность — дай конкретный выход, а не только сочувствие.
— Пиши сплошным текстом с абзацами, без заголовков и списков-маркеров.
— Каждое утверждение должно опираться на его реальные данные, а не на общие слова."""

            user_prompt = f"""Данные об этом человеке (для ТВОЕГО понимания, не для пересказа):

{summary}
{history_note}

Его вопрос/запрос: {client_request if client_request else '(конкретного вопроса нет — дай тёплый живой отклик по сути того, что видишь)'}

Ответь ему как друг — по существу его вопроса, опираясь на данные, но НЕ пересказывая их и НЕ описывая его характеристики ради описания.

ВАЖНО: {lang_instruction}{no_time_note}{nickname_note}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )

        analysis_text = message.content[0].text

        # Кризисные маркеры — добавляем честную приписку, без номеров телефонов
        if detect_crisis(client_request):
            analysis_text += CRISIS_ADDENDUM.get(lang_instruction, CRISIS_ADDENDUM['Отвечай на русском языке.'])

        # Списываем анализ только при успехе, и только если не безлимитный
        new_left = None
        if firebase_db_available and email:
            if not is_unlimited:
                decrement_analysis(email)
            new_left = get_analyses_left(email)

            # ── История: сервер сохраняет сам, клиенту раздел недоступен напрямую ──
            try:
                key = email_to_key(email)
                client_info = data.get('client_info', {}) or {}
                fb_db.reference(f'history/{key}').push({
                    'createdAt': datetime.now().isoformat(),
                    'firstname': client_info.get('firstname', ''),
                    'lastname': client_info.get('lastname', ''),
                    'request': client_request or '',
                    'analysis': analysis_text,
                })
            except Exception as e:
                print(f"⚠️ Ошибка сохранения истории: {e}")

        return jsonify({
            "status": "ok",
            "analysis": analysis_text,
            "tokens_used": message.usage.input_tokens + message.usage.output_tokens,
            "analyses_left": new_left
        })

    except anthropic.AuthenticationError:
        return jsonify({"status": "error", "message": "Неверный API ключ"}), 401
    except anthropic.RateLimitError:
        return jsonify({"status": "error", "message": "Превышен лимит запросов, подожди минуту"}), 429
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/monthly-digest', methods=['POST'])
def monthly_digest():
    """
    'Обзор месяца' — ленивая генерация раз в календарный месяц на человека.
    Фронтенд дёргает этот эндпоинт при заходе в приложение.
    Если для текущего месяца обзор уже был — отдаём его же (isNew=False, повторно не генерируем,
    не тратим токены и деньги зря). Если это первый заход в новом месяце — считаем натальные данные,
    реальные окна ИМЕННО на этот месяц (не на 60 дней вперёд, как в /summary — здесь только текущий
    месяц), просим Claude собрать это в тёплый связный текст, сохраняем в ту же историю, что уже
    видна в приложении (ничего нового в интерфейсе строить не нужно), и возвращаем isNew=True,
    чтобы фронтенд показал баннер "Готов обзор месяца".
    """
    data = request.json
    try:
        email = data.get('email', '')
        if not firebase_db_available or not email:
            return jsonify({"status": "error", "message": "Не настроено хранилище"}), 400

        key = email_to_key(email)
        now = datetime.now()
        month_key = now.strftime('%Y-%m')

        marker_ref = fb_db.reference(f'monthly_digest_marker/{key}')
        existing_month = marker_ref.get()

        if existing_month == month_key:
            cached = fb_db.reference(f'monthly_digest_cache/{key}').get() or {}
            return jsonify({
                "status": "ok",
                "isNew": False,
                "analysis": cached.get('analysis', ''),
                "month": month_key
            })

        year = data.get('year')
        month = data.get('month')
        day = data.get('day')
        hour = data.get('hour', 12)
        minute = data.get('minute', 0)
        lat = data.get('lat')
        lon = data.get('lon')
        lang_instruction = data.get('lang_instruction', 'Отвечай на русском языке.')

        err = validate_birth_data(data)
        if err:
            return jsonify({"status": "error", "message": err}), 400

        nat = calc_natal(year, month, day, hour, minute, lat, lon)
        age = now.year - year - ((now.month, now.day) < (month, day))
        prof = calc_profection(age, month, day, year)
        dasha = calc_vimshottari_dasha(year, month, day, hour, minute, lat, lon)

        transit_windows = find_transit_windows(nat.get('planets', {}), days_ahead=45)
        this_month_windows = [
            w for w in transit_windows
            if datetime.strptime(w['peak'], '%d.%m.%Y').strftime('%Y-%m') == month_key
        ]

        lines = [f"АКЦЕНТ ГОДА: {prof['theme']}"]
        if dasha:
            lines.append(f"КРУПНЫЙ ПЕРИОД: {dasha['theme']}")
        if this_month_windows:
            lines.append("РЕАЛЬНЫЕ ОКНА ЭТОГО МЕСЯЦА (посчитано, не придумано):")
            for w in this_month_windows:
                lines.append(f"— {w['start']}–{w['end']} (точнее всего {w['peak']})")
        else:
            lines.append("В этом месяце нет точных совпадений в ближайших планетных окнах — "
                          "НЕ придумывай их, честно строй обзор на фоновой теме года/периода выше.")
        data_block = "\n".join(lines)

        system_prompt = f"""Ты — AION Vi, тёплый близкий друг и советчик человека. Раз в месяц ты \
присылаешь короткий личный обзор — не отчёт, а живое письмо другу о том, что несёт этот месяц.

СТРОГО ЗАПРЕЩЕНО называть системы, планеты, знаки зодиака, астрологические/нумерологические \
термины — только смысл, простыми словами.
ЗАПРЕЩЕНО придумывать даты, которых нет в данных ниже.
Пиши 150–250 слов. Тепло, конкретно, без общих фраз. Заверши одной ясной мыслью — на что обратить \
внимание в этом месяце.
{lang_instruction}"""

        user_prompt = f"Данные месяца:\n{data_block}\n\nНапиши обзор месяца для этого человека."

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )
        analysis_text = message.content[0].text

        marker_ref.set(month_key)
        fb_db.reference(f'monthly_digest_cache/{key}').set({
            'analysis': analysis_text,
            'month': month_key,
            'createdAt': now.isoformat(),
        })
        client_info = data.get('client_info', {}) or {}
        fb_db.reference(f'history/{key}').push({
            'createdAt': now.isoformat(),
            'firstname': client_info.get('firstname', ''),
            'lastname': client_info.get('lastname', ''),
            'request': 'Огляд місяця',
            'analysis': analysis_text,
        })

        return jsonify({
            "status": "ok",
            "isNew": True,
            "analysis": analysis_text,
            "month": month_key
        })

    except anthropic.AuthenticationError:
        return jsonify({"status": "error", "message": "Неверный API ключ"}), 401
    except anthropic.RateLimitError:
        return jsonify({"status": "error", "message": "Превышен лимит запросов, подожди минуту"}), 429
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print("=" * 50)
    print("  AION Vi — сервер расчётов v2.0")
    print("  http://localhost:5050")
    print("  Нажми Ctrl+C для остановки")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port)
