import asyncio
import feedparser
import hashlib
import html
import sqlite3
from datetime import datetime
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
import aiohttp
from bs4 import BeautifulSoup

# === НАСТРОЙКИ ===
BOT_TOKEN = '7885944156:AAHrh2o1UPzJ67jviCULfOmP_BGPExdh6l8'
GROQ_API_KEY = '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'
CHANNEL_ID = '@askodasjiodasjdsa'

MEME_IMAGES = [
    "https://i.kym-cdn.com/photos/images/newsfeed/002/739/045/1ee.jpg",
    "https://i.kym-cdn.com/photos/images/newsfeed/002/672/027/52e.jpg",
    "https://i.kym-cdn.com/photos/images/newsfeed/002/702/956/520.jpg",
]

RSS_FEEDS = [
    'https://www.artificialintelligence-news.com/feed/',
    'https://www.theverge.com/rss/ai-artificial-intelligence/index.xml',
    'https://techcrunch.com/category/artificial-intelligence/feed/',
    'https://venturebeat.com/category/ai/feed/',
    'https://www.wired.com/feed/category/ai/latest/rss',
    'https://news.mit.edu/rss/topic/artificial-intelligence',
    'https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml',
    'https://feeds.feedburner.com/TechRadarAI',
]

AI_KEYWORDS = [
    'искусственный интеллект', 'ии', 'ai', 'artificial intelligence',
    'нейросеть', 'machine learning', 'deep learning', 'нейронная сеть',
    'алгоритм', 'автоматизация', 'робототехника', 'chatgpt', 'grok', 'groq'
]

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
conn = sqlite3.connect("news.db")
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    url_hash TEXT UNIQUE,
    title TEXT,
    url TEXT,
    published_at TEXT,
    summary TEXT,
    status TEXT,
    tg_msg_id INTEGER,
    times_considered INTEGER DEFAULT 0,
    keyword_score INTEGER DEFAULT 0
)
''')
conn.commit()

def is_ai_related(text):
    return any(word in text.lower() for word in AI_KEYWORDS)

def calculate_keyword_score(text):
    return sum(1 for word in AI_KEYWORDS if word in text.lower())

async def fetch_rss():
    new_articles = []
    for rss_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                url = entry.link
                title = entry.title
                published = entry.get("published", datetime.utcnow().isoformat())
                url_hash = hashlib.md5((url + title).encode()).hexdigest()

                c.execute("SELECT 1 FROM articles WHERE url_hash = ?", (url_hash,))
                if c.fetchone():
                    continue

                if is_ai_related(title):
                    score = calculate_keyword_score(title)
                    c.execute(
                        "INSERT INTO articles (url_hash, title, url, published_at, status, keyword_score) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (url_hash, title, url, published, "raw", score)
                    )
                    new_articles.append((title, url, score))
        except Exception as e:
            print(f"[RSS ERROR] Не удалось обработать {rss_url}: {e}")
    conn.commit()
    return new_articles

async def get_clean_articles():
    c.execute("SELECT id, title, url, keyword_score FROM articles WHERE status = 'raw' AND times_considered < 3")
    result = c.fetchall()
    for art_id, _, _, _ in result:
        c.execute("UPDATE articles SET times_considered = times_considered + 1 WHERE id = ?", (art_id,))
    conn.commit()
    return result

async def compare_and_update_articles(new_articles):
    c.execute("SELECT id, title, url, keyword_score FROM articles WHERE status = 'raw'")
    old_articles = c.fetchall()
    if not new_articles or not old_articles:
        return old_articles
    new_avg = sum(score for _, _, score in new_articles) / len(new_articles)
    old_avg = sum(score for _, _, _, score in old_articles) / len(old_articles)
    if new_avg > old_avg:
        for art_id, _, _, _ in old_articles:
            c.execute("UPDATE articles SET status = 'old' WHERE id = ?", (art_id,))
        conn.commit()
        c.execute("SELECT id, title, url, keyword_score FROM articles WHERE status = 'raw'")
        return c.fetchall()
    else:
        for title, url, _ in new_articles:
            url_hash = hashlib.md5((url + title).encode()).hexdigest()
            c.execute("UPDATE articles SET status = 'broke' WHERE url_hash = ?", (url_hash,))
        conn.commit()
        return old_articles

async def select_best_article(articles):
    if not articles:
        return None
    return max(articles, key=lambda x: x[3])

# === ЗАМЕНА ФУНКЦИИ smart_get_meme ===
async def smart_get_meme(title, url):
    image_url = await get_meme_from_kym(title)
    if image_url and image_url.lower().endswith((".jpg", ".jpeg", ".png")):
        return image_url
    image_url = await get_image(url)
    if image_url and image_url.lower().endswith((".jpg", ".jpeg", ".png")):
        return image_url
    print(f"[WARN] Нет подходящей картинки для '{title}'")
    return None


# === ЗАМЕНА ФУНКЦИИ post_news ===
from aiogram.types import BufferedInputFile
from aiogram.enums import ParseMode
import html

async def post_news(summary, art_id, title, url):
    if not summary:
        print(f"[ERROR] No summary for article {art_id}")
        return

    image_url = await smart_get_meme(title, url)
    if not image_url:
        print(f"[ERROR] Не удалось найти подходящую картинку для {title}")
        return  # ❗️Ничего не постим, если нет картинки

    print(f"[DEBUG] Итоговый URL картинки: {image_url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://knowyourmeme.com/"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, headers=headers) as img_resp:
                if img_resp.status != 200:
                    print(f"[ERROR] Не удалось загрузить картинку {image_url}: {img_resp.status}")
                    return
                photo_data = await img_resp.read()
                file = BufferedInputFile(photo_data, filename="meme.jpg")
                formatted_summary = f"<b>{html.escape(title)}</b>\n{summary}"
                msg = await bot.send_photo(CHANNEL_ID, file, caption=formatted_summary, parse_mode=ParseMode.HTML)
                c.execute("UPDATE articles SET summary=?, status='posted', tg_msg_id=? WHERE id=?",
                          (formatted_summary, msg.message_id, art_id))
                conn.commit()
    except Exception as e:
        print(f"[Post ERROR] {e}")


# === ЗАМЕНА get_image (если хочешь просто оставить как есть, можешь не трогать)
async def get_image(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return None
                html_text = await resp.text()
                soup = BeautifulSoup(html_text, "html.parser")
                og_image = soup.find("meta", property="og:image")
                return og_image["content"] if og_image and og_image.get("content") else None
    except Exception as e:
        print(f"[Image ERROR] {e}")
        return None


# === ЗАМЕНА get_meme_from_kym — с нужными headers
async def get_meme_from_kym(query: str) -> str | None:
    search_url = f"https://knowyourmeme.com/search?q={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(search_url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    return None
                html_text = await resp.text()
                soup = BeautifulSoup(html_text, "html.parser")
                entries = soup.select(".entry-grid-body .photo")
                if not entries:
                    return None

                meme_links = ["https://knowyourmeme.com" + e.get("href") for e in entries if e.get("href")]
                random.shuffle(meme_links)

                for meme_url in meme_links:
                    async with session.get(meme_url, headers=headers, timeout=10) as meme_resp:
                        if meme_resp.status != 200:
                            continue
                        meme_html = await meme_resp.text()
                        meme_soup = BeautifulSoup(meme_html, "html.parser")
                        image_tags = meme_soup.select("img")
                        urls = [
                            img["src"] for img in image_tags
                            if img.get("src") and "kym-cdn" in img["src"]
                            and img["src"].lower().endswith((".jpg", ".jpeg", ".png"))
                        ]
                        if urls:
                            return random.choice(urls)
        except Exception as e:
            print(f"[KYM ERROR] {e}")
            return None

# Модифицированная функция ask_groq для более шутливого стиля
async def ask_groq(title, url):
    prompt = (
        f"Ты — редактор новостей про ИИ для дружеского телеграм-канала.\n"
        f"Пиши ответ строго на русском языке.\n"
        f"Твоя задача — сделать короткий пост в лёгком, шутливом стиле (как мем, 2-4 предложения).\n"
        f"В начале поста будет картинка (мем), так что пиши текст живо.\n"
        f"Пример стиля: 'Жара бьёт по яйцам...' — с юмором и без сухости.\n"
        f"Заголовок выдели жирным с помощью <b>…</b>. Ссылку не добавляй.\n\n"
        f"Новость: {title}\n{url}"
    )
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "deepseek/deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 500
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers=headers) as resp:
                if resp.status != 200:
                    print(f"[Groq ERROR] {resp.status}: {await resp.text()}")
                    return None
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except aiohttp.ClientConnectionError as e:
            print(f"[Groq ERROR] Нет соединения: {e}")
            return None

async def summarize_and_post():
    print(f"[{datetime.now().isoformat()}] ⏳ Обработка...")
    new_articles = await fetch_rss()
    articles = await compare_and_update_articles(new_articles)
    if not articles:
        print("❗ Нет новостей.")
        return
    best_article = await select_best_article(articles)
    if not best_article:
        print("❗ Не выбрана новость.")
        return
    art_id, title, url, _ = best_article
    summary = await ask_groq(title, url)
    await post_news(summary, art_id, title, url)
    print(f"[{datetime.now().isoformat()}] ✅ Готово.")

async def main():
    await summarize_and_post()
    scheduler = AsyncIOScheduler()
    interval = random.randint(1800, 9000)  # 0.5–2.5 часа
    scheduler.add_job(summarize_and_post, "interval", seconds=interval)
    scheduler.start()
    print(f"✅ Бот запущен. Следующая проверка через {interval/3600:.1f} ч...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
