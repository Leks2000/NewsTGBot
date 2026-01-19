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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")

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
]

RU_NEWS_CHANNELS = [
    "РИА Новости", "ТАСС", "Известия", "Интерфакс", "РБК",
    "Коммерсантъ", "Ведомости", "Первый канал", "Россия 24",
    "НТВ", "RT", "ДЕНЬ ТВ", "Кремль", "Дождь", "Медуза",
    "вДудь", "Популярная политика", "ФЕЙГИН LIVE", "Время Прядко",
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
    """Сохраняет использованную картинку в БД"""
    c.execute("INSERT INTO used_images (url, used_at) VALUES (?, ?)", 
              (url, datetime.now().isoformat()))
    conn.commit()
    
    # Очищаем старые (>7 дней)
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    c.execute("DELETE FROM used_images WHERE used_at < ?", (week_ago,))
    conn.commit()

def get_recent_images() -> list:
    """Получает картинки использованные за последние 24 часа"""
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("news_bot")
bot = Bot(BOT_TOKEN)

# ================== AI: ВЫБОР НОВОСТИ ==================
async def ai_select_and_summarize(news_list: list) -> dict:
    """AI выбирает новость и делает ЯЗВИТЕЛЬНЫЙ/КОМИЧНЫЙ пересказ"""
    
    news_text = "\n".join([f"{i+1}. {n['title']}" for i, n in enumerate(news_list[:25])])
    
    prompt = f"""Ты редактор ДЕРЗКОГО новостного Telegram-канала в стиле "Медузы" или "Пивного журналиста".

Выбери ОДНУ самую взрывную новость и сделай язвительный/ироничный пересказ.

ВАЖНО:
1. Заголовок должен быть ОРИГИНАЛЬНЫМ (не копируй исходный)
2. Пересказ должен ДОПОЛНЯТЬ заголовок новыми фактами/контекстом
3. Тон: ироничный, язвительный, но без мата
4. Пересказ 2-3 предложения, НО без повторения инфы из заголовка

Примеры правильного стиля:

Исходная новость: "Путин подписал указ о повышении МРОТ"
❌ ПЛОХО:
Заголовок: Путин подписал указ о повышении МРОТ
Пересказ: Президент России Владимир Путин подписал указ о повышении минимального размера оплаты труда.

✅ ХОРОШО:
Заголовок: МРОТ подрос на 300 рублей
Пересказ: Кремль решил порадовать работающих бедняков прибавкой, которой хватит ровно на два похода в Макдоналдс. Экономисты уже подсчитали, что это покроет ровно треть инфляции.

Исходная: "Трамп объявил о пошлинах из-за Гренландии"
❌ ПЛОХО:
Заголовок: Трамп вводит пошлины
Пересказ: Дональд Трамп объявил о введении пошлин из-за ситуации с Гренландией.

✅ ХОРОШО:
Заголовок: Дания отказалась продавать Гренландию – Трамп включил экономические санкции
Пересказ: Президент США решил надавить на "жадных датчан" через кошелёк. Пошлины коснутся всех стран Европы, которые "мешают сделке века". Дания пока молчит, но её экспорт уже плачет.

Верни JSON:
{{
  "selected": номер (1-{len(news_list[:25])}),
  "title": "ПЕРЕПИСАННЫЙ заголовок (короткий, цепляющий)",
  "summary": "Пересказ с НОВЫМИ фактами/контекстом (без повтора заголовка)",
  "hashtags": "2-4 хештега через пробел"
}}

КРИТИЧНО:
- Заголовок НЕ должен повторять исходный
- Пересказ НЕ должен повторять заголовок
- Максимум информативности + ирония

Новости:
{news_text}"""
    
    # ВСЕ КЛЮЧИ ЧЕРЕЗ OPENROUTER
    api_keys = [
        ("OpenRouter-1", GROQ_API_KEY),
        ("OpenRouter-2", OPENROUTER_API_KEY),
        ("OpenRouter-3", os.getenv("OPENROUTER_API_KEY_2"))
    ]
    
    # РАБОЧИЕ БЕСПЛАТНЫЕ МОДЕЛИ (проверено 2026)
    models = [
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "google/gemini-flash-1.5-8b:free",
        "qwen/qwen-2-7b-instruct:free",
    ]
    
    for key_name, api_key in api_keys:
        if not api_key:
            continue
            
        for model in models:
            try:
                log.info(f"   🤖 Пробую {key_name} → {model}...")
                
                async with aiohttp.ClientSession() as s:
                    headers = {
                        "Authorization": f"Bearer {api_key}", 
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": model, 
                        "messages": [{"role": "user", "content": prompt}], 
                        "temperature": 0.9, 
                        "max_tokens": 500
                    }
                    
                    async with s.post("https://openrouter.ai/api/v1/chat/completions",
                                     headers=headers, json=payload, 
                                     timeout=aiohttp.ClientTimeout(total=30)) as r:
                        if r.status == 200:
                            data = await r.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            
                            # Извлекаем JSON
                            json_start = content.find('{')
                            json_end = content.rfind('}')
                            if json_start != -1 and json_end != -1:
                                content = content[json_start:json_end+1]
                            
                            result = json.loads(content)
                            selected_idx = int(result.get("selected", 1)) - 1
                            
                            if 0 <= selected_idx < len(news_list):
                                selected_news = news_list[selected_idx]
                                selected_news["ai_title"] = result.get("title", selected_news["title"])
                                selected_news["summary"] = result.get("summary", "")
                                selected_news["hashtags"] = result.get("hashtags", "")
                                log.info(f"✅ {key_name}/{model} выбрал #{selected_idx+1}")
                                log.info(f"   📝 Заголовок: {selected_news['ai_title'][:60]}")
                                return selected_news
                        else:
                            error_text = await r.text()
                            log.warning(f"⚠️ {key_name}/{model} HTTP {r.status}: {error_text[:150]}")
                            
            except asyncio.TimeoutError:
                log.warning(f"⚠️ {key_name}/{model} timeout")
                continue
            except Exception as e:
                log.warning(f"⚠️ {key_name}/{model} error: {e}")
                continue
    
    log.warning("⚠️ Все AI недоступны, делаю fallback с нормальным форматом")
    
    # Выбираем приоритетную новость
    priority_keywords = ['трамп', 'путин', 'война', 'взрыв', 'доллар', 'санкц', 'арест']
    scored = []
    for news in news_list[:10]:
        score = sum(1 for kw in priority_keywords if kw in news["title"].lower())
        scored.append((score, news))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = scored[0][1] if scored else random.choice(news_list[:5])
    
    # ДЕЛАЕМ НОРМАЛЬНЫЙ ПЕРЕСКАЗ БЕЗ ДУБЛЯЖА
    original_title = selected["title"]
    desc = selected["desc"] if selected["desc"] else ""
    
    # Извлекаем основные факты из описания
    sentences = re.split(r'[.!?]\s+', desc)
    
    # Ищем предложения которых НЕТ в заголовке
    unique_sentences = []
    for sent in sentences:
        if len(sent) > 30:  # Минимальная длина
            # Проверяем что предложение не дублирует заголовок
            words_in_title = set(original_title.lower().split())
            words_in_sent = set(sent.lower().split())
            overlap = len(words_in_title & words_in_sent) / max(len(words_in_sent), 1)
            
            if overlap < 0.5:  # Меньше 50% совпадения
                unique_sentences.append(sent)
    
    # Берём первые 2 уникальных предложения
    if unique_sentences:
        summary = '. '.join(unique_sentences[:2]) + '.'
    else:
        # Если совсем нет описания - делаем краткий пересказ заголовка
        summary = f"Подробности инцидента выясняются. Ситуация находится под контролем."
    
    # Обрезаем если слишком длинный
    if len(summary) > 300:
        summary = summary[:297] + '...'
    
    selected["ai_title"] = original_title  # Используем оригинальный заголовок
    selected["summary"] = summary
    selected["hashtags"] = generate_smart_hashtags(original_title, desc)
    
    log.info(f"   📝 Fallback выбрал: {original_title[:60]}")
    log.info(f"   📝 Пересказ: {summary[:80]}...")
    
    return selected

# ================== СБОР НОВОСТЕЙ + ПАРСИНГ КАРТИНОК ==================
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
                
                title = entry.title.strip()
                url = entry.link
                desc = entry.get("summary", "") or entry.get("description", "") or ""
                
                title = BeautifulSoup(title, "html.parser").get_text()
                desc = BeautifulSoup(desc, "html.parser").get_text()
                
                # ========== ПАРСИМ КАРТИНКУ ИЗ RSS ==========
                rss_image = None
                
                # 1. Пробуем media:content
                if hasattr(entry, 'media_content') and entry.media_content:
                    rss_image = entry.media_content[0].get('url')
                
                # 2. Пробуем enclosure
                if not rss_image and hasattr(entry, 'enclosures') and entry.enclosures:
                    for enc in entry.enclosures:
                        if enc.get('type', '').startswith('image/'):
                            rss_image = enc.get('href')
                            break
                
                # 3. Ищем <img> в description
                if not rss_image:
                    soup = BeautifulSoup(entry.get("summary", "") or entry.get("description", ""), "html.parser")
                    img_tag = soup.find('img')
                    if img_tag and img_tag.get('src'):
                        rss_image = img_tag['src']
                
                # Проверяем валидность URL
                if rss_image:
                    if not rss_image.startswith('http'):
                        rss_image = None
                    # Проверяем что URL не обрезан (минимальная длина)
                    elif len(rss_image) < 30:
                        rss_image = None
                        log.debug(f"   ⚠️ RSS картинка слишком короткая: {rss_image}")
                
                if len(title) < 20: continue
                if is_duplicate(title, url): continue
                if any(boring in title.lower() for boring in BORING_KEYWORDS): continue
                if not any(k in title.lower() for k in KEYWORDS): continue
                
                candidates.append({
                    "title": title, 
                    "url": url, 
                    "desc": desc, 
                    "source": source_name,
                    "rss_image": rss_image  # СОХРАНЯЕМ КАРТИНКУ ИЗ RSS
                })
                
        except Exception as e:
            log.error(f"RSS {source_name}: {e}")
    
    return candidates

# ================== УМНАЯ СИСТЕМА ПОИСКА КАРТИНОК ==================

def extract_keywords_for_image_search(title: str, description: str = "") -> list:
    """Извлекает конкретные ключевые слова для поиска"""
    text = f"{title} {description}".lower()
    queries = []
    
    # ГЕОГРАФИЯ - самое важное
    places = {
        'гренланд': ['greenland ice', 'greenland landscape', 'arctic greenland'],
        'исланд': ['iceland volcano', 'iceland nature', 'reykjavik'],
        'норвег': ['norway fjord', 'norway landscape'],
        'швец': ['sweden stockholm', 'sweden flag'],
        'дан': ['denmark copenhagen', 'denmark flag'],
        'сыктывкар': ['russian city', 'komi republic russia'],
        'москв': ['moscow kremlin', 'red square moscow'],
        'петербург': ['saint petersburg', 'hermitage russia'],
        'киев': ['kyiv ukraine', 'kiev city'],
        'украин': ['ukraine flag', 'ukraine country'],
        'вашингтон': ['washington dc', 'white house', 'capitol building'],
        'нью-йорк': ['new york city', 'manhattan skyline'],
        'лондон': ['london big ben', 'london eye'],
        'париж': ['paris eiffel tower', 'paris france'],
        'берлин': ['berlin brandenburg gate', 'berlin germany'],
        'пекин': ['beijing forbidden city', 'beijing china'],
        'токио': ['tokyo japan', 'tokyo tower'],
    }
    
    for key, search_terms in places.items():
        if key in text:
            queries.extend(search_terms)
            break
    
    # ПЕРСОНЫ
    if 'трамп' in text: queries.append('donald trump president')
    if 'путин' in text: queries.append('vladimir putin')
    if 'байден' in text: queries.append('joe biden')
    if 'зеленск' in text: queries.append('zelensky ukraine')
    
    # СОБЫТИЯ
    if 'взрыв' in text: queries.extend(['explosion fire', 'emergency disaster'])
    if 'пожар' in text: queries.extend(['fire building', 'firefighters'])
    if 'доллар' in text or 'курс' in text: queries.extend(['us dollar bills', 'currency money'])
    if 'война' in text: queries.extend(['military conflict', 'war soldiers'])
    if 'нефть' in text: queries.append('oil refinery petroleum')
    if 'газ' in text: queries.append('natural gas pipeline')
    if 'космос' in text or 'ракет' in text: queries.extend(['rocket launch', 'space exploration'])
    if 'ии' in text or 'искусственн' in text: queries.extend(['artificial intelligence', 'ai technology'])
    
    if not queries:
        queries.append('breaking news')
    
    return queries[:4]  # Топ-4 запроса

async def search_unsplash_with_retries(query: str, retries=2) -> str:
    """Ищет на Unsplash с повторными попытками"""
    if not UNSPLASH_ACCESS_KEY:
        return None
    
    for attempt in range(retries):
        try:
            url = "https://api.unsplash.com/search/photos"
            params = {
                "query": query,
                "per_page": 30,
                "orientation": "landscape",
                "order_by": "relevant",
            }
            headers = {
                "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
                "Accept-Version": "v1"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, 
                                      timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        data = await r.json()
                        results = data.get("results", [])
                        
                        if results and len(results) > 0:
                            recent = get_recent_images()
                            available = [
                                photo["urls"]["regular"] 
                                for photo in results[:20]
                                if photo["urls"]["regular"] not in recent
                            ]
                            
                            if available:
                                selected = random.choice(available)
                                log.info(f"   ✅ Unsplash нашёл по '{query}': {len(available)} вариантов")
                                return selected
                    elif r.status == 403:
                        log.error(f"   ❌ Unsplash API лимит исчерпан")
                        return None
                    elif r.status == 401:
                        log.error(f"   ❌ Unsplash API ключ неверный")
                        return None
                        
        except asyncio.TimeoutError:
            log.warning(f"   ⏱️ Unsplash timeout (попытка {attempt+1}/{retries})")
            if attempt < retries - 1:
                await asyncio.sleep(1)
        except Exception as e:
            log.debug(f"   ⚠️ Unsplash '{query}' error: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
    
    return None

async def get_perfect_image(title: str, description: str = "", rss_image: str = None) -> str:
    """
    ПРИОРИТЕТЫ ПОИСКА КАРТИНКИ:
    1. Картинка из RSS (если есть и валидна)
    2. Fallback пул (Unsplash отключён, нет ключа)
    """
    
    # ПРИОРИТЕТ 1: Картинка из RSS
    if rss_image and len(rss_image) > 50:
        log.info(f"   🎯 Проверяю RSS картинку: {rss_image[:80]}...")
        
        img_data = await download_image(rss_image)
        if img_data and len(img_data) > 5000:
            recent = get_recent_images()
            if rss_image not in recent:
                track_used_image(rss_image)
                log.info(f"   ✅ RSS картинка ОК ({len(img_data)//1024}KB)")
                return rss_image
            else:
                log.info(f"   ⚠️ RSS картинка уже использовалась")
        else:
            log.warning(f"   ❌ RSS картинка битая")
    
    # ПРИОРИТЕТ 2: Fallback (Unsplash отключён)
    log.info("   📦 Используем fallback пул")
    return get_fallback_image(f"{title} {description}".lower())

def get_fallback_image(text: str) -> str:
    """Огромный пул тематических картинок"""
    
    pools = {
        'greenland': [
            "https://images.unsplash.com/photo-1531366936337-7c912a4589a7",
            "https://images.unsplash.com/photo-1583422409516-2895a77efded",
            "https://images.unsplash.com/photo-1528127269322-539801943592",
        ],
        'usa': [
            "https://images.unsplash.com/photo-1529107386315-e1a2ed48e620",
            "https://images.unsplash.com/photo-1485081669829-bacb8c7bb1f3",
            "https://images.unsplash.com/photo-1563306406-e66174fa3787",
            "https://images.unsplash.com/photo-1509024644558-2f56ce76c490",
            "https://images.unsplash.com/photo-1566073771259-6a8506099945",
        ],
        'russia': [
            "https://images.unsplash.com/photo-1513326738677-b964603b136d",
            "https://images.unsplash.com/photo-1520106212299-d99c443e4568",
            "https://images.unsplash.com/photo-1547448415-e9f5b28e570d",
            "https://images.unsplash.com/photo-1523906834658-6e24ef2386f9",
        ],
        'ukraine': [
            "https://images.unsplash.com/photo-1562077772-3bd90403f7f0",
            "https://images.unsplash.com/photo-1599930113854-d6d7fd521f10",
        ],
        'war': [
            "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5",
            "https://images.unsplash.com/photo-1580982172477-9373ff52ae43",
            "https://images.unsplash.com/photo-1562007908-17c67e878c88",
        ],
        'finance': [
            "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3",
            "https://images.unsplash.com/photo-1460925895917-afdab827c52f",
            "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e",
        ],
        'general': [
            "https://images.unsplash.com/photo-1504711434969-e33886168f5c",
            "https://images.unsplash.com/photo-1495020689067-958852a7765e",
            "https://images.unsplash.com/photo-1586339949916-3e9457bef6d3",
        ]
    }
    
    # Выбор пула
    if 'гренланд' in text:
        pool = pools['greenland']
    elif any(w in text for w in ['трамп', 'сша', 'америк']):
        pool = pools['usa']
    elif any(w in text for w in ['путин', 'россия', 'кремл']):
        pool = pools['russia']
    elif 'украин' in text:
        pool = pools['ukraine']
    elif 'война' in text:
        pool = pools['war']
    elif any(w in text for w in ['доллар', 'рубль', 'курс']):
        pool = pools['finance']
    else:
        pool = pools['general']
    
    recent = get_recent_images()
    available = [img for img in pool if img not in recent]
    
    if not available:
        available = pool
    
    selected = random.choice(available)
    track_used_image(selected)
    return selected

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
    """Генерирует хештеги"""
    text = f"{title} {description}".lower()
    tags = []
    
    if any(w in text for w in ['путин', 'кремл']): tags.append('#Путин')
    if 'трамп' in text: tags.append('#Трамп')
    if 'сша' in text: tags.append('#США')
    if 'украин' in text: tags.append('#Украина')
    if any(w in text for w in ['рубль', 'доллар']): tags.append('#валюта')
    if 'война' in text: tags.append('#война')
    if any(w in text for w in ['взрыв', 'пожар']): tags.append('#ЧП')
    if any(w in text for w in ['арест', 'суд']): tags.append('#криминал')
    
    if not tags:
        tags.append('#новости')
    
    return ' '.join(tags[:4])

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
    
    # ФОРМАТ КАК ТЫ ХОЧЕШЬ
    caption = f"**{title}**\n\n{summary}\n\n{hashtags}"
    
    log.info(f"   📰 ПОСТ:")
    log.info(f"   Заголовок: {title}")
    log.info(f"   Пересказ: {summary[:100]}...")
    log.info(f"   Хештеги: {hashtags}")
    
    log.info(f"   🎨 Ищу идеальную картинку...")
    img_url = await get_perfect_image(title, desc, rss_image)
    
    img_data = await download_image(img_url)
    
    for attempt in range(3):
        try:
            if img_data and len(img_data) > 1024:
                file = BufferedInputFile(img_data, filename="news.jpg")
                await bot.send_photo(CHANNEL_ID, file, caption=caption, parse_mode=ParseMode.MARKDOWN)
            else:
                if attempt == 0:
                    log.warning("   ⚠️ Битая картинка, пробую fallback")
                    img_url = get_fallback_image(f"{title} {desc}".lower())
                    img_data = await download_image(img_url)
                    continue
                else:
                    await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.MARKDOWN)
            
            save_posted(news["title"], url)
            increment_stat()
            log.info(f"✅ Опубликовано: {title[:50]}")
            return True
        except Exception as e:
            if attempt == 2:
                log.error(f"❌ Ошибка: {e}")
                return False
            await asyncio.sleep(2)
    
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

# ================== YOUTUBE ==================
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
    log.info("🔍 Поиск разнообразных Shorts...")
    
    all_shorts = []
    diverse_queries = [
        "новости россии сегодня",
        "политика путин кремль",
        "путин заявил",
        "трамп новости",
        "украина война новости",
        "мировые новости",
        "курс доллара рубль",
        "экономика россии",
        "россия происшествия",
        "важные новости дня",
    ]
    
    for query in diverse_queries[:8]:
        try:
            log.info(f"   🔎 '{query}'...")
            
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "id,snippet",
                "q": query + " shorts",
                "type": "video",
                "maxResults": 40,
                "order": "viewCount",
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
                                
                                if not is_russian_content(title, channel_title, description):
                                    continue
                                
                                if not is_any_news_related(title, channel_title, description):
                                    continue
                                
                                views = int(stats.get("viewCount", 0))
                                
                                min_views = 2000 if is_trusted_news_channel(channel_title) else 5000
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
    
    seen_ids = set()
    unique_shorts = []
    for short in all_shorts:
        if short["id"] not in seen_ids:
            seen_ids.add(short["id"])
            unique_shorts.append(short)
    
    unique_shorts.sort(key=lambda x: (not x["is_trusted"], -x["views"]))
    
    log.info(f"✅ Найдено {len(unique_shorts)} разнообразных Shorts")
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
    log.info("🎬 Запуск: YouTube Shorts (19:00)...")
    
    shorts = await search_diverse_shorts()
    
    if not shorts:
        log.warning("⚠️ Shorts не найдены")
        return
    
    for i, short_video in enumerate(shorts[:10], 1):
        if is_youtube_posted_today(short_video["id"]):
            log.info(f"   [{i}/10] ⏭️ Пропуск (уже постили): {short_video['title'][:50]}")
            continue
        
        trust_badge = "⭐" if short_video["is_trusted"] else ""
        log.info(f"🎯 [{i}/10] {trust_badge} {short_video['title'][:60]}...")
        log.info(f"   👀 {format_views(short_video['views'])} | 📺 {short_video['channel']}")
        
        video_file_path = await download_shorts_video(short_video['id'])
        
        if not video_file_path:
            log.warning(f"   ⚠️ Не удалось скачать, пробую следующий...")
            continue
        
        try:
            caption = (
                f"⚡ **Главный новостной Shorts дня**\n\n"
                f"**{short_video['title']}**\n\n"
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
            log.info("✅ YouTube Shorts опубликован!")
            
            os.remove(video_file_path)
            log.info(f"🗑️ Файл удалён: {video_file_path}")
            
            return True
            
        except Exception as e:
            log.error(f"❌ Ошибка отправки: {e}")
            
            if os.path.exists(video_file_path):
                os.remove(video_file_path)
                log.info(f"🗑️ Файл удалён после ошибки")
            
            continue
    
    log.warning("⚠️ Не удалось запостить ни один Shorts из топ-10")
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
    
    # YouTube Shorts - 3 раза в день (утро, вечер, ночь)
    scheduler.add_job(post_youtube_shorts, "cron", hour=9, minute=0, name="shorts_morning")
    scheduler.add_job(post_youtube_shorts, "cron", hour=19, minute=0, name="shorts_evening")
    scheduler.add_job(post_youtube_shorts, "cron", hour=22, minute=0, name="shorts_night")
    
    # Очистка старых файлов
    scheduler.add_job(cleanup_old_files, "cron", hour=3, minute=0)
    
    scheduler.start()
    
    log.info("=" * 70)
    log.info("🤖 НОВОСТНОЙ БОТ ЗАПУЩЕН")
    log.info("=" * 70)
    log.info("📰 Новости: каждые 20-70 мин (макс 25/день)")
    log.info("🎬 YouTube Shorts: 3 раза в день (9:00, 19:00, 22:00)")
    log.info("🎨 Картинки:")
    log.info("    1️⃣ Приоритет: из RSS фида")
    log.info("    2️⃣ Fallback: тематический пул Unsplash")
    log.info("    ⚠️ Unsplash API отключён (нет ключа)")
    log.info("🤖 AI: язвительные пересказы (OpenRouter)")
    log.info("♻️ Ротация: никаких повторов 24 часа")
    log.info(f"📡 RSS источников: {len(RSS_SOURCES)}")
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