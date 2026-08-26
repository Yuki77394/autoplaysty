"""
/autoplay command + inline toggle button - ported from Meera Music.

Provides /autoplay [on|off] and /aplay [on|off] commands and an inline
✅/❌ toggle. State is stored in the DB-backed autoplaydb/autoplaycache
(same source of truth as the 📩 AutoPlay button and the natural
song-end / skip handlers).
"""

from pyrogram import enums, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from SWAGGYMUSIC import app
from SWAGGYMUSIC.utils.database import autoplay_off, autoplay_on, is_autoplay_on
from config import BANNED_USERS


def autoplay_markup(chat_id: int, status: bool):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="✅ ᴇɴᴀʙʟᴇᴅ" if status else "ᴇɴᴀʙʟᴇ ✅",
                    callback_data=f"autoplay_on_{chat_id}",
                ),
                InlineKeyboardButton(
                    text="ᴅɪsᴀʙʟᴇ ❌" if status else "❌ ᴅɪsᴀʙʟᴇᴅ",
                    callback_data=f"autoplay_off_{chat_id}",
                ),
            ]
        ]
    )


def autoplay_text(status: bool) -> str:
    return (
        "**🎧 ᴀᴜᴛᴏᴘʟᴀʏ sᴇᴛᴛɪɴɢs**\n\n"
        f"**ᴄᴜʀʀᴇɴᴛ sᴛᴀᴛᴜs :** {'✅ ᴏɴ' if status else '❌ ᴏꜰꜰ'}\n\n"
        "**ᴡʜᴇɴ ᴇɴᴀʙʟᴇᴅ**, ᴛʜᴇ ʙᴏᴛ ᴡɪʟʟ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴘʟᴀʏ ᴀ ʀᴀɴᴅᴏᴍ ʀᴇʟᴀᴛᴇᴅ sᴏɴɢ ᴏɴᴄᴇ ᴛʜᴇ ǫᴜᴇᴜᴇ ᴇɴᴅs, ɪɴsᴛᴇᴀᴅ ᴏꜰ ʟᴇᴀᴠɪɴɢ ᴛʜᴇ ᴠᴏɪᴄᴇ ᴄʜᴀᴛ.\n"
        "ɪᴛ ɴᴇᴠᴇʀ ʀᴇᴘᴇᴀᴛs ᴀ sᴏɴɢ ᴀʟʀᴇᴀᴅʏ ᴘʟᴀʏᴇᴅ, ᴀɴᴅ /skip ᴡɪʟʟ sᴋɪᴘ ᴀᴜᴛᴏᴘʟᴀʏ ᴛᴏᴏ.\n\n"
        "ᴛᴏɢɢʟᴇ ɪᴛ ᴜsɪɴɢ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ 👇"
    )


async def _is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await app.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    )


@app.on_message(
    filters.command(["autoplay", "aplay"]) & filters.group & ~BANNED_USERS
)
async def autoplay_cmd(client, message: Message):
    chat_id = message.chat.id

    if len(message.command) > 1 and message.from_user:
        if not await _is_admin(chat_id, message.from_user.id):
            return await message.reply_text(
                "❌ **ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴛᴏɢɢʟᴇ ᴀᴜᴛᴏᴘʟᴀʏ.**"
            )
        mode = message.command[1].lower()
        if mode in ("on", "enable"):
            await autoplay_on(chat_id)
            return await message.reply_text("✅ **ᴀᴜᴛᴏᴘʟᴀʏ ᴇɴᴀʙʟᴇᴅ ꜰᴏʀ ᴛʜɪs ᴄʜᴀᴛ.**")
        if mode in ("off", "disable"):
            await autoplay_off(chat_id)
            return await message.reply_text("❌ **ᴀᴜᴛᴏᴘʟᴀʏ ᴅɪsᴀʙʟᴇᴅ ꜰᴏʀ ᴛʜɪs ᴄʜᴀᴛ.**")
        return await message.reply_text(
            "**ᴜsᴀɢᴇ :**\n`/autoplay on`\n`/autoplay off`"
        )

    status = await is_autoplay_on(chat_id)
    await message.reply_text(
        autoplay_text(status),
        reply_markup=autoplay_markup(chat_id, status),
    )


@app.on_callback_query(
    filters.regex(r"^autoplay_(on|off)_(-?\d+)$") & ~BANNED_USERS
)
async def autoplay_toggle_cb(client, query: CallbackQuery):
    action, chat_id = query.matches[0].group(1), int(query.matches[0].group(2))

    if query.message.chat.id != chat_id:
        return await query.answer(
            "❌ ᴛʜɪs ʙᴜᴛᴛᴏɴ ɪs ɴᴏᴛ ꜰᴏʀ ᴛʜɪs ᴄʜᴀᴛ.", show_alert=True
        )
    if not await _is_admin(chat_id, query.from_user.id):
        return await query.answer(
            "❌ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴛᴏɢɢʟᴇ ᴛʜɪs.", show_alert=True
        )

    if action == "on":
        await autoplay_on(chat_id)
        status = True
        await query.answer("✅ ᴀᴜᴛᴏᴘʟᴀʏ ᴇɴᴀʙʟᴇᴅ")
    else:
        await autoplay_off(chat_id)
        status = False
        await query.answer("❌ ᴀᴜᴛᴏᴘʟᴀʏ ᴅɪsᴀʙʟᴇᴅ")

    try:
        await query.message.edit_text(
            autoplay_text(status),
            reply_markup=autoplay_markup(chat_id, status),
        )
    except Exception:
        pass
