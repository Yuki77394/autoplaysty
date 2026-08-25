from pyrogram import Client, errors
from pyrogram.enums import ChatMemberStatus, ParseMode
import pyrogram.utils as _pyro_utils

import config
import traceback

from ..logging import LOGGER


# Pyrogram 2.0.106 has a narrower channel ID range than Telegram currently
# assigns (MIN_CHANNEL_ID = -1002147483647). Newer supergroups/channels
# get IDs more negative than this. Patch get_peer_type so these IDs are
# correctly recognised as channels instead of raising ValueError.
_original_get_peer_type = _pyro_utils.get_peer_type


def _patched_get_peer_type(peer_id: int) -> str:
    try:
        return _original_get_peer_type(peer_id)
    except ValueError:
        # Telegram channel/supergroup IDs always start with -100
        if peer_id < 0 and str(peer_id).startswith("-100"):
            return "channel"
        raise


_pyro_utils.get_peer_type = _patched_get_peer_type


class Swaggy(Client):
    def __init__(self):
        LOGGER(__name__).info(f"Starting Bot...")
        super().__init__(
            name="SWAGGYMUSIC",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            in_memory=True,
            max_concurrent_transmissions=7,
        )

    async def start(self):
        await super().start()
        self.id = self.me.id
        self.name = self.me.first_name + " " + (self.me.last_name or "")
        self.username = self.me.username
        self.mention = self.me.mention

        try:
            await self.send_message(
                chat_id=config.LOGGER_ID,
                text=f"<u><b>» {self.mention} ʙᴏᴛ sᴛᴀʀᴛᴇᴅ :</b></u>\n\nɪᴅ : <code>{self.id}</code>\nɴᴀᴍᴇ : {self.name}\nᴜsᴇʀɴᴀᴍᴇ : @{self.username}",
            )
        except (errors.ChannelInvalid, errors.PeerIdInvalid):
            LOGGER(__name__).error(
                "Bot has failed to access the log group/channel. Make sure that you have added your bot to your log group/channel."
            )
            exit()
        except Exception as ex:
            LOGGER(__name__).error(
                f"Bot has failed to access the log group/channel.\n  Reason : {type(ex).__name__}: {ex}\n"
                f"  Traceback:\n{traceback.format_exc()}"
            )
            exit()

        a = await self.get_chat_member(config.LOGGER_ID, self.id)
        if a.status != ChatMemberStatus.ADMINISTRATOR:
            LOGGER(__name__).error(
                "Please promote your bot as an admin in your log group/channel."
            )
            exit()
        LOGGER(__name__).info(f"Music Bot Started as {self.name}")

    async def stop(self):
        await super().stop()
