from pyrogram import Client, filters
import httpx
from SWAGGYMUSIC import app

waifu_api_url = 'https://api.waifu.im/search'

# Define the asynchronous function to fetch waifu data
async def get_waifu_data(tags):
    params = {
        'included_tags': tags,
        'height': '>=1280'  # Optional height filter
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(waifu_api_url, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        return None


@app.on_message(filters.command("waifu"))
async def waifu_command(client, message):
    try:
        tags = ['maid']  # Default tags; customize as needed
        waifu_data = await get_waifu_data(tags)  # Correctly await the async function

        if waifu_data and 'images' in waifu_data and len(waifu_data['images']) > 0:
            first_image = waifu_data['images'][0]
            image_url = first_image['url']
            await message.reply_photo(image_url)
        else:
            await message.reply_text("❍ ɴᴏ ᴡᴀɪғᴜ ғᴏᴜɴᴅ ғᴏʀ ᴛʜᴇ sᴘᴇᴄɪғɪᴇᴅ ᴛᴀɢs.")
    except Exception as e:
        await message.reply_text(f"❍ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ: {str(e)}")
        
