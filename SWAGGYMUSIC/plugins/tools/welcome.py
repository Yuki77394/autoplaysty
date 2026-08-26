from SWAGGYMUSIC import app
from SWAGGYMUSIC.core.mongo import mongodb
from SWAGGYMUSIC.logging import LOGGER

from pyrogram import filters, enums
from pyrogram.types import (
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)

from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import asyncio
import os

# ─── MongoDB: reuse existing connection, dedicated collection ───────────────
welcomedb = mongodb.welcome_toggle


# ─── Welcome DB helpers ─────────────────────────────────────────────────────
async def get_welcome(chat_id: int) -> bool:
    try:
        data = await welcomedb.find_one({"chat_id": chat_id})
        if not data:
            return True  # default: enabled
        return data.get("welcome", True)
    except Exception as e:
        LOGGER(__name__).error(f"get_welcome db error: {e}")
        return True


async def enable_welcome(chat_id: int):
    try:
        await welcomedb.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome": True}},
            upsert=True,
        )
    except Exception as e:
        LOGGER(__name__).error(f"enable_welcome db error: {e}")


async def disable_welcome(chat_id: int):
    try:
        await welcomedb.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome": False}},
            upsert=True,
        )
    except Exception as e:
        LOGGER(__name__).error(f"disable_welcome db error: {e}")


# ─── In-memory store for auto-deleting previous welcome messages ────────────
class _WelcomeTemp:
    PREV_MSG = {}


_temp = _WelcomeTemp()


# ─── Asset paths (relative to CWD, same as other target plugins) ────────────
_WEL2_BG = os.path.join("SWAGGYMUSIC", "assets", "wel2.png")
_FALLBACK_PIC = os.path.join("SWAGGYMUSIC", "assets", "upic.png")
_FONT_PATH = os.path.join("SWAGGYMUSIC", "assets", "font2.ttf")
_DOWNLOADS_DIR = "downloads"


# ─── Image helpers ──────────────────────────────────────────────────────────
def _circle(pfp, size=(720, 720), brightness_factor=1.4):
    pfp = pfp.resize(size).convert("RGBA")
    pfp = ImageEnhance.Brightness(pfp).enhance(brightness_factor)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)
    pfp.putalpha(mask)
    return pfp


def _generate_welcome_image(pic_path, user_id, username):
    background = Image.open(_WEL2_BG).convert("RGBA")
    pfp = Image.open(pic_path).convert("RGBA")
    pfp = _circle(pfp, size=(720, 720), brightness_factor=1.3)
    background.paste(pfp, (520, 420), pfp)

    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(_FONT_PATH, 100)

    username_text = f"@{username}" if username else "Not Set"
    draw.text((1920, 1340), str(user_id), font=font, fill="#ffffff")
    draw.text((1920, 1480), username_text, font=font, fill="#ffffff")

    os.makedirs(_DOWNLOADS_DIR, exist_ok=True)
    output_path = os.path.join(_DOWNLOADS_DIR, f"welcome_{user_id}.png")
    background.save(output_path)
    return output_path


# ─── /welcome command ──────────────────────────────────────────────────────
@app.on_message(filters.command("welcome") & filters.group)
async def welcome_cmd(client, message: Message):
    chat = message.chat
    chat_id = chat.id

    try:
        user = await client.get_chat_member(chat_id, message.from_user.id)
        if user.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ):
            return await message.reply_text(
                "**» ᴏɴʟʏ ᴀᴅᴍɪɴꜱ ᴄᴀɴ ʜᴀɴᴅʟᴇ ᴡᴇʟᴄᴏᴍᴇ ꜱʏꜱᴛᴇᴍ**"
            )
    except Exception as e:
        LOGGER(__name__).error(f"welcome_cmd perm check error: {e}")
        return

    state = await get_welcome(chat_id)
    status = "ᴇɴᴀʙʟᴇᴅ" if state else "ᴅɪꜱᴀʙʟᴇᴅ"

    btn = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "ᴇɴᴀʙʟᴇ", callback_data=f"wlc_on_{chat_id}"
                ),
                InlineKeyboardButton(
                    "ᴅɪꜱᴀʙʟᴇ", callback_data=f"wlc_off_{chat_id}"
                ),
            ]
        ]
    )

    await message.reply_text(
        f"» ᴄᴜʀʀᴇɴᴛʟʏ ᴡᴇʟᴄᴏᴍᴇ ꜱᴛᴀᴛᴜꜱ **{status}** ɪɴ **{chat.title}**",
        reply_markup=btn,
    )


# ─── Callback handler for enable/disable buttons ──────────────────────────
@app.on_callback_query(filters.regex(r"^wlc_"))
async def welcome_toggle(client, query):
    try:
        data = query.data.split("_")
        action = data[1]
        chat_id = int(data[2])
    except (IndexError, ValueError):
        await query.answer("Invalid callback data", show_alert=True)
        return

    try:
        member = await client.get_chat_member(chat_id, query.from_user.id)
        if member.status not in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER,
        ):
            return await query.answer(
                "ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴅᴍɪɴ ʙᴀʙʏ 🥺", show_alert=True
            )
    except Exception as e:
        LOGGER(__name__).error(f"welcome_toggle perm check error: {e}")
        await query.answer("Permission check failed", show_alert=True)
        return

    if action == "on":
        await enable_welcome(chat_id)
        new_status = "ᴇɴᴀʙʟᴇᴅ"
    else:
        await disable_welcome(chat_id)
        new_status = "ᴅɪꜱᴀʙʟᴇᴅ"

    try:
        chat = await client.get_chat(chat_id)
        chat_title = chat.title or "this group"
    except Exception:
        chat_title = "this group"

    try:
        await query.message.edit_text(
            f"» ᴡᴇʟᴄᴏᴍᴇ ᴍᴇꜱꜱᴀɢᴇ **{new_status}** ɪɴ **{chat_title}** "
            f"ʙʏ :- **{query.from_user.mention}**"
        )
    except Exception as e:
        LOGGER(__name__).error(f"welcome_toggle edit error: {e}")

    await query.answer()


# ─── New member detection & welcome image generation ────────────────────────
@app.on_chat_member_updated(filters.group, group=-3)
async def greet_new_member(client, member: ChatMemberUpdated):
    chat_id = member.chat.id

    # Check if welcome is enabled for this chat (DB call wrapped in try/except)
    is_enabled = await get_welcome(chat_id)
    if not is_enabled:
        return

    new_cm = member.new_chat_member
    old_cm = member.old_chat_member

    if not new_cm or not new_cm.user:
        return

    # ── Fixed member-join detection for Pyrogram 2.0.106 ──
    # Detect: user was LEFT or BANNED, now is MEMBER or ADMINISTRATOR.
    # This correctly handles normal joins, re-joins, and unbans.
    # It excludes kicks (member->banned) and leaves (member->left).
    try:
        old_status = old_cm.status if old_cm else None
        new_status = new_cm.status

        is_join = (
            new_status
            in (
                enums.ChatMemberStatus.MEMBER,
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.RESTRICTED,
            )
            and old_status
            in (
                enums.ChatMemberStatus.LEFT,
                enums.ChatMemberStatus.BANNED,
            )
        )

        if not is_join:
            return
    except Exception as e:
        LOGGER(__name__).error(f"welcome status check error: {e}")
        return

    user = new_cm.user

    # ── Download profile photo with fallback ──
    pic_path = _FALLBACK_PIC
    downloaded_pic = None
    try:
        if user.photo and user.photo.big_file_id:
            downloaded_pic = os.path.join(
                _DOWNLOADS_DIR, f"pp{user.id}.png"
            )
            await client.download_media(
                user.photo.big_file_id, file_name=downloaded_pic
            )
            pic_path = downloaded_pic
    except Exception as e:
        LOGGER(__name__).warning(
            f"Failed to download profile photo for {user.id}: {e}. "
            f"Using fallback image."
        )

    # ── Delete previous welcome message for this chat (if any) ──
    old_msg = _temp.PREV_MSG.get(f"welcome-{chat_id}")
    if old_msg:
        try:
            await old_msg.delete()
        except Exception:
            pass

    # ── Generate welcome image ──
    welcome_img_path = None
    try:
        welcome_img_path = _generate_welcome_image(
            pic_path, user.id, user.username
        )
    except Exception as e:
        LOGGER(__name__).error(
            f"Welcome image generation failed for {user.id}: {e}"
        )
        # Clean up downloaded pic if image gen failed
        if downloaded_pic and os.path.exists(downloaded_pic):
            try:
                os.remove(downloaded_pic)
            except Exception:
                pass
        return  # Don't send text-only fallback to avoid partial experience

    # ── Send welcome message ──
    try:
        username_display = f"@{user.username}" if user.username else "N/A"
        msg = await client.send_photo(
            chat_id,
            photo=welcome_img_path,
            caption=f"""
**⏤͟͟͞͞★ ʜᴇʟʟᴏ ᴅᴇᴀʀ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ : {member.chat.title}**

<u>**❖ ᴜsᴇʀ sʜᴏʀᴛ ɪɴғᴏ**</u>

**➻ ɴᴀᴍᴇ »** {user.mention}
**➻ ᴄʜᴀᴛ_ɪᴅ »** `{user.id}`
**➻ ᴜ_ɴᴀᴍᴇ »** {username_display}

**➻ ᴛʜᴀɴᴋs ғᴏʀ ᴊᴏɪɴɪɴɢ ᴜs ⚡️~!
❅─────✧❅✦❅✧─────❅**
""",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ",
                            url=f"https://t.me/{client.username}?startgroup=true",
                        )
                    ]
                ]
            ),
        )

        # ── Schedule auto-delete after 10 seconds ──
        async def _delete_welcome():
            await asyncio.sleep(10)
            try:
                await msg.delete()
                key = f"welcome-{chat_id}"
                if key in _temp.PREV_MSG:
                    del _temp.PREV_MSG[key]
            except Exception:
                pass

        asyncio.create_task(_delete_welcome())
        _temp.PREV_MSG[f"welcome-{chat_id}"] = msg

    except Exception as e:
        LOGGER(__name__).error(f"Failed to send welcome message: {e}")

    finally:
        # Clean up downloaded profile photo to avoid accumulating files
        if downloaded_pic and os.path.exists(downloaded_pic):
            try:
                os.remove(downloaded_pic)
            except Exception:
                pass
