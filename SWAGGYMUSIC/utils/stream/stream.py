import asyncio
import os
from random import randint
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from SWAGGYMUSIC import Carbon, YouTube, app
from SWAGGYMUSIC.core.call import Swaggy
from SWAGGYMUSIC.misc import db
from SWAGGYMUSIC.utils.database import add_active_video_chat, is_active_chat, is_autoplay_on, is_thumb_on
from SWAGGYMUSIC.utils.exceptions import AssistantErr
from SWAGGYMUSIC.utils.inline import aq_markup, close_markup, stream_markup
from SWAGGYMUSIC.utils.pastebin import SwaggyBin
from SWAGGYMUSIC.utils.stream.queue import put_queue, put_queue_index
from SWAGGYMUSIC.utils.thumbnails import get_thumb


async def stream(
    _,
    mystic,
    user_id,
    result,
    chat_id,
    user_name,
    original_chat_id,
    video: Union[bool, str] = None,
    streamtype: Union[bool, str] = None,
    spotify: Union[bool, str] = None,
    forceplay: Union[bool, str] = None,
):
    if not result:
        return
    if forceplay:
        await Swaggy.force_stop_stream(chat_id)
    if streamtype == "playlist":
        msg = f"{_['play_19']}\n\n"
        count = 0
        for search in result:
            if int(count) == config.PLAYLIST_FETCH_LIMIT:
                continue
            try:
                (
                    title,
                    duration_min,
                    duration_sec,
                    thumbnail,
                    vidid,
                ) = await YouTube.details(search, False if spotify else True)
            except:
                continue
            if str(duration_min) == "None":
                continue
            if duration_sec > config.DURATION_LIMIT:
                continue
            if await is_active_chat(chat_id):
                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                )
                position = len(db.get(chat_id)) - 1
                count += 1
                msg += f"{count}. {title[:70]}\n"
                msg += f"{_['play_20']} {position}\n\n"
            else:
                if not forceplay:
                    db[chat_id] = []
                status = True if video else None
                try:
                    file_path, direct = await YouTube.download(
                        vidid, mystic, video=status, videoid=True
                    )
                except:
                    raise AssistantErr(_["play_14"])
                await Swaggy.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=status,
                    image=thumbnail,
                )
                await put_queue(
                    chat_id,
                    original_chat_id,
                    file_path if direct else f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video" if video else "audio",
                    forceplay=forceplay,
                )
                img = await get_thumb(
                    vidid,
                    title=title,
                    duration=duration_min,
                )
                thumb_on_now = await is_thumb_on(chat_id)
                button = stream_markup(
                    _,
                    chat_id,
                    autoplay_status=await is_autoplay_on(chat_id),
                    thumb_status=thumb_on_now,
                )
                caption = _["stream_1"].format(
                    f"https://t.me/{app.username}?start=info_{vidid}",
                    title[:23],
                    duration_min,
                    user_name,
                )
                if thumb_on_now:
                    run = await app.send_photo(
                        original_chat_id,
                        photo=img,
                        has_spoiler=True,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                else:
                    run = await app.send_message(
                        original_chat_id,
                        text=caption,
                        disable_web_page_preview=True,
                        reply_markup=InlineKeyboardMarkup(button),
                    )
                db[chat_id][0]["mystic"] = run
                db[chat_id][0]["markup"] = "stream"
        if count == 0:
            return
        else:
            link = await SwaggyBin(msg)
            lines = msg.count("\n")
            if lines >= 17:
                car = os.linesep.join(msg.split(os.linesep)[:17])
            else:
                car = msg
            carbon = await Carbon.generate(car, randint(100, 10000000))
            upl = close_markup(_)
            return await app.send_photo(
                original_chat_id,
                photo=carbon,
                caption=_["play_21"].format(position, link),
                reply_markup=upl,
            )
    elif streamtype == "youtube":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        duration_min = result["duration_min"]
        thumbnail = result["thumb"]
        status = True if video else None
        # Start thumbnail generation in parallel with download — get_thumb
        # does its own /search + HTTP download + PIL processing (3-10s),
        # so overlapping it with the audio download saves that entire time.
        # We pass the title + duration the caller already has so get_thumb
        # doesn't need to do an independent metadata lookup (root-cause fix
        # for the 'Unknown Title / Unknown Artist / 0 views' bug — the
        # previous implementation did a SEPARATE VideosSearch that often
        # drifted to a different video and fell through to defaults).
        thumb_task = asyncio.create_task(
            get_thumb(vidid, title=title, duration=duration_min)
        )
        try:
            file_path, direct = await YouTube.download(
                vidid, mystic, videoid=True, video=status
            )
        except:
            thumb_task.cancel()
            raise AssistantErr(_["play_14"])
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
            # Cancel the thumbnail task since we don't need it for queued items
            thumb_task.cancel()
        else:
            if not forceplay:
                db[chat_id] = []
            await Swaggy.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=thumbnail,
            )
            await put_queue(
                chat_id,
                original_chat_id,
                file_path if direct else f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            # Thumbnail should be ready by now (it was generating in parallel
            # with the download). If not, this await waits for the remainder.
            try:
                img = await thumb_task
            except Exception:
                img = thumbnail
            thumb_on_now = await is_thumb_on(chat_id)
            button = stream_markup(
                _,
                chat_id,
                autoplay_status=await is_autoplay_on(chat_id),
                thumb_status=thumb_on_now,
            )
            caption = _["stream_1"].format(
                f"https://t.me/{app.username}?start=info_{vidid}",
                title[:23],
                duration_min,
                user_name,
            )
            if thumb_on_now:
                run = await app.send_photo(
                    original_chat_id,
                    photo=img,
                    has_spoiler=True,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                run = await app.send_message(
                    original_chat_id,
                    text=caption,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "stream"
    elif streamtype == "soundcloud":
        file_path = result["filepath"]
        title = result["title"]
        duration_min = result["duration_min"]
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await Swaggy.join_call(chat_id, original_chat_id, file_path, video=None)
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "audio",
                forceplay=forceplay,
            )
            button = stream_markup(
                _,
                chat_id,
                autoplay_status=await is_autoplay_on(chat_id),
                thumb_status=await is_thumb_on(chat_id),
            )
            caption = _["stream_1"].format(
                config.SUPPORT_CHAT, title[:23], duration_min, user_name
            )
            if await is_thumb_on(chat_id):
                run = await app.send_photo(
                    original_chat_id,
                    photo=config.SOUNCLOUD_IMG_URL,
                    has_spoiler=True,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                run = await app.send_message(
                    original_chat_id,
                    text=caption,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
    elif streamtype == "telegram":
        file_path = result["path"]
        link = result["link"]
        title = (result["title"]).title()
        duration_min = result["dur"]
        status = True if video else None
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await Swaggy.join_call(chat_id, original_chat_id, file_path, video=status)
            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            if video:
                await add_active_video_chat(chat_id)
            button = stream_markup(
                _,
                chat_id,
                autoplay_status=await is_autoplay_on(chat_id),
                thumb_status=await is_thumb_on(chat_id),
            )
            caption = _["stream_1"].format(link, title[:23], duration_min, user_name)
            if await is_thumb_on(chat_id):
                run = await app.send_photo(
                    original_chat_id,
                    has_spoiler=True,
                    photo=config.TELEGRAM_VIDEO_URL if video else config.TELEGRAM_AUDIO_URL,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                run = await app.send_message(
                    original_chat_id,
                    text=caption,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
    elif streamtype == "live":
        link = result["link"]
        vidid = result["vidid"]
        title = (result["title"]).title()
        thumbnail = result["thumb"]
        duration_min = "Live Track"
        status = True if video else None
        if await is_active_chat(chat_id):
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await app.send_message(
                chat_id=original_chat_id,
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            n, file_path = await YouTube.video(link)
            if n == 0:
                raise AssistantErr(_["str_3"])
            await Swaggy.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=status,
                image=thumbnail if thumbnail else None,
            )
            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            img = await get_thumb(
                vidid,
                title=title,
                duration=duration_min,
            )
            thumb_on_now = await is_thumb_on(chat_id)
            button = stream_markup(
                _,
                chat_id,
                autoplay_status=await is_autoplay_on(chat_id),
                thumb_status=thumb_on_now,
            )
            caption = _["stream_1"].format(
                f"https://t.me/{app.username}?start=info_{vidid}",
                title[:23],
                duration_min,
                user_name,
            )
            if thumb_on_now:
                run = await app.send_photo(
                    original_chat_id,
                    photo=img,
                    has_spoiler=True,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                run = await app.send_message(
                    original_chat_id,
                    text=caption,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
    elif streamtype == "index":
        link = result
        title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"
        duration_min = "00:00"
        if await is_active_chat(chat_id):
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
            )
            position = len(db.get(chat_id)) - 1
            button = aq_markup(_, chat_id)
            await mystic.edit_text(
                text=_["queue_4"].format(position, title[:27], duration_min, user_name),
                reply_markup=InlineKeyboardMarkup(button),
            )
        else:
            if not forceplay:
                db[chat_id] = []
            await Swaggy.join_call(
                chat_id,
                original_chat_id,
                link,
                video=True if video else None,
            )
            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                "video" if video else "audio",
                forceplay=forceplay,
            )
            button = stream_markup(
                _,
                chat_id,
                autoplay_status=await is_autoplay_on(chat_id),
                thumb_status=await is_thumb_on(chat_id),
            )
            caption = _["stream_2"].format(user_name)
            if await is_thumb_on(chat_id):
                run = await app.send_photo(
                    original_chat_id,
                    photo=config.STREAM_IMG_URL,
                    has_spoiler=True,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            else:
                run = await app.send_message(
                    original_chat_id,
                    text=caption,
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(button),
                )
            db[chat_id][0]["mystic"] = run
            db[chat_id][0]["markup"] = "tg"
            await mystic.delete()
