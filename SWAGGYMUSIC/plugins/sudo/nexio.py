import requests
import random
from SWAGGYMUSIC import app, userbot
from SWAGGYMUSIC.misc import SUDOERS
from pyrogram import *
from pyrogram.types import *
from SWAGGYMUSIC.utils.Swaggy_BAN import admin_filter


Yumikoo_text = [
    "haan bolo, kya huaa?",
    "kya hai, kyun bula rahe ho?",
    "ab bologe?",
    "hey please don't disturb me.",
    "dekho abhi mere Sir ji aa jayenge, phir tumhari khair nahi.",
    "are yaar, baat samajh nahi aati kya?",
    "dekho mai abhi busy hu, so don't tag me.",
    "ab kya huaa?",
    "kya hai yaar, kaam batao.",
    "baar baar tag mat karo, gussa aa raha hai.",
    "@Swaggy_Rajput kahan ho aap? Dekho, ye kabse pareshan kiye ja raha hai.",
    "haan Shubhu yahin hu, bolo kya hua?",
]


strict_txt = [
    "i can't restrict against my besties",
    "are you serious i am not restrict to my friends",
    "fuck you bsdk k mai apne dosto ko kyu kru",
    "hey stupid admin ",
    "ha ye phele krlo maar lo ek dusre ki gwaand",
    "i can't hi is my closest friend",
    "i love him please don't restict this user try to usertand "
]


ban = ["ban", "boom"]
unban = ["unban"]
mute = ["mute", "silent", "shut"]
unmute = ["unmute", "speak", "free"]
kick = ["kick", "out", "nikaal", "nikal"]
promote = ["promote", "adminship"]
fullpromote = ["fullpromote", "fulladmin"]
demote = ["demote", "lelo"]
group = ["group"]
channel = ["channel"]


# ========================================= #
# SHUBHU RANDOM REPLY
# ALL USERS CAN USE THIS
# ========================================= #

@app.on_message(
    filters.command(["hubhu"], prefixes=["S"]),
    group=0
)
async def shubhu_random_reply(_, message):
    # Only respond to plain:
    # Shubhu
    #
    # If arguments are present, allow the
    # admin-only moderation handler below
    # to process the command.

    if len(message.text.split()) < 2:
        return await message.reply(random.choice(Yumikoo_text))


# ========================================= #
# ADMIN-ONLY MODERATION HANDLER
# ========================================= #

@app.on_message(
    filters.command(["hubhu"], prefixes=["S"]) & admin_filter,
    group=1
)
async def restriction_app(_, message):
    reply = message.reply_to_message
    chat_id = message.chat.id

    # Check if the command has additional arguments
    if len(message.text.split()) < 2:
        return

    # Extract the text after the command
    command_args = message.text.split(maxsplit=1)[1]
    data = command_args.split(" ")

    if reply:
        user_id = reply.from_user.id

        # ========================================= #
        # BAN
        # ========================================= #

        for banned in data:
            print(f"present {banned}")

            if banned in ban:
                if user_id in SUDOERS:
                    await message.reply(random.choice(strict_txt))
                else:
                    await app.ban_chat_member(chat_id, user_id)
                    await message.reply(
                        "OK, Ban kar diya madrchod ko sala Chutiya tha !"
                    )

        # ========================================= #
        # UNBAN
        # ========================================= #

        for unbanned in data:
            print(f"present {unbanned}")

            if unbanned in unban:
                await app.unban_chat_member(chat_id, user_id)
                await message.reply(
                    "Ok, aap bolte hai to unban kar diya"
                )

        # ========================================= #
        # KICK
        # ========================================= #

        for kicked in data:
            print(f"present {kicked}")

            if kicked in kick:
                if user_id in SUDOERS:
                    await message.reply(random.choice(strict_txt))
                else:
                    await app.ban_chat_member(chat_id, user_id)
                    await app.unban_chat_member(chat_id, user_id)
                    await message.reply(
                        "get lost! bhaga diya bhosdi wale ko"
                    )

        # ========================================= #
        # MUTE
        # ========================================= #

        for muted in data:
            print(f"present {muted}")

            if muted in mute:
                if user_id in SUDOERS:
                    await message.reply(random.choice(strict_txt))
                else:
                    permissions = ChatPermissions(
                        can_send_messages=False
                    )

                    await message.chat.restrict_member(
                        user_id,
                        permissions
                    )

                    await message.reply(
                        "muted successfully! aukatless people tha bkl."
                    )

        # ========================================= #
        # UNMUTE
        # ========================================= #

        for unmuted in data:
            print(f"present {unmuted}")

            if unmuted in unmute:
                permissions = ChatPermissions(
                    can_send_messages=True
                )

                await message.chat.restrict_member(
                    user_id,
                    permissions
                )

                await message.reply(
                    "Huh, OK, sir unmute kar diya maine !!"
                )

        # ========================================= #
        # PROMOTE
        # ========================================= #

        for promoted in data:
            print(f"present {promoted}")

            if promoted in promote:
                await app.promote_chat_member(
                    chat_id,
                    user_id,
                    privileges=ChatPrivileges(
                        can_change_info=False,
                        can_invite_users=True,
                        can_delete_messages=True,
                        can_restrict_members=False,
                        can_pin_messages=True,
                        can_promote_members=False,
                        can_manage_chat=True,
                        can_manage_video_chats=True,
                    )
                )

                await message.reply("promoted !")

        # ========================================= #
        # DEMOTE
        # ========================================= #

        for demoted in data:
            print(f"present {demoted}")

            if demoted in demote:
                await app.promote_chat_member(
                    chat_id,
                    user_id,
                    privileges=ChatPrivileges(
                        can_change_info=False,
                        can_invite_users=False,
                        can_delete_messages=False,
                        can_restrict_members=False,
                        can_pin_messages=False,
                        can_promote_members=False,
                        can_manage_chat=False,
                        can_manage_video_chats=False,
                    )
                )

                await message.reply("demoted !")

        # ========================================= #
        # FULL PROMOTE
        # ========================================= #

        for fullpromoted in data:
            print(f"present {fullpromoted}")

            if fullpromoted in fullpromote:
                await app.promote_chat_member(
                    chat_id,
                    user_id,
                    privileges=ChatPrivileges(
                        can_change_info=True,
                        can_invite_users=True,
                        can_delete_messages=True,
                        can_restrict_members=True,
                        can_pin_messages=True,
                        can_promote_members=True,
                        can_manage_chat=True,
                        can_manage_video_chats=True,
                    )
                )

                await message.reply("fullpromoted !")
