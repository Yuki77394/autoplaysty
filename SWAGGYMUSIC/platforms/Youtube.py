import asyncio
import os
import re
import time
from typing import Union
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.future import VideosSearch
import aiohttp
 
from VIVAANXMUSIC import app
from config import ARC_API_URL, ARC_API_KEY

# Short-lived cache: one YouTube extraction supplies metadata + direct media URL.
# This also fixes the previous NameError that caused direct-link playback to fail.
_DIRECT_URL_CACHE: dict[str, tuple[str, float]] = {}
_DIRECT_INFO_CACHE: dict[str, dict] = {}
_DIRECT_URL_CACHE_TTL = 8 * 60


async def _search_video_metadata(video_id: str) -> dict:
    """Fast metadata fallback when YouTube's media extractor is blocked.

    Search by the 11-character ID, never by the full URL. This avoids the
    old behaviour where a direct URL was accidentally treated as a search.
    """
    try:
        result = (await asyncio.wait_for(
            VideosSearch(video_id, limit=1).next(),
            timeout=2.5,
        )).get("result") or []
        if not result:
            return {}
        item = result[0]
        return {
            "title": item.get("title") or "",
            "duration": int(time_to_seconds(item.get("duration"))) if item.get("duration") else 0,
            "thumbnail": ((item.get("thumbnails") or [{}])[0].get("url") or "").split("?")[0],
            "id": item.get("id") or video_id,
        }
    except Exception:
        return {}


async def _oembed_title(video_id: str) -> str:
    """Very lightweight title fallback; no media download/extraction."""
    try:
        url = "https://www.youtube.com/oembed"
        params = {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return str(data.get("title") or "").strip()
    except Exception:
        pass
    return ""
 
 


def _youtube_video_id(value: str) -> str | None:
    """Extract a YouTube video id from common URL forms or a raw id."""
    if not value:
        return None
    value = str(value).strip()
    patterns = (
        r"(?:v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/(?:shorts|embed|live)/)([A-Za-z0-9_-]{11})",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    return None


def _canonical_youtube_url(value: str) -> str:
    video_id = _youtube_video_id(value)
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else value

def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))
 
 
async def _arc_request_download(video_id: str, is_video: bool) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{ARC_API_URL.rstrip('/')}/youtube/v2/download",
            params={"query": video_id, "isVideo": str(is_video).lower(), "api_key": ARC_API_KEY},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                return {}
            return await resp.json(content_type=None)
 
 
async def _arc_poll_job(job_id: str, retries: int = 15, interval: int = 3) -> str | None:
    async with aiohttp.ClientSession() as session:
        for _ in range(retries):
            async with session.get(
                f"{ARC_API_URL.rstrip('/')}/youtube/jobStatus",
                params={"job_id": job_id, "api_key": ARC_API_KEY},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    job = data.get("job", {})
                    if job.get("status") == "done":
                        return job.get("result", {}).get("cdn")
                    if job.get("status") == "error":
                        return None
            await asyncio.sleep(interval)
    return None
 
 
async def _arc_get_cdn(video_id: str, is_video: bool) -> str | None:
    data = await _arc_request_download(video_id, is_video)
    if not data:
        return None
 
    job_id = data.get("job_id")
    if not job_id:
        return data.get("result", {}).get("cdn")
 
    return await _arc_poll_job(job_id)
 
 
async def _save_from_cdn(cdn: str, file_path: str) -> bool:
    match = re.match(r"https?://(?:t\.me|telegram\.dog)/([^/]+)/(\d+)", cdn)
    if match:
        username, message_id = match.group(1), int(match.group(2))
        msg = await app.get_messages(username, message_id)
        if not msg or not (msg.audio or msg.video or msg.document):
            return False
        downloaded = await app.download_media(msg, file_name=file_path)
        return bool(downloaded)
 
    async with aiohttp.ClientSession() as session:
        async with session.get(cdn, timeout=aiohttp.ClientTimeout(total=600)) as resp:
            if resp.status != 200:
                return False
            with open(file_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(131072):
                    f.write(chunk)
    return True
 
 
async def download_song(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None
 
    os.makedirs("downloads", exist_ok=True)
    file_path = os.path.join("downloads", f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
 
    try:
        cdn = await _arc_get_cdn(video_id, is_video=False)
        if not cdn:
            return None
 
        if not await _save_from_cdn(cdn, file_path):
            return None
 
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None
 
 
async def download_video(link: str) -> str:
    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None
 
    os.makedirs("downloads", exist_ok=True)
    file_path = os.path.join("downloads", f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        return file_path
 
    try:
        cdn = await _arc_get_cdn(video_id, is_video=True)
        if not cdn:
            return None
 
        if not await _save_from_cdn(cdn, file_path):
            return None
 
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
        return None
    except Exception:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None
 
 
async def _yt_direct_info(link: str) -> dict | None:
    """Resolve title, duration and a playable audio URL in one extraction.

    The extraction is isolated in a worker thread so it never blocks the bot
    event loop. Authentication/cookie errors are swallowed and handled by the
    normal metadata/download fallback instead of being shown to users.
    """
    def _resolve():
        opts = {
            "format": "bestaudio[acodec!=none]/bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "socket_timeout": 3,
            "retries": 0,
            "fragment_retries": 0,
            "extractor_retries": 0,
            "skip_unavailable_fragments": True,
            "concurrent_fragment_downloads": 4,
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_safari", "mweb", "android"],
                }
            },
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(link, download=False)
            if not info:
                return None
            url = info.get("url")
            if not url:
                for fmt in info.get("formats") or []:
                    fmt_url = fmt.get("url")
                    acodec = fmt.get("acodec")
                    vcodec = fmt.get("vcodec")
                    if fmt_url and acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                        url = fmt_url
                        break
            return {
                "url": url,
                "title": info.get("title") or "",
                "duration": int(info.get("duration") or 0),
                "thumbnail": info.get("thumbnail") or "",
                "id": info.get("id") or "",
            }
    try:
        return await asyncio.wait_for(asyncio.to_thread(_resolve), timeout=5.0)
    except Exception:
        return None


async def _yt_direct_audio_url(link: str) -> str | None:
    data = await _yt_direct_info(link)
    return data.get("url") if data else None


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
 
    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))
 
    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None
 
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid
 
    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["title"]
 
    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["duration"]
 
    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            return result["thumbnails"][0]["url"].split("?")[0]
 
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"
 
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            plist = await Playlist.get(link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data:
                continue
            vid = data.get("id")
            if not vid:
                continue
            ids.append(vid)
        return ids
 
    async def track(self, link: str, videoid: Union[bool, str] = None):
        # Direct YouTube URLs must NOT be passed through VideosSearch.
        # VideosSearch treats the URL as a search query and can return an
        # empty result when YouTube search/extraction is rate limited.
        original = str(link or "").strip()
        direct_id = str(videoid).strip() if videoid else _youtube_video_id(original)

        if direct_id:
            yturl = f"https://www.youtube.com/watch?v={direct_id}"
            fallback_thumb = f"https://i.ytimg.com/vi/{direct_id}/hqdefault.jpg"

            # One extraction supplies ALL metadata + the playable URL.
            info = _DIRECT_INFO_CACHE.get(yturl)
            cached_url = _DIRECT_URL_CACHE.get(yturl)
            if info and (not cached_url or cached_url[1] <= time.monotonic()):
                # Metadata may remain useful, but the media URL is short-lived.
                # Re-extract when the cached media URL has expired.
                if not info.get("title") or not info.get("duration"):
                    info = None
                else:
                    info = dict(info)
                    info.pop("url", None)
            if not info or not cached_url or cached_url[1] <= time.monotonic():
                fresh = await _yt_direct_info(yturl)
                if fresh:
                    info = fresh
            if info:
                seconds = int(info.get("duration") or 0)
                title = info.get("title") or ""
                thumbnail = info.get("thumbnail") or fallback_thumb
                if info.get("url"):
                    now = time.monotonic()
                    _DIRECT_URL_CACHE[yturl] = (info["url"], now + _DIRECT_URL_CACHE_TTL)
                _DIRECT_INFO_CACHE[yturl] = info
            else:
                # Metadata fallback never passes the URL into VideosSearch.
                info = await _search_video_metadata(direct_id)
                title = info.get("title") or await _oembed_title(direct_id) or "YouTube Track"
                seconds = int(info.get("duration") or 0)
                thumbnail = info.get("thumbnail") or fallback_thumb

            duration_min = (
                f"{seconds // 60}:{seconds % 60:02d}"
                if seconds > 0 else "00:00"
            )
            if info:
                info = dict(info)
                info["title"] = title
                info["duration"] = seconds
                info["thumbnail"] = thumbnail
                info["id"] = direct_id
                _DIRECT_INFO_CACHE[yturl] = info

            return {
                "title": title,
                "link": yturl,
                "vidid": direct_id,
                "duration_min": duration_min,
                "thumb": thumbnail.split("?")[0],
                "direct_url": bool(info and info.get("url")),
            }, direct_id

        if "&" in original:
            original = original.split("&")[0]
        results = VideosSearch(original, limit=1)
        result_list = (await results.next()).get("result") or []
        if not result_list:
            raise ValueError("No YouTube search result found")
        result = result_list[0]
        track_details = {
            "title": result["title"],
            "link": result["link"],
            "vidid": result["id"],
            "duration_min": result.get("duration") or "",
            "thumb": result["thumbnails"][0]["url"].split("?")[0],
        }
        return track_details, result["id"]
 
    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        ytdl_opts = {"quiet": True}
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    if "dash" not in str(format["format"]).lower():
                        formats_available.append(
                            {
                                "format": format["format"],
                                "filesize": format.get("filesize"),
                                "format_id": format["format_id"],
                                "ext": format["ext"],
                                "format_note": format["format_note"],
                                "yturl": link,
                            }
                        )
                except Exception:
                    continue
        return formats_available, link
 
    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a = VideosSearch(link, limit=10)
        result = (await a.next()).get("result")
        title = result[query_type]["title"]
        duration_min = result[query_type]["duration"]
        vidid = result[query_type]["id"]
        thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid
 
    async def stream_url(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + str(link)
        link = _canonical_youtube_url(link)
        if "&" in link:
            link = link.split("&")[0]

        # track() already resolved this URL. Reuse it instead of doing a
        # second yt-dlp extraction.
        key = link
        cached = _DIRECT_URL_CACHE.get(key)
        now = time.monotonic()
        if cached and cached[1] > now:
            return cached[0]
        if cached:
            _DIRECT_URL_CACHE.pop(key, None)

        info = await _yt_direct_info(link)
        url = info.get("url") if info else None
        if url:
            _DIRECT_URL_CACHE[key] = (url, now + _DIRECT_URL_CACHE_TTL)
            _DIRECT_INFO_CACHE[key] = info
        return url

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        try:
            if video:
                downloaded_file = await download_video(link)
            else:
                downloaded_file = await download_song(link)
            if downloaded_file:
                return downloaded_file, True
            return None, False
        except Exception:
            return None, False
 
 
YouTube = YouTubeAPI()
