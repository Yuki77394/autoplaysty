from SWAGGYMUSIC.core.bot import Swaggy
from SWAGGYMUSIC.core.dir import dirr
from SWAGGYMUSIC.core.git import git
from SWAGGYMUSIC.core.userbot import Userbot
from SWAGGYMUSIC.misc import dbb, heroku

from SafoneAPI import SafoneAPI
from .logging import LOGGER

dirr()
git()
dbb()
heroku()

app = Swaggy()
api = SafoneAPI()
userbot = Userbot()


from .platforms import *

Apple = AppleAPI()
Carbon = CarbonAPI()
SoundCloud = SoundAPI()
Spotify = SpotifyAPI()
Resso = RessoAPI()
Telegram = TeleAPI()
YouTube = YouTubeAPI()
