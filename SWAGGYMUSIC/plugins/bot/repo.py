from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from SWAGGYMUSIC import app
from config import BOT_USERNAME
from SWAGGYMUSIC.utils.errors import capture_err
import httpx 
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

start_txt = """**
<u>❃ ᴡєʟᴄσϻє ᴛᴏ sᴘɪᴄʏ ɴєᴛᴡσʀᴋ ʀєᴘσs ❃</u>
 
✼ ʀєᴘᴏ ɪs ηᴏᴡ ᴘʀɪᴠᴧᴛє ᴅᴜᴅє 😌
 
❉  ʏᴏᴜ ᴄᴧη мʏ ᴜsє ᴘᴜʙʟɪᴄ ʀєᴘσs !!  

✼ || [˹sᴘɪᴄʏ ꭙ ɴᴇᴛᴡᴏʀᴋ˼ 💞](https://t.me/SpicyXNetwork) ||
 
❊ ʀᴜη 24x7 ʟᴧɢ ϝʀєє ᴡɪᴛʜσᴜᴛ sᴛσᴘ**
"""




@app.on_message(filters.command("repo"))
async def start(_, msg):
    buttons = [
        [ 
          InlineKeyboardButton("✙ ᴧᴅᴅ ϻє вᴧʙʏ ✙", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")
        ],
        [
          InlineKeyboardButton("• ɴєᴛᴡᴏʀᴋ •", url="https://t.me/SpicyXNetwork"),
          InlineKeyboardButton("• 𝛅ᴜᴘᴘσʀᴛ •", url="https://t.me/+gXCu09qmgwA0NjA9"),
          ],
[
InlineKeyboardButton("• ᴧʟʟ ʙσᴛѕ •", url=f"https://t.me/SpIcYxNeTwOrK/12"),

        ]]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await msg.reply_photo(
        photo="https://litter.catbox.moe/xr9jf82b2umeke7j.jpg",
        caption=start_txt,
        reply_markup=reply_markup
    )
