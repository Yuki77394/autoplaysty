import os
from random import randint
from typing import Union

from pyrogram.types import InlineKeyboardMarkup

import config
from VIVAANXMUSIC import Carbon, YouTube, app
from VIVAANXMUSIC.core.call import JARVIS
from VIVAANXMUSIC.misc import db
from VIVAANXMUSIC.utils.database import (
    add_active_video_chat,
    is_active_chat,
)
from VIVAANXMUSIC.utils.exceptions import AssistantErr
from VIVAANXMUSIC.utils.inline import (
    aq_markup,
    close_markup,
    stream_markup,
)
from VIVAANXMUSIC.utils.pastebin import VIVAANBIN
from VIVAANXMUSIC.utils.stream.cards import schedule_stream_card
from VIVAANXMUSIC.utils.stream.queue import (
    put_queue,
    put_queue_index,
)
from VIVAANXMUSIC.utils.errors import capture_internal_err


# =========================================================
# SAFE HELPERS
# =========================================================

def _safe_duration(value):
    try:
        if value is None:
            return 0

        if isinstance(value, (int, float)):
            return int(value)

        value = str(value).strip()

        if not value:
            return 0

        if ":" in value:
            total = 0

            for part in value.split(":"):
                total = total * 60 + int(part)

            return total

        return int(float(value))

    except Exception:
        return 0


def _safe_duration_min(value):
    """
    Convert duration to MM:SS.
    Accepts seconds or MM:SS.
    """
    try:
        if isinstance(value, str) and ":" in value:
            seconds = _safe_duration(value)
        else:
            seconds = _safe_duration(value)

        if seconds <= 0:
            return "00:00"

        return (
            f"{seconds // 60}:"
            f"{seconds % 60:02d}"
        )

    except Exception:
        return "00:00"


async def _resolve_youtube_result(result):
    """
    Makes YouTube playback self-healing.

    If the incoming result is incomplete, resolve
    the track again using YouTube.track().
    """

    if not result:
        return None

    # -----------------------------------------------------
    # Already complete
    # -----------------------------------------------------

    if isinstance(result, dict):

        vidid = str(
            result.get("vidid")
            or result.get("id")
            or ""
        ).strip()

        title = str(
            result.get("title")
            or ""
        ).strip()

        link = str(
            result.get("link")
            or ""
        ).strip()

        if (
            vidid
            and title
            and link
        ):
            duration_sec = _safe_duration(
                result.get("duration_sec")
                or result.get("duration")
                or result.get("duration_min")
            )

            duration_min = (
                result.get("duration_min")
                or _safe_duration_min(
                    duration_sec
                )
            )

            thumb = (
                result.get("thumb")
                or result.get("thumbnail")
                or (
                    "https://i.ytimg.com/vi/"
                    f"{vidid}/hqdefault.jpg"
                )
            )

            return {
                "link": link,
                "vidid": vidid,
                "title": title,
                "duration_min": duration_min,
                "duration_sec": duration_sec,
                "thumb": thumb,
                "direct_url": bool(result.get("direct_url")),
            }

        # -------------------------------------------------
        # Result has some data but is incomplete
        # -------------------------------------------------

        search_value = (
            result.get("link")
            or result.get("vidid")
            or result.get("id")
            or result.get("title")
        )

    else:
        search_value = result

    if not search_value:
        return None

    # -----------------------------------------------------
    # Resolve through YouTube.track()
    # -----------------------------------------------------

    try:
        track_result, vidid = await YouTube.track(
            str(search_value)
        )

        if not track_result:
            return None

        vidid = str(
            track_result.get("vidid")
            or vidid
            or ""
        ).strip()

        if not vidid:
            return None

        title = str(
            track_result.get("title")
            or "Unknown Title"
        ).strip()

        link = str(
            track_result.get("link")
            or (
                "https://www.youtube.com/watch?v="
                f"{vidid}"
            )
        ).strip()

        duration_min = str(
            track_result.get("duration_min")
            or "00:00"
        )

        thumb = (
            track_result.get("thumb")
            or (
                "https://i.ytimg.com/vi/"
                f"{vidid}/hqdefault.jpg"
            )
        )

        return {
            "link": link,
            "vidid": vidid,
            "title": title,
            "duration_min": duration_min,
            "duration_sec": _safe_duration(
                duration_min
            ),
            "thumb": thumb,
            "direct_url": bool(track_result.get("direct_url")),
        }

    except Exception:
        return None


def _youtube_error(error):
    error_text = str(
        error or ""
    ).lower()

    if (
        "authentication" in error_text
        or "cookies" in error_text
        or "not a bot" in error_text
        or "sign in" in error_text
    ):
        return AssistantErr(
            "ʏᴏᴜᴛᴜʙᴇ ᴀᴜᴛʜᴇɴᴛɪᴄᴀᴛɪᴏɴ ʀᴇǫᴜɪʀᴇᴅ. "
            "ᴘʟᴇᴀsᴇ sᴇᴛ ʏᴏᴜᴛᴜʙᴇ_ᴄᴏᴏᴋɪᴇs "
            "ɪɴ ᴄᴏɴғɪɢ ᴠᴀʀs."
        )

    return AssistantErr(
        config.PLAY_14
        if hasattr(config, "PLAY_14")
        else "Unable to play this YouTube track."
    )


# =========================================================
# MAIN STREAM
# =========================================================

@capture_internal_err
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
) -> None:

    if not result:
        return

    forceplay = bool(forceplay)

    is_video = str(
        video
    ).lower() in (
        "true",
        "video",
        "1",
    )

    # =====================================================
    # FORCE STOP
    # =====================================================

    if forceplay:
        await JARVIS.force_stop_stream(
            chat_id
        )

    # =====================================================
    # PLAYLIST
    # =====================================================

    if streamtype == "playlist":

        msg = f"{_['play_19']}\n\n"

        count = 0
        position = 0

        for search in result:

            if count >= config.PLAYLIST_FETCH_LIMIT:
                break

            try:
                (
                    title,
                    duration_min,
                    duration_sec,
                    thumbnail,
                    vidid,
                ) = await YouTube.details(
                    search,
                    videoid=search,
                )

            except Exception:
                continue

            if str(duration_min) == "None":
                continue

            if (
                duration_sec
                and duration_sec
                > config.DURATION_LIMIT
            ):
                continue

            if await is_active_chat(
                chat_id
            ):

                await put_queue(
                    chat_id,
                    original_chat_id,
                    f"vid_{vidid}",
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    "video"
                    if is_video
                    else "audio",
                )

                position = (
                    len(
                        db.get(
                            chat_id,
                            [],
                        )
                    )
                    - 1
                )

                count += 1

                msg += (
                    f"{count}. "
                    f"{title[:70]}\n"
                )

                msg += (
                    f"{_['play_20']} "
                    f"{position}\n\n"
                )

            else:

                if not forceplay:
                    db[chat_id] = []

                try:

                    file_path, direct = (
                        await YouTube.download(
                            vidid,
                            mystic,
                            video=is_video,
                            videoid=vidid,
                        )
                    )

                except Exception:
                    raise AssistantErr(
                        _["play_14"]
                    )

                if not file_path:
                    raise AssistantErr(
                        _["play_14"]
                    )

                await JARVIS.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=is_video,
                    image=thumbnail,
                )

                await put_queue(
                    chat_id,
                    original_chat_id,
                    (
                        file_path
                        if direct
                        else f"vid_{vidid}"
                    ),
                    title,
                    duration_min,
                    user_name,
                    vidid,
                    user_id,
                    (
                        "video"
                        if is_video
                        else "audio"
                    ),
                    forceplay=forceplay,
                )

                button = stream_markup(
                    _,
                    chat_id,
                )

                schedule_stream_card(
                    chat_id=chat_id,
                    original_chat_id=original_chat_id,
                    videoid=vidid,
                    user_id=user_id,
                    caption=_[
                        "stream_1"
                    ].format(
                        (
                            f"https://t.me/"
                            f"{app.username}"
                            f"?start=info_{vidid}"
                        ),
                        title[:23],
                        duration_min,
                        user_name,
                    ),
                    button=button,
                    markup="stream",
                )

        if count == 0:
            return

        link = await VIVAANBIN(
            msg
        )

        lines = msg.count("\n")

        car = (
            os.linesep.join(
                msg.split(os.linesep)[:17]
            )
            if lines >= 17
            else msg
        )

        try:

            carbon = await Carbon.generate(
                car,
                randint(
                    100,
                    10000000,
                ),
            )

            playlist_photo = carbon

        except Exception:
            playlist_photo = (
                config.PLAYLIST_IMG_URL
            )

        upl = close_markup(
            _
        )

        final_position = (
            len(
                db.get(
                    chat_id
                )
                or []
            )
            - 1
        )

        if final_position < 0:
            final_position = 0

        return await app.send_photo(
            original_chat_id,
            photo=playlist_photo,
            caption=_[
                "play_21"
            ].format(
                final_position,
                link,
            ),
            reply_markup=upl,
        )

    # =====================================================
    # YOUTUBE
    # =====================================================

    elif streamtype == "youtube":

        # -------------------------------------------------
        # IMPORTANT:
        # Resolve broken/incomplete search results.
        # -------------------------------------------------

        resolved = (
            await _resolve_youtube_result(
                result
            )
        )

        if not resolved:
            raise AssistantErr(
                "ғᴀɪʟᴇᴅ ᴛᴏ ғᴇᴛᴄʜ ᴛʀᴀᴄᴋ ᴅᴇᴛᴀɪʟs. "
                "ᴛʀʏ ᴘʟᴀʏɪɴɢ ᴀɴʏ ᴏᴛʜᴇʀ."
            )

        link = resolved[
            "link"
        ]

        vidid = resolved[
            "vidid"
        ]

        title = str(
            resolved[
                "title"
            ]
        ).title()

        duration_min = resolved[
            "duration_min"
        ]

        thumbnail = resolved[
            "thumb"
        ]

        # -------------------------------------------------
        # FAST PLAYBACK
        # -------------------------------------------------
        # Do not download the whole song before starting VC.
        # Resolve a short-lived direct YouTube media URL first.
        # Download is only the fallback when direct streaming fails.
        file_path = None
        direct = False

        if not is_video:
            try:
                direct_url = await asyncio.wait_for(
                    YouTube.stream_url(vidid, videoid=True),
                    timeout=4,
                )
            except Exception:
                direct_url = None

            if direct_url:
                file_path = direct_url
                direct = True

        if not file_path:
            try:
                file_path, direct = (
                    await YouTube.download(
                        vidid,
                        mystic,
                        video=is_video,
                        videoid=vidid,
                    )
                )
            except Exception:
                file_path, direct = None, False

        if not file_path:
            raise AssistantErr(_["play_14"])

        # -------------------------------------------------
        # Already active -> queue
        # -------------------------------------------------

        if await is_active_chat(
            chat_id
        ):

            # Never persist a short-lived YouTube CDN URL in the queue.
            # Store the video ID and resolve a fresh URL when that track starts.
            await put_queue(
                chat_id,
                original_chat_id,
                f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
            )

            position = (
                len(
                    db.get(
                        chat_id,
                        [],
                    )
                )
                - 1
            )

            button = aq_markup(
                _,
                chat_id,
            )

            await app.send_message(
                chat_id=original_chat_id,
                text=_[
                    "queue_4"
                ].format(
                    position,
                    title[:27],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

        # -------------------------------------------------
        # Start new stream
        # -------------------------------------------------

        else:

            if not forceplay:
                db[chat_id] = []

            # ---------------------------------------------
            # Join voice call
            # ---------------------------------------------

            try:

                await JARVIS.join_call(
                    chat_id,
                    original_chat_id,
                    file_path,
                    video=is_video,
                    image=thumbnail,
                )

            except Exception as e:

                raise AssistantErr(
                    str(e)
                    or _["play_14"]
                )

            # ---------------------------------------------
            # Save queue
            # ---------------------------------------------

            # Never persist a short-lived YouTube CDN URL in the queue.
            # Store the video ID and resolve a fresh URL when that track starts.
            await put_queue(
                chat_id,
                original_chat_id,
                f"vid_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
                forceplay=forceplay,
            )

            button = stream_markup(
                _,
                chat_id,
            )

            schedule_stream_card(
                chat_id=chat_id,
                original_chat_id=original_chat_id,
                videoid=vidid,
                user_id=user_id,
                caption=_[
                    "stream_1"
                ].format(
                    (
                        f"https://t.me/"
                        f"{app.username}"
                        f"?start=info_{vidid}"
                    ),
                    title[:23],
                    duration_min,
                    user_name,
                ),
                button=button,
                markup="stream",
            )

    # =====================================================
    # SOUNDCLOUD
    # =====================================================

    elif streamtype == "soundcloud":

        file_path = result[
            "filepath"
        ]

        title = result[
            "title"
        ]

        duration_min = result[
            "duration_min"
        ]

        if not file_path:
            raise AssistantErr(
                _["play_14"]
            )

        if await is_active_chat(
            chat_id
        ):

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

            position = (
                len(
                    db.get(
                        chat_id,
                        [],
                    )
                )
                - 1
            )

            button = aq_markup(
                _,
                chat_id,
            )

            await app.send_message(
                chat_id=original_chat_id,
                text=_[
                    "queue_4"
                ].format(
                    position,
                    title[:27],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

        else:

            if not forceplay:
                db[chat_id] = []

            await JARVIS.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=False,
            )

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
            )

            run = await app.send_photo(
                original_chat_id,
                photo=config.SOUNCLOUD_IMG_URL,
                caption=_[
                    "stream_1"
                ].format(
                    config.SUPPORT_CHAT,
                    title[:23],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

            db[chat_id][0][
                "mystic"
            ] = run

            db[chat_id][0][
                "markup"
            ] = "tg"

    # =====================================================
    # TELEGRAM
    # =====================================================

    elif streamtype == "telegram":

        file_path = result[
            "path"
        ]

        link = result[
            "link"
        ]

        title = str(
            result["title"]
        ).title()

        duration_min = result[
            "dur"
        ]

        if not file_path:
            raise AssistantErr(
                _["play_14"]
            )

        if await is_active_chat(
            chat_id
        ):

            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
            )

            position = (
                len(
                    db.get(
                        chat_id,
                        [],
                    )
                )
                - 1
            )

            button = aq_markup(
                _,
                chat_id,
            )

            await app.send_message(
                chat_id=original_chat_id,
                text=_[
                    "queue_4"
                ].format(
                    position,
                    title[:27],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

        else:

            if not forceplay:
                db[chat_id] = []

            await JARVIS.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
            )

            await put_queue(
                chat_id,
                original_chat_id,
                file_path,
                title,
                duration_min,
                user_name,
                streamtype,
                user_id,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
                forceplay=forceplay,
            )

            if is_video:
                await add_active_video_chat(
                    chat_id
                )

            button = stream_markup(
                _,
                chat_id,
            )

            run = await app.send_photo(
                original_chat_id,
                photo=(
                    config.TELEGRAM_VIDEO_URL
                    if is_video
                    else config.TELEGRAM_AUDIO_URL
                ),
                caption=_[
                    "stream_1"
                ].format(
                    link,
                    title[:23],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

            db[chat_id][0][
                "mystic"
            ] = run

            db[chat_id][0][
                "markup"
            ] = "tg"

    # =====================================================
    # LIVE
    # =====================================================

    elif streamtype == "live":

        link = result[
            "link"
        ]

        vidid = result[
            "vidid"
        ]

        title = str(
            result["title"]
        ).title()

        thumbnail = result[
            "thumb"
        ]

        duration_min = "Live Track"

        if await is_active_chat(
            chat_id
        ):

            await put_queue(
                chat_id,
                original_chat_id,
                f"live_{vidid}",
                title,
                duration_min,
                user_name,
                vidid,
                user_id,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
            )

            position = (
                len(
                    db.get(
                        chat_id,
                        [],
                    )
                )
                - 1
            )

            button = aq_markup(
                _,
                chat_id,
            )

            await app.send_message(
                chat_id=original_chat_id,
                text=_[
                    "queue_4"
                ].format(
                    position,
                    title[:27],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

        else:

            if not forceplay:
                db[chat_id] = []

            try:

                n, file_path = (
                    await YouTube.video(
                        link
                    )
                )

            except Exception as e:

                error = _youtube_error(
                    e
                )

                raise error

            if n == 0:
                raise AssistantErr(
                    _["str_3"]
                )

            if not file_path:
                raise AssistantErr(
                    _["play_14"]
                )

            await JARVIS.join_call(
                chat_id,
                original_chat_id,
                file_path,
                video=is_video,
                image=thumbnail or None,
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
                (
                    "video"
                    if is_video
                    else "audio"
                ),
                forceplay=forceplay,
            )

            button = stream_markup(
                _,
                chat_id,
            )

            schedule_stream_card(
                chat_id=chat_id,
                original_chat_id=original_chat_id,
                videoid=vidid,
                user_id=user_id,
                caption=_[
                    "stream_1"
                ].format(
                    (
                        f"https://t.me/"
                        f"{app.username}"
                        f"?start=info_{vidid}"
                    ),
                    title[:23],
                    duration_min,
                    user_name,
                ),
                button=button,
                markup="tg",
            )

    # =====================================================
    # INDEX / M3U8
    # =====================================================

    elif streamtype == "index":

        link = result

        title = "ɪɴᴅᴇx ᴏʀ ᴍ3ᴜ8 ʟɪɴᴋ"

        duration_min = "00:00"

        if await is_active_chat(
            chat_id
        ):

            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
            )

            position = (
                len(
                    db.get(
                        chat_id,
                        [],
                    )
                )
                - 1
            )

            button = aq_markup(
                _,
                chat_id,
            )

            await mystic.edit_text(
                text=_[
                    "queue_4"
                ].format(
                    position,
                    title[:27],
                    duration_min,
                    user_name,
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

        else:

            if not forceplay:
                db[chat_id] = []

            await JARVIS.join_call(
                chat_id,
                original_chat_id,
                link,
                video=is_video,
            )

            await put_queue_index(
                chat_id,
                original_chat_id,
                "index_url",
                title,
                duration_min,
                user_name,
                link,
                (
                    "video"
                    if is_video
                    else "audio"
                ),
                forceplay=forceplay,
            )

            button = stream_markup(
                _,
                chat_id,
            )

            run = await app.send_photo(
                original_chat_id,
                photo=config.STREAM_IMG_URL,
                caption=_[
                    "stream_2"
                ].format(
                    user_name
                ),
                reply_markup=InlineKeyboardMarkup(
                    button
                ),
            )

            db[chat_id][0][
                "mystic"
            ] = run

            db[chat_id][0][
                "markup"
            ] = "tg"

            try:
                await mystic.delete()
            except Exception:
                pass
