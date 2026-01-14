import asyncio
import aiohttp
import sqlite3
from datetime import datetime, timedelta
import logging
import re
import os
import sys
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile

# ================== CONFIG ==================
BOT_TOKEN = '7885944156:AAHrh2o1UPzJ67jviCULfOmP_BGPExdh6l8'
YOUTUBE_API_KEY = 'AIzaSyBVSJaPPKL_wzfc9iU38YEM8MxjUt3lZZk'
CHANNEL_ID = '@bulmyash'

# Определяем папку для скачивания (Windows/Linux)
if sys.platform == "win32":
    TEMP_DIR = "C:/temp/shorts"
else:
    TEMP_DIR = "/tmp/shorts"

# Создаём папку если нет
os.makedirs(TEMP_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("yt_news_shorts")
bot = Bot(BOT_TOKEN)

# ================== БАЗА ДАННЫХ ==================
DB_FILE = "news.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS youtube_posted (
    video_id TEXT UNIQUE, 
    posted_at TEXT, 
    type TEXT
)''')
conn.commit()

def is_youtube_posted_today(video_id):
    today = datetime.now().date().isoformat()
    c.execute("SELECT 1 FROM youtube_posted WHERE video_id = ? AND DATE(posted_at) = ?", (video_id, today))
    return c.fetchone() is not None

def save_youtube_posted(video_id, video_type):
    c.execute("INSERT OR IGNORE INTO youtube_posted (video_id, posted_at, type) VALUES (?, ?, ?)", 
              (video_id, datetime.now().isoformat(), video_type))
    conn.commit()

# ================== УЛУЧШЕННЫЕ ФИЛЬТРЫ РУ КОНТЕНТА ==================
def has_cyrillic(text):
    """Проверяет наличие кириллицы в тексте"""
    return bool(re.search('[а-яА-ЯёЁ]', text))

def has_ukrainian(text):
    """Проверяет наличие украинских букв"""
    ukrainian_letters = ['є', 'і', 'ї', 'ґ', 'Є', 'І', 'Ї', 'Ґ']
    return any(letter in text for letter in ukrainian_letters)

def is_russian_content(title, channel_title, description=""):
    """ЖЁСТКАЯ проверка ТОЛЬКО РУ контента"""
    full_text = f"{title} {channel_title} {description}".lower()
    
    # БЛОК 1: Обязательно должна быть русская кириллица
    if not has_cyrillic(title + channel_title):
        return False
    
    # БЛОК 2: Украинский язык - ЗАПРЕЩЁН
    if has_ukrainian(title + channel_title + description):
        log.debug(f"   ❌ Украинский язык: {title[:40]}")
        return False
    
    # БЛОК 3: Украинские ключевые слова
    ua_keywords = [
        'україн', 'ukrainian', 'kiev', 'kyiv', 'київ', 'зеленськ', 
        'zelensky', 'азов', 'azov', 'всу', 'afu', 'зсу'
    ]
    if any(kw in full_text for kw in ua_keywords):
        log.debug(f"   ❌ Украинский контент: {title[:40]}")
        return False
    
    # БЛОК 4: Исключаем другие алфавиты
    bad_patterns = [
        r'[\u0600-\u06FF]',  # Арабский
        r'[\u0900-\u097F]',  # Хинди
        r'[\u4E00-\u9FFF]',  # Китайский
        r'[\u3040-\u309F]',  # Японский (хирагана)
        r'[\u30A0-\u30FF]',  # Японский (катакана)
        r'[\uAC00-\uD7AF]',  # Корейский
    ]
    
    for pattern in bad_patterns:
        if re.search(pattern, title + channel_title):
            return False
    
    return True

# ================== БЕЛЫЙ СПИСОК РУ НОВОСТНЫХ КАНАЛОВ ==================
RU_NEWS_CHANNELS = [
    # ОСНОВНЫЕ НОВОСТИ
    "РИА Новости", "ТАСС", "Известия", "Интерфакс", 
    "РБК", "Коммерсантъ", "Ведомости", "Фонтанка",
    
    # ТВ КАНАЛЫ
    "Первый канал", "Россия 24", "НТВ", "Мир 24",
    "RT", "ДЕНЬ ТВ", "360°", "Звезда",
    
    # ОФИЦИАЛЬНЫЕ
    "Кремль", "Правительство РФ", "БелТА",
    
    # НЕЗАВИСИМЫЕ
    "Дождь", "Настоящее Время", "Редакция", "Медуза",
    
    # АНАЛИТИКА/БЛОГЕРЫ
    "вДудь", "Навальный LIVE", "Популярная политика",
    "НАРОД ПРОТИВ", "MetaPulsee", "А поговорить",
    "ФЕЙГИН LIVE", "Екатерина Шульман",
    
    # РЕГИОНАЛЬНЫЕ
    "Москва 24", "Санкт-Петербург", "Новости Урала",
]

def is_trusted_news_channel(channel_title):
    """Проверяет что канал в белом списке НОВОСТНЫХ"""
    channel_lower = channel_title.lower()
    return any(trusted.lower() in channel_lower for trusted in RU_NEWS_CHANNELS)

def is_news_content(title, description=""):
    """Проверяет что контент действительно новостной"""
    news_keywords = [
        'новост', 'сегодня', 'срочн', 'путин', 'россия', 'рф',
        'правительств', 'госдум', 'президент', 'политик',
        'война', 'украин', 'санкц', 'экономик', 'указ',
        'заявил', 'объявил', 'сообщил', 'произошл'
    ]
    
    text = f"{title} {description}".lower()
    matches = sum(1 for kw in news_keywords if kw in text)
    
    return matches >= 1  # Минимум 1 новостное слово

# ================== ПАРСИНГ ДЛИТЕЛЬНОСТИ ==================
def parse_duration_to_seconds(iso_duration):
    """Парсит ISO 8601 (PT1M30S) в секунды"""
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, iso_duration)
    
    if not match:
        return 0
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    
    return hours * 3600 + minutes * 60 + seconds

def format_views(views):
    """Форматирует просмотры (1500000 -> 1.5М)"""
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}М"
    elif views >= 1_000:
        return f"{views / 1_000:.1f}К"
    else:
        return str(views)

# ================== ПОИСК НОВОСТНЫХ SHORTS ==================
async def search_news_shorts():
    """Ищет популярные РУССКИЕ новостные Shorts"""
    log.info("🔍 Поиск РУССКИХ новостных Shorts...")
    
    all_shorts = []
    
    # ТОЛЬКО русские поисковые запросы
    news_queries = [
        "новости россии",
        "политика путин",
        "россия сегодня",
        "кремль заявил"
    ]
    
    for query in news_queries[:3]:
        try:
            log.info(f"   Поиск: '{query}'...")
            
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "id,snippet",
                "q": query + " shorts",
                "type": "video",
                "maxResults": 30,
                "order": "viewCount",
                "publishedAfter": (datetime.now() - timedelta(days=2)).isoformat() + "Z",
                "regionCode": "RU",
                "relevanceLanguage": "ru",
                "videoCategoryId": "25",  # News & Politics
                "key": YOUTUBE_API_KEY
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        log.warning(f"   ⚠️ YouTube API {response.status}: {error_text[:100]}")
                        continue
                    
                    data = await response.json()
                    video_ids = [item["id"]["videoId"] for item in data.get("items", []) 
                                if item["id"].get("kind") == "youtube#video"]
                    
                    if not video_ids:
                        log.info(f"   Ничего не найдено")
                        continue
                    
                    log.info(f"   Найдено {len(video_ids)} кандидатов, фильтрую...")
                    
                    # Получаем детали видео
                    details_url = "https://www.googleapis.com/youtube/v3/videos"
                    details_params = {
                        "part": "snippet,statistics,contentDetails",
                        "id": ",".join(video_ids[:50]),
                        "key": YOUTUBE_API_KEY
                    }
                    
                    async with session.get(details_url, params=details_params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            continue
                        
                        details_data = await resp.json()
                        
                        for item in details_data.get("items", []):
                            try:
                                duration = item["contentDetails"]["duration"]
                                total_sec = parse_duration_to_seconds(duration)
                                
                                # ФИЛЬТР 1: 10-60 секунд
                                if not (10 <= total_sec <= 60):
                                    continue
                                
                                snippet = item["snippet"]
                                stats = item["statistics"]
                                
                                title = snippet.get("title", "")
                                channel_title = snippet.get("channelTitle", "")
                                description = snippet.get("description", "")
                                
                                # ФИЛЬТР 2: ТОЛЬКО РУССКИЙ (не украинский!)
                                if not is_russian_content(title, channel_title, description):
                                    continue
                                
                                # ФИЛЬТР 3: ТОЛЬКО новостные каналы
                                if not is_trusted_news_channel(channel_title):
                                    log.debug(f"   ⚠️ Не новостной канал: {channel_title}")
                                    continue
                                
                                # ФИЛЬТР 4: НОВОСТНОЙ контент
                                if not is_news_content(title, description):
                                    log.debug(f"   ⚠️ Не новостной контент: {title[:40]}")
                                    continue
                                
                                # ФИЛЬТР 5: Минимум просмотров
                                views = int(stats.get("viewCount", 0))
                                if views < 5000:
                                    continue
                                
                                all_shorts.append({
                                    "id": item["id"],
                                    "title": title,
                                    "channel": channel_title,
                                    "channel_id": snippet["channelId"],
                                    "views": views,
                                    "likes": int(stats.get("likeCount", 0)),
                                    "duration_sec": total_sec,
                                    "published": snippet.get("publishedAt", ""),
                                    "url": f"https://youtube.com/shorts/{item['id']}"
                                })
                                
                            except Exception as e:
                                log.debug(f"   Пропуск видео: {e}")
                                continue
            
            await asyncio.sleep(0.3)
            
        except Exception as e:
            log.warning(f"   Ошибка поиска '{query}': {e}")
            continue
    
    # Убираем дубликаты по video_id
    seen_ids = set()
    unique_shorts = []
    for short in all_shorts:
        if short["id"] not in seen_ids:
            seen_ids.add(short["id"])
            unique_shorts.append(short)
    
    # Сортируем по просмотрам
    unique_shorts.sort(key=lambda x: x["views"], reverse=True)
    
    log.info(f"✅ Найдено {len(unique_shorts)} РУССКИХ новостных Shorts")
    return unique_shorts

# ================== СКАЧИВАНИЕ ЧЕРЕЗ YT-DLP ==================
async def download_shorts_video(video_id):
    """Скачивает Shorts через yt-dlp с диагностикой"""
    output_file = os.path.join(TEMP_DIR, f"shorts_{video_id}.mp4")
    
    try:
        log.info("   📥 Скачиваю через yt-dlp...")
        
        # Используем обычный URL вместо /shorts/ (работает стабильнее)
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # ВАЖНО: Используем Python модуль вместо прямого вызова
        # Работает на Windows даже если yt-dlp не в PATH
        cmd = [
            sys.executable,  # Путь к текущему Python
            "-m", "yt_dlp",  # Запуск как модуль
            "-f", "bv*+ba/b",  # Универсальный формат для Shorts (видео+аудио или лучший)
            "-o", output_file,
            "--no-playlist",
            "--merge-output-format", "mp4",  # Конвертируем в MP4
            "--extractor-args", "youtube:player_client=android",  # Используем Android клиент (обходит ограничения)
            "--no-check-certificate",  # Игнорируем SSL ошибки
            "--socket-timeout", "30",  # Таймаут соединения
            url
        ]
        
        log.info(f"   🔧 Скачиваю...")
        
        # Запускаем скачивание
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
        
        if process.returncode == 0 and os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / 1024 / 1024
            log.info(f"   ✅ Скачано {file_size:.1f} MB")
            return output_file
        else:
            error_msg = stderr.decode()[:300] if stderr else stdout.decode()[:300]
            log.error(f"   ❌ yt-dlp ошибка: {error_msg}")
            
            if os.path.exists(output_file):
                os.remove(output_file)
            
            return None
            
    except asyncio.TimeoutError:
        log.error("   ❌ Таймаут скачивания (>90 сек)")
        if os.path.exists(output_file):
            os.remove(output_file)
        return None
    except Exception as e:
        log.error(f"   ❌ Ошибка скачивания: {e}")
        if os.path.exists(output_file):
            os.remove(output_file)
        return None

# ================== ПОСТИНГ С АВТОУДАЛЕНИЕМ ==================
async def post_top_news_short(force=False):
    """Постит ТОП новостной Shorts → удаляет файл"""
    log.info("🚀 Запуск: Топ новостной Shorts (ТОЛЬКО РУ)...")
    
    # Ищем Shorts
    shorts = await search_news_shorts()
    
    if not shorts:
        log.warning("⚠️ Русские новостные Shorts не найдены")
        return False
    
    # Пробуем скачать и запостить топ-5
    for i, short_video in enumerate(shorts[:5], 1):
        # Проверяем что не постили сегодня
        if not force and is_youtube_posted_today(short_video["id"]):
            log.info(f"   [{i}/5] Пропуск (уже постили): {short_video['title'][:50]}")
            continue
        
        log.info(f"🎯 [{i}/5] Пробую: {short_video['title'][:60]}...")
        log.info(f"   👀 {format_views(short_video['views'])} | 📺 {short_video['channel']}")
        
        # Скачиваем
        video_file_path = await download_shorts_video(short_video['id'])
        
        if not video_file_path:
            log.warning(f"   ⚠️ Не удалось скачать, пробую следующий...")
            continue
        
        # Отправляем в Telegram
        try:
            caption = (
                f"⚡ **Главный новостной Shorts дня**\n\n"
                f"**{short_video['title']}**\n\n"
                f"📺 {short_video['channel']}\n"
                f"👀 {format_views(short_video['views'])} просмотров | "
                f"❤️ {format_views(short_video['likes'])}"
            )
            
            # Читаем файл
            with open(video_file_path, 'rb') as f:
                video_data = f.read()
            
            video_file = BufferedInputFile(video_data, filename=f"{short_video['id']}.mp4")
            
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
            log.info("✅ Опубликовано!")
            
            # Удаляем файл после отправки
            os.remove(video_file_path)
            log.info(f"🗑️ Файл удалён: {video_file_path}")
            
            return True
            
        except Exception as e:
            log.error(f"❌ Ошибка отправки: {e}")
            
            if os.path.exists(video_file_path):
                os.remove(video_file_path)
                log.info(f"🗑️ Файл удалён после ошибки")
            
            continue
    
    log.warning("⚠️ Не удалось запостить ни один Shorts из топ-5")
    return False

# ================== ОЧИСТКА СТАРЫХ ФАЙЛОВ ==================
def cleanup_old_files():
    """Удаляет старые файлы из папки temp (>1 день)"""
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

# ================== ТЕСТ ==================
async def main():
    """Тестовый запуск"""
    log.info("=" * 60)
    log.info("🧪 ТЕСТ: Русские новостные Shorts")
    log.info(f"📁 Папка скачивания: {TEMP_DIR}")
    log.info("=" * 60)
    
    # Очищаем старые файлы
    cleanup_old_files()
    
    shorts = await search_news_shorts()
    
    if shorts:
        log.info(f"\n⚡ ТОП-10 РУССКИХ НОВОСТНЫХ SHORTS:")
        for i, s in enumerate(shorts[:10], 1):
            posted = "✅" if is_youtube_posted_today(s["id"]) else "🆕"
            log.info(f"{i}. {posted} {s['title'][:70]}")
            log.info(f"   👀 {format_views(s['views'])} | 📺 {s['channel']}")
            log.info(f"   ⏱️ {s['duration_sec']}с | 🔗 {s['url']}")
            log.info("")
        
        print("=" * 60)
        print("Опции:")
        print("1. Скачать и отправить топ Shorts (только новый)")
        print("2. Скачать и отправить топ Shorts (force)")
        print("3. Очистить базу за сегодня")
        print("4. Очистить папку temp")
        print("5. Проверить установку yt-dlp")
        print("0. Выход")
        choice = input("Выбери: ").strip()
        
        if choice == '1':
            await post_top_news_short(force=False)
        elif choice == '2':
            await post_top_news_short(force=True)
        elif choice == '3':
            today = datetime.now().date().isoformat()
            c.execute("DELETE FROM youtube_posted WHERE DATE(posted_at) = ?", (today,))
            conn.commit()
            log.info(f"✅ Очищена база за {today}")
        elif choice == '4':
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
            log.info(f"✅ Папка {TEMP_DIR} очищена")
        elif choice == '5':
            # Проверка yt-dlp через Python модуль
            try:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "yt_dlp", "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    print(f"✅ yt-dlp установлен: {stdout.decode().strip()}")
                    print(f"✅ Python путь: {sys.executable}")
                else:
                    print(f"❌ Ошибка: {stderr.decode()}")
            except Exception as e:
                print(f"❌ yt-dlp НЕ НАЙДЕН: {e}")
                print(f"💡 Установи: {sys.executable} -m pip install yt-dlp")
        else:
            log.info("👋 Выход")
    else:
        log.warning("⚠️ Не найдено ни одного русского новостного Shorts")
    
    await bot.session.close()
    conn.close()

if __name__ == "__main__":
    asyncio.run(main())