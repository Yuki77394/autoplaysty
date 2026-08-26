import socket
import time

import heroku3
from pyrogram import filters

import config
from SWAGGYMUSIC.core.mongo import mongodb

from .logging import LOGGER

SUDOERS = filters.user()

HAPP = None
_boot_ = time.time()


def is_heroku():
    return "heroku" in socket.getfqdn()


XCB = [
    "/",
    "@",
    ".",
    "com",
    ":",
    "git",
    "heroku",
    "push",
    str(config.HEROKU_API_KEY),
    "https",
    str(config.HEROKU_APP_NAME),
    "HEAD",
    "master",
]


def dbb():
    global db
    db = {}
    LOGGER(__name__).info(f"𝗗𝗔𝗧𝗔𝗕𝗔𝗦𝗘 𝗟𝗢𝗔𝗗𝗘𝗗 𝗕𝗢𝗦𝗦")


async def sudo():
    global SUDOERS
    SUDOERS.add(config.OWNER_ID)
    sudoersdb = mongodb.sudoers
    sudoers = await sudoersdb.find_one({"sudo": "sudo"})
    sudoers = [] if not sudoers else sudoers["sudoers"]
    if config.OWNER_ID not in sudoers:
        sudoers.append(config.OWNER_ID)
        await sudoersdb.update_one(
            {"sudo": "sudo"},
            {"$set": {"sudoers": sudoers}},
            upsert=True,
        )
    if sudoers:
        for user_id in sudoers:
            SUDOERS.add(user_id)
    LOGGER(__name__).info(f"𝗦𝗨𝗗𝗢 𝗨𝗦𝗘𝗥 𝗗𝗢𝗡𝗘 𝗕𝗢𝗦𝗦")


def heroku():
    global HAPP
    if is_heroku:
        if config.HEROKU_API_KEY and config.HEROKU_APP_NAME:
            try:
                Heroku = heroku3.from_key(config.HEROKU_API_KEY)
                HAPP = Heroku.app(config.HEROKU_APP_NAME)
                LOGGER(__name__).info(f"𝗛𝗘𝗥𝗢𝗞𝗨 𝗔𝗣𝗣 𝗡𝗔𝗠𝗘 𝗟𝗢𝗔𝗗𝗘𝗗 || 𝗗𝗢𝗡𝗘")
            except BaseException:
                LOGGER(__name__).warning(
                    f"𝗬𝗢𝗨 𝗛𝗔𝗩𝗘 𝗡𝗢𝗧 𝗙𝗜𝗟𝗟𝗘𝗗 𝗛𝗘𝗥𝗢𝗞𝗨 𝗔𝗣𝗜 𝗞𝗘𝗬 𝗔𝗡𝗗 𝗛𝗘𝗥𝗢𝗞𝗨 𝗔𝗣𝗣 𝗡𝗔𝗠𝗘 𝗖𝗢𝗥𝗥𝗘𝗖𝗧"
)
