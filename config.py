import re
from os import getenv
from dotenv import load_dotenv
from pyrogram import filters

load_dotenv()

API_ID = int(getenv("API_ID"))
API_HASH = getenv("API_HASH")

BOT_TOKEN = getenv("BOT_TOKEN")
OWNER_USERNAME = getenv("OWNER_USERNAME","swaggy_Rajput")
BOT_USERNAME = getenv("BOT_USERNAME" , "ShubhuMusicBot")
BOT_NAME = getenv("BOT_NAME" , "˹𝑺𝒉𝒖𝒃𝒉𝒖 𝑴𝒖𝒔𝒊𝒄 𝑩𝒐𝒕")
ASSUSERNAME = getenv("ASSUSERNAME" , "Assistant4Shubhu")
MONGO_DB_URI = getenv("MONGO_DB_URI", None)
DURATION_LIMIT_MIN = int(getenv("DURATION_LIMIT", 17000))
LOGGER_ID = int(getenv("LOGGER_ID", 0))
OWNER_ID = int(getenv("OWNER_ID", None))
HEROKU_APP_NAME = getenv("HEROKU_APP_NAME")
HEROKU_API_KEY = getenv("HEROKU_API_KEY")
UPSTREAM_REPO = getenv("UPSTREAM_REPO", "https://github.com/Yuki77394/autoplaysty",)
UPSTREAM_BRANCH = getenv("UPSTREAM_BRANCH", "main")
GIT_TOKEN = getenv("GIT_TOKEN", None)

#API_URL = getenv("API_URL", 'https://pytdbotapi.thequickearn.xyz') #youtube song url
#VIDEO_API_URL = getenv("VIDEO_API_URL", 'https://api.video.thequickearn.xyz')

# --- New YouTube API (yt.riteshyt.in) -----------------------------------
# Primary backend for YouTube search / metadata / thumbnail / download.
# Used by SWAGGYMUSIC/platforms/Youtube.py. Falls back to
# youtubesearchpython + yt-dlp if these are unset or the API is down.
# Override in Heroku config vars if you have your own API instance.
YOUTUBE_API_URL = getenv("API_URL", "http://yt.riteshyt.in")
YOUTUBE_API_KEY = getenv("API_KEY", "riteshfree576fd88ed84a3f46c84fd556")

# Vars For API End Pont.
ARC_API_URL = getenv("ARC_API_URL", "https://api.arcmusic.fun")
ARC_API_KEY = getenv("ARC_API_KEY", "ARCbb2204210054d2c25478e9")

PRIVACY_LINK = getenv("PRIVACY_LINK", "")
SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/SpicyxNetwork")
SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/ChatropolisGc")
SUPPORT_GROUP = getenv("SUPPORT_GROUP", SUPPORT_CHAT)
AUTO_LEAVING_ASSISTANT = getenv("AUTO_LEAVING_ASSISTANT", "False")
AUTO_LEAVE_ASSISTANT_TIME = int(getenv("ASSISTANT_LEAVE_TIME", "9000"))
SONG_DOWNLOAD_DURATION = int(getenv("SONG_DOWNLOAD_DURATION", "9999999"))
SONG_DOWNLOAD_DURATION_LIMIT = int(getenv("SONG_DOWNLOAD_DURATION_LIMIT", "9999999"))
SPOTIFY_CLIENT_ID = getenv("SPOTIFY_CLIENT_ID", "1c21247d714244ddbb09925dac565aed")
SPOTIFY_CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET", "709e1a2969664491b58200860623ef19")
PLAYLIST_FETCH_LIMIT = int(getenv("PLAYLIST_FETCH_LIMIT", 25))
TG_AUDIO_FILESIZE_LIMIT = int(getenv("TG_AUDIO_FILESIZE_LIMIT", "5242880000"))
TG_VIDEO_FILESIZE_LIMIT = int(getenv("TG_VIDEO_FILESIZE_LIMIT", "5242880000"))
STRING1 = getenv("STRING_SESSION", None)
STRING2 = getenv("STRING_SESSION2", None)
STRING3 = getenv("STRING_SESSION3", None)
STRING4 = getenv("STRING_SESSION4", None)
STRING5 = getenv("STRING_SESSION5", None)
STRING6 = getenv("STRING_SESSION6", None)
STRING7 = getenv("STRING_SESSION7", None)
BANNED_USERS = filters.user()
adminlist = {}
lyrical = {}
votemode = {}
autoclean = []
confirmer = {}
START_IMG_URL = getenv("START_IMG_URL", "https://litter.catbox.moe/xr9jf82b2umeke7j.jpg")
PING_IMG_URL = getenv("PING_IMG_URL", "https://litter.catbox.moe/xyedznhk80hmial2.mp4")
PLAYLIST_IMG_URL = "https://litter.catbox.moe/o91jli53b2qn87v4.jpg"
STATS_IMG_URL = "https://litter.catbox.moe/mzciup11cxe1d6wt.jpg"
TELEGRAM_AUDIO_URL = "https://litter.catbox.moe/7x4b2jc2e6pz6pky.jpg"
TELEGRAM_VIDEO_URL = "https://litter.catbox.moe/7x4b2jc2e6pz6pky.jpg"
STREAM_IMG_URL = "https://telegra.ph/file/d30d11c4365c025c25e3e.jpg"
SOUNCLOUD_IMG_URL = "https://telegra.ph/file/d30d11c4365c025c25e3e.jpg"
YOUTUBE_IMG_URL = "https://files.catbox.moe/34xlvu.jpg"
SPOTIFY_ARTIST_IMG_URL = "https://files.catbox.moe/2y5o3g.jpg"
SPOTIFY_ALBUM_IMG_URL = "https://files.catbox.moe/2y5o3g.jpg"
SPOTIFY_PLAYLIST_IMG_URL = "https://telegra.ph/file/d30d11c4365c025c25e3e.jpg"
def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))
DURATION_LIMIT = int(time_to_seconds(f"{DURATION_LIMIT_MIN}:00"))
if SUPPORT_CHANNEL:
    if not re.match("(?:http|https)://", SUPPORT_CHANNEL):
        raise SystemExit(
            "[ERROR] - Your SUPPORT_CHANNEL url is wrong. Please ensure that it starts with https://"
        )

if SUPPORT_CHAT:
    if not re.match("(?:http|https)://", SUPPORT_CHAT):
        raise SystemExit(
            "[ERROR] - Your SUPPORT_CHAT url is wrong. Please ensure that it starts with https://"
        )
