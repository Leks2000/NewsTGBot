import asyncio
import feedparser
import aiohttp
import logging
import random
import sqlite3
import hashlib
import json
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, InputMediaPhoto, InputMediaVideo
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================== CONFIG ==================
BOT_TOKEN = '7885944156:AAHrh2o1UPzJ67jviCULfOmP_BGPExdh6l8'
GROQ_API_KEY = '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'
OPENROUTER_API_KEY = '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'
CHANNEL_ID = '@bulmyash'
TIMEZONE = "Europe/Moscow"

# Больше источников
RSS_SOURCES = {
    "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "tass": "https://tass.ru/rss/v2.xml",
    "interfax": "https://www.interfax.ru/rss.asp",
    "kommersant": "https://www.kommersant.ru/RSS/news.xml",
    "bbc_ru": "https://feeds.bbci.co.uk/russian/rss.xml",
    "reuters": "https://feeds.reuters.com/reuters/worldNews",
    "rt": "https://www.rt.com/rss/",
    "lenta": "https://lenta.ru/rss",
    "meduza": "https://meduza.io/rss/all",
    "ria": "https://ria.ru/export/rss2/index.xml",
    "fontanka": "https://www.fontanka.ru/fontanka.rss",
    "gazeta": "https://www.gazeta.ru/export/rss/first.xml",
    "vedomosti": "https://www.vedomosti.ru/rss/news",
    "izvestia": "https://iz.ru/xml/rss/all.xml",
    "rosbalt": "https://www.rosbalt.ru/feed/",
}

# ================== КЛЮЧЕВЫЕ СЛОВА (РАСШИРЕННЫЕ) ==================
KEYWORDS = [
    # Политика
    'санкц', 'трамп', 'путин', 'байден', 'зеленск', 'лукашенк', 
    'правительств', 'парламент', 'дума', 'минист', 'президент',
    'выбор', 'голосован', 'референдум', 'оппозиц',
    
    # Экономика
    'рубль', 'доллар', 'евро', 'нефть', 'газ', 'курс', 'цб', 'банк',
    'инфляц', 'рынок', 'биржа', 'акции', 'крипт', 'биткоин',
    'минфин', 'бюджет', 'налог', 'экспорт', 'импорт', 'внп', 'ввп',
    
    # Международные отношения
    'сша', 'китай', 'ес', 'евросоюз', 'нато', 'война', 'конфликт',
    'операц', 'войск', 'армия', 'удар', 'обстрел', 'атак',
    'переговор', 'саммит', 'встреча', 'договор', 'соглашен',
    
    # ЧП и происшествия
    'авар', 'катастроф', 'пожар', 'взрыв', 'обрушен', 'крушен',
    'погиб', 'жертв', 'ранен', 'спас', 'эвакуац', 'мчс',
    
    # Технологии
    'искусственн', 'нейросет', 'chatgpt', 'openai', 'google',
    'apple', 'microsoft', 'tesla', 'spacex', 'маск',
    'смартфон', 'процессор', 'квантов',
    
    # Криминал
    'задержа', 'арест', 'обыск', 'следств', 'суд', 'приговор',
    'мошенн', 'взятк', 'коррупц', 'украл', 'ограбл',
    
    # Наука
    'учен', 'исследован', 'открыт', 'изобрет', 'космос',
    'ракет', 'спутник', 'марс', 'луна',
    
    # Спорт (топовые события)
    'олимпиад', 'чемпионат мира', 'финал', 'сборная',
    'месси', 'роналду', 'овечкин'
]

BORING_KEYWORDS = ['погода', 'синоптик', 'температур', 'осадк', 
                   'прогноз погоды', 'гороскоп', 'лунный',
                   'сонник', 'примета']

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e",
    "https://images.unsplash.com/photo-1523995462485-3d171b5c8fa9"
]

# ================== БАЗА ДАННЫХ ==================
DB_FILE = "news.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Миграция БД
try:
    c.execute("ALTER TABLE posted ADD COLUMN priority TEXT")
    conn.commit()
except:
    pass

c.execute('''CREATE TABLE IF NOT EXISTS posted (
    hash TEXT UNIQUE, 
    posted_at TEXT, 
    priority TEXT,
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
conn.commit()

def get_today_stats():
    today = datetime.now().date().isoformat()
    c.execute("SELECT normal_count FROM daily_stats WHERE date = ?", (today,))
    result = c.fetchone()
    if result:
        return {"normal": result[0]}
    return {"normal": 0}

def increment_stat():
    today = datetime.now().date().isoformat()
    stats = get_today_stats()
    stats["normal"] += 1
    c.execute("""INSERT OR REPLACE INTO daily_stats (date, normal_count) 
                 VALUES (?, ?)""", (today, stats["normal"]))
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

def is_youtube_posted_today(video_id):
    today = datetime.now().date().isoformat()
    c.execute("SELECT 1 FROM youtube_posted WHERE video_id = ? AND DATE(posted_at) = ?", (video_id, today))
    return c.fetchone() is not None

def save_youtube_posted(video_id, video_type):
    c.execute("INSERT OR IGNORE INTO youtube_posted (video_id, posted_at, type) VALUES (?, ?, ?)", 
              (video_id, datetime.now().isoformat(), video_type))
    conn.commit()

# ================== ЛОГИ И БОТ ==================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("news_bot")
bot = Bot(BOT_TOKEN)

# ================== AI: GROQ + OPENROUTER ==================
async def ai_summarize(title: str, desc: str, source: str) -> dict:
    """Groq (Llama 70B) → OpenRouter (Mistral Large)"""
    
    if len(title) < 20 or any(boring in title.lower() for boring in BORING_KEYWORDS):
        return None
    
    prompt = f"""Перескажи новость КРАТКО (2-3 предложения), добавь острый комментарий.
Верни ТОЛЬКО JSON без лишнего текста:
{{
  "summary": "текст",
  "hashtags": "#тег1 #тег2"
}}

{title}
{desc[:200]}"""
    
    # 1️⃣ GROQ
    try:
        async with aiohttp.ClientSession() as s:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 200,
                "response_format": {"type": "json_object"}
            }
            async with s.post("https://api.groq.com/openai/v1/chat/completions", 
                            headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    data = await r.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    # Убираем markdown и мусор
                    content = re.sub(r'```json\s*|\s*```', '', content).strip()
                    result = json.loads(content)
                    log.info("✅ AI: Groq")
                    return result
                elif r.status == 429:
                    log.warning("⚠️ Groq rate limit")
    except Exception as e:
        log.warning(f"⚠️ Groq failed: {e}")
    
    # 2️⃣ OPENROUTER (усиленный парсинг)
    try:
        async with aiohttp.ClientSession() as s:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/news-bot",
                "X-Title": "News Bot"
            }
            payload = {
                "model": "mistralai/mistral-large-2411",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 300  # Увеличил лимит
            }
            async with s.post("https://openrouter.ai/api/v1/chat/completions",
                            headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    
                    # АГРЕССИВНАЯ ОЧИСТКА
                    # Убираем всё до первой {
                    json_start = content.find('{')
                    if json_start == -1:
                        raise ValueError("Нет JSON в ответе")
                    content = content[json_start:]
                    
                    # Убираем всё после последней }
                    json_end = content.rfind('}')
                    if json_end == -1:
                        raise ValueError("Нет закрывающей скобки")
                    content = content[:json_end+1]
                    
                    # Убираем markdown
                    content = re.sub(r'```(?:json)?\s*|\s*```', '', content).strip()
                    
                    result = json.loads(content)
                    log.info("✅ AI: OpenRouter")
                    return result
                else:
                    text = await r.text()
                    log.error(f"OpenRouter HTTP {r.status}: {text[:200]}")
    except json.JSONDecodeError as e:
        log.error(f"⚠️ OpenRouter JSON error: {e} | Content: {content[:100]}")
    except Exception as e:
        log.warning(f"⚠️ OpenRouter failed: {e}")
    
    log.error("❌ Все AI недоступны")
    return None
# ================== МЕДИА ==================
async def get_og_image(url: str) -> str | None:
    for attempt in range(3):
        try:
            connector = aiohttp.TCPConnector(ssl=False, force_close=True)
            async with aiohttp.ClientSession(connector=connector) as s:
                async with s.get(url, 
                               headers={"User-Agent": "Mozilla/5.0"}, 
                               timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200: 
                        return None
                    html = await r.text()
                    soup = BeautifulSoup(html, "html.parser")
                    og = soup.find("meta", property="og:image")
                    if og and og.get("content"):
                        img_url = og["content"]
                        if img_url.startswith("//"):
                            img_url = "https:" + img_url
                        return img_url
                    return None
        except Exception as e:
            if attempt == 2:
                log.error(f"OG image error: {e}")
            await asyncio.sleep(1)
    return None

async def download_image(url: str) -> bytes | None:
    for attempt in range(3):
        try:
            connector = aiohttp.TCPConnector(ssl=False, force_close=True)
            async with aiohttp.ClientSession(connector=connector) as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        return await r.read()
        except Exception as e:
            if attempt == 2:
                log.error(f"Download image error: {e}")
            await asyncio.sleep(1)
    return None

async def download_video(url: str) -> bytes | None:
    try:
        connector = aiohttp.TCPConnector(ssl=False, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200 and int(r.headers.get('content-length', 0)) < 50_000_000:
                    return await r.read()
    except Exception as e:
        log.error(f"Download video error: {e}")
    return None

async def extract_videos(entry):
    videos = []
    seen_urls = set()
    
    try:
        if hasattr(entry, "media_content"):
            for m in entry.media_content:
                u = m.get("url")
                if u and ("video" in m.get("medium", "") or u.endswith((".mp4", ".webm"))):
                    if u not in seen_urls:
                        videos.append(u)
                        seen_urls.add(u)
        
        if hasattr(entry, "enclosures"):
            for enc in entry.enclosures:
                if "video" in enc.get("type", ""):
                    href = enc["href"]
                    if href not in seen_urls:
                        videos.append(href)
                        seen_urls.add(href)
    except Exception as e:
        log.error(f"Extract videos error: {e}")
    
    return videos[:3]

# ================== YOUTUBE ТОПЫ ==================
async def parse_youtube_trending():
    url = "https://www.youtube.com/feed/trending?gl=RU&hl=ru"
    
    try:
        async with aiohttp.ClientSession() as s:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9"
            }
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return []
                
                html = await r.text()
                match = re.search(r'var ytInitialData = ({.*?});', html)
                if not match:
                    return []
                
                data = json.loads(match.group(1))
                videos = []
                try:
                    tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
                    for tab in tabs:
                        if "tabRenderer" in tab:
                            content = tab["tabRenderer"].get("content", {})
                            section = content.get("richGridRenderer", {}).get("contents", [])
                            
                            for item in section:
                                if "richItemRenderer" in item:
                                    video_data = item["richItemRenderer"]["content"]["videoRenderer"]
                                    
                                    video_id = video_data.get("videoId")
                                    title = video_data.get("title", {}).get("runs", [{}])[0].get("text", "")
                                    views = video_data.get("viewCountText", {}).get("simpleText", "0")
                                    length = video_data.get("lengthText", {}).get("simpleText", "")
                                    
                                    if video_id and title:
                                        videos.append({
                                            "id": video_id,
                                            "title": title,
                                            "views": views,
                                            "length": length,
                                            "url": f"https://www.youtube.com/watch?v={video_id}"
                                        })
                except:
                    pass
                
                return videos[:20]
    except Exception as e:
        log.error(f"YouTube error: {e}")
        return []

def is_short_video(length_str: str) -> bool:
    if not length_str:
        return False
    try:
        parts = length_str.split(":")
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes == 0 and seconds < 60
        elif len(parts) == 1:
            return int(parts[0]) < 60
    except:
        pass
    return False

async def post_youtube_tops():
    videos = await parse_youtube_trending()
    if not videos:
        return
    
    full_videos = [v for v in videos if not is_short_video(v.get("length", ""))]
    short_videos = [v for v in videos if is_short_video(v.get("length", ""))]
    
    top_full = None
    for v in full_videos:
        if not is_youtube_posted_today(v["id"]):
            top_full = v
            break
    
    top_short = None
    for v in short_videos:
        if not is_youtube_posted_today(v["id"]):
            top_short = v
            break
    
    if top_full:
        try:
            caption = f"🔥 **Самое популярное видео сегодня в РФ**\n\n{top_full['title']}\n\n👀 {top_full['views']}\n\n{top_full['url']}"
            await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=False)
            save_youtube_posted(top_full['id'], 'full')
            log.info(f"✅ YouTube топ")
        except Exception as e:
            log.error(f"YouTube error: {e}")
    
    await asyncio.sleep(3)
    
    if top_short:
        try:
            caption = f"⚡ **Самый популярный Shorts сегодня**\n\n{top_short['title']}\n\n👀 {top_short['views']}\n\n{top_short['url']}"
            await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=False)
            save_youtube_posted(top_short['id'], 'shorts')
            log.info(f"✅ YouTube shorts")
        except Exception as e:
            log.error(f"YouTube error: {e}")

# ================== ПОСТИНГ ==================
async def post_news(entry, source_name: str):
    """ПОСТИТ ОДНУ НОВОСТЬ (формат как на скринах)"""
    title = entry.title.strip()
    url = entry.link
    
    # Проверка дубля
    if is_duplicate(title, url):
        return False
    
    # Проверка лимита
    stats = get_today_stats()
    if stats["normal"] >= 25:
        return False
    
    # Проверка на скучное
    title_lower = title.lower()
    if any(boring in title_lower for boring in BORING_KEYWORDS):
        return False
    
    # Проверка релевантности
    if not any(k in title_lower for k in KEYWORDS):
        return False
    
    # Берём описание из RSS
    desc = entry.get("summary", "") or entry.get("description", "") or ""
    
    # AI обработка
    analysis = await ai_summarize(title, desc, source_name)
    
    if not analysis:
        log.warning(f"⚠️ Пропущено (нет AI): {title[:50]}")
        return False
    
    # Формат как на скринах (БЕЗ эмодзи, БЕЗ ссылок)
    caption = f"**{title}**\n\n{analysis['summary']}\n\n_{source_name}_\n\n{analysis['hashtags']}"
    
    # 1️⃣ ВИДЕО (медиагруппа)
    videos = await extract_videos(entry)
    if videos:
        try:
            media_group = []
            for i, video_url in enumerate(videos):
                video_data = await download_video(video_url)
                if video_data:
                    video_file = BufferedInputFile(video_data, filename=f"video{i}.mp4")
                    if i == 0:
                        media_group.append(InputMediaVideo(media=video_file, caption=caption, parse_mode=ParseMode.MARKDOWN))
                    else:
                        media_group.append(InputMediaVideo(media=video_file))
            
            if media_group:
                await bot.send_media_group(CHANNEL_ID, media_group)
                save_posted(title, url)
                increment_stat()
                log.info(f"✅ Видео ({len(media_group)}шт): {title[:40]}")
                return True
        except Exception as e:
            log.error(f"Video error: {e}")
    
    # 2️⃣ ФОТО
    img_url = await get_og_image(url)
    if not img_url:
        img_url = random.choice(FALLBACK_IMAGES)
    
    img_data = await download_image(img_url)
    
    try:
        if img_data:
            file = BufferedInputFile(img_data, filename="news.jpg")
            await bot.send_photo(CHANNEL_ID, file, caption=caption, parse_mode=ParseMode.MARKDOWN)
        else:
            await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error(f"Post error: {e}")
        return False
    
    save_posted(title, url)
    increment_stat()
    log.info(f"✅ Пост: {title[:40]}")
    return True

# ================== ОСНОВНОЙ ЦИКЛ ==================
async def check_news():
    """Проверяет RSS и постит ОДНУ новость"""
    sources_list = list(RSS_SOURCES.items())
    random.shuffle(sources_list)
    
    for source_name, rss_url in sources_list:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:10]:
                success = await post_news(entry, source_name)
                if success:
                    return  # СТОП после первого успешного поста
        except Exception as e:
            log.error(f"RSS error {source_name}: {e}")
    
    log.info("⚠️ Не найдено подходящих новостей")

async def news_loop():
    """Постинг каждые 20-70 мин"""
    log.info("⏰ Первый пост через 3 мин...")
    await asyncio.sleep(3 * 60)
    
    while True:
        await check_news()
        next_interval = random.randint(20, 70)
        log.info(f"⏰ Следующий пост через {next_interval} мин")
        await asyncio.sleep(next_interval * 60)

async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(post_youtube_tops, "cron", hour=19, minute=0)
    scheduler.start()
    
    log.info("🤖 БОТ ЗАПУЩЕН")
    log.info("📰 Посты каждые 20-70 мин (макс 25/день)")
    log.info("🎬 YouTube: 19:00 (топ видео + shorts)")
    log.info("🤖 AI: Groq → OpenRouter")
    log.info(f"📡 Источников: {len(RSS_SOURCES)}")
    log.info(f"🔑 Ключевых слов: {len(KEYWORDS)}")
    
    await news_loop()

if __name__ == "__main__":
    asyncio.run(main())