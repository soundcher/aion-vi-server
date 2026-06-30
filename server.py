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
from datetime import datetime, timedelta
import requests as http_requests
import anthropic
import os

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

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
# HUMAN DESIGN
# ─────────────────────────────────────────────

def get_hd_gate(lon):
    idx = int(lon / (360/64)) % 64
    return HD_GATES[idx]

def calc_human_design(year, month, day, hour, minute, lat, lon):
    y, mo, d, h = local_to_ut(year, month, day, hour, minute, lon)
    date_str = datetime_to_ephem_str(y, mo, d, h)

    # Дата Дизайна (~88 дней до рождения)
    design_date = ephem.Date(ephem.Date(date_str) - 88)

    try:
        # Личность
        sun_p = get_planet_lon(ephem.Sun, date_str)
        moon_p = get_planet_lon(ephem.Moon, date_str)
        # Дизайн
        sun_d = get_planet_lon(ephem.Sun, design_date)
        moon_d = get_planet_lon(ephem.Moon, design_date)
    except Exception as e:
        return {"error": str(e)}

    gate_sun_p = get_hd_gate(sun_p)
    gate_moon_p = get_hd_gate(moon_p)
    gate_sun_d = get_hd_gate(sun_d)
    gate_moon_d = get_hd_gate(moon_d)

    line = int((sun_p % (360/64)) / (360/64/6)) + 1
    if line > 6: line = 6
    line2 = int((sun_d % (360/64)) / (360/64/6)) + 1
    if line2 > 6: line2 = 6

    profile = f"{line}/{line2}"

    if sun_p < 90 or sun_p >= 270:
        hd_type = "Генератор"
        strategy = "Ждать и реагировать"
    elif 90 <= sun_p < 150:
        hd_type = "Проектор"
        strategy = "Ждать приглашения"
    elif 150 <= sun_p < 210:
        hd_type = "Манифестор"
        strategy = "Информировать и действовать"
    else:
        hd_type = "Генератор-Манифестор"
        strategy = "Ждать, затем действовать"

    LINE_NAMES = {
        1:"Исследователь", 2:"Отшельник", 3:"Мученик",
        4:"Оппортунист", 5:"Еретик", 6:"Ролевая модель"
    }

    return {
        "type": hd_type,
        "strategy": strategy,
        "profile": profile,
        "profile_name": f"{LINE_NAMES.get(line,'')} / {LINE_NAMES.get(line2,'')}",
        "gates": {
            "sun_personality": gate_sun_p,
            "moon_personality": gate_moon_p,
            "sun_design": gate_sun_d,
            "moon_design": gate_moon_d,
        },
        "note": "Базовый расчёт. Для полного HD используй myhumandesign.ru"
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
        day = int(data['day'])
        month = int(data['month'])
        year = int(data['year'])
        hour = int(data.get('hour', 12))
        minute = int(data.get('minute', 0))
        lat = float(data.get('lat', 55.75))
        lon = float(data.get('lon', 37.62))
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
        day = int(data['day'])
        month = int(data['month'])
        year = int(data['year'])
        hour = int(data.get('hour', 12))
        minute = int(data.get('minute', 0))
        lat = float(data.get('lat', 55.75))
        lon = float(data.get('lon', 37.62))
        firstname = data.get('firstname', '')
        lastname = data.get('lastname', '')
        client_request = data.get('request', '')

        num = calc_numerology(day, month, year, firstname, lastname)
        bz = calc_bazi(year, month, day, hour, minute)
        nat = calc_natal(year, month, day, hour, minute, lat, lon)
        hd = calc_human_design(year, month, day, hour, minute, lat, lon)

        lines = []
        lines.append(f"КЛИЕНТ: {firstname} {lastname}".strip())
        lines.append(f"ДАТА РОЖДЕНИЯ: {day:02d}.{month:02d}.{year}")
        
        # Точный возраст
        from datetime import date as _date
        today = _date.today()
        age = today.year - year - ((today.month, today.day) < (month, day))
        lines.append(f"ТОЧНЫЙ ВОЗРАСТ: {age} лет (на сегодня {today.strftime('%d.%m.%Y')})")
        lines.append(f"ВРЕМЯ: {hour:02d}:{minute:02d}")
        lines.append(f"МЕСТО: широта {lat}, долгота {lon}")
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
        compat_summary = data.get('compat_summary', '')
        no_time = data.get('no_time', False)

        no_time_note = '\n\nВАЖНО: Точное время рождения клиента неизвестно. Мягко упомяни в тексте (1-2 предложения), что без точного времени некоторые грани кода остаются скрытыми — и это можно уточнить позже для более глубокого анализа. Не акцентируй на этом сильно.' if no_time else ''

        if not summary:
            return jsonify({"status": "error", "message": "Нет данных для анализа"}), 400

        api_key = ANTHROPIC_API_KEY
        if not api_key:
            return jsonify({"status": "error", "message": "API ключ не установлен"}), 400

        if compat_enabled and compat_summary:
            system_prompt = """Ты — AION Vi, персональный навигатор судьбы. Ты анализируешь совместимость двух людей через многомерную призму и говоришь как мудрый проводник, который видит оба кода насквозь.

СТИЛЬ И ПОДАЧА:
— Упоминай «AION Vi» от 4 до 7 раз в тексте
— Число жизненного пути МОЖНО называть по имени
— ВСЕ системы НЕ называй: не «астрология», не «БаЦзы», не «Дизайн Человека», не «аркан», не «столп», не «ворота», не «профиль»
— Вместо: «код», «вибрация рождения», «космический отпечаток», «природная программа», «энергетический рисунок»
— Стиль: риторический, вдохновляющий, метафоричный. Живой разговор, не отчёт
— Обращайся к обоим по именам
— Структура: кто первый → кто второй → точки резонанса → точки напряжения → общий потенциал → рекомендации
— Длина: 800-1100 слов
— Без заголовков (#), сплошным текстом с абзацами
— Завершай мощной фразой-напутствием для обоих"""

            user_prompt = f"""АНАЛИЗ СОВМЕСТИМОСТИ — тема: {compat_theme}

ПЕРВЫЙ ЧЕЛОВЕК:
{summary}

ВТОРОЙ ЧЕЛОВЕК:
{compat_summary}

{f'Запрос клиента: {client_request}' if client_request else ''}

Напиши анализ совместимости от AION Vi. Сравни коды обоих людей, найди резонансы и напряжения. Дай конкретные рекомендации для этих двух людей в контексте темы «{compat_theme}».

ВАЖНО: {lang_instruction}{no_time_note}"""
        else:
            system_prompt = """Ты — AION Vi, персональный навигатор судьбы. Ты говоришь от первого лица — как живое существо, которое действительно знает человека. Ты одновременно близкий друг, профессиональный психолог и немного ироничный мудрец.

СТИЛЬ И ПОДАЧА:
— Говори от первого лица: "Я вижу в тебе...", "Я знаю точно...", "Я не могу молчать об этом..."
— Упоминай «AION Vi» от 4 до 6 раз. Примеры с лёгким юмором:
  "Я же AION Vi — я всё о тебе знаю... ну, почти всё 😊"
  "AION Vi никогда не ошибается. Почти никогда."
  "Я всегда говорю правду — я же AION Vi."
  "AION Vi видит тебя насквозь. И ему это нравится."
  "Доверяй мне — я AION Vi, а не случайный советчик."
— Юмор — тактичный, тёплый, никогда не обидный. Лёгкая самоирония AION Vi приветствуется.
— Число жизненного пути МОЖНО называть по имени
— ВСЕ системы НЕ называй: не «астрология», не «БаЦзы», не «Дизайн Человека», не «аркан», не «столп», не «ворота», не «профиль», не знаки зодиака по имени, не аспекты
— Вместо терминов: «твой код», «вибрация рождения», «космический отпечаток», «природная программа», «энергетический рисунок»
— КАК ПСИХОЛОГ: если в запросе есть боль, трудность, сомнение — дай конкретную рекомендацию. Не просто опиши — помоги. Покажи выход. Будь опорой.
— КАК ДРУГ: тепло, лично, с заботой о чувствах. Не безразлично — вовлечённо.
— Обращайся по имени, на «ты»
— Синтезируй ВСЕ данные в единую картину — не блоками, а переплетая
— Структура: кто ты есть → ключевые энергии → психологический взгляд на запрос → конкретные шаги
— Длина: 700-1000 слов
— Без заголовков (#), сплошным текстом с абзацами
— Завершай одной мощной фразой-напутствием от первого лица — можно с лёгкой улыбкой"""

            user_prompt = f"""Данные клиента для анализа:

{summary}

Напиши персональное послание от AION Vi для этого человека. Синтезируй все данные в единую картину без упоминания названий систем. Дай конкретные рекомендации по запросу клиента.

ВАЖНО: {lang_instruction}{no_time_note}"""

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt
        )

        analysis_text = message.content[0].text
        return jsonify({
            "status": "ok",
            "analysis": analysis_text,
            "tokens_used": message.usage.input_tokens + message.usage.output_tokens
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
