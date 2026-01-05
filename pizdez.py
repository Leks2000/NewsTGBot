import asyncio
import aiohttp
import sqlite3
from datetime import datetime
import logging
from aiogram import Bot
from aiogram.enums import ParseMode

# ================== CONFIG ==================
BOT_TOKEN = '7885944156:AAHrh2o1UPzJ67jviCULfOmP_BGPExdh6l8'
YOUTUBE_API_KEY = 'AIzaSyBVSJaPPKL_wzfc9iU38YEM8MxjUt3lZZk'
CHANNEL_ID = '@bulmyash'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("youtube_api")
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

# ================== НОВОСТНЫЕ РУССКОЯЗЫЧНЫЕ КАНАЛЫ ==================
RUSSIAN_CHANNELS = [
    # Новости и политика (ПРИОРИТЕТ)
    "UCMCgOm8GZkHp8zJ6l7_hIuA",  # вДудь
    "UCHIJ5zaY0WzX3N9LZYjUwBg",  # Мир 24
    "UCjN1IYtqJ-u1KLPa-UtlzOA",  # RT Russian
    "UCuqVG3sNARAMZY5ddJSRO2A",  # ДЕНЬ ТВ
    "UC_wRgdKWVcz1dwnBqfXK_-g",  # Кремль
    "UCMkIm7hI9oOPb3CUIOyfnhQ",  # varlamov (урбанистика)
    "UCrDVws_483jJq4xYbgYudKw",  # А поговорить?
    "UCh6SzS3eqGw-IMU9-rf6RJw",  # Редакция
    "UCknKb2QJL0LLm5MkQAhBlCQ",  # Popular Politics
    "UCQwJI3H6_WxAdKN8tGmb-Vw",  # Навальный LIVE
    
    # Экономика и аналитика
    "UCU1eNBVq9lwKb76qJPf3ksw",  # Популярная экономика
    "UCEU6OjJUdT6gkRJTMCa8C5w",  # Экономика просто
    
    # Международные новости на русском
    "UC101o-vQ2iOj5ytnlSloweredWY7g",  # НАРОД ПРОТИВ
]

# ================== YOUTUBE API ==================
async def get_trending_videos():
    """Получает топ 50 популярных видео в РФ"""
    log.info("🎬 Запрос к YouTube Data API v3 (регион: RU)...")
    
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,contentDetails,statistics",
        "chart": "mostPopular",
        "regionCode": "RU",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status != 200:
                    error_text = await response.text()
                    log.error(f"❌ YouTube API HTTP {response.status}: {error_text[:200]}")
                    return []
                
                data = await response.json()
                
                if "error" in data:
                    log.error(f"❌ YouTube API error: {data['error']['message']}")
                    return []
                
                items = data.get("items", [])
                log.info(f"✅ Получено {len(items)} видео из trending")
                
                videos = []
                for item in items:
                    try:
                        video_id = item["id"]
                        snippet = item["snippet"]
                        stats = item["statistics"]
                        content = item["contentDetails"]
                        
                        # Фильтруем только русскоязычные видео
                        channel_id = snippet["channelId"]
                        default_lang = snippet.get("defaultAudioLanguage", "")
                        
                        # Пропускаем нерусский контент
                        if default_lang and default_lang not in ["ru", "ru-RU"]:
                            continue
                        
                        duration = content["duration"]
                        is_short = parse_duration(duration)
                        
                        videos.append({
                            "id": video_id,
                            "title": snippet["title"],
                            "channel": snippet["channelTitle"],
                            "channel_id": channel_id,
                            "views": int(stats.get("viewCount", 0)),
                            "likes": int(stats.get("likeCount", 0)),
                            "duration": duration,
                            "is_short": is_short,
                            "url": f"https://www.youtube.com/watch?v={video_id}"
                        })
                    except Exception as e:
                        continue
                
                log.info(f"✅ Отфильтровано {len(videos)} русскоязычных видео")
                return videos
                
    except Exception as e:
        log.error(f"❌ API request error: {e}")
        return []


async def search_popular_shorts():
    """Ищет популярные НАСТОЯЩИЕ Shorts на русских каналах"""
    log.info("🔍 Ищу популярные Shorts на русских каналах...")
    
    all_shorts = []
    
    for channel_id in RUSSIAN_CHANNELS[:10]:
        try:
            # Ищем ТОЛЬКО Shorts (videoDuration=short)
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "id",
                "channelId": channel_id,
                "maxResults": 10,
                "order": "viewCount",
                "publishedAfter": (datetime.now() - timedelta(days=3)).isoformat() + "Z",  # За 3 дня
                "type": "video",
                "videoDuration": "short",  # ТОЛЬКО короткие (<4 мин)
                "key": YOUTUBE_API_KEY
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        continue
                    
                    data = await response.json()
                    video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
                    
                    if not video_ids:
                        continue
                    
                    # Получаем детали
                    details_url = "https://www.googleapis.com/youtube/v3/videos"
                    details_params = {
                        "part": "snippet,statistics,contentDetails",
                        "id": ",".join(video_ids),
                        "key": YOUTUBE_API_KEY
                    }
                    
                    async with session.get(details_url, params=details_params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status != 200:
                            continue
                        
                        details_data = await resp.json()
                        
                        for item in details_data.get("items", []):
                            duration = item["contentDetails"]["duration"]
                            total_sec = parse_duration_to_seconds(duration)
                            
                            # СТРОГИЙ ФИЛЬТР: только 10-60 секунд
                            if 10 <= total_sec <= 60:
                                all_shorts.append({
                                    "id": item["id"],
                                    "title": item["snippet"]["title"],
                                    "channel": item["snippet"]["channelTitle"],
                                    "channel_id": item["snippet"]["channelId"],
                                    "views": int(item["statistics"].get("viewCount", 0)),
                                    "likes": int(item["statistics"].get("likeCount", 0)),
                                    "duration": duration,
                                    "is_short": True,
                                    "url": f"https://youtube.com/shorts/{item['id']}"  # Shorts URL!
                                })
            
            await asyncio.sleep(0.1)
            
        except Exception as e:
            log.debug(f"Ошибка канала {channel_id}: {e}")
            continue
    
    log.info(f"✅ Найдено {len(all_shorts)} настоящих Shorts")
    return all_shorts


def parse_duration_to_seconds(iso_duration):
    """Парсит ISO 8601 в секунды"""
    import re
    
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, iso_duration)
    
    if not match:
        return 0
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    
    return hours * 3600 + minutes * 60 + seconds


def parse_duration(iso_duration):
    """Парсит ISO 8601 и определяет Shorts (строго 5-59 сек)"""
    import re
    
    pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
    match = re.match(pattern, iso_duration)
    
    if not match:
        return False
    
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    
    total_seconds = hours * 3600 + minutes * 60 + seconds
    
    # Shorts - это видео от 5 до 59 секунд (не реклама 0-5 сек)
    return 5 <= total_seconds <= 59


def format_views(views):
    """Форматирует просмотры"""
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}М"
    elif views >= 1_000:
        return f"{views / 1_000:.1f}К"
    else:
        return str(views)


async def download_youtube_video(video_id):
    """Скачивает YouTube видео через несколько методов"""
    
    # Метод 1: y2mate API (быстрый)
    try:
        log.info("   Пробую y2mate...")
        async with aiohttp.ClientSession() as session:
            # Получаем инфу о видео
            api_url = f"https://www.y2mate.com/mates/analyzeV2/ajax"
            data = {
                "k_query": f"https://www.youtube.com/watch?v={video_id}",
                "k_page": "home",
                "hl": "en",
                "q_auto": 0
            }
            
            async with session.post(api_url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    
                    if result.get("status") == "ok":
                        # Ищем ссылку на скачивание (360p или 480p)
                        links = result.get("links", {}).get("mp4", {})
                        
                        for quality in ["360", "480", "720"]:
                            if quality in links:
                                video_url = links[quality].get("url")
                                if video_url:
                                    # Скачиваем
                                    async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as video_resp:
                                        if video_resp.status == 200:
                                            video_data = await video_resp.read()
                                            log.info(f"   ✅ Скачано через y2mate: {len(video_data) / 1024 / 1024:.1f} MB")
                                            return video_data
    except Exception as e:
        log.debug(f"   y2mate failed: {e}")
    
    # Метод 2: ssyoutube (добавляем ss перед youtube.com)
    try:
        log.info("   Пробую ssyoutube...")
        download_url = f"https://ssyoutube.com/watch?v={video_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    
                    # Ищем прямую ссылку в HTML
                    import re
                    match = re.search(r'"url":"(https://[^"]+\.mp4[^"]*)"', html)
                    if match:
                        video_url = match.group(1).replace("\\u0026", "&")
                        
                        async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as video_resp:
                            if video_resp.status == 200:
                                video_data = await video_resp.read()
                                log.info(f"   ✅ Скачано через ssyoutube: {len(video_data) / 1024 / 1024:.1f} MB")
                                return video_data
    except Exception as e:
        log.debug(f"   ssyoutube failed: {e}")
    
    # Метод 3: Прямой запрос к YouTube (работает для некоторых видео)
    try:
        log.info("   Пробую прямой запрос...")
        async with aiohttp.ClientSession() as session:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*"
            }
            
            async with session.get(video_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    
                    # Ищем streamingData
                    import re
                    match = re.search(r'"streamingData":\s*({.+?})\s*[,}]', html)
                    if match:
                        import json
                        streaming_data = json.loads(match.group(1))
                        
                        # Берём адаптивный формат (видео+аудио)
                        formats = streaming_data.get("formats", [])
                        if formats:
                            video_url = formats[0].get("url")
                            
                            if video_url:
                                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=60)) as video_resp:
                                    if video_resp.status == 200:
                                        video_data = await video_resp.read()
                                        log.info(f"   ✅ Скачано напрямую: {len(video_data) / 1024 / 1024:.1f} MB")
                                        return video_data
    except Exception as e:
        log.debug(f"   Прямой запрос failed: {e}")
    
    log.error("   ❌ Все методы скачивания провалились")
    return None


async def post_youtube_tops(force=False):
    """Постит ОДИН пост: Shorts видео + инфа про full видео в подписи"""
    log.info("🚀 Запуск задачи YouTube топов...")
    
    # Получаем trending full видео
    trending = await get_trending_videos()
    full_videos = [v for v in trending if not v["is_short"]]
    full_videos.sort(key=lambda x: x["views"], reverse=True)
    
    # Получаем НАСТОЯЩИЕ Shorts
    shorts_videos = await search_popular_shorts()
    shorts_videos.sort(key=lambda x: x["views"], reverse=True)
    
    log.info(f"📊 Найдено: {len(full_videos)} полных видео, {len(shorts_videos)} Shorts")
    
    # Ищем неопубликованные
    top_full = None
    for v in full_videos:
        if force or not is_youtube_posted_today(v["id"]):
            top_full = v
            break
    
    top_short = None
    for v in shorts_videos:
        if force or not is_youtube_posted_today(v["id"]):
            top_short = v
            break
    
    if not top_full or not top_short:
        log.info(f"ℹ️ Не хватает видео: full={'✅' if top_full else '❌'}, shorts={'✅' if top_short else '❌'}")
        
        if force and (top_full or top_short):
            log.info("🔄 Force режим: публикую что есть")
            top_full = top_full or (full_videos[0] if full_videos else None)
            top_short = top_short or (shorts_videos[0] if shorts_videos else None)
        
        if not top_full or not top_short:
            return
    
    # ГЛАВНЫЙ ПОСТ: Shorts видео + инфа про full в caption
    try:
        log.info(f"📥 Скачиваю Shorts: {top_short['title'][:50]}...")
        log.info(f"   URL: {top_short['url']}")
        
        # Скачиваем Shorts
        video_data = await download_youtube_video(top_short['id'])
        
        if not video_data:
            log.error("❌ Не удалось скачать Shorts, отправляю ссылками")
            raise Exception("Download failed")
        
        # Формируем подпись
        caption = (
            f"🎬 **Топ YouTube РФ сегодня**\n\n"
            f"⚡ **Самый популярный Shorts:**\n"
            f"{top_short['title']}\n"
            f"📺 {top_short['channel']}\n"
            f"👀 {format_views(top_short['views'])} | ❤️ {format_views(top_short['likes'])}\n\n"
            f"🔥 **Самое популярное видео:**\n"
            f"{top_full['title']}\n"
            f"📺 {top_full['channel']}\n"
            f"👀 {format_views(top_full['views'])} | ❤️ {format_views(top_full['likes'])}\n"
            f"🔗 {top_full['url']}"
        )
        
        # Отправляем Shorts как видео
        from aiogram.types import BufferedInputFile
        
        video_file = BufferedInputFile(video_data, filename=f"{top_short['id']}.mp4")
        
        await bot.send_video(
            CHANNEL_ID,
            video=video_file,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            supports_streaming=True
        )
        
        save_youtube_posted(top_full['id'], 'full')
        save_youtube_posted(top_short['id'], 'shorts')
        log.info("✅ Комбо-пост опубликован")
        
    except Exception as e:
        log.error(f"❌ Ошибка комбо-поста: {e}")
        log.info("📤 Отправляю ссылками...")
        
        # FALLBACK: Оба как ссылки
        try:
            caption = (
                f"🎬 **Топ YouTube РФ сегодня**\n\n"
                f"⚡ **Самый популярный Shorts:**\n"
                f"{top_short['title']}\n"
                f"📺 {top_short['channel']}\n"
                f"👀 {format_views(top_short['views'])} | ❤️ {format_views(top_short['likes'])}\n"
                f"🔗 {top_short['url']}\n\n"
                f"🔥 **Самое популярное видео:**\n"
                f"{top_full['title']}\n"
                f"📺 {top_full['channel']}\n"
                f"👀 {format_views(top_full['views'])} | ❤️ {format_views(top_full['likes'])}\n"
                f"🔗 {top_full['url']}"
            )
            
            await bot.send_message(
                CHANNEL_ID,
                caption,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )
            
            save_youtube_posted(top_full['id'], 'full')
            save_youtube_posted(top_short['id'], 'shorts')
            log.info("✅ Пост со ссылками опубликован")
            
        except Exception as e2:
            log.error(f"❌ Ошибка fallback: {e2}")


async def main():
    """Тестовый запуск"""
    log.info("=" * 60)
    log.info("🧪 ТЕСТ YouTube Data API v3 (только РУ контент)")
    log.info("=" * 60)
    
    if YOUTUBE_API_KEY == 'ВАША_API_KEY':
        log.error("❌ Укажите YOUTUBE_API_KEY!")
        return
    
    trending = await get_trending_videos()
    shorts = await search_popular_shorts()
    
    if trending or shorts:
        full_videos = [v for v in trending if not v.get("is_short")]
        full_videos.sort(key=lambda x: x["views"], reverse=True)
        
        shorts.sort(key=lambda x: x["views"], reverse=True)
        
        log.info(f"\n🎬 ТОП-5 ПОЛНЫХ ВИДЕО (РУ):")
        for i, v in enumerate(full_videos[:5], 1):
            posted = "✅" if is_youtube_posted_today(v["id"]) else "🆕"
            log.info(f"{i}. {posted} {v['title'][:60]}...")
            log.info(f"   👀 {format_views(v['views'])} | 📺 {v['channel']}")
        
        log.info(f"\n⚡ ТОП-5 SHORTS (РУ):")
        for i, v in enumerate(shorts[:5], 1):
            posted = "✅" if is_youtube_posted_today(v["id"]) else "🆕"
            log.info(f"{i}. {posted} {v['title'][:60]}...")
            log.info(f"   👀 {format_views(v['views'])} | 📺 {v['channel']}")
            log.info(f"   🔗 {v['url']}")
        
        print("\n" + "=" * 60)
        print("Опции:")
        print("1. Отправить топы (только новые)")
        print("2. Отправить топы (force - игнорировать дубликаты)")
        print("3. Очистить базу за сегодня")
        print("0. Выход")
        choice = input("Выбери: ").strip()
        
        if choice == '1':
            await post_youtube_tops(force=False)
        elif choice == '2':
            await post_youtube_tops(force=True)
        elif choice == '3':
            today = datetime.now().date().isoformat()
            c.execute("DELETE FROM youtube_posted WHERE DATE(posted_at) = ?", (today,))
            conn.commit()
            log.info(f"✅ Очищена база за {today}")
        else:
            log.info("👋 Выход")
    
    await bot.session.close()
    conn.close()


if __name__ == "__main__":
    from datetime import timedelta
    asyncio.run(main())