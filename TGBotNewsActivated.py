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

CHANNEL_ID = '@bulmyash'
TIMEZONE = "Europe/Moscow"

if sys.platform == "win32":
    TEMP_DIR = "C:/temp/shorts"
else:
    TEMP_DIR = "/tmp/shorts"
os.makedirs(TEMP_DIR, exist_ok=True)

RSS_SOURCES = {
    "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "tass": "https://tass.ru/rss/v2.xml",
    "interfax": "https://www.interfax.ru/rss.asp",
    "kommersant": "https://www.kommersant.ru/RSS/news.xml",
    "ria": "https://ria.ru/export/rss2/index.xml",
    "lenta": "https://lenta.ru/rss",
    "gazeta": "https://www.gazeta.ru/export/rss/first.xml",
    "vedomosti": "https://www.vedomosti.ru/rss/news",
    "izvestia": "https://iz.ru/xml/rss/all.xml",
    "rt": "https://www.rt.com/rss/",
    "fontanka": "https://www.fontanka.ru/fontanka.rss",
    "rosbalt": "https://www.rosbalt.ru/feed/",
    "forbes": "https://www.forbes.ru/newrss.xml",
    "rbc_economics": "https://rssexport.rbc.ru/rbcnews/news/20/full.rss",
    "cnews": "https://www.cnews.ru/inc/rss/news.xml",
    "habr": "https://habr.com/ru/rss/all/all/",
    "bbc_ru": "https://feeds.bbci.co.uk/russian/rss.xml",
    "reuters": "https://feeds.reuters.com/reuters/worldNews",
    "meduza": "https://meduza.io/rss/all",
}

KEYWORDS = [
    'путин', 'правительств', 'кремл', 'госдум', 'президент', 
    'министр', 'трамп', 'байден', 'зеленск', 'сша', 'китай',
    'рубль', 'доллар', 'евро', 'курс', 'цб', 'банк', 'инфляц',
    'нефть', 'газ', 'санкц', 'война', 'конфликт', 'армия',
    'удар', 'обстрел', 'атак', 'авар', 'пожар', 'взрыв',
    'погиб', 'жертв', 'задержа', 'арест', 'суд', 'приговор',
    'искусственн', 'нейросет', 'chatgpt', 'google', 'apple',
    'учен', 'космос', 'выбор', 'закон', 'олимпиад', 'чемпионат'
]

BORING_KEYWORDS = [
    'погода', 'синоптик', 'температур', 'осадк', 'прогноз погоды',
    'гороскоп', 'лунный', 'сонник', 'приметы', 'именины',
    'стажировк', 'обеспечить', 'поручил',
]

# РАСШИРЕННЫЙ СПИСОК НОВОСТНЫХ КАНАЛОВ
RU_NEWS_CHANNELS = [
    # Официальные СМИ
    "РИА Новости", "ТАСС", "Известия", "Интерфакс", "РБК",
    "Коммерсантъ", "Ведомости", "Первый канал", "Россия 24",
    "НТВ", "RT", "ДЕНЬ ТВ", "Кремль", 
    # Независимые
    "Дождь", "Медуза", "Новая газета",
    # Блогеры/авторы
    "вДудь", "Популярная политика", "ФЕЙГИН LIVE", 
    "Время Прядко", "Время Прядко Shorts",
    # Новые каналы для разнообразия
    "Редакция", "Навальный LIVE", "Varlamov", "Varlamov News",
    "Soloviev LIVE", "Соловьёв LIVE", "60 минут",
    "Царьград ТВ", "Спутник", "Life", "Лайф",
    "Mash", "Shot", "112", "Baza", "База",
    "Readovka", "WarGonzo", "Rybar", "Рыбарь",
    "BRIEF", "Незыгарь", "Подъём", "Новости",
    "Политика сегодня", "Россия 1", "ОТР",
    "Эхо", "The Insider", "Важные истории",
]

# ================== БАЗА ДАННЫХ ==================
DB_FILE = "news.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS posted (
    hash TEXT UNIQUE, 
    posted_at TEXT, 
    title TEXT,
    url TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS youtube_posted (
    video_id TEXT UNIQUE, 
    posted_at TEXT, 
    type TEXT
)''')
# НОВАЯ ТАБЛИЦА: отслеживание каналов YouTube
c.execute('''CREATE TABLE IF NOT EXISTS youtube_channels_used (
    channel_name TEXT,
    used_at TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT UNIQUE, 
    normal_count INT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS used_images (
    url TEXT,
    used_at TEXT
)''')
conn.commit()

def get_today_stats():
    today = datetime.now().date().isoformat()
    c.execute("SELECT normal_count FROM daily_stats WHERE date = ?", (today,))
    result = c.fetchone()
    return {"normal": result[0]} if result else {"normal": 0}

def increment_stat():
    today = datetime.now().date().isoformat()
    stats = get_today_stats()
    stats["normal"] += 1
    c.execute("INSERT OR REPLACE INTO daily_stats (date, normal_count) VALUES (?, ?)", 
              (today, stats["normal"]))
    conn.commit()

def is_duplicate(title, url):
    h = hashlib.md5((title + url).encode()).hexdigest()
    c.execute("SELECT 1 FROM posted WHERE hash = ?", (h,))
    return c.fetchone() is not None

def save_posted(title, url):
    h = hashlib.md5((title + url).encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO posted (hash, posted_at, title, url) VALUES (?, ?, ?, ?)", 
              (h, datetime.now().isoformat(), title, url))
    conn.commit()

def track_used_image(url: str):
    c.execute("INSERT INTO used_images (url, used_at) VALUES (?, ?)", 
              (url, datetime.now().isoformat()))
    conn.commit()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("DELETE FROM used_images WHERE used_at < ?", (week_ago,))
    conn.commit()

def get_recent_images() -> list:
    yesterday = (datetime.now() - timedelta(hours=24)).isoformat()
    c.execute("SELECT url FROM used_images WHERE used_at > ?", (yesterday,))
    return [row[0] for row in c.fetchall()]

def is_youtube_posted_today(video_id):
    today = datetime.now().date().isoformat()
    c.execute("SELECT 1 FROM youtube_posted WHERE video_id = ? AND DATE(posted_at) = ?", 
              (video_id, today))
    return c.fetchone() is not None

def save_youtube_posted(video_id, video_type):
    c.execute("INSERT OR IGNORE INTO youtube_posted (video_id, posted_at, type) VALUES (?, ?, ?)", 
              (video_id, datetime.now().isoformat(), video_type))
    conn.commit()

# НОВЫЕ ФУНКЦИИ: отслеживание каналов
def track_youtube_channel(channel_name: str):
    """Запоминаем использованный канал"""
    c.execute("INSERT INTO youtube_channels_used (channel_name, used_at) VALUES (?, ?)", 
              (channel_name.lower(), datetime.now().isoformat()))
    conn.commit()
    # Чистим старые записи (старше 3 дней)
    three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
    c.execute("DELETE FROM youtube_channels_used WHERE used_at < ?", (three_days_ago,))
    conn.commit()

def get_recent_channels(hours: int = 12) -> list:
    """Получаем недавно использованные каналы"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    c.execute("SELECT DISTINCT channel_name FROM youtube_channels_used WHERE used_at > ?", (cutoff,))
    return [row[0] for row in c.fetchall()]

def get_channel_usage_count(channel_name: str, hours: int = 24) -> int:
    """Сколько раз использовали канал за последние N часов"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    c.execute("SELECT COUNT(*) FROM youtube_channels_used WHERE channel_name = ? AND used_at > ?", 
              (channel_name.lower(), cutoff))
    result = c.fetchone()
    return result[0] if result else 0

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("news_bot")
bot = Bot(BOT_TOKEN)

# ================== AI HELPER ==================
async def ask_ai(prompt: str, temperature=0.7) -> str:
    """Универсальная функция для AI запросов"""
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

# ================== AI: ВЫБОР НОВОСТИ ==================
async def ai_select_and_summarize(news_list: list) -> dict:
    """AI выбирает новость и делает пересказ с КОРОТКИМИ хештегами"""
    news_text = "\n".join([f"{i+1}. {n['title']}" for i, n in enumerate(news_list[:25])])
    
    prompt = f"""Ты редактор ДЕРЗКОГО новостного Telegram-канала.

Выбери ОДНУ самую взрывную новость и сделай язвительный пересказ.

ВАЖНО:
1. Выбирай ГОРЯЧИЕ новости (конфликты, деньги, взрывы, скандалы)
2. Заголовок КОРОТКИЙ (макс 60 символов)
3. Убери "как", "почему", лишние слова
4. Пересказ ДОПОЛНЯЕТ заголовок
5. НЕ ВЫБИРАЙ философские цитаты и скучную хуйню!

ХЕШТЕГИ - КРИТИЧЕСКИ ВАЖНО:
- ТОЛЬКО односложные слова!
- КАЖДЫЙ хештег ОТДЕЛЬНО через пробел
- Максимум 4 хештега
- БЕЗ склейки слов!

Примеры ПРАВИЛЬНЫХ хештегов:
✅ #Путин #Москва #Переговоры #Дипломатия
✅ #Трамп #США #Санкции #Экономика
✅ #Доллар #Курс #Рубль #Биржа
✅ #Миграция #США #Тюрьма #Журналистика

Примеры НЕПРАВИЛЬНЫХ хештегов:
❌ #войнавУкраине (склейка!)
❌ #УиткоффКушнерПутин (склейка!)
❌ #ЗеленскийТрамп (склейка!)
❌ #ПереговорыВМоскве (склейка!)

Верни JSON:
{{
  "selected": номер (1-{len(news_list[:25])}),
  "title": "КОРОТКИЙ заголовок (макс 60 символов)",
  "summary": "Пересказ 2-3 предложения",
  "hashtags": "#Слово1 #Слово2 #Слово3 #Слово4"
}}

Новости:
{news_text}"""
    
    response = await ask_ai(prompt, temperature=0.9)
    
    if response:
        try:
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                content = response[json_start:json_end+1]
            else:
                content = response
            
            result = json.loads(content)
            selected_idx = int(result.get("selected", 1)) - 1
            
            if 0 <= selected_idx < len(news_list):
                selected_news = news_list[selected_idx]
                selected_news["ai_title"] = result.get("title", selected_news["title"])
                selected_news["summary"] = result.get("summary", "")
                
                # Валидация хештегов - разбиваем склеенные
                raw_hashtags = result.get("hashtags", "")
                selected_news["hashtags"] = fix_hashtags(raw_hashtags)
                
                log.info(f"✅ AI выбрал #{selected_idx+1}: {selected_news['ai_title'][:50]}")
                return selected_news
        except Exception as e:
            log.warning(f"⚠️ AI parse error: {e}")
    
    # Fallback
    log.warning("⚠️ AI недоступен, fallback")
    priority_keywords = ['трамп', 'путин', 'война', 'взрыв', 'доллар']
    scored = [(sum(1 for kw in priority_keywords if kw in n["title"].lower()), n) for n in news_list[:10]]
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[0][1] if scored else random.choice(news_list[:5])
    
    desc = selected["desc"] if selected["desc"] else ""
    sentences = [s for s in re.split(r'[.!?]\s+', desc) if len(s) > 30]
    summary = '. '.join(sentences[:2]) + '.' if sentences else "Подробности выясняются."
    
    selected["ai_title"] = selected["title"]
    selected["summary"] = summary[:300]
    selected["hashtags"] = generate_smart_hashtags(selected["title"], desc)
    
    return selected

# ================== ФИКС ХЕШТЕГОВ ==================
def fix_hashtags(raw_hashtags: str) -> str:
    """Разбивает склеенные хештеги на отдельные слова"""
    
    # Убираем @ упоминания
    raw_hashtags = re.sub(r'@\w+', '', raw_hashtags).strip()
    
    # Находим все хештеги
    tags = re.findall(r'#\w+', raw_hashtags)
    
    fixed_tags = []
    for tag in tags:
        word = tag[1:]  # убираем #
        
        # Проверяем, не склеено ли (ищем CamelCase или несколько заглавных)
        parts = re.findall(r'[А-ЯЁA-Z][а-яёa-z]*|[а-яёa-z]+', word)
        
        if len(parts) > 1 and len(word) > 12:
            # Склеенный хештег - берём только значимые части (длиннее 2 букв)
            for part in parts:
                if len(part) > 2:
                    fixed_tags.append(f"#{part}")
        else:
            # Нормальный хештег
            fixed_tags.append(tag)
    
    # Убираем дубликаты, оставляем максимум 4
    seen = set()
    unique_tags = []
    for tag in fixed_tags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique_tags.append(tag)
    
    return ' '.join(unique_tags[:4])

# ================== СБОР НОВОСТЕЙ ==================
async def collect_fresh_news(limit=30):
    candidates = []
    sources = list(RSS_SOURCES.items())
    random.shuffle(sources)
    
    for source_name, rss_url in sources:
        if len(candidates) >= limit: break
        
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                if len(candidates) >= limit: break
                
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
                
                if len(title) < 20: continue
                if is_duplicate(title, url): continue
                if any(boring in title.lower() for boring in BORING_KEYWORDS): continue
                if not any(k in title.lower() for k in KEYWORDS): continue
                
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

# ================== УЛУЧШЕННАЯ СИСТЕМА КАРТИНОК ==================

# ПЕРСОНЫ ДЛЯ ПОИСКА КОНКРЕТНЫХ ФОТ
PERSON_SEARCH_QUERIES = {
    'трамп': ['donald trump', 'trump president', 'trump speech'],
    'путин': ['vladimir putin', 'putin russia', 'putin kremlin'],
    'байден': ['joe biden', 'biden president', 'biden speech'],
    'зеленск': ['zelensky ukraine', 'zelensky president'],
    'макрон': ['macron france', 'macron president'],
    'си цзиньпин': ['xi jinping', 'china president xi'],
    'кушнер': ['jared kushner', 'kushner trump'],
}

async def ai_generate_image_queries(title: str, description: str) -> list:
    """AI генерирует запросы, ВКЛЮЧАЯ КОНКРЕТНЫХ ЛЮДЕЙ если они в новости"""
    
    text_lower = f"{title} {description}".lower()
    
    # СНАЧАЛА проверяем персон в новости
    person_queries = []
    for person_key, queries in PERSON_SEARCH_QUERIES.items():
        if person_key in text_lower:
            # Добавляем запросы для этой персоны
            person_queries.extend(queries[:2])
            log.info(f"   🎯 Найдена персона: {person_key} → добавляю запросы: {queries[:2]}")
    
    # Если нашли персон - сразу их возвращаем (они приоритетнее)
    if person_queries:
        return person_queries[:3]
    
    # Иначе AI генерирует тематические запросы
    prompt = f"""Новость: "{title}"

Сгенерируй 3 поисковых запроса на АНГЛИЙСКОМ для поиска фото.

ВАЖНО:
- Если в новости есть ИЗВЕСТНЫЕ ЛЮДИ (политики, бизнесмены) - ИЩИ ИХ ФОТО!
- Максимум 2-3 слова
- На английском

Примеры:
"Путин встретился с Трампом" → ["putin trump", "kremlin meeting", "russia usa summit"]
"Курс доллара вырос" → ["dollar currency", "stock market", "money exchange"]
"Взрыв в жилом доме" → ["building explosion", "fire rescue", "emergency"]

Верни JSON:
{{"queries": ["запрос1", "запрос2", "запрос3"]}}"""
    
    response = await ask_ai(prompt, temperature=0.7)
    
    if response:
        try:
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                content = response[json_start:json_end+1]
                result = json.loads(content)
                queries = result.get("queries", [])[:3]
                
                # Ограничиваем 3 словами
                cleaned = []
                for q in queries:
                    q = re.sub(r'\b(19|20)\d{2}\b', '', q).strip()
                    words = q.split()
                    if len(words) <= 3:
                        cleaned.append(q)
                    else:
                        cleaned.append(' '.join(words[:3]))
                
                if cleaned:
                    log.info(f"   ✅ AI сгенерировал запросы: {cleaned}")
                    return cleaned
        except Exception as e:
            log.warning(f"   ⚠️ AI parse error: {e}")
    
    return generate_fallback_queries(title, description)


def generate_fallback_queries(title: str, description: str) -> list:
    """Генерирует запросы без AI на основе темы"""
    text = f"{title} {description}".lower()
    queries = []
    
    # ПЕРСОНЫ - приоритет!
    if 'трамп' in text: queries.append('donald trump')
    if 'путин' in text: queries.append('vladimir putin')
    if 'байден' in text: queries.append('joe biden')
    if 'зеленск' in text: queries.append('zelensky')
    if 'макрон' in text: queries.append('macron')
    
    # Если нашли персон - возвращаем
    if queries:
        return queries[:3]
    
    # Политика и дипломатия
    if any(w in text for w in ['перегов', 'встреч', 'визит', 'саммит']):
        queries.append('diplomatic meeting')
        queries.append('conference room')
    
    # Россия
    if any(w in text for w in ['кремл', 'москв', 'росси']):
        queries.append('kremlin moscow')
        queries.append('russian government')
    
    # США
    if any(w in text for w in ['сша', 'америк', 'вашингтон', 'белый дом']):
        queries.append('white house washington')
        queries.append('american flag')
    
    # Украина
    if 'украин' in text or 'киев' in text:
        queries.append('ukraine kyiv')
    
    # Война/конфликт
    if any(w in text for w in ['война', 'конфликт', 'военн', 'армия']):
        queries.append('military conflict')
        queries.append('war zone')
    
    # Экономика
    if any(w in text for w in ['доллар', 'рубль', 'курс', 'биржа', 'экономик']):
        queries.append('stock market trading')
        queries.append('dollar currency')
    
    # ЧП
    if any(w in text for w in ['взрыв', 'пожар', 'авари']):
        queries.append('explosion fire')
        queries.append('emergency rescue')
    
    # Тюрьма/миграция
    if any(w in text for w in ['тюрьм', 'мигр', 'депорт', 'задерж']):
        queries.append('prison bars')
        queries.append('detention center')
    
    # Давос
    if 'давос' in text:
        queries.append('davos forum')
        queries.append('economic summit')
    
    # Дефолт
    if not queries:
        queries = ['world news', 'breaking news', 'global politics']
    
    log.info(f"   ⚠️ Fallback запросы: {queries[:3]}")
    return queries[:3]

async def search_unsplash(query: str, count=30) -> list:
    """Ищет картинки на Unsplash"""
    if not UNSPLASH_ACCESS_KEY:
        log.warning("   ❌ Unsplash API ключ не найден!")
        return []
    
    try:
        log.info(f"   🔍 Unsplash запрос: '{query}' (ищу {count} фото)")
        
        url = "https://api.unsplash.com/search/photos"
        params = {"query": query, "per_page": count, "orientation": "landscape"}
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                log.info(f"   📡 Unsplash ответ: HTTP {r.status}")
                
                if r.status == 200:
                    data = await r.json()
                    results = data.get("results", [])
                    log.info(f"   ✅ Unsplash вернул {len(results)} фото")
                    
                    return [{"url": p["urls"]["regular"], "desc": p.get("description", "") or p.get("alt_description", ""), "source": "unsplash"} 
                            for p in results[:count]]
                elif r.status == 401:
                    error_text = await r.text()
                    log.error(f"   ❌ Unsplash 401 (неверный ключ): {error_text[:200]}")
                elif r.status == 403:
                    error_text = await r.text()
                    log.error(f"   ❌ Unsplash 403 (лимит исчерпан): {error_text[:200]}")
                else:
                    error_text = await r.text()
                    log.error(f"   ❌ Unsplash {r.status}: {error_text[:200]}")
                    
    except asyncio.TimeoutError:
        log.error(f"   ⏱️ Unsplash timeout для '{query}'")
    except Exception as e:
        log.error(f"   ❌ Unsplash exception: {e}")
    
    return []

async def search_pexels(query: str, count=30) -> list:
    """Ищет картинки на Pexels"""
    if not PEXELS_API_KEY:
        log.warning("   ❌ Pexels API ключ не найден!")
        return []
    
    try:
        log.info(f"   🔍 Pexels запрос: '{query}' (ищу {count} фото)")
        
        url = "https://api.pexels.com/v1/search"
        params = {"query": query, "per_page": count, "orientation": "landscape"}
        headers = {"Authorization": PEXELS_API_KEY}
        
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                log.info(f"   📡 Pexels ответ: HTTP {r.status}")
                
                if r.status == 200:
                    data = await r.json()
                    photos = data.get("photos", [])
                    log.info(f"   ✅ Pexels вернул {len(photos)} фото")
                    
                    return [{"url": p["src"]["large"], "desc": p.get("alt", ""), "source": "pexels"} 
                            for p in photos[:count]]
                else:
                    error_text = await r.text()
                    log.error(f"   ❌ Pexels {r.status}: {error_text[:100]}")
                    
    except asyncio.TimeoutError:
        log.error(f"   ⏱️ Pexels timeout для '{query}'")
    except Exception as e:
        log.error(f"   ❌ Pexels exception: {e}")
    
    return []

async def ai_rate_images(images: list, title: str) -> dict:
    """AI оценивает картинки по URL + ОПИСАНИЯМ"""
    if not images:
        return None
    
    # ПОКАЗЫВАЕМ КАРТИНКИ С ОПИСАНИЯМИ
    log.info(f"   📋 Найденные картинки ({len(images)} шт):")
    for i, img in enumerate(images[:10], 1):
        desc_preview = img.get('desc', 'нет описания')[:50]
        log.info(f"      {i}. {img['source']}: {desc_preview}")
    
    images_text = "\n".join([
        f"{i+1}. Описание: \"{img.get('desc', 'нет')}\" | Источник: {img['source']}" 
        for i, img in enumerate(images[:30])
    ])
    
    prompt = f"""Новость: "{title}"

Вот {len(images[:30])} картинок с ОПИСАНИЯМИ:
{images_text}

Оцени каждую от 1 до 10 по релевантности к новости. ИСПОЛЬЗУЙ ОПИСАНИЯ для оценки!

Верни JSON:
{{
  "best_id": номер лучшей (1-{len(images[:30])}),
  "score": оценка (1-10),
  "reason": "почему выбрал"
}}

Если ВСЕ картинки плохие (оценка < 5), верни {{"best_id": 0, "score": 0, "reason": "все плохие"}}"""
    
    response = await ask_ai(prompt, temperature=0.5)
    
    if response:
        try:
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                content = response[json_start:json_end+1]
                result = json.loads(content)
                best_id = int(result.get("best_id", 0))
                score = int(result.get("score", 0))
                reason = result.get("reason", "")
                
                log.info(f"   🤖 AI выбрал картинку #{best_id}, оценка {score}/10")
                log.info(f"   💭 Причина: {reason}")
                
                if best_id > 0 and score >= 5 and best_id <= len(images):
                    return {"image": images[best_id - 1], "score": score}
        except Exception as e:
            log.warning(f"   ⚠️ AI parse error: {e}")
    
    # Fallback - берём первую
    if images:
        log.warning("   ⚠️ AI не смог выбрать, беру первую")
        return {"image": images[0], "score": 5}
    
    return None

async def get_perfect_image(title: str, description: str, rss_image: str = None) -> str:
    """
    УЛУЧШЕННАЯ СИСТЕМА с НЕСКОЛЬКИМИ запросами:
    1. AI генерирует запросы (включая персон)
    2. Делаем ДО 5 запросов к Unsplash (разные запросы)
    3. AI выбирает лучшее
    """
    
    log.info("   🎨 Запускаю УЛУЧШЕННЫЙ поиск картинок...")
    
    all_images = []
    
    # Шаг 1: AI генерирует запросы
    queries = await ai_generate_image_queries(title, description)
    
    # Шаг 2: Делаем НЕСКОЛЬКО запросов к Unsplash (до 5)
    for i, query in enumerate(queries[:3]):
        log.info(f"   🔍 Запрос {i+1}/3: '{query}'")
        
        unsplash_images = await search_unsplash(query, count=15)
        if unsplash_images:
            all_images.extend(unsplash_images)
            log.info(f"   ✅ +{len(unsplash_images)} фото от Unsplash")
        
        # Небольшая пауза между запросами
        await asyncio.sleep(0.3)
    
    # Шаг 3: Pexels как дополнение
    if queries:
        pexels_images = await search_pexels(queries[0], count=15)
        if pexels_images:
            all_images.extend(pexels_images)
            log.info(f"   ✅ +{len(pexels_images)} фото от Pexels")
    
    # Шаг 4: RSS картинка
    if rss_image and len(rss_image) > 50:
        log.info(f"   🎯 Добавляю RSS картинку...")
        img_data = await download_image(rss_image)
        if img_data and len(img_data) > 5000:
            all_images.append({"url": rss_image, "desc": "RSS original image", "source": "rss"})
    
    # Шаг 5: Убираем дубликаты
    seen_urls = set()
    unique_images = []
    for img in all_images:
        if img["url"] not in seen_urls:
            seen_urls.add(img["url"])
            unique_images.append(img)
    
    log.info(f"   📊 Всего уникальных картинок: {len(unique_images)}")
    
    if not unique_images:
        log.error("   ❌ НЕ НАЙДЕНО КАРТИНОК!")
        return None
    
    # Шаг 6: AI выбирает лучшую
    best = await ai_rate_images(unique_images, title)
    
    if best and best["score"] >= 5:
        img_url = best["image"]["url"]
        log.info(f"   🏆 ПОБЕДИТЕЛЬ: {best['image']['source']} (оценка {best['score']}/10)")
        track_used_image(img_url)
        return img_url
    
    # Fallback - первая картинка
    if unique_images:
        log.warning("   ⚠️ Все картинки плохие, беру первую")
        img_url = unique_images[0]["url"]
        track_used_image(img_url)
        return img_url
    
    return None

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

def generate_smart_hashtags(title: str, description: str = "") -> str:
    """Генерирует КОРОТКИЕ односложные хештеги"""
    text = f"{title} {description}".lower()
    tags = []
    
    # Персоны (односложные!)
    if 'путин' in text: tags.append('#Путин')
    if 'трамп' in text: tags.append('#Трамп')
    if 'байден' in text: tags.append('#Байден')
    if 'зеленск' in text: tags.append('#Зеленский')
    if 'кушнер' in text: tags.append('#Кушнер')
    if 'уиткофф' in text: tags.append('#Уиткофф')
    if 'макрон' in text: tags.append('#Макрон')
    if 'си цзиньпин' in text or 'цзиньпин' in text: tags.append('#Китай')
    
    # Страны (односложные!)
    if 'сша' in text or 'америк' in text: tags.append('#США')
    if 'украин' in text: tags.append('#Украина')
    if 'росси' in text or ' рф ' in text: tags.append('#Россия')
    if 'герман' in text: tags.append('#Германия')
    if 'китай' in text or 'пекин' in text: tags.append('#Китай')
    if 'москв' in text: tags.append('#Москва')
    if 'давос' in text: tags.append('#Давос')
    
    # Темы (односложные!)
    if any(w in text for w in ['доллар', 'рубль', 'курс', 'валют']): tags.append('#Курс')
    if any(w in text for w in ['экономик', 'санкци', 'пошлин']): tags.append('#Экономика')
    if 'война' in text or 'конфликт' in text: tags.append('#Война')
    if 'перегов' in text or 'встреч' in text or 'визит' in text: tags.append('#Переговоры')
    if any(w in text for w in ['взрыв', 'пожар', 'авари']): tags.append('#ЧП')
    if any(w in text for w in ['арест', 'суд', 'задерж']): tags.append('#Криминал')
    if any(w in text for w in ['тюрьм', 'мигр', 'депорт']): tags.append('#Миграция')
    if any(w in text for w in ['журнал', 'сми', 'газет']): tags.append('#СМИ')
    
    # Убираем дубликаты
    seen = set()
    unique = []
    for tag in tags:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            unique.append(tag)
    
    if not unique:
        unique.append('#Новости')
    
    return ' '.join(unique[:4])

# ================== ПОСТИНГ ==================
async def post_selected_news(news):
    title = news.get("ai_title", news["title"])
    url = news["url"]
    summary = news.get("summary", "")
    hashtags = news.get("hashtags", "")
    desc = news.get("desc", "")
    rss_image = news.get("rss_image")
    
    hashtags = re.sub(r'@\w+', '', hashtags).strip()
    if not hashtags:
        hashtags = generate_smart_hashtags(title, desc)
    
    caption = f"**{title}**\n\n{summary}\n\n{hashtags}"
    
    log.info(f"   📰 ПОСТ:")
    log.info(f"   Заголовок: {title}")
    log.info(f"   Хештеги: {hashtags}")
    
    img_url = await get_perfect_image(title, desc, rss_image)
    
    if not img_url:
        log.warning("   ⚠️ Картинка не найдена, пропускаем пост")
        return False
    
    img_data = await download_image(img_url)
    
    if img_data and len(img_data) > 1024:
        try:
            file = BufferedInputFile(img_data, filename="news.jpg")
            await bot.send_photo(CHANNEL_ID, file, caption=caption, parse_mode=ParseMode.MARKDOWN)
            save_posted(news["title"], url)
            increment_stat()
            log.info(f"✅ Опубликовано: {title[:50]}")
            return True
        except Exception as e:
            log.error(f"❌ Ошибка: {e}")
            return False
    else:
        log.warning("   ⚠️ Битая картинка")
        return False

# ================== ЦИКЛ ==================
async def check_news():
    stats = get_today_stats()
    if stats["normal"] >= 25:
        log.info("📊 Лимит 25 постов")
        return
    
    log.info("📥 Собираю новости...")
    candidates = await collect_fresh_news(30)
    
    if not candidates:
        log.info("⚠️ Новых новостей нет")
        return
    
    log.info(f"📊 Найдено {len(candidates)} кандидатов")
    
    selected = await ai_select_and_summarize(candidates)
    
    if not selected:
        log.warning("⚠️ AI не выбрал новость")
        return
    
    await post_selected_news(selected)

async def news_loop():
    log.info("⏰ Первый пост через 5 секунд...")
    await asyncio.sleep(5)
    
    while True:
        await check_news()
        next_interval = random.randint(20, 70)
        log.info(f"⏰ Следующий пост через {next_interval} мин")
        await asyncio.sleep(next_interval * 60)

# ================== YOUTUBE SHORTS - УЛУЧШЕННЫЙ ==================
def has_cyrillic(text):
    return bool(re.search('[а-яА-ЯёЁ]', text))

def has_ukrainian(text):
    return any(l in text for l in ['є', 'і', 'ї', 'ґ', 'Є', 'І', 'Ї', 'Ґ'])

def is_russian_content(title, channel_title, description=""):
    full_text = f"{title} {channel_title} {description}".lower()
    
    if not has_cyrillic(title + channel_title):
        return False
    
    if has_ukrainian(title + channel_title + description):
        return False
    
    ua_keywords = ['україн', 'ukrainian', 'kiev', 'kyiv', 'київ', 'зеленськ', 'zelensky', 'азов', 'всу', 'зсу']
    if any(kw in full_text for kw in ua_keywords):
        return False
    
    return True

def is_trusted_news_channel(channel_title):
    return any(t.lower() in channel_title.lower() for t in RU_NEWS_CHANNELS)

def is_any_news_related(title: str, channel: str, description: str = "") -> bool:
    text = f"{title} {channel} {description}".lower()
    
    if is_trusted_news_channel(channel):
        return True
    
    news_keywords = [
        'новост', 'сегодня', 'срочн', 'главное', 'итоги',
        'путин', 'россия', 'правительств', 'президент', 'министр',
        'кремль', 'дума', 'политик', 'закон', 'реформ',
        'трамп', 'байден', 'сша', 'украин', 'война', 'мир',
        'европ', 'китай', 'нато',
        'рубль', 'доллар', 'курс', 'эконом', 'инфляц',
        'цены', 'зарплат', 'пенси', 'нефть', 'газ',
        'заявил', 'объявил', 'сообщил', 'произошл', 'случил',
        'решил', 'подписал', 'принял',
        'пожар', 'взрыв', 'авария', 'задержа', 'арест',
        'важн', 'главн', 'скандал', 'сенсац'
    ]
    
    matches = sum(1 for kw in news_keywords if kw in text)
    return matches >= 1

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
        return f"{views / 1_000_000:.1f}М"
    elif views >= 1_000:
        return f"{views / 1_000:.1f}К"
    else:
        return str(views)

async def search_diverse_shorts():
    """УЛУЧШЕННЫЙ поиск с РОТАЦИЕЙ каналов"""
    log.info("🔍 Поиск РАЗНООБРАЗНЫХ Shorts...")
    
    # Получаем недавно использованные каналы
    recent_channels = get_recent_channels(hours=12)
    log.info(f"   ⏭️ Исключаю {len(recent_channels)} недавних каналов: {recent_channels[:5]}...")
    
    all_shorts = []
    
    # РАСШИРЕННЫЙ список запросов для разнообразия
    diverse_queries = [
        "новости россии сегодня",
        "политика путин кремль",
        "путин заявил",
        "трамп новости",
        "мировые новости",
        "курс доллара рубль",
        "экономика россии",
        "россия происшествия",
        "важные новости дня",
        "срочные новости",
        "итоги недели россия",
        "главное за день",
        "политические новости",
        "международные отношения",
        "скандал россия",
    ]
    
    # Перемешиваем запросы для разнообразия
    random.shuffle(diverse_queries)
    
    for query in diverse_queries[:10]:
        try:
            log.info(f"   🔎 '{query}'...")
            
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "id,snippet",
                "q": query + " shorts",
                "type": "video",
                "maxResults": 50,  # Увеличил
                "order": "date",   # ИЗМЕНИЛ: сначала по дате, потом фильтруем
                "publishedAfter": (datetime.now() - timedelta(days=3)).isoformat() + "Z",
                "regionCode": "RU",
                "relevanceLanguage": "ru",
                "videoCategoryId": "25",
                "key": YOUTUBE_API_KEY
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
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
                    
                    async with session.get(details_url, params=details_params, 
                                          timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
                                channel_title = snippet.get("channelTitle", "")
                                description = snippet.get("description", "")
                                
                                # ПРОВЕРКА: канал уже использовался недавно?
                                if channel_title.lower() in recent_channels:
                                    log.debug(f"      ⏭️ Пропуск (недавний канал): {channel_title}")
                                    continue
                                
                                # Проверяем сколько раз использовали канал за 24ч
                                channel_usage = get_channel_usage_count(channel_title, hours=24)
                                if channel_usage >= 2:  # Максимум 2 видео с одного канала в день
                                    log.debug(f"      ⏭️ Пропуск (лимит канала): {channel_title} ({channel_usage}/2)")
                                    continue
                                
                                if not is_russian_content(title, channel_title, description):
                                    continue
                                
                                if not is_any_news_related(title, channel_title, description):
                                    continue
                                
                                views = int(stats.get("viewCount", 0))
                                
                                min_views = 1000 if is_trusted_news_channel(channel_title) else 3000
                                if views < min_views:
                                    continue
                                
                                all_shorts.append({
                                    "id": item["id"],
                                    "title": title,
                                    "channel": channel_title,
                                    "views": views,
                                    "likes": int(stats.get("likeCount", 0)),
                                    "duration_sec": total_sec,
                                    "url": f"https://youtube.com/shorts/{item['id']}",
                                    "is_trusted": is_trusted_news_channel(channel_title)
                                })
                                
                            except Exception as e:
                                continue
            
            await asyncio.sleep(0.4)
            
        except Exception as e:
            log.warning(f"   ⚠️ Ошибка поиска '{query}': {e}")
            continue
    
    # Убираем дубликаты видео
    seen_ids = set()
    unique_shorts = []
    for short in all_shorts:
        if short["id"] not in seen_ids:
            seen_ids.add(short["id"])
            unique_shorts.append(short)
    
    # НОВАЯ СОРТИРОВКА: приоритет каналам которые давно не использовались + просмотры
    def sort_key(x):
        channel_usage = get_channel_usage_count(x["channel"], hours=48)
        # Чем меньше использовали - тем выше приоритет
        # Trusted каналы всё ещё имеют бонус
        return (channel_usage, not x["is_trusted"], -x["views"])
    
    unique_shorts.sort(key=sort_key)
    
    log.info(f"✅ Найдено {len(unique_shorts)} РАЗНООБРАЗНЫХ Shorts")
    
    # Показываем топ-5 для отладки
    for i, s in enumerate(unique_shorts[:5], 1):
        usage = get_channel_usage_count(s["channel"], hours=24)
        log.info(f"   {i}. [{s['channel'][:20]}] (использований: {usage}) - {s['title'][:40]}...")
    
    return unique_shorts

async def download_shorts_video(video_id):
    output_file = os.path.join(TEMP_DIR, f"shorts_{video_id}.mp4")
    
    try:
        log.info("   📥 Скачивание через yt-dlp...")
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        cmd = [
            sys.executable,
            "-m", "yt_dlp",
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
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), 
            timeout=90
        )
        
        if process.returncode == 0 and os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / 1024 / 1024
            log.info(f"   ✅ Скачано {file_size:.1f} MB")
            return output_file
        else:
            if os.path.exists(output_file):
                os.remove(output_file)
            return None
            
    except Exception as e:
        log.error(f"   ❌ Ошибка скачивания: {e}")
        if os.path.exists(output_file):
            os.remove(output_file)
        return None

async def post_youtube_shorts():
    """ОБНОВЛЁННЫЙ постинг Shorts с НОВЫМ форматом"""
    log.info("🎬 Запуск: YouTube Shorts...")
    
    shorts = await search_diverse_shorts()
    
    if not shorts:
        log.warning("⚠️ Shorts не найдены")
        return
    
    for i, short_video in enumerate(shorts[:15], 1):  # Увеличил до 15 попыток
        if is_youtube_posted_today(short_video["id"]):
            log.info(f"   [{i}/15] ⏭️ Пропуск (уже постили): {short_video['title'][:50]}")
            continue
        
        trust_badge = "⭐" if short_video["is_trusted"] else ""
        log.info(f"🎯 [{i}/15] {trust_badge} {short_video['title'][:60]}...")
        log.info(f"   👀 {format_views(short_video['views'])} | 📺 {short_video['channel']}")
        
        video_file_path = await download_shorts_video(short_video['id'])
        
        if not video_file_path:
            log.warning(f"   ⚠️ Не удалось скачать, пробую следующий...")
            continue
        
        try:
            # ================== НОВЫЙ ФОРМАТ ПОСТА ==================
            # Убираем "Главный новостной Short дня" и хештеги после //
            # Просто: название + канал + статистика
            
            # Очищаем название от лишнего
            clean_title = short_video['title']
            # Убираем хештеги из названия если есть
            clean_title = re.sub(r'#\S+', '', clean_title).strip()
            # Убираем // и всё после
            if '//' in clean_title:
                clean_title = clean_title.split('//')[0].strip()
            # Убираем | и всё после
            if '|' in clean_title:
                clean_title = clean_title.split('|')[0].strip()
            
            caption = (
                f"❗ {clean_title}\n\n"
                f"📺 {short_video['channel']}\n"
                f"👀 {format_views(short_video['views'])} просмотров | "
                f"❤️ {format_views(short_video['likes'])}\n\n"
                f"#shorts #новости"
            )
            
            with open(video_file_path, 'rb') as f:
                video_data = f.read()
            
            video_file = BufferedInputFile(
                video_data, 
                filename=f"{short_video['id']}.mp4"
            )
            
            await bot.send_video(
                CHANNEL_ID,
                video=video_file,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True,
                width=1080,
                height=1920
            )
            
            save_youtube_posted(short_video['id'], 'shorts')
            # ВАЖНО: отслеживаем использованный канал
            track_youtube_channel(short_video['channel'])
            log.info(f"✅ YouTube Shorts опубликован! (канал: {short_video['channel']})")
            
            os.remove(video_file_path)
            log.info(f"🗑️ Файл удалён: {video_file_path}")
            
            return True
            
        except Exception as e:
            log.error(f"❌ Ошибка отправки: {e}")
            
            if os.path.exists(video_file_path):
                os.remove(video_file_path)
                log.info(f"🗑️ Файл удалён после ошибки")
            
            continue
    
    log.warning("⚠️ Не удалось запостить ни один Shorts из топ-15")
    return False

def cleanup_old_files():
    try:
        now = datetime.now().timestamp()
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                
                if file_age > 86400:
                    os.remove(filepath)
                    log.info(f"🗑️ Удалён старый файл: {filename}")
    except Exception as e:
        log.warning(f"⚠️ Ошибка очистки: {e}")

# ================== ГЛАВНАЯ ФУНКЦИЯ ==================
async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    
    # YouTube Shorts - 3 раза в день
    scheduler.add_job(post_youtube_shorts, "cron", hour=9, minute=0, name="shorts_morning")
    scheduler.add_job(post_youtube_shorts, "cron", hour=19, minute=0, name="shorts_evening")
    scheduler.add_job(post_youtube_shorts, "cron", hour=22, minute=0, name="shorts_night")
    
    # Очистка старых файлов
    scheduler.add_job(cleanup_old_files, "cron", hour=3, minute=0)
    
    scheduler.start()
    
    log.info("=" * 70)
    log.info("🤖 НОВОСТНОЙ БОТ v2.0 - УЛУЧШЕННЫЙ")
    log.info("=" * 70)
    log.info("📰 Новости: каждые 20-70 мин (макс 25/день)")
    log.info("🎬 YouTube Shorts: 3 раза в день (9:00, 19:00, 22:00)")
    log.info("")
    log.info("🆕 ЧТО НОВОГО:")
    log.info("   ✅ Ротация каналов YouTube (макс 2 видео/канал/день)")
    log.info("   ✅ Новый формат Shorts постов (без 'Главный Short дня')")
    log.info("   ✅ Улучшенный поиск картинок (конкретные персоны)")
    log.info("   ✅ До 5 запросов к Unsplash для лучших результатов")
    log.info("   ✅ Расширенный список новостных каналов")
    log.info("=" * 70)
    
    await news_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("👋 Бот остановлен")
        conn.close()
    except Exception as e:
        log.error(f"💥 Критическая ошибка: {e}")
        conn.close()