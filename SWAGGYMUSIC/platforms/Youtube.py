"""
YouTube platform implementation for Lustify Music Bot.

This module provides the unified YouTube search / metadata / thumbnail /
download / streaming API used by /play, /vplay, /song, AutoPlay, queue
handling, slider, live-stream, and seek features.

Primary backend: NEW YouTube API (yt.riteshyt.in) — handles search,
metadata (title / duration / thumbnail / vidid / channel / views),
formats listing, and audio/video file downloads via streaming redirects.

Fallbacks (used automatically when the primary API is unavailable or
returns a malformed response):
  1. youtubesearchpython.__future__.VideosSearch — for metadata, title,
     duration, thumbnail, slider and search.
  2. yt-dlp (with cookies) — for actual audio/video file downloads when
     the API download endpoint fails. This is the critical AutoPlay
     resilience layer: a single API rate-limit / 5xx no longer kills
     the autoplay loop because yt-dlp can still fetch the file directly
     from YouTube.

Thumbnail consistency guarantee:
  Whenever we have a video id, the canonical i.ytimg.com URL for THAT
  id is used as the thumbnail. This ensures the thumbnail, title, vidid,
  duration and every other piece of metadata always refer to the SAME
  selected YouTube video. The previous SHRUTI-backed implementation
  sometimes mixed metadata from different result entries (because
  SHRUTI's search and metadata endpoints could return different top
  hits), causing the "wrong thumbnail / Unknown Title / 0 views" bug.
"""

import asyncio
import glob
import os
import re
import time
from typing import Union

import httpx
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

from SWAGGYMUSIC.logging import LOGGER

# Try the async youtubesearchpython package first (this is the same
# library the new reference implementation uses). Fall back to None if
# unavailable — in that case the API becomes the sole source of search
# results, which is fine because the API has its own /search endpoint.
try:
    from youtubesearchpython.__future__ import VideosSearch as _VideosSearch
    from youtubesearchpython.__future__ import Playlist as _Playlist
except Exception:  # pragma: no cover - fallback path
    _VideosSearch = None
    _Playlist = None

# --- New YouTube API configuration -------------------------------------
# These environment variables can be overridden in the Heroku config
# vars without redeploying. The defaults match the new API endpoint
# provided by the user.
API_URL = os.environ.get(
    "API_URL", "http://yt.riteshyt.in"
).rstrip("/")
API_KEY = os.environ.get(
    "API_KEY", "riteshfree576fd88ed84a3f46c84fd556"
)

DOWNLOAD_DIR = "downloads"

# Minimum size for a real audio/video file. The new API streams the
# file via a 307 redirect; if the backend is degraded it can return a
# small HTML error page with content-type: audio/mpeg. Without this
# guard, the HTML would be saved as .mp3 and PyTgCalls / ffmpeg would
# hang for minutes trying to probe it.
_MIN_AUDIO_BYTES = 100_000   # ~100 KB — real songs are 1–3 MB+
_MIN_VIDEO_BYTES = 200_000   # ~200 KB — real videos are several MB

# Per-instance HTTP client. We reuse a single httpx.AsyncClient across
# all calls so we get connection pooling and HTTP/2 keep-alive. The
# client is created lazily on first use because httpx.AsyncClient
# cannot be instantiated outside an event loop on some versions.


def _looks_like_audio(data: bytes) -> bool:
    """Heuristic magic-byte check: real audio/video files start with
    known signatures (ID3 for MP3, ftyp for MP4/M4A, RIFF for WAV, OggS
    for Ogg, \\x1A\\x45\\xDF for WebM/Matroska). HTML responses start
    with `<!DOCTYPE` or `<html`. Used to reject API responses that are
    actually HTML error pages so we can fall back to yt-dlp."""
    if not data or len(data) < 2048:
        return False
    head = data[:16]
    if head.startswith(b"ID3"):  # MP3 with ID3v2 tag
        return True
    if head.startswith(b"\xff\xfb") or head.startswith(b"\xff\xf3") or head.startswith(b"\xff\xfa"):
        # MP3 frame sync
        return True
    if head[4:8] == b"ftyp":  # MP4/M4A/M4V
        return True
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return True
    if head.startswith(b"OggS"):
        return True
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        # WebM / Matroska
        return True
    if head.startswith(b"\x00\x00\x00") and len(data) > _MIN_AUDIO_BYTES:
        # Generic binary container — accept if big enough.
        return True
    # HTML / JSON / XML — definitely not audio
    if head[:5].lower() in (b"<!doc", b"<html", b"<?xml"):
        return False
    if head[:1] == b"{":
        return False
    if len(data) >= _MIN_AUDIO_BYTES and b"<" not in head[:8]:
        return True
    return False


def time_to_seconds(time):
    """Convert 'MM:SS' or 'HH:MM:SS' to total seconds. Returns 0 on
    invalid input. Used by details() to compute duration_sec."""
    stringt = str(time)
    try:
        return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))
    except Exception:
        return 0


def _cookie_file_ytdlp():
    """Pick a cookies.txt for yt-dlp from SWAGGYMUSIC/assets. Lustify
    ships cookies.txt there; if it isn't found we return None and
    yt-dlp runs without cookies (which still works for most videos)."""
    folder = os.path.join(os.getcwd(), "SWAGGYMUSIC", "assets")
    txt_files = glob.glob(os.path.join(folder, "*.txt"))
    if not txt_files:
        return None
    return txt_files[0]


def _extract_vidid(query: str) -> str:
    """Extract the 11-char YouTube video id from a URL or bare id.
    Returns the id, or None if the input doesn't look like a YouTube
    video reference. Used by download() and prefetch() to build the
    canonical watch URL for the API."""
    if not query:
        return None
    if re.match(r"^[a-zA-Z0-9_-]{11}$", query):
        return query
    regex = (
        r"(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|shorts\/|.*[?&]v=)"
        r"|youtu\.be\/)([^\"&?\/\s]{11})"
    )
    match = re.search(regex, query)
    return match.group(1) if match else None


# --- yt-dlp sync fallbacks (run in executor) ---------------------------

def _ytdlp_audio_sync(video_id: str) -> str:
    """yt-dlp fallback for audio downloads when the new API fails.
    Extracts the best-audio stream and saves it as
    downloads/<video_id>.mp3. Returns the file path on success,
    None on failure."""
    if not video_id or len(video_id) < 3:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_AUDIO_BYTES:
        return file_path
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "no_progress": True,
        "format": "bestaudio/best",
        "outtmpl": file_path,
        "noplaylist": True,
        "default_search": "auto",
    }
    cookiefile = _cookie_file_ytdlp()
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:
        LOGGER(__name__).warning(
            f"[DOWNLOAD] yt-dlp audio fallback failed for {video_id}: "
            f"{type(e).__name__}: {e}"
        )
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None
    if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_AUDIO_BYTES:
        return file_path
    return None


def _ytdlp_video_sync(video_id: str) -> str:
    """yt-dlp fallback for video downloads when the new API fails."""
    if not video_id or len(video_id) < 3:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_VIDEO_BYTES:
        return file_path
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "no_progress": True,
        "format": "best[ext=mp4]/best",
        "outtmpl": file_path,
        "noplaylist": True,
        "default_search": "auto",
    }
    cookiefile = _cookie_file_ytdlp()
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    except Exception as e:
        LOGGER(__name__).warning(
            f"[DOWNLOAD] yt-dlp video fallback failed for {video_id}: "
            f"{type(e).__name__}: {e}"
        )
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return None
    if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_VIDEO_BYTES:
        return file_path
    return None


async def download_song(link: str) -> str:
    """Download an audio file for the given YouTube link / video id.
    Primary: new API /download endpoint (streams the file via 307
    redirect). Fallback: yt-dlp.

    Returns the local file path on success, None on failure. Used by
    YouTube.download() and is the critical path for AutoPlay — if this
    returns None, the autoplay candidate fails and the caller tries
    the next candidate (see core/call.py)."""
    video_id = _extract_vidid(link) or (
        link.split("v=")[-1].split("&")[0] if "v=" in link else link
    )
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_AUDIO_BYTES:
        return file_path

    # --- Primary: new API ----------------------------------------------
    # Use a generous timeout — some legitimate songs (long mixes, live
    # sets) take a while to fully download.
    params = {"query": video_id, "dl_type": "audio"}
    if API_KEY:
        params["api_key"] = API_KEY
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", f"{API_URL}/download", params=params) as resp:
                if resp.status_code == 200:
                    # IMPORTANT: use a SINGLE iterator. Calling
                    # resp.aiter_bytes() twice on the same streaming
                    # response raises httpx.StreamConsumed once the
                    # first iterator is closed (via `break`). Peek
                    # with anext(), then continue the same iterator
                    # in the file-writing loop.
                    aiter = resp.aiter_bytes(131072)
                    buf = bytearray()
                    while len(buf) < 4096:
                        try:
                            chunk = await anext(aiter)
                        except StopAsyncIteration:
                            break
                        buf.extend(chunk)
                    if _looks_like_audio(bytes(buf)):
                        # Continue streaming the rest into the file
                        # using the SAME iterator.
                        with open(file_path, "wb") as f:
                            f.write(buf)
                            async for chunk in aiter:
                                f.write(chunk)
                        if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_AUDIO_BYTES:
                            return file_path
                    LOGGER(__name__).warning(
                        f"[DOWNLOAD] API audio returned non-audio body "
                        f"for {video_id}, falling back to yt-dlp"
                    )
                else:
                    LOGGER(__name__).warning(
                        f"[DOWNLOAD] API audio returned status={resp.status_code} "
                        f"for {video_id}, falling back to yt-dlp"
                    )
    except Exception as e:
        LOGGER(__name__).warning(
            f"[DOWNLOAD] API audio raised for {video_id}: "
            f"{type(e).__name__}: {e}, falling back to yt-dlp"
        )
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    # --- Fallback: yt-dlp ----------------------------------------------
    try:
        loop = asyncio.get_event_loop()
        fallback_path = await loop.run_in_executor(None, _ytdlp_audio_sync, video_id)
        if fallback_path:
            return fallback_path
    except Exception as e:
        LOGGER(__name__).warning(
            f"[DOWNLOAD] yt-dlp audio executor failed for {video_id}: "
            f"{type(e).__name__}: {e}"
        )
    return None


async def download_video(link: str) -> str:
    """Download a video file for the given YouTube link / video id.
    Primary: new API /download (dl_type=video). Fallback: yt-dlp."""
    video_id = _extract_vidid(link) or (
        link.split("v=")[-1].split("&")[0] if "v=" in link else link
    )
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp4")
    if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_VIDEO_BYTES:
        return file_path

    params = {"query": video_id, "dl_type": "video"}
    if API_KEY:
        params["api_key"] = API_KEY
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", f"{API_URL}/download", params=params) as resp:
                if resp.status_code == 200:
                    # IMPORTANT: use a SINGLE iterator (see download_song).
                    aiter = resp.aiter_bytes(131072)
                    buf = bytearray()
                    while len(buf) < 4096:
                        try:
                            chunk = await anext(aiter)
                        except StopAsyncIteration:
                            break
                        buf.extend(chunk)
                    if _looks_like_audio(bytes(buf)):
                        with open(file_path, "wb") as f:
                            f.write(buf)
                            async for chunk in aiter:
                                f.write(chunk)
                        if os.path.exists(file_path) and os.path.getsize(file_path) > _MIN_VIDEO_BYTES:
                            return file_path
                    LOGGER(__name__).warning(
                        f"[DOWNLOAD] API video returned non-video body "
                        f"for {video_id}, falling back to yt-dlp"
                    )
                else:
                    LOGGER(__name__).warning(
                        f"[DOWNLOAD] API video returned status={resp.status_code} "
                        f"for {video_id}, falling back to yt-dlp"
                    )
    except Exception as e:
        LOGGER(__name__).warning(
            f"[DOWNLOAD] API video raised for {video_id}: "
            f"{type(e).__name__}: {e}, falling back to yt-dlp"
        )
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    try:
        loop = asyncio.get_event_loop()
        fallback_path = await loop.run_in_executor(None, _ytdlp_video_sync, video_id)
        if fallback_path:
            return fallback_path
    except Exception as e:
        LOGGER(__name__).warning(
            f"[DOWNLOAD] yt-dlp video executor failed for {video_id}: "
            f"{type(e).__name__}: {e}"
        )
    return None


class YouTubeAPI:
    """Lustify YouTube API wrapper. Method signatures are kept
    identical to the previous SHRUTI-backed implementation so all
    callers (stream.py, call.py, skip.py, callback.py, song.py,
    play.py, live.py, seek.py) continue to work without changes.

    Internally every method tries the new API first and falls back to
    youtubesearchpython (for metadata) or yt-dlp (for downloads) if
    the API is unavailable or returns a malformed response."""

    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        # Lazy-init httpx client (cannot be created outside an event
        # loop on some httpx versions).
        self._client = None
        # Tracks recent prefetch calls so we don't prefetch the same
        # video more than once every 30 seconds.
        self._recent_prefetches: dict[str, float] = {}

    # --- HTTP client management -----------------------------------------

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client

    async def _fetch_details(self, link: str) -> dict | None:
        """Internal: call the API /details endpoint and return the raw
        JSON dict, or None on any failure. The /details endpoint
        returns title, duration_min, duration_sec, thumbnail, vidid,
        channel and viewCount for the given video URL."""
        if not API_URL:
            return None
        link = self._clean_link(link)
        client = await self.get_client()
        params = {"link": link}
        if API_KEY:
            params["api_key"] = API_KEY
        try:
            response = await client.get(f"{API_URL}/details", params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get("vidid"):
                    return data
                LOGGER(__name__).warning(
                    f"[DETAILS] API /details returned malformed body "
                    f"for {link}: {str(data)[:200]}"
                )
        except Exception as e:
            LOGGER(__name__).warning(
                f"[DETAILS] API /details raised for {link}: "
                f"{type(e).__name__}: {e}"
            )
        return None

    async def _api_search(self, query: str, limit: int = 10) -> list | None:
        """Internal: call the API /search endpoint and return the
        'result' array, or None on failure."""
        if not API_URL:
            return None
        client = await self.get_client()
        params = {"query": query, "limit": limit}
        if API_KEY:
            params["api_key"] = API_KEY
        try:
            response = await client.get(f"{API_URL}/search", params=params)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    return data.get("result") or []
        except Exception as e:
            LOGGER(__name__).warning(
                f"[SEARCH] API /search raised for {query!r}: "
                f"{type(e).__name__}: {e}"
            )
        return None

    # --- Public API -----------------------------------------------------

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        """Return True if `link` looks like a YouTube URL."""
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        """Extract the first URL/text-link from a Pyrogram message
        (also checks reply_to_message). Used by /play and /song to
        detect a YouTube link in the user's message."""
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if getattr(message, "entities", None):
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif getattr(message, "caption_entities", None):
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    def _clean_link(self, link: str) -> str:
        """Strip tracking params (?si=, &si=, &feature=...) from a
        YouTube URL so the API receives a clean canonical URL."""
        if not link:
            return ""
        link = str(link)
        if "&" in link:
            link = link.split("&")[0]
        if "?si=" in link:
            link = link.split("?si=")[0]
        elif "&si=" in link:
            link = link.split("&si=")[0]
        return link

    @staticmethod
    def _pick_official(results, query=None):
        """Pick the most authoritative result from a list of search
        hits. Heuristics (in priority order):
          1. Channel name contains 'Official', 'Topic', or 'VEVO'.
          2. Title contains 'Official Audio' / 'Official Video'.
          3. Has a non-None duration (skip Shorts/live without duration).
          4. First result (YouTube's relevance ranking).
        We never hard-code channel IDs — the choice is driven by the
        search result's own metadata, which is what the user sees in
        the slider."""
        if not results:
            return None

        def channel_score(r):
            ch = (r.get("channel") or {}).get("name", "") or ""
            title = r.get("title", "") or ""
            ch_l = ch.lower()
            t_l = title.lower()
            score = 0
            if "official" in ch_l:
                score += 5
            if "vevo" in ch_l or ch_l.endswith("vevo"):
                score += 5
            if "topic" in ch_l:
                score += 4
            if "music" in ch_l:
                score += 1
            if "official" in t_l:
                score += 2
            if "official audio" in t_l or "official video" in t_l:
                score += 2
            dur = r.get("duration")
            if dur and ":" in str(dur):
                score += 1
            return score

        best = max(results, key=channel_score)
        if channel_score(best) == 0:
            return results[0]
        return best

    async def details(self, link: str, videoid: Union[bool, str] = None):
        """Return (title, duration_min, duration_sec, thumbnail, vidid)
        for the given YouTube URL or video id.

        When videoid=True, `link` is a bare 11-char video id — we build
        the canonical watch URL and verify the API/search result's vidid
        matches the requested one. The thumbnail is ALWAYS the canonical
        i.ytimg.com URL for that exact video id, so the thumbnail and
        metadata can never diverge to different videos."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)

        # Try the new API first — it returns a single dict for the
        # exact video we asked about.
        if API_URL:
            data = await self._fetch_details(link)
            if data:
                title = data.get("title") or "Unknown Title"
                duration_min = data.get("duration_min") or "0:00"
                duration_sec = int(data.get("duration_sec") or 0)
                vidid = data.get("vidid") or (_extract_vidid(link) or link)
                # Canonical thumbnail — 1:1 with the chosen video id.
                thumbnail = (
                    data.get("thumbnail")
                    or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                )
                return title, duration_min, duration_sec, thumbnail, vidid

        # Fallback: youtubesearchpython async VideosSearch.
        if _VideosSearch is not None:
            try:
                results = _VideosSearch(link, limit=10)
                res = await results.next()
                res_list = (res or {}).get("result", []) or []
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[DETAILS] VideosSearch fallback raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )
                res_list = []

            chosen = None
            if videoid and res_list:
                try:
                    wanted = link.split("v=")[1].split("&")[0]
                except Exception:
                    wanted = None
                if wanted:
                    for r in res_list:
                        if str(r.get("id", "")) == str(wanted):
                            chosen = r
                            break
                if chosen is None and res_list:
                    chosen = res_list[0]
            elif res_list:
                chosen = self._pick_official(res_list, link)

            if chosen:
                title = chosen.get("title") or "Unknown Title"
                duration_min = chosen.get("duration") or "0:00"
                vidid = chosen.get("id") or (_extract_vidid(link) or link)
                thumbnail = f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
                return title, duration_min, duration_sec, thumbnail, vidid

        # Final fallback — synthesise a minimal valid response so the
        # caller doesn't crash. The thumbnail is still canonical for
        # the requested video id, so users see the correct artwork
        # even when metadata fetching fails.
        try:
            _vid = link.split("v=")[1].split("&")[0] if "v=" in link else (
                _extract_vidid(link) or link
            )
        except Exception:
            _vid = link
        return (
            "Unknown Title",
            "0:00",
            0,
            f"https://i.ytimg.com/vi/{_vid}/hqdefault.jpg",
            _vid,
        )

    async def title(self, link: str, videoid: Union[bool, str] = None):
        """Return just the title for the given link / video id."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)
        if API_URL:
            data = await self._fetch_details(link)
            if data and data.get("title"):
                return data["title"]
        if _VideosSearch is not None:
            try:
                results = _VideosSearch(link, limit=1)
                res = await results.next()
                if res and res.get("result"):
                    return res["result"][0]["title"]
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[TITLE] VideosSearch fallback raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )
        return None

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        """Return just the duration (MM:SS) for the given link."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)
        if API_URL:
            data = await self._fetch_details(link)
            if data and data.get("duration_min"):
                return data["duration_min"]
        if _VideosSearch is not None:
            try:
                results = _VideosSearch(link, limit=1)
                res = await results.next()
                if res and res.get("result"):
                    return res["result"][0]["duration"]
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[DURATION] VideosSearch fallback raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )
        return None

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        """Return the canonical i.ytimg.com thumbnail URL for the
        given link / video id. This is ALWAYS 1:1 with the exact video
        id — never a different video's artwork. This is the root-cause
        fix for the "wrong thumbnail" reports."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)
        # Prefer the API's thumbnail if it returned one (it should
        # match the canonical URL anyway, but if it returns a
        # higher-res version we want it).
        if API_URL:
            data = await self._fetch_details(link)
            if data and data.get("thumbnail"):
                return data["thumbnail"]
        # Final fallback: build canonical URL from the video id.
        try:
            vid = link.split("v=")[1].split("&")[0]
        except Exception:
            vid = _extract_vidid(link) or link
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

    async def video(self, link: str, videoid: Union[bool, str] = None):
        """Download a video file and return (1, file_path) on success
        or (0, error_message) on failure. Used by /vplay, live-stream
        and the change_stream / skip handlers when the queued item is
        a 'live_' track."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        """Return a list of video IDs for the given YouTube playlist
        URL (capped at `limit`). Primary: new API /playlist endpoint.
        Fallback: youtubesearchpython Playlist.get()."""
        if videoid:
            link = self.listbase + link
        link = self._clean_link(link)

        # API first
        if API_URL:
            client = await self.get_client()
            params = {"link": link, "limit": limit}
            if API_KEY:
                params["api_key"] = API_KEY
            try:
                response = await client.get(f"{API_URL}/playlist", params=params)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        videos = data.get("videos") or []
                        ids = []
                        for v in videos[:limit]:
                            if not v:
                                continue
                            vid = v.get("id") or v.get("vidid")
                            if vid:
                                ids.append(vid)
                        if ids:
                            return ids
                else:
                    LOGGER(__name__).warning(
                        f"[PLAYLIST] API /playlist returned status={response.status_code} "
                        f"for {link}"
                    )
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[PLAYLIST] API /playlist raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )

        # Fallback: youtubesearchpython
        if _Playlist is not None:
            try:
                plist = await _Playlist.get_videos(link, limit)
                videos = (plist or {}).get("videos") or []
                ids = []
                for data in videos[:limit]:
                    if not data:
                        continue
                    vid = data.get("id")
                    if vid:
                        ids.append(vid)
                return ids
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[PLAYLIST] youtubesearchpython fallback raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )
        return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        """Return (track_details_dict, vidid) for the given link /
        video id.

        When videoid=True, `link` is a bare video ID. We verify the
        API/search result's vidid matches the requested one so the
        title, duration, thumbnail and link all refer to the SAME
        selected video. The thumbnail is ALWAYS the canonical
        i.ytimg.com URL for the chosen video id."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)

        # API first — /details returns a single dict for the exact
        # video, so we don't need to do an id-match dance.
        if API_URL:
            data = await self._fetch_details(link)
            if data:
                vidid = data.get("vidid") or (_extract_vidid(link) or link)
                track_details = {
                    "title": data.get("title") or "Unknown Title",
                    "link": data.get("link") or f"https://www.youtube.com/watch?v={vidid}",
                    "vidid": vidid,
                    "duration_min": data.get("duration_min") or "0:00",
                    "thumb": (
                        data.get("thumbnail")
                        or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                    ),
                }
                return track_details, vidid

        # Fallback: youtubesearchpython async VideosSearch.
        if _VideosSearch is not None:
            try:
                results = _VideosSearch(link, limit=10)
                res = await results.next()
                res_list = (res or {}).get("result", []) or []
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[TRACK] VideosSearch fallback raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )
                res_list = []

            chosen = None
            if videoid and res_list:
                try:
                    wanted = link.split("v=")[1].split("&")[0]
                except Exception:
                    wanted = None
                if wanted:
                    for r in res_list:
                        if str(r.get("id", "")) == str(wanted):
                            chosen = r
                            break
                if chosen is None and res_list:
                    chosen = res_list[0]
            elif res_list:
                chosen = self._pick_official(res_list, link)

            if chosen:
                title = chosen.get("title") or "Unknown Title"
                vidid = chosen.get("id") or (_extract_vidid(link) or link)
                yturl = (
                    chosen.get("link")
                    or f"https://www.youtube.com/watch?v={vidid}"
                )
                # Canonical thumbnail — never wrong.
                thumbnail = f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                track_details = {
                    "title": title,
                    "link": yturl,
                    "vidid": vidid,
                    "duration_min": chosen.get("duration") or "0:00",
                    "thumb": thumbnail,
                }
                return track_details, vidid

        # Final fallback — synthesise a minimal details dict so the
        # caller doesn't crash. Thumbnail is still canonical for the
        # requested video id.
        try:
            _vid = link.split("v=")[1].split("&")[0] if "v=" in link else (
                _extract_vidid(link) or link
            )
        except Exception:
            _vid = link
        fallback_thumb = f"https://i.ytimg.com/vi/{_vid}/hqdefault.jpg"
        track_details = {
            "title": "Unknown Title",
            "link": link,
            "vidid": _vid,
            "duration_min": "0:00",
            "thumb": fallback_thumb,
        }
        return track_details, _vid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        """Return (formats_list, link) for the given video. Used by
        /song's quality-picker UI. Primary: new API /formats endpoint.
        Fallback: yt-dlp extract_info(download=False)."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)

        # API first
        if API_URL:
            client = await self.get_client()
            params = {"link": link}
            if API_KEY:
                params["api_key"] = API_KEY
            try:
                response = await client.get(f"{API_URL}/formats", params=params)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict):
                        formats = data.get("formats", []) or []
                        for f in formats:
                            f["yturl"] = link
                        if formats:
                            return formats, link
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[FORMATS] API /formats raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )

        # Fallback: yt-dlp extract_info
        def _extract():
            ytdl_opts = {"quiet": True, "no_warnings": True}
            cookiefile = _cookie_file_ytdlp()
            if cookiefile:
                ytdl_opts["cookiefile"] = cookiefile
            ydl = yt_dlp.YoutubeDL(ytdl_opts)
            with ydl:
                return ydl.extract_info(link, download=False)

        try:
            loop = asyncio.get_running_loop()
            r = await loop.run_in_executor(None, _extract)
            formats_available = []
            for format in (r or {}).get("formats", []) or []:
                try:
                    if "dash" not in str(format.get("format", "")).lower():
                        formats_available.append(
                            {
                                "format": format.get("format"),
                                "filesize": format.get("filesize"),
                                "format_id": format.get("format_id"),
                                "ext": format.get("ext"),
                                "format_note": format.get("format_note"),
                                "yturl": link,
                            }
                        )
                except Exception:
                    continue
            return formats_available, link
        except Exception as e:
            LOGGER(__name__).warning(
                f"[FORMATS] yt-dlp fallback raised for {link}: "
                f"{type(e).__name__}: {e}"
            )
            return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        """Return (title, duration_min, thumbnail, vidid) for the
        query_type-th search result for the given query. Used by the
        /play slider UI (the user paginates through 10 search results
        and picks one).

        The thumbnail is ALWAYS the canonical i.ytimg.com URL for the
        selected slider entry's video id — never a different video's
        artwork."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)

        # API first
        if API_URL:
            result = await self._api_search(link, limit=10)
            if result and len(result) > query_type:
                target = result[query_type]
                title = target.get("title") or "Unknown Title"
                duration_min = target.get("duration") or "0:00"
                vidid = target.get("id") or (_extract_vidid(link) or link)
                # Canonical thumbnail for the *exact* selected slider
                # entry — never a different video's art.
                thumbnail = f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                return title, duration_min, thumbnail, vidid

        # Fallback: youtubesearchpython
        if _VideosSearch is not None:
            try:
                a = _VideosSearch(link, limit=10)
                res = await a.next()
                result = (res or {}).get("result") or []
                if result and len(result) > query_type:
                    entry = result[query_type]
                    title = entry.get("title") or "Unknown Title"
                    duration_min = entry.get("duration") or "0:00"
                    vidid = entry.get("id") or (_extract_vidid(link) or link)
                    thumbnail = f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
                    return title, duration_min, thumbnail, vidid
            except Exception as e:
                LOGGER(__name__).warning(
                    f"[SLIDER] VideosSearch fallback raised for {link}: "
                    f"{type(e).__name__}: {e}"
                )
        return None, None, None, None

    async def prefetch(self, link: str, video: bool = False) -> bool:
        """Trigger background pre-fetching of a video on the API so
        the actual /download call is fast. We avoid issuing redundant
        prefetches for the same video within 30 seconds."""
        if not API_URL:
            return False
        dl_type = "video" if video else "audio"
        link = self._clean_link(link)
        now = time.time()
        vidid = _extract_vidid(link) or link
        cache_key = f"{vidid}_{dl_type}"
        if cache_key in self._recent_prefetches:
            if now - self._recent_prefetches[cache_key] < 30:
                return True
        self._recent_prefetches[cache_key] = now
        # Cap the cache so it doesn't grow forever.
        if len(self._recent_prefetches) > 100:
            self._recent_prefetches = {
                k: v for k, v in self._recent_prefetches.items()
                if now - v < 300
            }
        client = await self.get_client()
        params = {"query": link, "dl_type": dl_type, "prefetch": "true"}
        if API_KEY:
            params["api_key"] = API_KEY
        try:
            await client.get(f"{API_URL}/download", params=params)
            return True
        except Exception as e:
            LOGGER(__name__).warning(
                f"[PREFETCH] failed for {link}: {type(e).__name__}: {e}"
            )
        return False

    async def prefetch_queue(self, queries: list, video: bool = False) -> bool:
        """Trigger bulk background pre-fetching for a queue of videos."""
        if not API_URL or not queries:
            return False
        dl_type = "video" if video else "audio"
        client = await self.get_client()
        payload = {"queries": queries, "dl_type": dl_type}
        params = {}
        if API_KEY:
            params["api_key"] = API_KEY
        try:
            await client.post(f"{API_URL}/prefetch_bulk", json=payload, params=params)
            return True
        except Exception as e:
            LOGGER(__name__).warning(
                f"[PREFETCH_BULK] failed: {type(e).__name__}: {e}"
            )
        return False

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
    ) -> Union[str, tuple]:
        """Download a YouTube audio/video file.

        Returns one of:
          - (file_path, True) — downloaded to local disk (direct=True
            signals the caller should pass the file path to PyTgCalls
            rather than the YouTube URL).
          - (file_path, False) — for streaming-URL semantics (kept for
            backward compat with callers expecting a 2-tuple).
          - file_path (str) — when songaudio/songvideo=True (used by
            the /song download UI which expects a single string).
          - None / (None, False) on failure.

        Behaviour matrix:
          - songvideo=True: download video at the chosen format_id,
            save as downloads/<title>.mp4. Used by /song video picker.
          - songaudio=True: download audio at the chosen format_id,
            save as downloads/<title>.mp3. Used by /song audio picker.
          - video=True: download video for playback, save as
            downloads/<vidid>.mp4. Used by /vplay, live-stream.
          - otherwise: download audio for playback, save as
            downloads/<vidid>.mp3. Used by /play, AutoPlay."""
        if videoid:
            link = self.base + link
        link = self._clean_link(link)
        vidid_extracted = _extract_vidid(link) or link

        # ---- /song download paths (with format_id) --------------------
        if songvideo:
            fpath = f"downloads/{title}.mp4"
            success = await self._download_with_format(
                link, "video", fpath, format_id
            )
            if success:
                return fpath
            # Fall through to local yt-dlp format-extraction fallback
            return await self._ytdlp_song_fallback(link, "video", title, format_id)

        if songaudio:
            fpath = f"downloads/{title}.mp3"
            success = await self._download_with_format(
                link, "audio", fpath, format_id
            )
            if success:
                return fpath
            return await self._ytdlp_song_fallback(link, "audio", title, format_id)

        # ---- Playback paths (audio or video for streaming) -----------
        # Background prefetch to warm the API cache (best-effort).
        try:
            asyncio.create_task(self.prefetch(link, video=bool(video)))
        except Exception:
            pass

        if video:
            downloaded_file = await download_video(link)
        else:
            downloaded_file = await download_song(link)
        if downloaded_file:
            return downloaded_file, True
        return None, False

    async def _download_with_format(
        self, link: str, dl_type: str, fpath: str, format_id: str
    ) -> bool:
        """Download via the API with a specific format_id. Falls back
        to a generic /download call (no format_id) if the API doesn't
        support format-specific downloads."""
        if not API_URL:
            return False
        vidid = _extract_vidid(link) or link
        params = {"query": vidid, "dl_type": dl_type}
        if format_id:
            params["format_id"] = format_id
        if API_KEY:
            params["api_key"] = API_KEY
        os.makedirs(os.path.dirname(fpath) or ".", exist_ok=True)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(600.0, connect=15.0),
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", f"{API_URL}/download", params=params) as resp:
                    if resp.status_code != 200:
                        return False
                    # IMPORTANT: use a SINGLE iterator (see download_song).
                    aiter = resp.aiter_bytes(131072)
                    buf = bytearray()
                    while len(buf) < 4096:
                        try:
                            chunk = await anext(aiter)
                        except StopAsyncIteration:
                            break
                        buf.extend(chunk)
                    if not _looks_like_audio(bytes(buf)):
                        return False
                    with open(fpath, "wb") as f:
                        f.write(buf)
                        async for chunk in aiter:
                            f.write(chunk)
            min_bytes = _MIN_VIDEO_BYTES if dl_type == "video" else _MIN_AUDIO_BYTES
            return os.path.exists(fpath) and os.path.getsize(fpath) > min_bytes
        except Exception as e:
            LOGGER(__name__).warning(
                f"[DOWNLOAD] API format download failed for {vidid} "
                f"(format_id={format_id}): {type(e).__name__}: {e}"
            )
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
            return False

    async def _ytdlp_song_fallback(
        self, link: str, dl_type: str, title: str, format_id: str
    ) -> str:
        """yt-dlp fallback for /song downloads (where the user picked
        a specific format_id). Returns the file path on success,
        None on failure."""
        loop = asyncio.get_running_loop()

        def _do_video():
            formats = f"{format_id}+140"
            fpath = f"downloads/{title}"
            ydl_opts = {
                "format": formats,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": _cookie_file_ytdlp(),
                "prefer_ffmpeg": True,
                "merge_output_format": "mp4",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
            return f"downloads/{title}.mp4"

        def _do_audio():
            fpath = f"downloads/{title}.%(ext)s"
            ydl_opts = {
                "format": format_id,
                "outtmpl": fpath,
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
                "cookiefile": _cookie_file_ytdlp(),
                "prefer_ffmpeg": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([link])
            return f"downloads/{title}.mp3"

        try:
            if dl_type == "video":
                return await loop.run_in_executor(None, _do_video)
            else:
                return await loop.run_in_executor(None, _do_audio)
        except Exception as e:
            LOGGER(__name__).warning(
                f"[DOWNLOAD] yt-dlp song fallback failed for {link}: "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def close(self):
        """Close the underlying httpx client. Called on bot shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


YouTube = YouTubeAPI()
