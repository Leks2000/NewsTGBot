import io
import os
import asyncio
import feedparser
import aiohttp
import logging
import random
import sqlite3
import hashlib
import json
import re
import sys
from dotenv import load_dotenv
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz

load_dotenv()

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")

CHANNEL_RU = '@bulmyash'
CHANNEL_EN = '@WORLD_ALERT_NEWS'

TIMEZONE = "Europe/Moscow"

if sys.platform == "win32":
    TEMP_DIR = "C:/temp/shorts"
else:
    TEMP_DIR = "/tmp/shorts"
os.makedirs(TEMP_DIR, exist_ok=True)

# ================== RSS ИСТОЧНИКИ ==================
RSS_SOURCES_RU = {
    "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "tass": "https://tass.ru/rss/v2.xml",
    "interfax": "https://www.interfax.ru/rss.asp",
    "kommersant": "https://www.kommersant.ru/RSS/news.xml",
    "ria": "https://ria.ru/export/rss2/index.xml",
    "lenta": "https://lenta.ru/rss",
    "gazeta": "https://www.gazeta.ru/export/rss/first.xml",
    "vedomosti": "https://www.vedomosti.ru/rss/news",
    "izvestia": "https://iz.ru/xml/rss/all.xml",
    "rt_ru": "https://russian.rt.com/rss",
    "fontanka": "https://www.fontanka.ru/fontanka.rss",
    "rosbalt": "https://www.rosbalt.ru/feed/",
    "forbes_ru": "https://www.forbes.ru/newrss.xml",
    "cnews": "https://www.cnews.ru/inc/rss/news.xml",
    "habr": "https://habr.com/ru/rss/all/all/",
    "meduza": "https://meduza.io/rss/all",
}

RSS_SOURCES_EN = {
    "reuters": "https://feeds.reuters.com/reuters/worldNews",
    "bbc": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "cnn": "http://rss.cnn.com/rss/edition_world.rss",
    "ap": "https://rsshub.app/apnews/topics/world-news",
    "guardian": "https://www.theguardian.com/world/rss",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "aljazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "france24": "https://www.france24.com/en/rss",
    "dw": "https://rss.dw.com/rdf/rss-en-all",
    "rt_en": "https://www.rt.com/rss/news/",
    "politico": "https://www.politico.com/rss/politicopicks.xml",
    "thehill": "https://thehill.com/feed/",
    "npr": "https://feeds.npr.org/1001/rss.xml",
    "abc": "https://abcnews.go.com/abcnews/internationalheadlines",
    "sky": "https://feeds.skynews.com/feeds/rss/world.xml",
}

# ================== BREAKING KEYWORDS (НОВОЕ!) ==================
BREAKING_KEYWORDS_RU = [
    'срочно', 'молния', 'экстренно', 'взрыв', 'теракт', 'война',
    'ядерн', 'ракетн', 'вторжен', 'переворот', 'убит', 'погиб',
    'крушени', 'катастроф', 'обвал', 'дефолт', 'импичмент',
    'объявил войну', 'ввёл войска', 'чрезвычайн', 'эвакуац',
]

BREAKING_KEYWORDS_EN = [
    'breaking', 'urgent', 'explosion', 'terror', 'war declared',
    'nuclear', 'missile', 'invasion', 'coup', 'killed', 'dead',
    'crash', 'catastrophe', 'collapse', 'default', 'impeach',
    'troops deployed', 'emergency', 'evacuation', 'assassination',
    'martial law', 'airspace closed',
]

# ================== КЛЮЧЕВЫЕ СЛОВА ==================
KEYWORDS_RU = [
    'путин', 'правительств', 'кремл', 'госдум', 'президент',
    'министр', 'трамп', 'байден', 'зеленск', 'сша', 'китай',
    'биткоин', 'bitcoin', 'btc', 'криптовалют', 'рубль', 'доллар',
    'евро', 'курс валют', 'цб', 'центробанк', 'инфляц',
    'нефть', 'газ', 'золото', 'драгметалл', 'brent', 'urals',
    'санкц', 'война', 'конфликт', 'армия', 'всу',
    'удар', 'обстрел', 'атак', 'авар', 'пожар', 'взрыв',
    'погиб', 'жертв', 'задержа', 'арест', 'суд', 'приговор',
    'искусственн', 'нейросет', 'chatgpt', 'google', 'apple',
    'учен', 'космос', 'выбор', 'закон', 'олимпиад', 'чемпионат',
    'скандал', 'коррупц', 'расследован'
]

KEYWORDS_EN = [
    'putin', 'kremlin', 'russia', 'president', 'government',
    'trump', 'biden', 'zelensky', 'usa', 'china', 'nato',
    'bitcoin', 'btc', 'crypto', 'cryptocurrency', 'ethereum',
    'dollar', 'euro', 'pound', 'fed', 'federal reserve',
    'stock market', 'wall street', 'dow jones', 'nasdaq',
    'inflation', 'economy', 'recession', 'gdp',
    'oil', 'crude', 'brent', 'gas', 'gold', 'silver',
    'sanctions', 'war', 'conflict', 'military',
    'attack', 'strike', 'explosion', 'fire', 'crash',
    'killed', 'death', 'arrest', 'court', 'verdict',
    'ai', 'chatgpt', 'google', 'apple', 'tesla', 'musk',
    'science', 'space', 'election', 'law', 'breaking',
    'scandal', 'corruption', 'investigation'
]

# ================== ЧЁРНЫЕ СПИСКИ ==================
BORING_KEYWORDS_RU = [
    'погода', 'синоптик', 'температур', 'осадк', 'прогноз погоды',
    'гороскоп', 'лунный', 'сонник', 'приметы', 'именины',
    'стажировк', 'обеспечить', 'поручил', 'совещани', 'заседани',
    'вручил', 'наградил', 'поздравил', 'встретился',
    'туберкулез', 'грипп', 'орви', 'простуд', 'вакцинац',
    'прививк', 'поликлиник', 'больниц',
    'школьник', 'ученик', 'учител', 'урок', 'домашн',
    'экзамен', 'егэ', 'олимпиад',
    'выставк', 'концерт', 'фестивал', 'премьер', 'спектакл',
    'чемпионат', 'турнир', 'матч', 'игра', 'тренер',
]

BORING_KEYWORDS_EN = [
    'weather', 'forecast', 'temperature', 'rain', 'snow',
    'horoscope', 'zodiac', 'lottery', 'astrology',
    'meeting', 'conference', 'seminar', 'workshop',
    'awarded', 'honored', 'congratulated',
    'flu', 'cold', 'vaccine', 'vaccination', 'clinic',
    'kardashian', 'royal family', 'celebrity baby',
    'engagement', 'wedding', 'divorce',
    'recipe', 'cooking tips', 'lifestyle',
]

BLACKLIST_CHANNELS = [
    'kids', 'children', 'cartoon', 'animation', 'nursery',
    'minecraft', 'майнкрафт', 'roblox', 'fortnite', 'gaming', 'геймер',
    'asmr', 'асмр', 'mukbang', 'мукбанг', 'prank', 'пранк',
    'tiktok compilation', 'shorts compilation',
    # ИНДИЯ — расширенный список
    'rankers gurukul', 'study iq', 'dhruv rathee', 'technical guruji',
    'total gaming', 'carryminati', 'bb ki vines', 'ashish chanchlani',
    'round2hell', 'harsh beniwal', 'elvish yadav', 'physics wallah',
    'unacademy', 'byju', 'vedantu', 'khan sir', 'alakh pandey',
    'sandeep maheshwari', 'vivek bindra', 'beer biceps',
    'amit bhadana', 'triggered insaan', 'lakshay chaudhary',
    'flying beast', 'sourav joshi', 'manoj dey', 'techno gamerz',
    'gyan therapy', 'facts mine', 'top 10 hindi', 'abhi and niyu',
]

BLACKLIST_TOPICS = [
    'майнкрафт', 'minecraft', 'roblox', 'fortnite',
    'asmr', 'асмр', 'мукбанг', 'mukbang',
    'детский', 'kids', 'children', 'cartoon',
    'пранк', 'prank', 'челлендж', 'challenge',
    'гадание', 'tarot', 'астролог',
]

# ================== YOUTUBE КАНАЛЫ ==================
RU_NEWS_CHANNELS = [
    "РИА Новости", "ТАСС", "Известия", "Интерфакс", "РБК",
    "Коммерсантъ", "Ведомости", "Первый канал", "Россия 24",
    "НТВ", "RT", "ДЕНЬ ТВ", "Кремль",
    "Дождь", "Медуза", "Новая газета",
    "вДудь", "Популярная политика", "ФЕЙГИН LIVE",
    "Время Прядко", "Время Прядко Shorts",
    "Редакция", "Varlamov", "Varlamov News",
    "Soloviev LIVE", "Соловьёв LIVE", "60 минут",
    "Царьград ТВ", "Спутник", "Life", "Лайф",
    "Mash", "Shot", "112", "Baza", "База",
    "Readovka", "WarGonzo", "Rybar", "Рыбарь",
    "BRIEF", "Незыгарь", "Подъём", "Новости",
    "Политика сегодня", "Россия 1", "ОТР",
    "Эхо", "The Insider", "Важные истории",
]

EN_NEWS_CHANNELS = [
    "BBC News", "CNN", "Reuters", "Al Jazeera English",
    "Sky News", "NBC News", "ABC News", "CBS News",
    "Fox News", "MSNBC", "Bloomberg", "CNBC",
    "The Guardian", "The New York Times", "Washington Post",
    "AP Archive", "AFP News Agency", "DW News",
    "France 24 English", "Euronews", "WION",
    "Times Radio", "Channel 4 News", "ITV News",
    "Global News", "CTV News", "PBS NewsHour",
    "Vice News", "Vox", "The Economist",
]

RU_ENTERTAINMENT_CHANNELS = [
    "ЧБД", "Labelcom", "Stand-Up Club #1", "Roast Battle",
    "Импровизация", "Где логика", "Что было дальше",
    "SciOne", "Научпок", "Арзамас", "Правда Глаза Колет",
    "Топлес", "Utopia Show", "Droider", "Wylsacom",
    "AdMe", "5-Minute Crafts LIKE",
]

EN_ENTERTAINMENT_CHANNELS = [
    "Veritasium", "Vsauce", "Kurzgesagt", "SmarterEveryDay",
    "Mark Rober", "Tom Scott", "CGP Grey",
    "MKBHD", "Linus Tech Tips", "JerryRigEverything",
    "Johnny Harris", "Wendover Productions", "RealLifeLore",
    "Half as Interesting", "PolyMatter",
]

RU_COMMENTARY_CHANNELS = [
    "Дмитрий Гордон", "Невзоров", "Кац", "Шульман",
    "Популярная политика", "А поговорить",
    "KamikadzeDead", "ThisIsХорошо", "Бородач",
    "Живой Гвоздь", "Cynicmansion",
    "ФЕЙГИН LIVE", "Навальный LIVE",
]

EN_COMMENTARY_CHANNELS = [
    "Shawn Ryan Show", "Joe Rogan Experience",
    "Ben Shapiro", "Tucker Carlson",
    "The Daily Show", "Last Week Tonight",
    "Late Night with Seth Meyers",
    "Breaking Points", "Russell Brand",
    "Tim Pool", "Jordan Peterson",
    "The Young Turks", "TYT",
    "The Jimmy Dore Show",
]

# ================== КАТЕГОРИИ КОНТЕНТА ==================
CONTENT_CATEGORIES = {
    "news": {
        "weight": 35,
        "queries_ru": [
            "новости россии сегодня", "путин заявил", "трамп новости",
            "мировые новости", "срочные новости", "главное за день",
        ],
        "queries_en": [
            "breaking news today", "world news", "trump news",
            "biden news", "russia news", "china news",
        ]
    },
    "politics": {
        "weight": 15,
        "queries_ru": [
            "политика россия", "кремль новости", "госдума",
            "международные отношения", "санкции",
        ],
        "queries_en": [
            "politics news", "white house", "congress",
            "european union", "nato news",
        ]
    },
    "economy": {
        "weight": 10,
        "queries_ru": [
            "курс доллара", "экономика россии", "рубль сегодня",
            "нефть газ", "биржа",
        ],
        "queries_en": [
            "stock market", "economy news", "bitcoin",
            "inflation", "fed rates",
        ]
    },
    "science_tech": {
        "weight": 15,
        "queries_ru": [
            "наука открытия", "технологии новости", "космос",
            "искусственный интеллект", "нейросети",
        ],
        "queries_en": [
            "science news", "tech news", "ai news",
            "space news", "innovation",
        ]
    },
    "entertainment": {
        "weight": 10,
        "queries_ru": [
            "интересные факты", "невероятные истории", "топ фактов",
            "удивительное рядом", "познавательное",
        ],
        "queries_en": [
            "amazing facts", "interesting facts", "mind blowing",
            "did you know", "incredible stories",
        ]
    },
    "commentary": {
        "weight": 15,
        "queries_ru": [
            "политический юмор", "сатира новости", "смешные новости",
            "политические мемы", "разбор политики", "мнение эксперта",
        ],
        "queries_en": [
            "political satire", "news commentary", "political memes",
            "political humor", "expert opinion", "political reaction",
        ]
    },
}

# ================== БАЗА ДАННЫХ ==================
DB_FILE = "news.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Таблицы для RU
c.execute('''CREATE TABLE IF NOT EXISTS posted_ru (
    hash TEXT UNIQUE, posted_at TEXT, title TEXT, url TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS youtube_posted_ru (
    video_id TEXT UNIQUE, posted_at TEXT, type TEXT, category TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_stats_ru (
    date TEXT UNIQUE, news_count INT DEFAULT 0, shorts_count INT DEFAULT 0
)''')

# Таблицы для EN
c.execute('''CREATE TABLE IF NOT EXISTS posted_en (
    hash TEXT UNIQUE, posted_at TEXT, title TEXT, url TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS youtube_posted_en (
    video_id TEXT UNIQUE, posted_at TEXT, type TEXT, category TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_stats_en (
    date TEXT UNIQUE, news_count INT DEFAULT 0, shorts_count INT DEFAULT 0
)''')

# Общие таблицы
c.execute('''CREATE TABLE IF NOT EXISTS youtube_channels_used (
    channel_name TEXT, used_at TEXT, lang TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS used_images (
    url TEXT, used_at TEXT
)''')

# АНАЛИТИКА
c.execute('''CREATE TABLE IF NOT EXISTS analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, lang TEXT, content_type TEXT, category TEXT,
    title TEXT, channel TEXT, views INT, likes INT, success BOOLEAN
)''')

# НОВОЕ! Таблица горячих тем для тредов
c.execute('''CREATE TABLE IF NOT EXISTS hot_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_hash TEXT,
    keywords TEXT,
    first_message_id INT,
    channel_id TEXT,
    lang TEXT,
    created_at TEXT,
    last_update TEXT,
    update_count INT DEFAULT 1
)''')

# НОВОЕ! Таблица breaking-событий (антифлуд)
c.execute('''CREATE TABLE IF NOT EXISTS breaking_events (
    hash TEXT UNIQUE,
    title TEXT,
    lang TEXT,
    posted_at TEXT
)''')

conn.commit()


def migrate_database():
    """Добавляет недостающие колонки в старую базу"""
    try:
        c.execute("SELECT lang FROM youtube_channels_used LIMIT 1")
    except sqlite3.OperationalError:
        log.info("🔧 Миграция базы: добавляю колонку 'lang'...")
        c.execute("ALTER TABLE youtube_channels_used ADD COLUMN lang TEXT DEFAULT 'ru'")
        c.execute("UPDATE youtube_channels_used SET lang = 'ru' WHERE lang IS NULL")
        conn.commit()
        log.info("✅ База обновлена!")

    c.execute("SELECT COUNT(*) FROM youtube_channels_used WHERE lang IS NULL")
    null_count = c.fetchone()[0]
    if null_count > 0:
        c.execute("UPDATE youtube_channels_used SET lang = 'ru' WHERE lang IS NULL")
        conn.commit()


# ================== СТАТИСТИКА ==================
def get_today_stats(lang: str):
    today = datetime.now().date().isoformat()
    table = f"daily_stats_{lang}"
    c.execute(f"SELECT news_count, shorts_count FROM {table} WHERE date = ?", (today,))
    result = c.fetchone()
    return {"news": result[0], "shorts": result[1]} if result else {"news": 0, "shorts": 0}


def increment_stat(lang: str, stat_type: str):
    today = datetime.now().date().isoformat()
    table = f"daily_stats_{lang}"
    stats = get_today_stats(lang)
    if stat_type == "news":
        stats["news"] += 1
    else:
        stats["shorts"] += 1
    c.execute(f"INSERT OR REPLACE INTO {table} (date, news_count, shorts_count) VALUES (?, ?, ?)",
              (today, stats["news"], stats["shorts"]))
    conn.commit()


def is_duplicate(title: str, url: str, lang: str):
    h = hashlib.md5((title + url).encode()).hexdigest()
    table = f"posted_{lang}"
    c.execute(f"SELECT 1 FROM {table} WHERE hash = ?", (h,))
    return c.fetchone() is not None


def save_posted(title: str, url: str, lang: str):
    h = hashlib.md5((title + url).encode()).hexdigest()
    table = f"posted_{lang}"
    c.execute(f"INSERT OR IGNORE INTO {table} (hash, posted_at, title, url) VALUES (?, ?, ?, ?)",
              (h, datetime.now().isoformat(), title, url))
    conn.commit()


def is_youtube_posted(video_id: str, lang: str):
    table = f"youtube_posted_{lang}"
    c.execute(f"SELECT 1 FROM {table} WHERE video_id = ?", (video_id,))
    return c.fetchone() is not None


def save_youtube_posted(video_id: str, video_type: str, category: str, lang: str):
    table = f"youtube_posted_{lang}"
    c.execute(f"INSERT OR IGNORE INTO {table} (video_id, posted_at, type, category) VALUES (?, ?, ?, ?)",
              (video_id, datetime.now().isoformat(), video_type, category))
    conn.commit()


def track_youtube_channel(channel_name: str, lang: str):
    c.execute("INSERT INTO youtube_channels_used (channel_name, used_at, lang) VALUES (?, ?, ?)",
              (channel_name.lower(), datetime.now().isoformat(), lang))
    conn.commit()
    three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
    c.execute("DELETE FROM youtube_channels_used WHERE used_at < ?", (three_days_ago,))
    conn.commit()


def get_recent_channels(hours: int, lang: str) -> list:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    c.execute("SELECT DISTINCT channel_name FROM youtube_channels_used WHERE used_at > ? AND lang = ?",
              (cutoff, lang))
    return [row[0] for row in c.fetchall()]


def get_channel_usage_count(channel_name: str, hours: int, lang: str) -> int:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    c.execute("SELECT COUNT(*) FROM youtube_channels_used WHERE channel_name = ? AND used_at > ? AND lang = ?",
              (channel_name.lower(), cutoff, lang))
    result = c.fetchone()
    return result[0] if result else 0


def track_used_image(url: str):
    c.execute("INSERT INTO used_images (url, used_at) VALUES (?, ?)",
              (url, datetime.now().isoformat()))
    conn.commit()
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute("DELETE FROM used_images WHERE used_at < ?", (month_ago,))
    conn.commit()


def log_analytics(lang: str, content_type: str, category: str, title: str,
                  channel: str = "", views: int = 0, likes: int = 0, success: bool = True):
    c.execute("""INSERT INTO analytics
                 (timestamp, lang, content_type, category, title, channel, views, likes, success)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (datetime.now().isoformat(), lang, content_type, category,
               title[:200], channel[:100], views, likes, success))
    conn.commit()


def get_analytics_summary(days: int = 7):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    summary = {}
    c.execute("""SELECT lang, COUNT(*), SUM(CASE WHEN success THEN 1 ELSE 0 END)
                 FROM analytics WHERE timestamp > ? GROUP BY lang""", (cutoff,))
    summary["by_lang"] = {row[0]: {"total": row[1], "success": row[2]} for row in c.fetchall()}
    c.execute("""SELECT category, COUNT(*), AVG(views)
                 FROM analytics WHERE timestamp > ? AND content_type = 'shorts'
                 GROUP BY category ORDER BY COUNT(*) DESC""", (cutoff,))
    summary["by_category"] = {row[0]: {"count": row[1], "avg_views": row[2]} for row in c.fetchall()}
    c.execute("""SELECT channel, COUNT(*), AVG(views)
                 FROM analytics WHERE timestamp > ? AND channel != ''
                 GROUP BY channel ORDER BY COUNT(*) DESC LIMIT 10""", (cutoff,))
    summary["top_channels"] = [(row[0], row[1], row[2]) for row in c.fetchall()]
    return summary


# ================== НОВОЕ! ГОРЯЧИЕ ТЕМЫ (треды) ==================
def extract_topic_keywords(title: str) -> list:
    """Извлекает ключевые слова из заголовка для матчинга тем"""
    stop_words_ru = {'в', 'на', 'и', 'по', 'с', 'из', 'за', 'к', 'от', 'до', 'о', 'об', 'что', 'как', 'не', 'но', 'а'}
    stop_words_en = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'has', 'had', 'do', 'did', 'not', 'and', 'or', 'but', 'if'}

    words = re.findall(r'[а-яёa-z]{3,}', title.lower())
    stop = stop_words_ru | stop_words_en
    return [w for w in words if w not in stop]


def find_related_topic(title: str, lang: str) -> dict:
    """Ищет связанную горячую тему за последние 6 часов"""
    keywords = extract_topic_keywords(title)
    if len(keywords) < 2:
        return None

    cutoff = (datetime.now() - timedelta(hours=6)).isoformat()
    c.execute("""SELECT id, topic_hash, keywords, first_message_id, channel_id, update_count
                 FROM hot_topics WHERE lang = ? AND created_at > ? ORDER BY created_at DESC""",
              (lang, cutoff))

    for row in c.fetchall():
        saved_keywords = json.loads(row[2])
        overlap = set(keywords) & set(saved_keywords)
        # Если 3+ общих слова — это та же тема
        if len(overlap) >= 3:
            return {
                "id": row[0],
                "topic_hash": row[1],
                "keywords": saved_keywords,
                "first_message_id": row[3],
                "channel_id": row[4],
                "update_count": row[5]
            }
    return None


def save_hot_topic(title: str, message_id: int, channel_id: str, lang: str):
    """Сохраняет новую горячую тему"""
    keywords = extract_topic_keywords(title)
    topic_hash = hashlib.md5(' '.join(sorted(keywords[:5])).encode()).hexdigest()

    c.execute("""INSERT INTO hot_topics (topic_hash, keywords, first_message_id, channel_id, lang, created_at, last_update, update_count)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
              (topic_hash, json.dumps(keywords), message_id, channel_id, lang,
               datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()


def update_hot_topic(topic_id: int):
    """Обновляет счётчик горячей темы"""
    c.execute("""UPDATE hot_topics SET last_update = ?, update_count = update_count + 1 WHERE id = ?""",
              (datetime.now().isoformat(), topic_id))
    conn.commit()


# ================== НОВОЕ! BREAKING антифлуд ==================
def is_breaking_duplicate(title: str, lang: str) -> bool:
    """Не постим одно и то же breaking дважды за 2 часа"""
    keywords = extract_topic_keywords(title)
    h = hashlib.md5(' '.join(sorted(keywords[:5])).encode()).hexdigest()
    cutoff = (datetime.now() - timedelta(hours=2)).isoformat()
    c.execute("SELECT 1 FROM breaking_events WHERE hash = ? AND posted_at > ?", (h, cutoff))
    return c.fetchone() is not None


def save_breaking_event(title: str, lang: str):
    keywords = extract_topic_keywords(title)
    h = hashlib.md5(' '.join(sorted(keywords[:5])).encode()).hexdigest()
    c.execute("INSERT OR REPLACE INTO breaking_events (hash, title, lang, posted_at) VALUES (?, ?, ?, ?)",
              (h, title[:200], lang, datetime.now().isoformat()))
    conn.commit()
    # Чистим старые
    old = (datetime.now() - timedelta(days=1)).isoformat()
    c.execute("DELETE FROM breaking_events WHERE posted_at < ?", (old,))
    conn.commit()


# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("news_bot")
bot = Bot(BOT_TOKEN)

# ================== AI HELPER ==================
async def ask_ai(prompt: str, temperature=0.7) -> str:
    if not OPENROUTER_API_KEY:
        return None

    models = [
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "google/gemma-2-9b-it:free",
    ]

    for model in models:
        try:
            async with aiohttp.ClientSession() as s:
                headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 800
                }
                async with s.post("https://openrouter.ai/api/v1/chat/completions",
                                  headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.debug(f"AI error ({model}): {e}")
            continue
    return None


# ================== ПРОВЕРКА КОНТЕНТА ==================
def has_cyrillic(text):
    return bool(re.search('[а-яА-ЯёЁ]', text))


def has_ukrainian(text):
    return any(l in text for l in ['є', 'і', 'ї', 'ґ', 'Є', 'І', 'Ї', 'Ґ'])


def is_russian_content(title: str, channel: str, description: str = "") -> bool:
    full_text = f"{title} {channel} {description}".lower()
    if not has_cyrillic(title + channel):
        return False
    if has_ukrainian(title + channel + description):
        return False
    ua_keywords = ['україн', 'ukrainian', 'київ', 'зеленськ', 'азов', 'всу', 'зсу']
    if any(kw in full_text for kw in ua_keywords):
        return False
    return True


def is_english_content(title: str, channel: str, description: str = "") -> bool:
    """ЖЁСТКАЯ проверка ТОЛЬКО английского контента — убиваем индусов"""
    full_text = f"{title} {channel} {description}"
    text_lower = full_text.lower()

    # 1. НЕТ кириллицы
    if has_cyrillic(full_text):
        return False

    # 2. ОБЯЗАТЕЛЬНО латиница
    if not re.search('[a-zA-Z]', title):
        return False

    # 3. НЕТ других алфавитов
    non_english_scripts = [
        r'[\u0900-\u097F]',  # Хинди (деванагари)
        r'[\u0980-\u09FF]',  # Бенгальский
        r'[\u0A00-\u0A7F]',  # Гурмукхи
        r'[\u0600-\u06FF]',  # Арабский
        r'[\u0750-\u077F]',  # Арабский доп
        r'[\u4E00-\u9FFF]',  # Китайский
        r'[\u3040-\u309F]',  # Хирагана
        r'[\u30A0-\u30FF]',  # Катакана
        r'[\uAC00-\uD7AF]',  # Корейский
        r'[\u0E00-\u0E7F]',  # Тайский
        r'[\u1000-\u109F]',  # Бирманский
        r'[\u0B80-\u0BFF]',  # Тамильский
        r'[\u0C00-\u0C7F]',  # Телугу
        r'[\u0C80-\u0CFF]',  # Каннада
        r'[\u0D00-\u0D7F]',  # Малаялам
        r'[\u0A80-\u0AFF]',  # Гуджарати
        r'[\u0B00-\u0B7F]',  # Ория
    ]
    for pattern in non_english_scripts:
        if re.search(pattern, full_text):
            return False

    # 4. Португальский/испанский/французский
    non_english_chars = ['ñ', 'ç', 'ã', 'õ', 'ü', 'ö', 'ä', 'ß', 'è', 'é', 'à', 'ô', 'ê', 'î', 'û']
    if any(char in text_lower for char in non_english_chars):
        return False

    portuguese_words = [
        'você', 'como', 'funciona', 'sabia', 'aqui', 'muito', 'mais',
        'esse', 'essa', 'quando', 'porque', 'então', 'agora', 'também',
        'ainda', 'depois', 'antes', 'sempre', 'nunca', 'apenas',
    ]
    spanish_words = [
        'cómo', 'qué', 'para', 'está', 'aquí', 'más', 'muy',
        'este', 'esta', 'cuando', 'porque', 'ahora', 'entonces',
        'también', 'siempre', 'nunca', 'después', 'antes',
    ]
    if any(word in text_lower for word in portuguese_words + spanish_words):
        return False

    # 5. ЖЁСТКИЙ ИНДИЙСКИЙ ФИЛЬТР
    indian_channel_keywords = [
        'hindi', 'हिन्दी', 'bengali', 'বাংলা', 'sangbad', 'khabar',
        'tamil', 'telugu', 'urdu', 'punjabi', 'gujarati', 'marathi',
        'bollywood', 'zee', 'aaj tak', 'ndtv india', 'republic bharat',
        'tomazoli', 'curiosidades', 'curioso', 'increible',
        'brasileiro', 'português', 'español',
        'india today', 'india tv', 'abp news', 'tv9',
        'news18', 'news24', 'first india', 'good news today',
        'the lallantop', 'soch by mohak', 'satish ray',
        'drishti ias', 'pw', 'allen', 'motion',
    ]
    channel_lower = channel.lower()
    if any(kw in channel_lower for kw in indian_channel_keywords):
        return False

    # 6. НОВОЕ! Проверка по описанию на хинди-слова в латинице
    hindi_transliterated = [
        'kya', 'hai', 'aur', 'yeh', 'woh', 'kaise', 'kyun', 'kab',
        'nahi', 'hoga', 'karo', 'dekho', 'bhai', 'yaar', 'dost',
        'bharat', 'desh', 'jaan', 'zindagi', 'pyar', 'dil',
        'samajh', 'padhai', 'paisa', 'sarkari', 'naukri',
    ]
    desc_lower = description.lower() if description else ""
    hindi_hits = sum(1 for w in hindi_transliterated if w in desc_lower)
    if hindi_hits >= 3:
        return False

    return True


def is_trusted_channel(channel: str, lang: str) -> bool:
    if lang == "ru":
        channels = RU_NEWS_CHANNELS + RU_ENTERTAINMENT_CHANNELS + RU_COMMENTARY_CHANNELS
    else:
        channels = EN_NEWS_CHANNELS + EN_ENTERTAINMENT_CHANNELS + EN_COMMENTARY_CHANNELS
    return any(t.lower() in channel.lower() for t in channels)


def is_blacklisted(title: str, channel: str) -> bool:
    text = f"{title} {channel}".lower()
    for banned in BLACKLIST_CHANNELS:
        if banned.lower() in text:
            return True
    for banned in BLACKLIST_TOPICS:
        if banned.lower() in text:
            return True
    return False


# ================== ВЫБОР КАТЕГОРИИ ==================
def select_category_by_time(lang: str) -> str:
    if lang == "ru":
        tz = pytz.timezone('Europe/Moscow')
    else:
        tz = pytz.timezone('America/New_York')

    local_time = datetime.now(tz)
    hour = local_time.hour

    if 6 <= hour < 10:
        weights = {"news": 60, "politics": 20, "economy": 10, "science_tech": 5, "entertainment": 3, "commentary": 2}
    elif 10 <= hour < 18:
        weights = {"news": 35, "politics": 20, "economy": 15, "science_tech": 15, "entertainment": 10, "commentary": 5}
    elif 18 <= hour < 23:
        weights = {"news": 25, "politics": 15, "economy": 5, "science_tech": 15, "entertainment": 25, "commentary": 15}
    else:
        weights = {"news": 20, "politics": 5, "economy": 5, "science_tech": 20, "entertainment": 35, "commentary": 15}

    categories = list(weights.keys())
    probs = list(weights.values())
    return random.choices(categories, weights=probs, k=1)[0]

# ================== НОВОЕ! ОПРЕДЕЛЕНИЕ BREAKING ==================
def calculate_breaking_score(title: str, lang: str) -> int:
    """Считает 'горячесть' новости. 0 = обычная, 3+ = BREAKING"""
    text = title.lower()
    breaking_kw = BREAKING_KEYWORDS_RU if lang == "ru" else BREAKING_KEYWORDS_EN
    score = sum(1 for kw in breaking_kw if kw in text)
    return score


# ================== AI: ВЫБОР И ОБРАБОТКА С ГОЛОСОМ ==================
async def ai_select_and_summarize(news_list: list, lang: str, is_breaking: bool = False) -> dict:
    news_text = "\n".join([f"{i+1}. {n['title']}" for i, n in enumerate(news_list[:25])])

    if lang == "ru":
        prompt = f"""Ты — злой, циничный редактор новостного канала в духе Лепры и Топора.
Твой стиль: едкий сарказм, чёрный юмор, без цензуры мыслей (но без мата).
Ты не сюсюкаешь. Ты пишешь так, будто устал от этого мира, но всё ещё следишь за ним.

{"🚨 ЭТО BREAKING! Пиши жёстко и срочно!" if is_breaking else ""}

⚠️ НЕ ВЫБИРАЙ: погоду, школы, совещания, философию, бюрократию.

✅ ВЫБИРАЙ: деньги, войну, скандалы, политику, шок, крипту.

ФОРМАТ:
- ЗАГОЛОВОК: 30-50 символов, цепляющий, с подколом или сарказмом. БЕЗ эмодзи.
- ПЕРЕСКАЗ: 1-3 предложения. Язвительно, но информативно. Читатель должен и узнать факт, и усмехнуться.
  {"Начни с ⚡️ BREAKING:" if is_breaking else ""}
- ХЕШТЕГИ: 3-4 штуки

ПРИМЕРЫ СТИЛЯ:
━━━━━━━━━━━━━━━━
Золото пробило $5K, а ты нет

Пока ты читал мемы, золото обновило исторический рекорд — $5,000 за унцию. Спрос на блестящие кирпичи растёт быстрее, чем твоя тревожность.

#Золото #Рекорд #Экономика
━━━━━━━━━━━━━━━━
Трамп опять сказал. Мир опять охнул

Экс-президент пообещал "закончить все войны за 24 часа". Осталось понять, он про чужие или про свои.

#Трамп #Политика #США
━━━━━━━━━━━━━━━━

ВАЖНО: "summary" НЕ ДОЛЖЕН БЫТЬ ПУСТЫМ. Минимум 2 предложения.

Верни JSON:
{{
  "selected": номер (1-{len(news_list[:25])}),
  "title": "Едкий заголовок 30-50 символов",
  "summary": "Циничный пересказ 2-3 предложения",
  "hashtags": "#Тег1 #Тег2 #Тег3"
}}

Новости:
{news_text}"""

    else:
        prompt = f"""You are a sharp, cynical news editor. Think The Daily Show meets Reuters.
Your style: dry wit, dark humor, no sugarcoating. You're tired of the world but still watching it burn.

{"🚨 THIS IS BREAKING! Write urgently and sharply!" if is_breaking else ""}

⚠️ DON'T PICK: weather, schools, meetings, celebrity gossip, recipes.
✅ PICK: money, war, scandals, politics, shock, crypto, tech.

FORMAT:
- TITLE: 30-50 chars, catchy with a twist. NO emojis.
- SUMMARY: 2-3 sentences. Sarcastic but informative. Reader should learn the fact AND smirk.
  {"Start with ⚡️ BREAKING:" if is_breaking else ""}
- HASHTAGS: 3-4 single words

STYLE EXAMPLES:
━━━━━━━━━━━━━━━━
Gold hits $5K. Your savings didn't.

Gold just smashed through $5,000/oz while your portfolio weeps quietly in the corner. Safe haven demand is up. So is everyone's anxiety.

#Gold #Record #Economy
━━━━━━━━━━━━━━━━
Trump promised again. World sighed again.

The former president vowed to "end all wars in 24 hours." Unclear if he means other people's wars or his own.

#Trump #Politics #USA
━━━━━━━━━━━━━━━━

IMPORTANT: "summary" MUST NOT BE EMPTY. Minimum 2 sentences.

Return JSON:
{{
  "selected": number (1-{len(news_list[:25])}),
  "title": "Sharp witty title 30-50 chars",
  "summary": "Cynical summary 2-3 sentences",
  "hashtags": "#tag1 #tag2 #tag3"
}}

News:
{news_text}"""

    response = await ask_ai(prompt, temperature=0.9)

    if response:
        try:
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                content = response[json_start:json_end + 1]
                result = json.loads(content)
                selected_idx = int(result.get("selected", 1)) - 1

                if 0 <= selected_idx < len(news_list):
                    selected = news_list[selected_idx]
                    selected["ai_title"] = result.get("title", selected["title"])
                    selected["summary"] = result.get("summary", "")
                    selected["hashtags"] = fix_hashtags(result.get("hashtags", ""), selected["title"], lang)
                    selected["is_breaking"] = is_breaking
                    return selected
        except Exception as e:
            log.warning(f"AI parse error: {e}")

    # Fallback
    selected = random.choice(news_list[:5])
    selected["ai_title"] = selected["title"]
    selected["summary"] = selected["desc"][:200] if selected["desc"] else ""
    selected["hashtags"] = generate_smart_hashtags(selected["title"], selected["desc"], lang)
    selected["is_breaking"] = is_breaking
    return selected


def fix_hashtags(raw_hashtags: str, title: str = "", lang: str = "ru") -> str:
    raw_hashtags = re.sub(r'@\w+', '', raw_hashtags).strip()
    tags = re.findall(r'#\w+', raw_hashtags)

    fixed_tags = []
    for tag in tags:
        word = tag[1:]
        parts = re.findall(r'[А-ЯЁA-Z][а-яёa-z]*|[а-яёa-z]+|[A-Z][a-z]*|[a-z]+', word)
        if len(parts) > 1 and len(word) > 12:
            for part in parts:
                if len(part) > 2:
                    fixed_tags.append(f"#{part}")
        else:
            fixed_tags.append(tag)

    if len(fixed_tags) < 2:
        auto_tags = generate_smart_hashtags(title, "", lang)
        auto_list = re.findall(r'#\w+', auto_tags)
        for auto_tag in auto_list:
            if auto_tag.lower() not in [t.lower() for t in fixed_tags]:
                fixed_tags.append(auto_tag)
                if len(fixed_tags) >= 3:
                    break

    seen = set()
    unique = []
    for tag in fixed_tags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique.append(tag)

    if len(unique) < 2:
        if lang == "ru":
            if "#новости" not in [t.lower() for t in unique]:
                unique.append("#Новости")
            if "#россия" not in [t.lower() for t in unique]:
                unique.append("#Россия")
        else:
            if "#news" not in [t.lower() for t in unique]:
                unique.append("#News")
            if "#world" not in [t.lower() for t in unique]:
                unique.append("#World")

    return ' '.join(unique[:4])


def generate_smart_hashtags(title: str, description: str, lang: str) -> str:
    text = f"{title} {description}".lower()
    tags = []

    if lang == "ru":
        if 'путин' in text: tags.append('#Путин')
        if 'трамп' in text: tags.append('#Трамп')
        if 'байден' in text: tags.append('#Байден')
        if 'сша' in text: tags.append('#США')
        if 'росси' in text: tags.append('#Россия')
        if 'украин' in text: tags.append('#Украина')
        if 'доллар' in text or 'рубль' in text: tags.append('#Курс')
        if 'война' in text: tags.append('#Война')
        if not tags: tags.append('#Новости')
    else:
        if 'putin' in text: tags.append('#Putin')
        if 'trump' in text: tags.append('#Trump')
        if 'biden' in text: tags.append('#Biden')
        if 'russia' in text: tags.append('#Russia')
        if 'usa' in text or 'america' in text: tags.append('#USA')
        if 'ukraine' in text: tags.append('#Ukraine')
        if 'war' in text: tags.append('#War')
        if not tags: tags.append('#News')

    return ' '.join(tags[:4])

# ================== КАРТИНКИ ==================
PERSON_SEARCH_QUERIES = {
    'трамп': ['donald trump', 'trump president'],
    'путин': ['vladimir putin', 'putin russia'],
    'байден': ['joe biden', 'biden president'],
    'trump': ['donald trump', 'trump president'],
    'putin': ['vladimir putin', 'putin russia'],
    'biden': ['joe biden', 'biden president'],
}


async def search_unsplash(query: str, count=10) -> list:
    if not UNSPLASH_ACCESS_KEY:
        return []
    try:
        url = "https://api.unsplash.com/search/photos"
        params = {"query": query, "per_page": count, "orientation": "landscape"}
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    return [{"url": p["urls"]["regular"], "source": "unsplash"}
                            for p in data.get("results", [])[:count]]
    except:
        pass
    return []


async def download_image(url: str):
    try:
        connector = aiohttp.TCPConnector(ssl=False, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


# ========== ГРАФИКИ ==========
async def get_bitcoin_data(days=30):
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    params = {"vs_currency": "usd", "days": days}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    return [(datetime.fromtimestamp(p[0] / 1000), p[1]) for p in data["prices"]]
    except:
        pass
    return []


async def get_gold_data(days=30):
    url = "https://api.coingecko.com/api/v3/coins/pax-gold/market_chart"
    params = {"vs_currency": "usd", "days": days}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    return [(datetime.fromtimestamp(p[0] / 1000), p[1]) for p in data["prices"]]
    except:
        pass
    return []


async def create_chart(data: list, title: str, ylabel: str, color: str = "#00ff00") -> bytes:
    if not data or len(data) < 2:
        return None
    dates = [d[0] for d in data]
    values = [d[1] for d in data]
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(dates, values, color=color, linewidth=2)
    ax.fill_between(dates, values, alpha=0.3, color=color)
    ax.set_title(title, fontsize=16, fontweight='bold', color='white')
    ax.set_ylabel(ylabel, fontsize=12, color='white')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    plt.xticks(rotation=45)
    current_price = values[-1]
    prev_price = values[-2]
    change = ((current_price - prev_price) / prev_price) * 100
    change_text = f"+{change:.2f}%" if change > 0 else f"{change:.2f}%"
    change_color = "#00ff00" if change > 0 else "#ff0000"
    ax.text(0.02, 0.98, f"${current_price:,.2f}",
            transform=ax.transAxes, fontsize=20,
            verticalalignment='top', color='white', fontweight='bold')
    ax.text(0.02, 0.90, change_text,
            transform=ax.transAxes, fontsize=14,
            verticalalignment='top', color=change_color, fontweight='bold')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a')
    buf.seek(0)
    plt.close()
    return buf.read()


async def get_economic_chart(title: str, lang: str) -> bytes:
    text_lower = title.lower()
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'bitcoin', 'крипт', 'crypto']):
        data = await get_bitcoin_data(30)
        if data:
            title_text = "Bitcoin (BTC) - Last 30 Days" if lang == "en" else "Биткоин (BTC) - 30 дней"
            return await create_chart(data, title_text, "USD", color="#f7931a")
    if any(kw in text_lower for kw in ['золото', 'gold']):
        data = await get_gold_data(30)
        if data:
            title_text = "Gold - Last 30 Days" if lang == "en" else "Золото - 30 дней"
            return await create_chart(data, title_text, "USD", color="#ffd700")
    return None


async def get_perfect_image(title: str, description: str, rss_image: str = None, lang: str = "ru") -> str:
    text_lower = f"{title} {description}".lower()

    if rss_image:
        bad_domains = [
            'meduza.io/logo', 'meduza.io/images', 'meduza.io/css',
            'logo.png', 'placeholder', 'default.jpg', 'avatar',
            '1x1.png', 'pixel.gif', 'blank.jpg'
        ]
        if len(rss_image) >= 40 and not any(bad in rss_image.lower() for bad in bad_domains):
            img_data = await download_image(rss_image)
            if img_data and len(img_data) > 50000:
                if not (img_data[:100].startswith(b'<svg') or img_data[:100].startswith(b'<!DOCTYPE')):
                    track_used_image(rss_image)
                    return rss_image

    person_queries = []
    for person, queries in PERSON_SEARCH_QUERIES.items():
        if person in text_lower:
            person_queries.extend(queries[:1])
            break

    theme_queries = []
    if lang == "ru":
        themes = {
            'трамп': ['donald trump president', 'trump politics'],
            'путин': ['vladimir putin russia', 'putin kremlin'],
            'биткоин': ['bitcoin crypto', 'cryptocurrency chart', 'btc price'],
            'btc': ['bitcoin mining', 'crypto trading', 'blockchain'],
            'рубль': ['russian ruble', 'ruble exchange rate', 'russian currency'],
            'золото': ['gold bars', 'gold bullion', 'gold price chart'],
            'нефть': ['oil refinery', 'crude oil', 'oil barrels'],
            'доллар': ['us dollar bills', 'dollar currency', 'usd banknotes'],
            'евро': ['euro currency', 'euro banknotes', 'eurozone'],
            'крипт': ['cryptocurrency', 'crypto market', 'digital currency'],
            'война': ['war zone', 'military conflict', 'soldiers combat'],
            'обстрел': ['artillery fire', 'missile strike', 'explosion'],
            'удар': ['air strike', 'military attack', 'bombing'],
            'всу': ['ukrainian army', 'military forces', 'soldiers'],
            'армия': ['military troops', 'armed forces', 'army soldiers'],
            'арест': ['police arrest', 'handcuffs', 'detained person'],
            'коррупц': ['corruption scandal', 'bribery', 'fraud investigation'],
            'суд': ['courtroom', 'judge gavel', 'trial'],
            'экономик': ['economy business', 'stock market'],
            'политик': ['politics government', 'parliament'],
            'технолог': ['technology innovation', 'digital tech'],
            'наука': ['science research', 'laboratory'],
        }
    else:
        themes = {
            'trump': ['donald trump president', 'trump politics'],
            'putin': ['vladimir putin russia', 'putin kremlin'],
            'bitcoin': ['bitcoin', 'btc chart', 'crypto'],
            'crypto': ['cryptocurrency', 'blockchain', 'digital currency'],
            'dollar': ['us dollar', 'usd bills', 'dollar currency'],
            'gold': ['gold bars', 'gold price', 'bullion'],
            'oil': ['crude oil', 'oil refinery', 'petroleum'],
            'stock': ['stock market', 'trading floor', 'wall street'],
            'fed': ['federal reserve', 'fed building', 'central bank'],
            'war': ['war zone', 'military', 'combat'],
            'strike': ['air strike', 'missile attack', 'bombing'],
            'military': ['army', 'soldiers', 'troops'],
            'econom': ['economy business', 'stock market'],
            'politic': ['politics government', 'parliament'],
            'tech': ['technology innovation', 'digital tech'],
            'science': ['science research', 'laboratory'],
            'arrest': ['police arrest', 'handcuffs', 'detained'],
            'scandal': ['corruption', 'investigation', 'fraud'],
            'court': ['courtroom', 'trial', 'judge'],
        }

    for keyword, queries in themes.items():
        if keyword in text_lower:
            theme_queries.extend(queries[:2])

    if not person_queries and not theme_queries:
        if lang == "ru":
            fallback = ['breaking news russia', 'moscow kremlin', 'russian politics',
                        'world events', 'global crisis', 'international news']
        else:
            fallback = ['breaking news visual', 'world politics crisis',
                        'global events', 'international affairs', 'major news']
        theme_queries = [random.choice(fallback)]

    all_queries = person_queries + theme_queries
    random.shuffle(all_queries)

    all_images = []
    for query in all_queries[:5]:
        images = await search_unsplash(query, count=15)
        all_images.extend(images)
        await asyncio.sleep(0.3)
        if len(all_images) >= 40:
            break

    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute("SELECT url FROM used_images WHERE used_at > ?", (month_ago,))
    used_urls = {row[0] for row in c.fetchall()}

    fresh_images = [img for img in all_images if img['url'] not in used_urls]

    if fresh_images:
        selected = random.choice(fresh_images[:15])
        track_used_image(selected['url'])
        return selected['url']

    if all_images:
        selected = random.choice(all_images[:15])
        track_used_image(selected['url'])
        return selected['url']

    return None


def escape_md_v2(text: str) -> str:
    if not text:
        return ""
    special = r'\_*[]()~`>#+-=|{}.!'
    escaped = ""
    for char in text:
        if char in special:
            escaped += '\\' + char
        else:
            escaped += char
    return escaped


# ================== СБОР НОВОСТЕЙ ==================
async def collect_fresh_news(lang: str, limit=30):
    candidates = []
    sources = RSS_SOURCES_RU if lang == "ru" else RSS_SOURCES_EN
    keywords = KEYWORDS_RU if lang == "ru" else KEYWORDS_EN
    boring = BORING_KEYWORDS_RU if lang == "ru" else BORING_KEYWORDS_EN

    sources_list = list(sources.items())
    random.shuffle(sources_list)

    for source_name, rss_url in sources_list:
        if len(candidates) >= limit:
            break
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                if len(candidates) >= limit:
                    break

                title = BeautifulSoup(entry.title.strip(), "html.parser").get_text()
                url = entry.link
                desc = BeautifulSoup(entry.get("summary", "") or entry.get("description", ""), "html.parser").get_text()

                rss_image = None
                if hasattr(entry, 'media_content') and entry.media_content:
                    rss_image = entry.media_content[0].get('url')
                if not rss_image and hasattr(entry, 'enclosures') and entry.enclosures:
                    for enc in entry.enclosures:
                        if enc.get('type', '').startswith('image/'):
                            rss_image = enc.get('href')
                            break
                if not rss_image:
                    soup = BeautifulSoup(entry.get("summary", "") or entry.get("description", ""), "html.parser")
                    img_tag = soup.find('img')
                    if img_tag and img_tag.get('src'):
                        rss_image = img_tag['src']
                if rss_image and (not rss_image.startswith('http') or len(rss_image) < 30):
                    rss_image = None

                if len(title) < 20:
                    continue
                if is_duplicate(title, url, lang):
                    continue
                if any(b in title.lower() for b in boring):
                    continue
                if not any(k in title.lower() for k in keywords):
                    continue

                # НОВОЕ! Считаем breaking-score
                breaking_score = calculate_breaking_score(title, lang)

                candidates.append({
                    "title": title,
                    "url": url,
                    "desc": desc,
                    "source": source_name,
                    "rss_image": rss_image,
                    "breaking_score": breaking_score,
                })

        except Exception as e:
            log.error(f"RSS {source_name}: {e}")

    return candidates


# ================== ПОСТИНГ НОВОСТЕЙ (с тредами) ==================
async def post_news(news: dict, lang: str):
    channel = CHANNEL_RU if lang == "ru" else CHANNEL_EN
    title = news.get("ai_title", news["title"])
    summary = news.get("summary", "").strip()
    is_breaking = news.get("is_breaking", False)

    if not summary and news.get("desc"):
        summary = news["desc"][:300].strip()

    if not summary:
        log.warning(f"[{lang.upper()}] Summary пустой, скипаем")
        return False

    # Ссылка на канал
    if lang == "ru":
        channel_text = "👉 Бульмяш +18. Подписаться"
        channel_url = "https://t.me/+QYYYj7ofUM8yODRi"
    else:
        channel_text = "👉 WORLD // ALERT +18. Subscribe"
        channel_url = "https://t.me/+MSAD4bRuxxY0Nzc6"

    # НОВОЕ! Источник
    source_name = news.get("source", "").upper()

    # НОВОЕ! Breaking-префикс
    if is_breaking:
        if lang == "ru":
            breaking_prefix = "⚡️ СРОЧНО\n\n"
        else:
            breaking_prefix = "⚡️ BREAKING\n\n"
    else:
        breaking_prefix = ""

    escaped_title = escape_md_v2(title)
    escaped_summary = escape_md_v2(summary)
    escaped_channel = escape_md_v2(channel_text)
    escaped_source = escape_md_v2(source_name)
    escaped_prefix = escape_md_v2(breaking_prefix)

    caption = (
        f"{escaped_prefix}"
        f"**{escaped_title}**\n\n"
        f"{escaped_summary}\n\n"
        f"📡 {escaped_source}\n\n"
        f"[{escaped_channel}]({channel_url})"
    )

    # Картинка
    chart_bytes = await get_economic_chart(title, lang)

    if chart_bytes:
        img_data = chart_bytes
    else:
        img_url = await get_perfect_image(title, news.get("desc", ""), news.get("rss_image"), lang)
        if not img_url:
            log.warning(f"[{lang.upper()}] Картинка не найдена")
            return False
        img_data = await download_image(img_url)

    if not img_data or len(img_data) <= 1024:
        return False

    try:
        # НОВОЕ! Проверяем тред — есть ли связанная тема?
        related_topic = find_related_topic(news["title"], lang)
        reply_to = None

        if related_topic:
            reply_to = related_topic["first_message_id"]
            update_count = related_topic["update_count"]

            # Добавляем маркер обновления
            if lang == "ru":
                update_marker = f"🔄 ОБНОВЛЕНИЕ \\#{update_count + 1}\n\n"
            else:
                update_marker = f"🔄 UPDATE \\#{update_count + 1}\n\n"

            caption = update_marker + caption
            update_hot_topic(related_topic["id"])
            log.info(f"🔗 [{lang.upper()}] Тред! Обновление #{update_count + 1}")

        file = BufferedInputFile(img_data, filename="news.jpg")

        sent = await bot.send_photo(
            channel, file,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_to_message_id=reply_to
        )

        save_posted(news["title"], news["url"], lang)
        increment_stat(lang, "news")
        log_analytics(lang, "news", "breaking" if is_breaking else "news", title, success=True)

        # Сохраняем как горячую тему если не тред
        if not related_topic:
            save_hot_topic(news["title"], sent.message_id, channel, lang)

        # Лог с ссылкой
        channel_link = channel.replace('@', '')
        post_url = f"https://t.me/{channel_link}/{sent.message_id}"
        prefix = "⚡️ BREAKING" if is_breaking else "✅"
        log.info(f"{prefix} [{lang.upper()}] {title[:50]} → {post_url}")

        if is_breaking:
            save_breaking_event(news["title"], lang)

        return True

    except Exception as e:
        log.error(f"❌ [{lang.upper()}] Ошибка отправки: {e}")
        log_analytics(lang, "news", "news", title, success=False)
        return False

# ================== YOUTUBE SHORTS ==================
def parse_duration_to_seconds(iso_duration):
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def format_views(views):
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    elif views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)


async def search_shorts(lang: str, category: str):
    log.info(f"🔍 [{lang.upper()}] Поиск Shorts, категория: {category}")
    recent_channels = get_recent_channels(12, lang)
    all_shorts = []

    cat_data = CONTENT_CATEGORIES.get(category, CONTENT_CATEGORIES["news"])
    queries = cat_data["queries_ru"] if lang == "ru" else cat_data["queries_en"]
    random.shuffle(queries)

    for query in queries[:5]:
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "id,snippet",
                "q": query + " shorts",
                "type": "video",
                "maxResults": 50,
                "order": "date",
                "publishedAfter": (datetime.now() - timedelta(days=3)).isoformat() + "Z",
                "regionCode": "RU" if lang == "ru" else "US",
                "relevanceLanguage": lang,
                "key": YOUTUBE_API_KEY
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=15) as response:
                    if response.status != 200:
                        continue
                    data = await response.json()
                    video_ids = [item["id"]["videoId"] for item in data.get("items", [])
                                 if item["id"].get("kind") == "youtube#video"]
                    if not video_ids:
                        continue

                    details_url = "https://www.googleapis.com/youtube/v3/videos"
                    details_params = {
                        "part": "snippet,statistics,contentDetails",
                        "id": ",".join(video_ids[:50]),
                        "key": YOUTUBE_API_KEY
                    }

                    async with session.get(details_url, params=details_params, timeout=15) as resp:
                        if resp.status != 200:
                            continue
                        details_data = await resp.json()

                        for item in details_data.get("items", []):
                            try:
                                duration = item["contentDetails"]["duration"]
                                total_sec = parse_duration_to_seconds(duration)
                                if not (8 <= total_sec <= 65):
                                    continue

                                snippet = item["snippet"]
                                stats = item["statistics"]
                                title = snippet.get("title", "")
                                channel_name = snippet.get("channelTitle", "")
                                description = snippet.get("description", "")

                                # НОВОЕ! Фильтр по audio language
                                audio_lang = snippet.get("defaultAudioLanguage", "")
                                default_lang = snippet.get("defaultLanguage", "")

                                if lang == "en":
                                    # Если YouTube знает язык и он НЕ английский — скип
                                    if audio_lang and not audio_lang.startswith("en"):
                                        continue
                                    if default_lang and not default_lang.startswith("en"):
                                        continue

                                if is_blacklisted(title, channel_name):
                                    continue
                                if channel_name.lower() in recent_channels:
                                    continue
                                if get_channel_usage_count(channel_name, 24, lang) >= 2:
                                    continue

                                if lang == "ru" and not is_russian_content(title, channel_name, description):
                                    continue
                                if lang == "en" and not is_english_content(title, channel_name, description):
                                    continue

                                views = int(stats.get("viewCount", 0))

                                if category == "commentary":
                                    min_views = 500 if is_trusted_channel(channel_name, lang) else 2000
                                else:
                                    min_views = 1000 if is_trusted_channel(channel_name, lang) else 3000

                                if views < min_views:
                                    continue

                                all_shorts.append({
                                    "id": item["id"],
                                    "title": title,
                                    "channel": channel_name,
                                    "views": views,
                                    "likes": int(stats.get("likeCount", 0)),
                                    "duration_sec": total_sec,
                                    "is_trusted": is_trusted_channel(channel_name, lang),
                                    "category": category
                                })

                            except:
                                continue

            await asyncio.sleep(0.4)

        except Exception as e:
            log.warning(f"Ошибка поиска: {e}")
            continue

    seen_ids = set()
    unique = []
    for s in all_shorts:
        if s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            unique.append(s)

    unique.sort(key=lambda x: (get_channel_usage_count(x["channel"], 48, lang),
                                not x["is_trusted"], -x["views"]))

    log.info(f"✅ [{lang.upper()}] Найдено {len(unique)} Shorts")
    return unique


async def download_shorts_video(video_id: str):
    output_file = os.path.join(TEMP_DIR, f"shorts_{video_id}.mp4")
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bv*+ba/b",
            "-o", output_file,
            "--no-playlist",
            "--merge-output-format", "mp4",
            "--extractor-args", "youtube:player_client=android",
            "--no-check-certificate",
            "--socket-timeout", "30",
            url
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await asyncio.wait_for(process.communicate(), timeout=90)
        if process.returncode == 0 and os.path.exists(output_file):
            return output_file
    except Exception as e:
        log.error(f"Ошибка скачивания: {e}")
    if os.path.exists(output_file):
        os.remove(output_file)
    return None


async def post_youtube_shorts(lang: str):
    stats = get_today_stats(lang)
    if stats["shorts"] >= 12:
        log.info(f"[{lang.upper()}] Лимит 12 shorts")
        return

    channel = CHANNEL_RU if lang == "ru" else CHANNEL_EN
    category = select_category_by_time(lang)

    log.info(f"🎬 [{lang.upper()}] Запуск Shorts, категория: {category}")
    shorts = await search_shorts(lang, category)

    if not shorts:
        log.warning(f"[{lang.upper()}] Shorts не найдены")
        return

    for i, short in enumerate(shorts[:15], 1):
        if is_youtube_posted(short["id"], lang):
            continue

        log.info(f"[{lang.upper()}] [{i}/15] {short['title'][:50]}...")
        video_path = await download_shorts_video(short["id"])

        if not video_path:
            continue

        try:
            clean_title = short['title']
            clean_title = re.sub(r'#\S+', '', clean_title).strip()
            clean_title = re.sub(r'[😀-🙏🌀-🗿🚀-🛿]', '', clean_title).strip()
            if '//' in clean_title:
                clean_title = clean_title.split('//')[0].strip()
            if '|' in clean_title:
                clean_title = clean_title.split('|')[0].strip()
            if '►' in clean_title:
                clean_title = clean_title.split('►')[0].strip()
            clean_title = clean_title.replace('*', '').replace('_', '').replace('`', '')
            if len(clean_title) > 100:
                clean_title = clean_title[:97] + "..."
            if not clean_title or len(clean_title) < 10:
                clean_title = f"Video from {short['channel']}" if lang == "en" else f"Видео от {short['channel']}"

            clean_channel = short['channel'].replace('*', '').replace('_', '').replace('`', '')

            if lang == "ru":
                caption = (
                    f"{clean_title}\n\n"
                    f"📺 {clean_channel}\n"
                    f"👀 {format_views(short['views'])} просмотров"
                )
            else:
                caption = (
                    f"{clean_title}\n\n"
                    f"📺 {clean_channel}\n"
                    f"👀 {format_views(short['views'])} views"
                )

            if len(caption) > 1000:
                caption = caption[:997] + "..."

            with open(video_path, 'rb') as f:
                video_data = f.read()

            video_file = BufferedInputFile(video_data, filename=f"{short['id']}.mp4")

            sent = await bot.send_video(
                channel, video=video_file, caption=caption,
                parse_mode=None, supports_streaming=True, width=1080, height=1920
            )

            channel_link = channel.replace('@', '')
            post_url = f"https://t.me/{channel_link}/{sent.message_id}"
            log.info(f"📬 [{lang.upper()}] Shorts: {post_url}")

            save_youtube_posted(short['id'], 'shorts', category, lang)
            track_youtube_channel(short['channel'], lang)
            increment_stat(lang, "shorts")
            log_analytics(lang, "shorts", category, short['title'],
                          short['channel'], short['views'], short['likes'], True)

            os.remove(video_path)
            return True

        except Exception as e:
            log.error(f"❌ [{lang.upper()}] Ошибка: {e}")
            log_analytics(lang, "shorts", category, short['title'],
                          short['channel'], short['views'], short['likes'], False)
            if os.path.exists(video_path):
                os.remove(video_path)
            continue

    return False


# ================== НОВОЕ! ДАЙДЖЕСТ ==================
async def post_daily_digest(lang: str):
    """Вечерний дайджест — топ-5 новостей дня"""
    log.info(f"📋 [{lang.upper()}] Формирую дайджест...")

    channel = CHANNEL_RU if lang == "ru" else CHANNEL_EN
    today = datetime.now().date().isoformat()

    # Берём все сегодняшние новости из аналитики
    c.execute("""SELECT title FROM analytics
                 WHERE lang = ? AND content_type = 'news' AND success = 1
                 AND timestamp LIKE ? ORDER BY timestamp DESC LIMIT 20""",
              (lang, f"{today}%"))
    rows = c.fetchall()

    if len(rows) < 3:
        log.info(f"[{lang.upper()}] Мало новостей для дайджеста ({len(rows)})")
        return

    titles = [row[0] for row in rows]
    titles_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(titles)])

    if lang == "ru":
        prompt = f"""Ты — циничный редактор в стиле Лепры/Топора. Составь ВЕЧЕРНИЙ ДАЙДЖЕСТ из этих новостей.

Выбери 5 самых важных/интересных. Для каждой напиши ОДНО едкое предложение.

Формат:
1. Краткий циничный пересказ новости
2. Краткий циничный пересказ новости
...и так 5 штук.

В конце добавь одну фразу-подводку типа "Спокойной ночи, страна" или "Ну, вы поняли".

Новости дня:
{titles_text}

Верни ТОЛЬКО текст дайджеста, без JSON."""

    else:
        prompt = f"""You're a cynical news editor. Write an EVENING DIGEST from these stories.

Pick 5 most important/interesting. For each, write ONE sharp witty sentence.

Format:
1. Sharp one-liner about the story
2. Sharp one-liner about the story
...5 total.

End with a closing quip like "Sleep tight, world" or "That's your Tuesday."

Today's news:
{titles_text}

Return ONLY the digest text, no JSON."""

    digest_text = await ask_ai(prompt, temperature=0.9)

    if not digest_text or len(digest_text) < 50:
        log.warning(f"[{lang.upper()}] AI не сгенерировал дайджест")
        return

    stats = get_today_stats(lang)

    if lang == "ru":
        header = "🌙 ИТОГИ ДНЯ"
        footer = f"\n\n📊 Сегодня: {stats['news']} новостей, {stats['shorts']} видео"
    else:
        header = "🌙 DAY IN REVIEW"
        footer = f"\n\n📊 Today: {stats['news']} news, {stats['shorts']} videos"

    full_text = f"{header}\n\n{digest_text}{footer}"

    # Экранируем для MarkdownV2
    # Но дайджест сложный, шлём без Markdown
    try:
        await bot.send_message(channel, full_text, parse_mode=None)
        log.info(f"📋 [{lang.upper()}] Дайджест опубликован!")
    except Exception as e:
        log.error(f"❌ [{lang.upper()}] Ошибка дайджеста: {e}")


# ================== CHECK NEWS с BREAKING ==================
async def check_news(lang: str):
    stats = get_today_stats(lang)
    if stats["news"] >= 25:
        log.info(f"[{lang.upper()}] Лимит 25 новостей")
        return

    log.info(f"[{lang.upper()}] Собираю новости...")
    candidates = await collect_fresh_news(lang, 30)

    if not candidates:
        log.info(f"[{lang.upper()}] Новых новостей нет")
        return

    # НОВОЕ! Проверяем BREAKING
    breaking_candidates = [n for n in candidates if n.get("breaking_score", 0) >= 3]

    if breaking_candidates:
        # Есть breaking! Постим срочно
        for bc in breaking_candidates[:2]:  # Макс 2 breaking за раз
            if not is_breaking_duplicate(bc["title"], lang):
                log.info(f"⚡️ [{lang.upper()}] BREAKING DETECTED: {bc['title'][:60]}")
                selected = await ai_select_and_summarize([bc], lang, is_breaking=True)
                if selected:
                    await post_news(selected, lang)
                    return

    # Обычный режим
    selected = await ai_select_and_summarize(candidates, lang, is_breaking=False)
    if selected:
        await post_news(selected, lang)


# ================== НОВОЕ! BREAKING MONITOR (отдельный быстрый цикл) ==================
async def breaking_monitor(lang: str):
    """Быстрый цикл — проверяет RSS каждые 2 минуты ТОЛЬКО на breaking"""
    log.info(f"⚡️ [{lang.upper()}] Breaking monitor запущен")

    while True:
        try:
            sources = RSS_SOURCES_RU if lang == "ru" else RSS_SOURCES_EN
            keywords = KEYWORDS_RU if lang == "ru" else KEYWORDS_EN
            boring = BORING_KEYWORDS_RU if lang == "ru" else BORING_KEYWORDS_EN

            # Берём только 5 случайных источников (быстро!)
            quick_sources = random.sample(list(sources.items()), min(5, len(sources)))

            for source_name, rss_url in quick_sources:
                try:
                    feed = feedparser.parse(rss_url)
                    for entry in feed.entries[:3]:  # Только первые 3
                        title = BeautifulSoup(entry.title.strip(), "html.parser").get_text()
                        url = entry.link

                        if len(title) < 20:
                            continue
                        if is_duplicate(title, url, lang):
                            continue
                        if any(b in title.lower() for b in boring):
                            continue

                        score = calculate_breaking_score(title, lang)

                        if score >= 3 and not is_breaking_duplicate(title, lang):
                            log.info(f"🚨 [{lang.upper()}] BREAKING НАЙДЕН (score={score}): {title[:60]}")

                            desc = BeautifulSoup(
                                entry.get("summary", "") or entry.get("description", ""),
                                "html.parser"
                            ).get_text()

                            # RSS Image
                            rss_image = None
                            if hasattr(entry, 'media_content') and entry.media_content:
                                rss_image = entry.media_content[0].get('url')

                            news_item = {
                                "title": title,
                                "url": url,
                                "desc": desc,
                                "source": source_name,
                                "rss_image": rss_image,
                                "breaking_score": score,
                            }

                            selected = await ai_select_and_summarize([news_item], lang, is_breaking=True)
                            if selected:
                                await post_news(selected, lang)
                                # После breaking — пауза 10 минут
                                await asyncio.sleep(600)

                except Exception as e:
                    log.debug(f"Breaking monitor RSS error {source_name}: {e}")
                    continue

        except Exception as e:
            log.error(f"Breaking monitor error [{lang}]: {e}")

        # Проверяем каждые 2 минуты
        await asyncio.sleep(120)

# ================== ЦИКЛЫ ==================
async def news_loop_ru():
    log.info("⏰ [RU] Первый пост через 5 сек...")
    await asyncio.sleep(5)
    while True:
        await check_news("ru")
        interval = random.randint(15, 45)
        log.info(f"⏰ [RU] Следующие новости через {interval} мин")
        await asyncio.sleep(interval * 60)


async def news_loop_en():
    log.info("⏰ [EN] Первый пост через 30 сек...")
    await asyncio.sleep(30)
    while True:
        await check_news("en")
        interval = random.randint(15, 45)
        log.info(f"⏰ [EN] Следующие новости через {interval} мин")
        await asyncio.sleep(interval * 60)


async def shorts_loop_ru():
    log.info("⏰ [RU] Первый Shorts через 2 мин...")
    await asyncio.sleep(120)
    while True:
        await post_youtube_shorts("ru")
        interval = random.randint(90, 150)
        log.info(f"⏰ [RU] Следующий Shorts через {interval} мин")
        await asyncio.sleep(interval * 60)


async def shorts_loop_en():
    log.info("⏰ [EN] Первый Shorts через 3 мин...")
    await asyncio.sleep(180)
    while True:
        await post_youtube_shorts("en")
        interval = random.randint(90, 150)
        log.info(f"⏰ [EN] Следующий Shorts через {interval} мин")
        await asyncio.sleep(interval * 60)


def cleanup_old_files():
    try:
        now = datetime.now().timestamp()
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath):
                if now - os.path.getmtime(filepath) > 86400:
                    os.remove(filepath)
                    log.info(f"🗑️ Удалён: {filename}")
    except Exception as e:
        log.warning(f"Ошибка очистки: {e}")


async def daily_analytics():
    summary = get_analytics_summary(1)
    log.info("=" * 50)
    log.info("📊 АНАЛИТИКА ЗА ДЕНЬ:")
    log.info(f"По языкам: {summary['by_lang']}")
    log.info(f"По категориям: {summary['by_category']}")
    log.info(f"Топ каналы: {summary['top_channels'][:5]}")
    log.info("=" * 50)


# ================== MAIN ==================
async def main():
    migrate_database()

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Очистка и аналитика
    scheduler.add_job(cleanup_old_files, "cron", hour=3, minute=0)
    scheduler.add_job(daily_analytics, "cron", hour=23, minute=55)

    # НОВОЕ! Вечерний дайджест
    scheduler.add_job(lambda: asyncio.ensure_future(post_daily_digest("ru")),
                      "cron", hour=22, minute=0)
    scheduler.add_job(lambda: asyncio.ensure_future(post_daily_digest("en")),
                      "cron", hour=22, minute=30)

    scheduler.start()

    log.info("=" * 70)
    log.info("🤖 НОВОСТНОЙ БОТ v4.0 — DUAL LANG + BREAKING + THREADS + DIGEST")
    log.info("=" * 70)
    log.info(f"📰 RU канал: {CHANNEL_RU}")
    log.info(f"🌍 EN канал: {CHANNEL_EN}")
    log.info("")
    log.info("📰 Новости: каждые 15-45 мин (макс 25/день/канал)")
    log.info("🎬 Shorts: каждые 1.5-2.5 часа (макс 12/день/канал)")
    log.info("⚡️ Breaking monitor: каждые 2 мин")
    log.info("🧵 Треды: автоматическая линковка обновлений")
    log.info("🌙 Дайджест: 22:00 MSK (RU), 22:30 MSK (EN)")
    log.info("🗣️ Голос: Лепра/Топор (RU), Daily Show (EN)")
    log.info("")
    log.info("🆕 v4.0:")
    log.info("   ⚡️ BREAKING-режим (мгновенная публикация)")
    log.info("   🧵 Тред-формат (обновления по теме)")
    log.info("   🌙 Вечерний дайджест")
    log.info("   🗣️ Уникальный голос (сарказм)")
    log.info("   🇮🇳 Жёсткий антииндийский фильтр")
    log.info("   📡 Источник в каждом посте")
    log.info("=" * 70)

    # Запуск всех циклов
    await asyncio.gather(
        news_loop_ru(),
        news_loop_en(),
        shorts_loop_ru(),
        shorts_loop_en(),
        breaking_monitor("ru"),   # НОВОЕ!
        breaking_monitor("en"),   # НОВОЕ!
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("👋 Бот остановлен")
        conn.close()
    except Exception as e:
        log.error(f"💥 Критическая ошибка: {e}")
        conn.close()
