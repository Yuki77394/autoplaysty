from datetime import datetime
from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from SWAGGYMUSIC import app
from SWAGGYMUSIC.core.call import Swaggy
from SWAGGYMUSIC.utils import bot_sys_stats
from SWAGGYMUSIC.utils.decorators.language import language
from SWAGGYMUSIC.utils.inline import supp_markup
from SWAGGYMUSIC.utils.inline import close_markup
from config import BANNED_USERS




@app.on_message(filters.command("ping", prefixes=["/", "!"]) & ~BANNED_USERS)
@language
async def ping_com(client, message: Message, _):
    start = datetime.now()
    response = await message.reply_video(
        video="https://litter.catbox.moe/zmybs6tifcxdpl0r.mp4",
        caption=_["ping_1"].format(app.mention),
    )
    pytgping = await Swaggy.ping()
    UP, CPU, RAM, DISK = await bot_sys_stats()
    resp = (datetime.now() - start).microseconds / 1000
    await response.edit_text(
        _["ping_2"].format(resp, app.mention, UP, RAM, CPU, DISK, pytgping),
        reply_markup=supp_markup(_),
    )
    
