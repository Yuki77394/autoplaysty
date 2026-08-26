from pyrogram import filters
from pyrogram.types import Message

from SWAGGYMUSIC import app
from SWAGGYMUSIC.core.call import Swaggy
from SWAGGYMUSIC.utils.database import autoplay_off, set_loop
from SWAGGYMUSIC.utils.decorators import AdminRightsCheck
from SWAGGYMUSIC.utils.inline import close_markup
from config import BANNED_USERS


@app.on_message(
    filters.command(["end", "stop", "cend", "cstop"], prefixes=["/", "!", "%", ",", "", ".", "@", "#"]) & filters.group & ~BANNED_USERS
)
@AdminRightsCheck
async def stop_music(cli, message: Message, _, chat_id):
    if not len(message.command) == 1:
        return
    await Swaggy.stop_stream(chat_id)
    await set_loop(chat_id, 0)
    # Reset autoplay for this chat so the next /play starts fresh — matches
    # the /autoplay help text: "autoplay setting resets when music ended
    # or stopped by someone".
    try:
        await autoplay_off(chat_id)
    except Exception:
        pass
    await message.reply_text(
        _["admin_5"].format(message.from_user.mention), reply_markup=close_markup(_)
    )
