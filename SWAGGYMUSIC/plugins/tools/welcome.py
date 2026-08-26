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

_log = LOGGER(__name__)

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
        _log.error(f"get_welcome db error for {chat_id}: {e}")
        return True


async def enable_welcome(chat_id: int):
    try:
        await welcomedb.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome": True}},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"enable_welcome db error: {e}")


async def disable_welcome(chat_id: int):
    try:
        await welcomedb.update_one(
            {"chat_id": chat_id},
            {"$set": {"welcome": False}},
            upsert=True,
        )
    except Exception as e:
        _log.error(f"disable_welcome db error: {e}")


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
# Frame dimensions measured from wel2.png (1734x907 background):
#   Circular gold frame center: (457, 409)
#   Dark circle interior radius: 178 px  →  diameter 356 px
#   Gold ring: inner r≈187, outer r≈238, thickness ≈52 px
_CIRCLE_SIZE = (354, 354)
_CIRCLE_PASTE_POS = (280, 232)  # center(457,409) - radius(177)

# Text layout measured from the template's pre-printed labels on wel2.png (1734x907):
#   Both "User id :" and "Username :" are pre-printed on the template.
#   Labels are left-aligned at x≈814, rendered with font2.ttf at 34px.
#   "User id :" draw-y ≈ 763, colon ends at x ≈ 944.
#   "Username :" draw-y ≈ 808, colon ends at x ≈ 998.
#   DO NOT redraw the static labels — only render the dynamic values.
_TEXT_FONT_SIZE = 34
_TEXT_COLOR = (230, 210, 160)  # gold, matches the template's pre-printed label
_LABEL_X = 814
_UID_LABEL_Y = 763
_UNAME_LABEL_Y = 808
_VALUE_GAP = 12
_MAX_TEXT_X = 1380  # right boundary for text truncation


def _circle(pfp, size=None, brightness_factor=1.4):
    if size is None:
        size = _CIRCLE_SIZE
    # Center-crop to square first so rectangular photos aren't stretched
    w, h = pfp.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    pfp = pfp.crop((left, top, left + min_dim, top + min_dim))
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
    pfp = _circle(pfp, size=_CIRCLE_SIZE, brightness_factor=1.3)
    background.paste(pfp, _CIRCLE_PASTE_POS, pfp)

    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype(_FONT_PATH, _TEXT_FONT_SIZE)

    # User ID value — placed right after the template's pre-printed "User id :" colon
    uid_label_bbox = font.getbbox("User id :")
    uid_val_x = _LABEL_X + uid_label_bbox[2] + _VALUE_GAP
    draw.text((uid_val_x, _UID_LABEL_Y), str(user_id), font=font, fill=_TEXT_COLOR)

    # Username value — placed right after the template's pre-printed "Username :" colon
    uname_label_bbox = font.getbbox("Username :")
    uname_val_x = _LABEL_X + uname_label_bbox[2] + _VALUE_GAP
    uname_val = f"@{username}" if username else "No Username"

    # Truncate long usernames to stay within _MAX_TEXT_X
    uname_val_w = font.getbbox(uname_val)[2]
    if uname_val_x + uname_val_w > _MAX_TEXT_X:
        while len(uname_val) > 3:
            test = uname_val + "..."
            if font.getbbox(test)[2] + uname_val_x <= _MAX_TEXT_X:
                uname_val = test
                break
            uname_val = uname_val[:-1]
        else:
            uname_val += "..."

    draw.text((uname_val_x, _UNAME_LABEL_Y), uname_val, font=font, fill=_TEXT_COLOR)

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
        _log.error(f"welcome cmd perm check error: {e}")
        return

    try:
        state = await get_welcome(chat_id)
    except Exception as e:
        _log.error(f"welcome get_welcome error: {e}")
        state = True

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

    try:
        await message.reply_text(
            f"» ᴄᴜʀʀᴇɴᴛʟʏ ᴡᴇʟᴄᴏᴍᴇ ꜱᴛᴀᴛᴜꜱ **{status}** ɪɴ **{chat.title}**",
            reply_markup=btn,
        )
    except Exception as e:
        _log.error(f"welcome failed to send reply: {e}")


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
        _log.error(f"welcome toggle perm check error: {e}")
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
        _log.error(f"welcome toggle edit error: {e}")

    await query.answer()


# ─── New member detection & welcome image generation ────────────────────────
# NOTE: No filters.group here — we check chat type inside the handler.
# This avoids any subtle compatibility issues between filters.group
# and ChatMemberUpdated objects across Pyrogram versions.
@app.on_chat_member_updated(group=-3)
async def greet_new_member(client, member: ChatMemberUpdated):
    chat_id = member.chat.id
    user_id = member.new_chat_member.user.id if member.new_chat_member and member.new_chat_member.user else None
    # Only process supergroups and basic groups
    if member.chat.type not in (enums.ChatType.SUPERGROUP, enums.ChatType.GROUP):
        return

    # Check if welcome is enabled for this chat
    try:
        is_enabled = await get_welcome(chat_id)
    except Exception as e:
        _log.error(f"welcome get_welcome error: {e}")
        is_enabled = True

    if not is_enabled:
        return

    new_cm = member.new_chat_member
    old_cm = member.old_chat_member

    if not new_cm or not new_cm.user:
        return

    # ── Member-join detection ──
    # Detect actual joins:
    # - User was LEFT or BANNED, now is MEMBER, ADMINISTRATOR, or RESTRICTED
    try:
        if old_cm is None:
            return

        old_status_val = old_cm.status
        new_status_val = new_cm.status

        is_join = (
            new_status_val
            in (
                enums.ChatMemberStatus.MEMBER,
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.RESTRICTED,
            )
            and old_status_val
            in (
                enums.ChatMemberStatus.LEFT,
                enums.ChatMemberStatus.BANNED,
            )
        )

        if not is_join:
            return

    except Exception as e:
        _log.error(f"welcome status check error: {e}")
        return

    user = new_cm.user

    # ── Download profile photo with fallback ──
    pic_path = _FALLBACK_PIC
    downloaded_pic = None
    try:
        if user.photo and user.photo.big_file_id:
            downloaded_pic = os.path.join(_DOWNLOADS_DIR, f"pp{user.id}.png")
            await client.download_media(
                user.photo.big_file_id, file_name=downloaded_pic
            )
            pic_path = downloaded_pic
    except Exception as e:
        _log.warning(f"welcome pfp download failed for {user.id}: {e}")

    # ── Delete previous welcome message for this chat ──
    old_msg = _temp.PREV_MSG.get(f"welcome-{chat_id}")
    if old_msg:
        try:
            await old_msg.delete()
        except Exception:
            pass

    # ── Generate welcome image ──
    welcome_img_path = None
    try:
        welcome_img_path = _generate_welcome_image(pic_path, user.id, user.username)
    except Exception as e:
        _log.error(f"welcome image generation failed for {user.id}: {e}")
        if downloaded_pic and os.path.exists(downloaded_pic):
            try:
                os.remove(downloaded_pic)
            except Exception:
                pass
        return

    # ── Send welcome message ──
    try:
        username_display = f"@{user.username}" if user.username else "No Username"
        msg = await client.send_photo(
            chat_id,
            photo=welcome_img_path,
            caption=f"""
**⏤͟͟͞͞★ ʜᴇʟʟᴏ ᴅᴇᴀʀ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ : {member.chat.title}**

<u>**❖ ᴜsᴇʀ sʜᴏʀᴛ ɪɴғᴏ**</u>

**➻ ɴᴀᴍᴇ »** {user.mention}
**➻ ᴜsᴇʀ_ɪᴅ »** `{user.id}`
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
        _log.error(f"welcome failed to send message: {e}")

    finally:
        if downloaded_pic and os.path.exists(downloaded_pic):
            try:
                os.remove(downloaded_pic)
            except Exception:
                pass


# ─── BACKUP: Also listen via on_message(new_chat_members) ──────────────────
# In some Pyrogram/Telegram API versions, on_chat_member_updated may not
# fire reliably. This backup catches the service message that Telegram sends
# when members join. Uses group=-4 to avoid conflicts with start.py (group=-1)
# and chatlog.py (group=2).
@app.on_message(filters.new_chat_members, group=-4)
async def welcome_backup(client, message: Message):
    for new_user in message.new_chat_members:
        # Skip bot itself (handled by start.py)
        if new_user.id == app.id:
            continue

        chat_id = message.chat.id

        try:
            is_enabled = await get_welcome(chat_id)
        except Exception as e:
            _log.error(f"welcome backup get_welcome error: {e}")
            is_enabled = True

        if not is_enabled:
            continue

        user = new_user

        pic_path = _FALLBACK_PIC
        downloaded_pic = None
        try:
            if user.photo and user.photo.big_file_id:
                downloaded_pic = os.path.join(_DOWNLOADS_DIR, f"pp{user.id}.png")
                await client.download_media(
                    user.photo.big_file_id, file_name=downloaded_pic
                )
                pic_path = downloaded_pic
        except Exception as e:
            _log.warning(f"welcome backup pfp download failed: {e}")

        old_msg = _temp.PREV_MSG.get(f"welcome-{chat_id}")
        if old_msg:
            try:
                await old_msg.delete()
            except Exception:
                pass

        welcome_img_path = None
        try:
            welcome_img_path = _generate_welcome_image(
                pic_path, user.id, user.username
            )
        except Exception as e:
            _log.error(f"welcome backup image gen failed: {e}")
            if downloaded_pic and os.path.exists(downloaded_pic):
                try:
                    os.remove(downloaded_pic)
                except Exception:
                    pass
            continue

        try:
            username_display = f"@{user.username}" if user.username else "No Username"
            msg = await client.send_photo(
                chat_id,
                photo=welcome_img_path,
                caption=f"""
**⏤͟͟͞͞★ ʜᴇʟʟᴏ ᴅᴇᴀʀ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ : {message.chat.title}**

<u>**❖ ᴜsᴇʀ sʜᴏʀᴛ ɪɴғᴏ**</u>

**➻ ɴᴀᴍᴇ »** {user.mention}
**➻ ᴜsᴇʀ_ɪᴅ »** `{user.id}`
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

            async def _del():
                await asyncio.sleep(10)
                try:
                    await msg.delete()
                except Exception:
                    pass

            asyncio.create_task(_del())
            _temp.PREV_MSG[f"welcome-{chat_id}"] = msg

        except Exception as e:
            _log.error(f"welcome backup send failed: {e}")

        finally:
            if downloaded_pic and os.path.exists(downloaded_pic):
                try:
                    os.remove(downloaded_pic)
                except Exception:
                    pass
