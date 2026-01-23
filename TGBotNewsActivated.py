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
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# КАНАЛЫ
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

# ================== КЛЮЧЕВЫЕ СЛОВА ==================
KEYWORDS_RU = [
    'путин', 'правительств', 'кремл', 'госдум', 'президент', 
    'министр', 'трамп', 'байден', 'зеленск', 'сша', 'китай',
    'рубль', 'доллар', 'евро', 'курс', 'цб', 'банк', 'инфляц',
    'нефть', 'газ', 'санкц', 'война', 'конфликт', 'армия',
    'удар', 'обстрел', 'атак', 'авар', 'пожар', 'взрыв',
    'погиб', 'жертв', 'задержа', 'арест', 'суд', 'приговор',
    'искусственн', 'нейросет', 'chatgpt', 'google', 'apple',
    'учен', 'космос', 'выбор', 'закон', 'олимпиад', 'чемпионат'
]

KEYWORDS_EN = [
    'putin', 'kremlin', 'russia', 'president', 'government',
    'trump', 'biden', 'zelensky', 'usa', 'china', 'nato',
    'dollar', 'euro', 'stock', 'fed', 'inflation', 'economy',
    'oil', 'gas', 'sanctions', 'war', 'conflict', 'military',
    'attack', 'strike', 'explosion', 'fire', 'crash',
    'killed', 'death', 'arrest', 'court', 'verdict',
    'ai', 'chatgpt', 'google', 'apple', 'tesla', 'musk',
    'science', 'space', 'election', 'law', 'breaking'
]

# ================== ЧЁРНЫЕ СПИСКИ ==================
BORING_KEYWORDS_RU = [
    'погода', 'синоптик', 'температур', 'осадк', 'прогноз погоды',
    'гороскоп', 'лунный', 'сонник', 'приметы', 'именины',
    'стажировк', 'обеспечить', 'поручил',
]

BORING_KEYWORDS_EN = [
    'weather', 'forecast', 'horoscope', 'zodiac', 'lottery',
    'celebrity', 'kardashian', 'royal family', 'recipe',
]

# Чёрный список каналов YouTube
BLACKLIST_CHANNELS = [
    # Детский контент
    'kids', 'children', 'cartoon', 'animation', 'nursery',
    # Майнкрафт и игры
    'minecraft', 'майнкрафт', 'roblox', 'fortnite', 'gaming', 'геймер',
    # Мусор
    'asmr', 'асмр', 'mukbang', 'мукбанг', 'prank', 'пранк',
    'tiktok compilation', 'shorts compilation',
]

# Чёрный список тем
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

# РАЗВЛЕКАТЕЛЬНЫЕ КАНАЛЫ (RU)
RU_ENTERTAINMENT_CHANNELS = [
    # Юмор/приколы (качественные)
    "ЧБД", "Labelcom", "Stand-Up Club #1", "Roast Battle",
    "Импровизация", "Где логика", "Что было дальше",
    # Интересные факты/наука
    "SciOne", "Научпок", "Арзамас", "Правда Глаза Колет",
    "Топлес", "Utopia Show", "Droider", "Wylsacom",
    # Лайфхаки/полезное
    "AdMe", "5-Minute Crafts LIKE", 
]

# РАЗВЛЕКАТЕЛЬНЫЕ КАНАЛЫ (EN)
EN_ENTERTAINMENT_CHANNELS = [
    # Facts/Science
    "Veritasium", "Vsauce", "Kurzgesagt", "SmarterEveryDay",
    "Mark Rober", "Tom Scott", "CGP Grey",
    # Tech
    "MKBHD", "Linus Tech Tips", "JerryRigEverything",
    # Interesting
    "Johnny Harris", "Wendover Productions", "RealLifeLore",
    "Half as Interesting", "PolyMatter",
]

# ================== КАТЕГОРИИ КОНТЕНТА ==================
CONTENT_CATEGORIES = {
    "news": {
        "weight": 50,  # 50% контента
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
        "weight": 20,
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
        "weight": 10,
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
    timestamp TEXT,
    lang TEXT,
    content_type TEXT,
    category TEXT,
    title TEXT,
    channel TEXT,
    views INT,
    likes INT,
    success BOOLEAN
)''')

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
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("DELETE FROM used_images WHERE used_at < ?", (week_ago,))
    conn.commit()

# АНАЛИТИКА
def log_analytics(lang: str, content_type: str, category: str, title: str, 
                  channel: str = "", views: int = 0, likes: int = 0, success: bool = True):
    c.execute("""INSERT INTO analytics 
                 (timestamp, lang, content_type, category, title, channel, views, likes, success) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (datetime.now().isoformat(), lang, content_type, category, 
               title[:200], channel[:100], views, likes, success))
    conn.commit()

def get_analytics_summary(days: int = 7):
    """Получить сводку аналитики за N дней"""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    summary = {}
    
    # По языкам
    c.execute("""SELECT lang, COUNT(*), SUM(CASE WHEN success THEN 1 ELSE 0 END) 
                 FROM analytics WHERE timestamp > ? GROUP BY lang""", (cutoff,))
    summary["by_lang"] = {row[0]: {"total": row[1], "success": row[2]} for row in c.fetchall()}
    
    # По категориям
    c.execute("""SELECT category, COUNT(*), AVG(views) 
                 FROM analytics WHERE timestamp > ? AND content_type = 'shorts' 
                 GROUP BY category ORDER BY COUNT(*) DESC""", (cutoff,))
    summary["by_category"] = {row[0]: {"count": row[1], "avg_views": row[2]} for row in c.fetchall()}
    
    # Топ каналы
    c.execute("""SELECT channel, COUNT(*), AVG(views) 
                 FROM analytics WHERE timestamp > ? AND channel != '' 
                 GROUP BY channel ORDER BY COUNT(*) DESC LIMIT 10""", (cutoff,))
    summary["top_channels"] = [(row[0], row[1], row[2]) for row in c.fetchall()]
    
    return summary

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
    """Проверка что контент английский"""
    full_text = f"{title} {channel} {description}"
    
    # Не должно быть кириллицы
    if has_cyrillic(full_text):
        return False
    
    # Должны быть латинские буквы
    if not re.search('[a-zA-Z]', title):
        return False
    
    # Исключаем испанский, португальский и т.д. по характерным символам
    non_english = ['ñ', 'ç', 'ã', 'õ', 'ü', 'ö', 'ä', 'ß']
    if any(char in full_text.lower() for char in non_english):
        return False
    
    return True

def is_blacklisted(title: str, channel: str) -> bool:
    """Проверка на чёрный список"""
    text = f"{title} {channel}".lower()
    
    for banned in BLACKLIST_CHANNELS:
        if banned.lower() in text:
            return True
    
    for banned in BLACKLIST_TOPICS:
        if banned.lower() in text:
            return True
    
    return False

def is_trusted_channel(channel: str, lang: str) -> bool:
    """Проверка на доверенный канал"""
    channels = RU_NEWS_CHANNELS + RU_ENTERTAINMENT_CHANNELS if lang == "ru" else EN_NEWS_CHANNELS + EN_ENTERTAINMENT_CHANNELS
    return any(t.lower() in channel.lower() for t in channels)

# ================== ВЫБОР КАТЕГОРИИ ==================
def select_category_by_time() -> str:
    """Выбор категории с учётом времени суток"""
    hour = datetime.now().hour
    
    # Утро (6-10) - больше новостей
    if 6 <= hour < 10:
        weights = {"news": 60, "politics": 20, "economy": 10, "science_tech": 5, "entertainment": 5}
    # День (10-18) - разнообразие
    elif 10 <= hour < 18:
        weights = {"news": 40, "politics": 20, "economy": 15, "science_tech": 15, "entertainment": 10}
    # Вечер (18-23) - больше развлечений
    elif 18 <= hour < 23:
        weights = {"news": 30, "politics": 15, "economy": 10, "science_tech": 20, "entertainment": 25}
    # Ночь (23-6) - лёгкий контент
    else:
        weights = {"news": 25, "politics": 10, "economy": 5, "science_tech": 25, "entertainment": 35}
    
    categories = list(weights.keys())
    probs = list(weights.values())
    
    return random.choices(categories, weights=probs, k=1)[0]

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
                
                # Парсим картинку
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
                
                candidates.append({
                    "title": title,
                    "url": url,
                    "desc": desc,
                    "source": source_name,
                    "rss_image": rss_image
                })
                
        except Exception as e:
            log.error(f"RSS {source_name}: {e}")
    
    return candidates

# ================== AI: ВЫБОР И ОБРАБОТКА ==================
async def ai_select_and_summarize(news_list: list, lang: str) -> dict:
    news_text = "\n".join([f"{i+1}. {n['title']}" for i, n in enumerate(news_list[:25])])
    
    if lang == "ru":
        prompt = f"""Ты редактор ДЕРЗКОГО новостного Telegram-канала.
Выбери ОДНУ самую взрывную новость и сделай язвительный пересказ.

ВАЖНО:
1. Выбирай ГОРЯЧИЕ новости (конфликты, деньги, взрывы, скандалы)
2. Заголовок КОРОТКИЙ (макс 60 символов)
3. Пересказ ДОПОЛНЯЕТ заголовок
4. НЕ ВЫБИРАЙ философские цитаты и скучную хуйню!

ХЕШТЕГИ - односложные слова, максимум 4, через пробел.

Верни JSON:
{{
  "selected": номер (1-{len(news_list[:25])}),
  "title": "КОРОТКИЙ заголовок",
  "summary": "Пересказ 2-3 предложения",
  "hashtags": "#Слово1 #Слово2 #Слово3"
}}

Новости:
{news_text}"""
    else:
        prompt = f"""You are an editor of a BOLD news Telegram channel.
Pick ONE most explosive news and write a catchy summary.

IMPORTANT:
1. Choose HOT news (conflicts, money, explosions, scandals)
2. Title MUST be SHORT (max 60 chars)
3. Summary COMPLEMENTS the title
4. NO boring philosophical stuff!

HASHTAGS - single words, max 4, space-separated.

Return JSON:
{{
  "selected": number (1-{len(news_list[:25])}),
  "title": "SHORT catchy title",
  "summary": "Summary 2-3 sentences",
  "hashtags": "#Word1 #Word2 #Word3"
}}

News:
{news_text}"""
    
    response = await ask_ai(prompt, temperature=0.9)
    
    if response:
        try:
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                content = response[json_start:json_end+1]
                result = json.loads(content)
                selected_idx = int(result.get("selected", 1)) - 1
                
                if 0 <= selected_idx < len(news_list):
                    selected = news_list[selected_idx]
                    selected["ai_title"] = result.get("title", selected["title"])
                    selected["summary"] = result.get("summary", "")
                    selected["hashtags"] = fix_hashtags(result.get("hashtags", ""))
                    return selected
        except Exception as e:
            log.warning(f"AI parse error: {e}")
    
    # Fallback
    selected = random.choice(news_list[:5])
    selected["ai_title"] = selected["title"]
    selected["summary"] = selected["desc"][:200] if selected["desc"] else ""
    selected["hashtags"] = generate_smart_hashtags(selected["title"], selected["desc"], lang)
    return selected

def fix_hashtags(raw_hashtags: str) -> str:
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
    
    seen = set()
    unique = []
    for tag in fixed_tags:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            unique.append(tag)
    
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

async def get_perfect_image(title: str, description: str, rss_image: str = None) -> str:
    text_lower = f"{title} {description}".lower()
    
    # Персоны
    queries = []
    for person, person_queries in PERSON_SEARCH_QUERIES.items():
        if person in text_lower:
            queries.extend(person_queries[:2])
            break
    
    if not queries:
        queries = ['world news', 'breaking news', 'politics']
    
    all_images = []
    
    for query in queries[:2]:
        images = await search_unsplash(query, count=10)
        all_images.extend(images)
        await asyncio.sleep(0.3)
    
    if rss_image:
        img_data = await download_image(rss_image)
        if img_data and len(img_data) > 5000:
            all_images.insert(0, {"url": rss_image, "source": "rss"})
    
    if all_images:
        img_url = all_images[0]["url"]
        track_used_image(img_url)
        return img_url
    
    return None

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

# ================== ПОСТИНГ НОВОСТЕЙ ==================
async def post_news(news: dict, lang: str):
    channel = CHANNEL_RU if lang == "ru" else CHANNEL_EN
    title = news.get("ai_title", news["title"])
    summary = news.get("summary", "")
    hashtags = news.get("hashtags", "")
    
    caption = f"**{title}**\n\n{summary}\n\n{hashtags}"
    
    img_url = await get_perfect_image(title, news.get("desc", ""), news.get("rss_image"))
    
    if not img_url:
        log.warning(f"[{lang.upper()}] Картинка не найдена")
        return False
    
    img_data = await download_image(img_url)
    
    if img_data and len(img_data) > 1024:
        try:
            file = BufferedInputFile(img_data, filename="news.jpg")
            await bot.send_photo(channel, file, caption=caption, parse_mode=ParseMode.MARKDOWN)
            save_posted(news["title"], news["url"], lang)
            increment_stat(lang, "news")
            log_analytics(lang, "news", "news", title, success=True)
            log.info(f"✅ [{lang.upper()}] Опубликовано: {title[:50]}")
            return True
        except Exception as e:
            log.error(f"❌ [{lang.upper()}] Ошибка: {e}")
            log_analytics(lang, "news", "news", title, success=False)
    
    return False

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
    
    selected = await ai_select_and_summarize(candidates, lang)
    if selected:
        await post_news(selected, lang)

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
    """Поиск Shorts с учётом языка и категории"""
    log.info(f"🔍 [{lang.upper()}] Поиск Shorts, категория: {category}")
    
    recent_channels = get_recent_channels(12, lang)
    all_shorts = []
    
    # Выбираем запросы по категории и языку
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
                    
                    # Детали видео
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
                                channel = snippet.get("channelTitle", "")
                                description = snippet.get("description", "")
                                
                                # Проверки
                                if is_blacklisted(title, channel):
                                    continue
                                
                                if channel.lower() in recent_channels:
                                    continue
                                
                                if get_channel_usage_count(channel, 24, lang) >= 2:
                                    continue
                                
                                # Проверка языка
                                if lang == "ru" and not is_russian_content(title, channel, description):
                                    continue
                                if lang == "en" and not is_english_content(title, channel, description):
                                    continue
                                
                                views = int(stats.get("viewCount", 0))
                                min_views = 1000 if is_trusted_channel(channel, lang) else 3000
                                if views < min_views:
                                    continue
                                
                                all_shorts.append({
                                    "id": item["id"],
                                    "title": title,
                                    "channel": channel,
                                    "views": views,
                                    "likes": int(stats.get("likeCount", 0)),
                                    "duration_sec": total_sec,
                                    "is_trusted": is_trusted_channel(channel, lang),
                                    "category": category
                                })
                                
                            except:
                                continue
            
            await asyncio.sleep(0.4)
            
        except Exception as e:
            log.warning(f"Ошибка поиска: {e}")
            continue
    
    # Убираем дубликаты и сортируем
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
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
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
    """Постинг Shorts для конкретного языка"""
    stats = get_today_stats(lang)
    if stats["shorts"] >= 12:  # Увеличил лимит
        log.info(f"[{lang.upper()}] Лимит 12 shorts")
        return
    
    channel = CHANNEL_RU if lang == "ru" else CHANNEL_EN
    category = select_category_by_time()
    
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
            # Очистка названия
            clean_title = short['title']
            clean_title = re.sub(r'#\S+', '', clean_title).strip()
            if '//' in clean_title:
                clean_title = clean_title.split('//')[0].strip()
            if '|' in clean_title:
                clean_title = clean_title.split('|')[0].strip()
            
            if lang == "ru":
                caption = (
                    f"❗ {clean_title}\n\n"
                    f"📺 {short['channel']}\n"
                    f"👀 {format_views(short['views'])} просмотров\n\n"
                    f"#shorts #{category}"
                )
            else:
                caption = (
                    f"❗ {clean_title}\n\n"
                    f"📺 {short['channel']}\n"
                    f"👀 {format_views(short['views'])} views\n\n"
                    f"#shorts #{category}"
                )
            
            with open(video_path, 'rb') as f:
                video_data = f.read()
            
            video_file = BufferedInputFile(video_data, filename=f"{short['id']}.mp4")
            
            await bot.send_video(
                channel,
                video=video_file,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
                width=1080,
                height=1920
            )
            
            save_youtube_posted(short['id'], 'shorts', category, lang)
            track_youtube_channel(short['channel'], lang)
            increment_stat(lang, "shorts")
            log_analytics(lang, "shorts", category, short['title'], 
                         short['channel'], short['views'], short['likes'], True)
            
            log.info(f"✅ [{lang.upper()}] Shorts опубликован!")
            
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

# ================== ЦИКЛЫ ==================
async def news_loop_ru():
    """Цикл новостей для RU"""
    log.info("⏰ [RU] Первый пост через 5 сек...")
    await asyncio.sleep(5)
    
    while True:
        await check_news("ru")
        interval = random.randint(20, 70)
        log.info(f"⏰ [RU] Следующие новости через {interval} мин")
        await asyncio.sleep(interval * 60)

async def news_loop_en():
    """Цикл новостей для EN"""
    log.info("⏰ [EN] Первый пост через 30 сек...")
    await asyncio.sleep(30)
    
    while True:
        await check_news("en")
        interval = random.randint(25, 80)
        log.info(f"⏰ [EN] Следующие новости через {interval} мин")
        await asyncio.sleep(interval * 60)

async def shorts_loop_ru():
    """Цикл Shorts для RU - каждые 1.5-2.5 часа"""
    log.info("⏰ [RU] Первый Shorts через 2 мин...")
    await asyncio.sleep(120)
    
    while True:
        await post_youtube_shorts("ru")
        interval = random.randint(90, 150)  # 1.5-2.5 часа
        log.info(f"⏰ [RU] Следующий Shorts через {interval} мин")
        await asyncio.sleep(interval * 60)

async def shorts_loop_en():
    """Цикл Shorts для EN - каждые 1.5-2.5 часа"""
    log.info("⏰ [EN] Первый Shorts через 3 мин...")
    await asyncio.sleep(180)
    
    while True:
        await post_youtube_shorts("en")
        interval = random.randint(90, 150)  # 1.5-2.5 часа
        log.info(f"⏰ [EN] Следующий Shorts через {interval} мин")
        await asyncio.sleep(interval * 60)

def cleanup_old_files():
    """Очистка старых файлов"""
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
    """Ежедневная аналитика"""
    summary = get_analytics_summary(1)
    log.info("=" * 50)
    log.info("📊 АНАЛИТИКА ЗА ДЕНЬ:")
    log.info(f"По языкам: {summary['by_lang']}")
    log.info(f"По категориям: {summary['by_category']}")
    log.info(f"Топ каналы: {summary['top_channels'][:5]}")
    log.info("=" * 50)

# ================== MAIN ==================
async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    
    # Очистка и аналитика
    scheduler.add_job(cleanup_old_files, "cron", hour=3, minute=0)
    scheduler.add_job(daily_analytics, "cron", hour=23, minute=55)
    
    scheduler.start()
    
    log.info("=" * 70)
    log.info("🤖 НОВОСТНОЙ БОТ v3.0 - DUAL LANGUAGE")
    log.info("=" * 70)
    log.info(f"📰 RU канал: {CHANNEL_RU}")
    log.info(f"🌍 EN канал: {CHANNEL_EN}")
    log.info("")
    log.info("📰 Новости: каждые 20-80 мин (макс 25/день/канал)")
    log.info("🎬 Shorts: каждые 1.5-2.5 часа (макс 12/день/канал)")
    log.info("")
    log.info("🆕 ЧТО НОВОГО:")
    log.info("   ✅ Два канала (RU + EN)")
    log.info("   ✅ Больше Shorts (до 12/день)")
    log.info("   ✅ 5 категорий контента")
    log.info("   ✅ Приоритеты по времени суток")
    log.info("   ✅ Чёрные списки каналов/тем")
    log.info("   ✅ Аналитика")
    log.info("=" * 70)
    
    # Запуск всех циклов параллельно
    await asyncio.gather(
        news_loop_ru(),
        news_loop_en(),
        shorts_loop_ru(),
        shorts_loop_en(),
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
