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

KEYWORDS = [
    'санкц', 'трамп', 'путин', 'байден', 'зеленск', 'лукашенк', 
    'правительств', 'парламент', 'дума', 'минист', 'президент',
    'рубль', 'доллар', 'евро', 'нефть', 'газ', 'курс', 'цб', 'банк',
    'инфляц', 'рынок', 'биржа', 'акции', 'крипт', 'биткоин',
    'сша', 'китай', 'ес', 'евросоюз', 'нато', 'война', 'конфликт',
    'операц', 'войск', 'армия', 'удар', 'обстрел', 'атак',
    'авар', 'катастроф', 'пожар', 'взрыв', 'обрушен', 'крушен',
    'погиб', 'жертв', 'ранен', 'спас', 'эвакуац', 'мчс',
    'искусственн', 'нейросет', 'chatgpt', 'openai', 'google',
    'apple', 'microsoft', 'tesla', 'spacex', 'маск',
    'задержа', 'арест', 'обыск', 'следств', 'суд', 'приговор',
    'учен', 'исследован', 'открыт', 'изобрет', 'космос',
    'ракет', 'спутник', 'марс', 'луна', 'олимпиад', 'чемпионат'
]

BORING_KEYWORDS = ['погода', 'синоптик', 'температур', 'осадк', 
                   'прогноз погоды', 'гороскоп', 'лунный', 'сонник']

FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c",
    "https://images.unsplash.com/photo-1495020689067-958852a7765e",
    "https://images.unsplash.com/photo-1523995462485-3d171b5c8fa9"
]

# ================== БАЗА ДАННЫХ ==================
DB_FILE = "news.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

try:
    c.execute("ALTER TABLE posted ADD COLUMN title TEXT")
    conn.commit()
except:
    pass

try:
    c.execute("ALTER TABLE posted ADD COLUMN url TEXT")
    conn.commit()
except:
    pass

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

def is_youtube_posted_today(video_id):
    today = datetime.now().date().isoformat()
    c.execute("SELECT 1 FROM youtube_posted WHERE video_id = ? AND DATE(posted_at) = ?", (video_id, today))
    return c.fetchone() is not None

def save_youtube_posted(video_id, video_type):
    c.execute("INSERT OR IGNORE INTO youtube_posted (video_id, posted_at, type) VALUES (?, ?, ?)", 
              (video_id, datetime.now().isoformat(), video_type))
    conn.commit()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger("news_bot")
bot = Bot(BOT_TOKEN)

# ================== AI: ВЫБОР ТОПОВОЙ НОВОСТИ ==================
async def ai_select_and_summarize(news_list: list) -> dict:
    """
    Один запрос к AI:
    1. Выбирает ТОП-1 новость из списка
    2. Пишет краткий пересказ и хештеги
    """
    
    # Формируем список для AI
    news_text = "\n".join([f"{i+1}. {n['title']}" for i, n in enumerate(news_list[:25])])
    
    prompt = f"""Ты редактор новостного канала. Из списка выбери ОДНУ самую важную/шокирующую/трендовую новость.
Верни JSON:
{{
  "selected": номер новости (1-{len(news_list[:25])}),
  "summary": "краткий пересказ 2-3 предложения с острым комментарием",
  "hashtags": "#тег1 #тег2 #тег3"
}}

Новости:
{news_text}"""
    
    # 1️⃣ GROQ
    try:
        async with aiohttp.ClientSession() as s:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.1-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 300,
                "response_format": {"type": "json_object"}
            }
            async with s.post("https://api.groq.com/openai/v1/chat/completions", 
                            headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    content = re.sub(r'```json\s*|\s*```', '', content).strip()
                    result = json.loads(content)
                    
                    # Валидация
                    selected_idx = int(result.get("selected", 1)) - 1
                    if 0 <= selected_idx < len(news_list):
                        selected_news = news_list[selected_idx]
                        selected_news.update({
                            "summary": result.get("summary", ""),
                            "hashtags": result.get("hashtags", "")
                        })
                        log.info(f"✅ AI: Groq выбрал #{selected_idx+1}")
                        return selected_news
                elif r.status == 429:
                    log.warning("⚠️ Groq rate limit")
    except Exception as e:
        log.warning(f"⚠️ Groq failed: {e}")
    
    # 2️⃣ OPENROUTER
    try:
        async with aiohttp.ClientSession() as s:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/news-bot",
                "X-Title": "News Bot"
            }
            payload = {
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 400
            }
            async with s.post("https://openrouter.ai/api/v1/chat/completions",
                            headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=25)) as r:
                if r.status == 200:
                    data = await r.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    
                    # Агрессивная очистка
                    json_start = content.find('{')
                    json_end = content.rfind('}')
                    if json_start != -1 and json_end != -1:
                        content = content[json_start:json_end+1]
                    content = re.sub(r'```(?:json)?\s*|\s*```', '', content).strip()
                    
                    result = json.loads(content)
                    selected_idx = int(result.get("selected", 1)) - 1
                    
                    if 0 <= selected_idx < len(news_list):
                        selected_news = news_list[selected_idx]
                        selected_news.update({
                            "summary": result.get("summary", ""),
                            "hashtags": result.get("hashtags", "")
                        })
                        log.info(f"✅ AI: OpenRouter выбрал #{selected_idx+1}")
                        return selected_news
                else:
                    log.error(f"OpenRouter HTTP {r.status}")
    except Exception as e:
        log.warning(f"⚠️ OpenRouter failed: {e}")
    
    log.error("❌ Все AI недоступны")
    return None

# ================== СБОР НОВОСТЕЙ ==================
async def collect_fresh_news(limit=30):
    """Собирает новости из RSS без AI-обработки"""
    candidates = []
    sources = list(RSS_SOURCES.items())
    random.shuffle(sources)
    
    for source_name, rss_url in sources:
        if len(candidates) >= limit:
            break
        
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                if len(candidates) >= limit:
                    break
                
                title = entry.title.strip()
                url = entry.link
                desc = entry.get("summary", "") or entry.get("description", "") or ""
                
                # Фильтры
                if len(title) < 20:
                    continue
                if is_duplicate(title, url):
                    continue
                if any(boring in title.lower() for boring in BORING_KEYWORDS):
                    continue
                if not any(k in title.lower() for k in KEYWORDS):
                    continue
                
                candidates.append({
                    "title": title,
                    "url": url,
                    "desc": desc,
                    "source": source_name,
                    "entry": entry
                })
        except Exception as e:
            log.error(f"RSS error {source_name}: {e}")
    
    return candidates

# ================== МЕДИА ==================
async def get_og_image(url: str):
    for attempt in range(2):
        try:
            connector = aiohttp.TCPConnector(ssl=False, force_close=True)
            async with aiohttp.ClientSession(connector=connector) as s:
                async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}, 
                               timeout=aiohttp.ClientTimeout(total=5)) as r:
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
        except:
            pass
    return None

async def download_image(url: str):
    try:
        connector = aiohttp.TCPConnector(ssl=False, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None

# ================== ПОСТИНГ ==================
async def post_selected_news(news):
    """Постит выбранную AI новость"""
    title = news["title"]
    url = news["url"]
    summary = news.get("summary", "")
    hashtags = news.get("hashtags", "")
    source = news["source"]
    
    caption = f"**{title}**\n\n{summary}\n\n_{source}_\n\n{hashtags}"
    
    # Получаем картинку
    img_url = await get_og_image(url)
    if not img_url:
        img_url = random.choice(FALLBACK_IMAGES)
    
    img_data = await download_image(img_url)
    
    # Отправка с retry
    for attempt in range(3):
        try:
            if img_data:
                file = BufferedInputFile(img_data, filename="news.jpg")
                await bot.send_photo(CHANNEL_ID, file, caption=caption, parse_mode=ParseMode.MARKDOWN)
            else:
                await bot.send_message(CHANNEL_ID, caption, parse_mode=ParseMode.MARKDOWN)
            
            save_posted(title, url)
            increment_stat()
            log.info(f"✅ Пост: {title[:50]}")
            return True
        except Exception as e:
            if attempt == 2:
                log.error(f"Post error: {e}")
                return False
            await asyncio.sleep(2)
    
    return False

# ================== ОСНОВНОЙ ЦИКЛ ==================
async def check_news():
    """1 запрос к AI → 1 пост"""
    stats = get_today_stats()
    if stats["normal"] >= 25:
        log.info("📊 Лимит 25 постов достигнут")
        return
    
    # Шаг 1: Собрать 30 свежих новостей
    log.info("📥 Собираю новости...")
    candidates = await collect_fresh_news(30)
    
    if not candidates:
        log.info("⚠️ Нет новых новостей")
        return
    
    log.info(f"📊 Найдено {len(candidates)} кандидатов")
    
    # Шаг 2: AI выбирает ТОП-1
    selected = await ai_select_and_summarize(candidates)
    
    if not selected:
        log.warning("⚠️ AI не смог выбрать новость")
        return
    
    # Шаг 3: Постим
    await post_selected_news(selected)

async def news_loop():
    """Постинг каждые 20-70 мин"""
    log.info("⏰ Первый пост через 3 мин...")
    await asyncio.sleep(3 * 60)
    
    while True:
        await check_news()
        next_interval = random.randint(20, 70)
        log.info(f"⏰ Следующий пост через {next_interval} мин")
        await asyncio.sleep(next_interval * 60)

# ================== YOUTUBE ==================
async def parse_youtube_trending():
    """Парсит топ-20 из YouTube Trending"""
    url = "https://www.youtube.com/feed/trending?gl=RU&hl=ru"
    
    try:
        log.info("🎬 Парсинг YouTube Trending...")
        
        async with aiohttp.ClientSession() as s:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    log.error(f"❌ YouTube HTTP {r.status}")
                    return []
                
                html = await r.text()
                
                # Ищем ytInitialData
                match = re.search(r'var ytInitialData = ({.+?});', html, re.DOTALL)
                if not match:
                    log.error("❌ Не найден ytInitialData в HTML")
                    # Попробуем альтернативный способ
                    match = re.search(r'window\["ytInitialData"\] = ({.+?});', html, re.DOTALL)
                    if not match:
                        log.error("❌ Альтернативный поиск также провалился")
                        return []
                
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError as e:
                    log.error(f"❌ JSON parse error: {e}")
                    return []
                
                videos = []
                
                try:
                    # Навигация по структуре данных
                    tabs = data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]
                    
                    for tab in tabs:
                        if "tabRenderer" not in tab:
                            continue
                        
                        content = tab["tabRenderer"].get("content", {})
                        
                        # Ищем richGridRenderer или sectionListRenderer
                        if "richGridRenderer" in content:
                            items = content["richGridRenderer"].get("contents", [])
                        elif "sectionListRenderer" in content:
                            sections = content["sectionListRenderer"].get("contents", [])
                            items = []
                            for section in sections:
                                if "itemSectionRenderer" in section:
                                    items.extend(section["itemSectionRenderer"].get("contents", []))
                        else:
                            continue
                        
                        for item in items:
                            # Пропускаем рекламу и продолжения
                            if "richItemRenderer" not in item:
                                continue
                            
                            try:
                                video_data = item["richItemRenderer"]["content"]["videoRenderer"]
                                
                                video_id = video_data.get("videoId")
                                if not video_id:
                                    continue
                                
                                # Заголовок
                                title_data = video_data.get("title", {})
                                if "runs" in title_data:
                                    title = title_data["runs"][0].get("text", "")
                                else:
                                    title = title_data.get("simpleText", "")
                                
                                if not title:
                                    continue
                                
                                # Просмотры
                                views_data = video_data.get("viewCountText", {})
                                views = views_data.get("simpleText", "0")
                                
                                # Длительность
                                length_data = video_data.get("lengthText", {})
                                length = length_data.get("simpleText", "")
                                
                                videos.append({
                                    "id": video_id,
                                    "title": title,
                                    "views": views,
                                    "length": length,
                                    "url": f"https://www.youtube.com/watch?v={video_id}"
                                })
                                
                            except KeyError as e:
                                log.debug(f"Пропускаю item: {e}")
                                continue
                
                except KeyError as e:
                    log.error(f"❌ Ошибка структуры данных: {e}")
                    return []
                
                log.info(f"✅ Найдено {len(videos)} видео")
                return videos[:20]
                
    except asyncio.TimeoutError:
        log.error("❌ YouTube timeout")
        return []
    except Exception as e:
        log.error(f"❌ YouTube error: {type(e).__name__}: {e}")
        return []


def is_short_video(length_str: str):
    """Определяет, является ли видео Shorts (<60 сек)"""
    if not length_str:
        return False
    
    try:
        parts = length_str.split(":")
        
        if len(parts) == 1:
            # Формат "45" (секунды)
            return int(parts[0]) < 60
        elif len(parts) == 2:
            # Формат "0:45" (минуты:секунды)
            m, s = map(int, parts)
            return m == 0 and s < 60
        elif len(parts) == 3:
            # Формат "0:00:45" (часы:минуты:секунды)
            h, m, s = map(int, parts)
            return h == 0 and m == 0 and s < 60
    except ValueError:
        pass
    
    return False


async def post_youtube_tops():
    """Постит топ полное видео + топ Shorts"""
    log.info("🎬 Запуск задачи YouTube топов...")
    
    # Парсим trending
    videos = await parse_youtube_trending()
    
    if not videos:
        log.warning("⚠️ Не удалось получить видео из YouTube")
        return
    
    # Разделяем на полные видео и Shorts
    full_videos = [v for v in videos if not is_short_video(v.get("length", ""))]
    short_videos = [v for v in videos if is_short_video(v.get("length", ""))]
    
    log.info(f"📊 Полных видео: {len(full_videos)}, Shorts: {len(short_videos)}")
    
    # Ищем неопубликованные
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
    
    # Постим полное видео
    if top_full:
        try:
            log.info(f"📤 Отправляю топ видео: {top_full['title'][:50]}...")
            
            caption = (
                f"🔥 **Самое популярное видео сегодня в РФ**\n\n"
                f"{top_full['title']}\n\n"
                f"👀 {top_full['views']}\n\n"
                f"{top_full['url']}"
            )
            
            await bot.send_message(
                CHANNEL_ID, 
                caption, 
                parse_mode=ParseMode.MARKDOWN, 
                disable_web_page_preview=False
            )
            
            save_youtube_posted(top_full['id'], 'full')
            log.info("✅ YouTube топ видео опубликовано")
            
        except Exception as e:
            log.error(f"❌ Ошибка отправки топ видео: {e}")
    else:
        log.info("ℹ️ Топ видео уже опубликовано сегодня")
    
    # Пауза между постами
    await asyncio.sleep(5)
    
    # Постим Shorts
    if top_short:
        try:
            log.info(f"📤 Отправляю топ Shorts: {top_short['title'][:50]}...")
            
            caption = (
                f"⚡ **Самый популярный Shorts сегодня**\n\n"
                f"{top_short['title']}\n\n"
                f"👀 {top_short['views']}\n\n"
                f"{top_short['url']}"
            )
            
            await bot.send_message(
                CHANNEL_ID, 
                caption, 
                parse_mode=ParseMode.MARKDOWN, 
                disable_web_page_preview=False
            )
            
            save_youtube_posted(top_short['id'], 'shorts')
            log.info("✅ YouTube Shorts опубликован")
            
        except Exception as e:
            log.error(f"❌ Ошибка отправки Shorts: {e}")
    else:
        log.info("ℹ️ Топ Shorts уже опубликован сегодня")
    
    log.info("🎬 Задача YouTube топов завершена")
async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(post_youtube_tops, "cron", hour=19, minute=0)
    scheduler.start()
    
    log.info("🤖 БОТ ЗАПУЩЕН")
    log.info("📰 Посты каждые 20-70 мин (макс 25/день)")
    log.info("🎬 YouTube: 19:00 (топ видео + shorts)")
    log.info("🤖 AI: 1 запрос = 1 пост (выбор из 30 новостей)")
    log.info(f"📡 Источников: {len(RSS_SOURCES)}")
    
    await news_loop()

if __name__ == "__main__":
    asyncio.run(main())