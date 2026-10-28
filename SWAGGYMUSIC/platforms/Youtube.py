import asyncio
import os
import re
import time
from typing import Union
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython import VideosSearch, Playlist
import aiohttp
 
from SWAGGYMUSIC import app
from config import ARC_API_URL, ARC_API_KEY

# Short-lived cache: one YouTube extraction supplies metadata + direct media URL.
# This also fixes the previous NameError that caused direct-link playback to fail.
_DIRECT_URL_CACHE: dict[str, tuple[str, float]] = {}
_DIRECT_INFO_CACHE: dict[str, dict] = {}
_DIRECT_URL_CACHE_TTL = 8 * 60
# Cache failed extractions briefly too: avoid repeating a blocked YouTube request
# for every metadata method/track action. This is not an authentication bypass.
_DIRECT_INFO_FAILURE_CACHE: dict[str, float] = {}
_DIRECT_INFO_FAILURE_TTL = 30


class _QuietYtDlpLogger:
    """Keep expected upstream extractor failures out of worker logs."""
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


async def _search_results(query: str, limit: int = 1) -> list[dict]:
    """Search YouTube with youtube-search-python first, then yt-dlp.

    Returns a consistent result shape so callers do not fail when one provider
    changes its response format or temporarily stops responding.
    """
    query = str(query or "").strip()
    if not query:
        return []

    try:
        response = await asyncio.wait_for(
            VideosSearch(query, limit=limit).next(), timeout=7.0
        )
        results = (response or {}).get("result") or []
        if results:
            return results[:limit]
    except Exception:
        pass

    def _fallback_search():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": True,
            "ignoreerrors": True,
            "socket_timeout": 8,
            "retries": 1,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"ytsearch{max(1, int(limit))}:{query}", download=False)

    try:
        data = await asyncio.wait_for(asyncio.to_thread(_fallback_search), timeout=18.0)
        entries = (data or {}).get("entries") or []
        normalized = []
        for item in entries:
            if not item or not item.get("id"):
                continue
            vid = str(item["id"])
            seconds = int(item.get("duration") or 0)
            thumbs = item.get("thumbnails") or []
            thumb = item.get("thumbnail") or (thumbs[-1].get("url") if thumbs else "")
            normalized.append({
                "title": item.get("title") or query,
                "id": vid,
                "link": item.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}",
                "duration": f"{seconds // 60}:{seconds % 60:02d}" if seconds else "",
                "thumbnails": [{"url": thumb}] if thumb else [],
                "thumbnail": thumb,
            })
        return normalized[:limit]
    except Exception:
        return []


async def _search_video_metadata(video_id: str) -> dict:
    """Fetch metadata for a video ID without treating its URL as a query."""
    try:
        results = await _search_results(video_id, 1)
        if not results:
            return {}
        item = results[0]
        thumbs = item.get("thumbnails") or []
        thumb = item.get("thumbnail") or (thumbs[0].get("url") if thumbs else "")
        duration = item.get("duration") or ""
        try:
            seconds = int(time_to_seconds(duration)) if duration else int(item.get("duration_seconds") or 0)
        except Exception:
            seconds = int(item.get("duration_seconds") or 0)
        return {
            "title": item.get("title") or "",
            "duration": seconds,
            "thumbnail": str(thumb or "").split("?")[0],
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
    video_id = _youtube_video_id(link) or str(link).strip()
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
    video_id = _youtube_video_id(link) or str(link).strip()
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
    """Resolve audio metadata/URL quickly, reusing successful and failed lookups.

    YouTube may reject datacenter requests with an authentication challenge.
    That failure is cached briefly and returned to the caller so the existing
    metadata/API-download fallback can run without repeatedly blocking playback.
    This deliberately does not attempt to bypass YouTube's challenge.
    """
    link = _canonical_youtube_url(str(link or "").strip())
    now = time.monotonic()
    cached = _DIRECT_INFO_CACHE.get(link)
    if cached and cached.get("url") and _DIRECT_URL_CACHE.get(link, (None, 0))[1] > now:
        return dict(cached)
    if _DIRECT_INFO_FAILURE_CACHE.get(link, 0) > now:
        return None

    def _resolve():
        opts = {
            "format": "bestaudio[acodec!=none]/bestaudio/best",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "logger": _QuietYtDlpLogger(),
            "skip_download": True,
            "socket_timeout": 2,
            "retries": 0,
            "fragment_retries": 0,
            "extractor_retries": 0,
            "skip_unavailable_fragments": True,
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
        result = await asyncio.wait_for(asyncio.to_thread(_resolve), timeout=3.0)
        if result and result.get("url"):
            _DIRECT_INFO_CACHE[link] = result
            _DIRECT_URL_CACHE[link] = (result["url"], time.monotonic() + _DIRECT_URL_CACHE_TTL)
            _DIRECT_INFO_FAILURE_CACHE.pop(link, None)
            return dict(result)
    except Exception:
        pass
    _DIRECT_INFO_FAILURE_CACHE[link] = time.monotonic() + _DIRECT_INFO_FAILURE_TTL
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
        """Return track metadata, with yt-dlp fallback if search API fails."""
        original = str(link or "").strip()
        if videoid:
            original = self.base + original
        direct_id = _youtube_video_id(original)
        if direct_id:
            info = await _yt_direct_info(f"https://www.youtube.com/watch?v={direct_id}")
            if not info:
                info = await _search_video_metadata(direct_id)
            title = (info or {}).get("title") or await _oembed_title(direct_id) or "YouTube Track"
            seconds = int((info or {}).get("duration") or 0)
            duration_min = f"{seconds // 60}:{seconds % 60:02d}" if seconds else "00:00"
            thumbnail = (info or {}).get("thumbnail") or f"https://i.ytimg.com/vi/{direct_id}/hqdefault.jpg"
            return title, duration_min, seconds, thumbnail, direct_id

        query = original.split("&", 1)[0].strip()
        result_list = await _search_results(query, 1)
        if result_list:
            result = result_list[0]
            duration_min = result.get("duration") or ""
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else int(result.get("duration_seconds") or 0)
            thumbs = result.get("thumbnails") or []
            thumbnail = result.get("thumbnail") or (thumbs[0].get("url") if thumbs else "")
            vidid = result.get("id")
            if vidid:
                return result.get("title") or query, duration_min or (f"{duration_sec // 60}:{duration_sec % 60:02d}" if duration_sec else "00:00"), duration_sec, str(thumbnail or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg").split("?")[0], vidid
        raise ValueError("No YouTube search result found for query")

    async def title(self, link: str, videoid: Union[bool, str] = None):
        value = self.base + str(link) if videoid else str(link or "")
        direct_id = _youtube_video_id(value)
        if direct_id:
            info = await _yt_direct_info(f"https://www.youtube.com/watch?v={direct_id}") or await _search_video_metadata(direct_id)
            return info.get("title") or await _oembed_title(direct_id) or "YouTube Track"
        results = await _search_results(value.split("&", 1)[0], 1)
        return results[0].get("title") if results else None

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        value = self.base + str(link) if videoid else str(link or "")
        direct_id = _youtube_video_id(value)
        if direct_id:
            info = await _yt_direct_info(f"https://www.youtube.com/watch?v={direct_id}") or await _search_video_metadata(direct_id)
            seconds = int(info.get("duration") or 0)
            return f"{seconds // 60}:{seconds % 60:02d}" if seconds else "00:00"
        results = await _search_results(value.split("&", 1)[0], 1)
        return (results[0].get("duration") or "00:00") if results else None

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        value = self.base + str(link) if videoid else str(link or "")
        direct_id = _youtube_video_id(value)
        if direct_id:
            info = await _yt_direct_info(f"https://www.youtube.com/watch?v={direct_id}") or await _search_video_metadata(direct_id)
            return (info.get("thumbnail") or f"https://i.ytimg.com/vi/{direct_id}/hqdefault.jpg").split("?")[0]
        results = await _search_results(value.split("&", 1)[0], 1)
        if not results:
            return None
        item = results[0]
        thumbs = item.get("thumbnails") or []
        return (item.get("thumbnail") or (thumbs[0].get("url") if thumbs else "") or "").split("?")[0] or None

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
        # `videoid` may be a real ID or a boolean flag used by older callers.
        if isinstance(videoid, str) and videoid.lower() not in {"true", "false"}:
            direct_id = _youtube_video_id(videoid) or videoid.strip()
        else:
            direct_id = _youtube_video_id(self.base + original if videoid else original)

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
            original = original.split("&", 1)[0]
        result_list = await _search_results(original, 1)
        if not result_list:
            raise ValueError("No YouTube search result found for query")
        result = result_list[0]
        vidid = result.get("id")
        if not vidid:
            raise ValueError("YouTube search result has no video ID")
        thumbs = result.get("thumbnails") or []
        thumbnail = result.get("thumbnail") or (thumbs[0].get("url") if thumbs else "")
        track_details = {
            "title": result.get("title") or original,
            "link": result.get("link") or result.get("webpage_url") or f"https://www.youtube.com/watch?v={vidid}",
            "vidid": vidid,
            "duration_min": result.get("duration") or "00:00",
            "thumb": (thumbnail or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg").split("?")[0],
        }
        return track_details, vidid
 
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
        value = self.base + str(link) if videoid else str(link or "")
        if "&" in value:
            value = value.split("&", 1)[0]
        results = await _search_results(value, max(10, int(query_type) + 1))
        if not results or query_type < 0 or query_type >= len(results):
            raise ValueError("No YouTube search results available for slider")
        item = results[query_type]
        vidid = item.get("id")
        if not vidid:
            raise ValueError("YouTube search result has no video ID")
        thumbs = item.get("thumbnails") or []
        thumbnail = item.get("thumbnail") or (thumbs[0].get("url") if thumbs else "")
        return item.get("title") or "YouTube Track", item.get("duration") or "00:00", (thumbnail or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg").split("?")[0], vidid

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
            link = self.base + str(link)
        try:
            # Audio: stream the resolved media URL directly instead of waiting
            # for a full MP3 download through the API. track()/details() may
            # already have populated this cache, so the common path is quick.
            if not video:
                canonical = _canonical_youtube_url(str(link))
                video_id = _youtube_video_id(canonical)
                if video_id:
                    key = f"https://www.youtube.com/watch?v={video_id}"
                    now = time.monotonic()
                    cached = _DIRECT_URL_CACHE.get(key)
                    if cached and cached[1] > now:
                        return cached[0], True
                    info = await _yt_direct_info(key)
                    media_url = (info or {}).get("url")
                    if media_url:
                        _DIRECT_URL_CACHE[key] = (media_url, time.monotonic() + _DIRECT_URL_CACHE_TTL)
                        if info:
                            _DIRECT_INFO_CACHE[key] = info
                        return media_url, True

            # Keep the existing API download path as a fallback, and for video.
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
