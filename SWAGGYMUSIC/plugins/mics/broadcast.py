import asyncio

from pyrogram import filters
from pyrogram.enums import ChatMembersFilter
from pyrogram.errors import FloodWait

from SWAGGYMUSIC import app
from SWAGGYMUSIC.misc import SUDOERS
from SWAGGYMUSIC.utils.database import (
    get_active_chats,
    get_authuser_names,
    get_client,
    get_served_chats,
    get_served_users,
)
from SWAGGYMUSIC.utils.decorators.language import language
from SWAGGYMUSIC.utils.formatters import alpha_to_int
from config import adminlist

IS_BROADCASTING = False


@app.on_message(filters.command("broadcast") & SUDOERS)
@language
async def braodcast_message(client, message, _):
    global IS_BROADCASTING

    if IS_BROADCASTING:
        return await message.reply_text("Already broadcasting in progress...")

    reply_markup = None

    # 🔹 If reply message
    if message.reply_to_message:
        x = message.reply_to_message.id
        y = message.chat.id
        reply_markup = message.reply_to_message.reply_markup
    else:
        if len(message.command) < 2:
            return await message.reply_text(_["broad_2"])

        query = message.text.split(None, 1)[1]

        # 🔹 Clean flags
        flags = ["-pin", "-nobot", "-pinloud", "-assistant", "-user"]
        for f in flags:
            query = query.replace(f, "")

        query = query.strip()

        if query == "":
            return await message.reply_text(_["broad_8"])

    IS_BROADCASTING = True
    await message.reply_text(_["broad_1"])

    # ================= CHAT BROADCAST =================
    if "-nobot" not in message.text:
        sent = 0
        pin = 0

        chats = [int(chat["chat_id"]) for chat in await get_served_chats()]

        for i in chats:
            try:
                m = (
                    await app.copy_message(
                        chat_id=i,
                        from_chat_id=y,
                        message_id=x,
                        reply_markup=reply_markup
                    )
                    if message.reply_to_message
                    else await app.send_message(i, text=query)
                )

                # 🔹 Pin logic
                if "-pin" in message.text:
                    try:
                        await m.pin(disable_notification=True)
                        pin += 1
                    except:
                        pass

                elif "-pinloud" in message.text:
                    try:
                        await m.pin(disable_notification=False)
                        pin += 1
                    except:
                        pass

                sent += 1
                await asyncio.sleep(0.2)

            except FloodWait as fw:
                await asyncio.sleep(fw.value)
            except:
                continue

        await message.reply_text(_["broad_3"].format(sent, pin))

    # ================= USER BROADCAST =================
    if "-user" in message.text:
        susr = 0

        users = [int(user["user_id"]) for user in await get_served_users()]

        for i in users:
            try:
                await app.copy_message(
                    chat_id=i,
                    from_chat_id=y,
                    message_id=x
                ) if message.reply_to_message else await app.send_message(i, text=query)

                susr += 1
                await asyncio.sleep(0.2)

            except FloodWait as fw:
                await asyncio.sleep(fw.value)
            except:
                continue

        await message.reply_text(_["broad_4"].format(susr))

    # ================= ASSISTANT BROADCAST =================
    if "-assistant" in message.text:
        aw = await message.reply_text(_["broad_5"])
        text = _["broad_6"]

        from PURVIMUSIC.core.userbot import assistants

        for num in assistants:
            sent = 0
            client = await get_client(num)

            async for dialog in client.get_dialogs():
                try:
                    if message.reply_to_message:
                        await client.copy_message(
                            chat_id=dialog.chat.id,
                            from_chat_id=y,
                            message_id=x
                        )
                    else:
                        await client.send_message(dialog.chat.id, text=query)

                    sent += 1
                    await asyncio.sleep(2)

                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except:
                    continue

            text += _["broad_7"].format(num, sent)

        await aw.edit_text(text)

    IS_BROADCASTING = False


# ================= AUTO CLEAN =================
async def auto_clean():
    while True:
        await asyncio.sleep(10)
        try:
            served_chats = await get_active_chats()

            for chat_id in served_chats:
                if chat_id not in adminlist:
                    adminlist[chat_id] = []

                    async for user in app.get_chat_members(
                        chat_id, filter=ChatMembersFilter.ADMINISTRATORS
                    ):
                        if user.privileges.can_manage_video_chats:
                            adminlist[chat_id].append(user.user.id)

                    authusers = await get_authuser_names(chat_id)

                    for user in authusers:
                        user_id = await alpha_to_int(user)
                        adminlist[chat_id].append(user_id)

        except:
            continue


asyncio.create_task(auto_clean())
