from pyrogram import Client, filters
import requests
import random
from SWAGGYMUSIC import app

# Truth or Dare API URLs
truth_api_url = "https://api.truthordarebot.xyz/v1/truth"
dare_api_url = "https://api.truthordarebot.xyz/v1/dare"


@app.on_message(filters.command("truth"))
async def get_truth(client, message):
    try:
        # Make a GET request to the Truth API
        response = requests.get(truth_api_url)
        if response.status_code == 200:
            truth_question = response.json()["question"]
            await message.reply_text(f"<u>**тʀᴜᴛʜ ǫᴜєsᴛɪση :-**</u> \n\n{truth_question}")
        else:
            await message.reply_text("Failed to fetch a truth question. Please try again later.")
    except Exception as e:
        await message.reply_text("An error occurred while fetching a truth question. Please try again later.")
        

@app.on_message(filters.command("dare"))
async def get_dare(client, message):
    try:
        # Make a GET request to the Dare API
        response = requests.get(dare_api_url)
        if response.status_code == 200:
            try:
                dare_data = response.json()
                dare_question = dare_data.get("question", "No dare question available.")
                await message.reply_text(f"<u>**ᴅᴀʀє ǫᴜєsᴛɪση :-**</u>\n\n{dare_question}")
            except ValueError:
                await message.reply_text("Failed to parse the dare question. Please try again later.")
        else:
            await message.reply_text("Failed to fetch a dare question. Please try again later.")
    except Exception as e:
        await message.reply_text(f"An error occurred: {str(e)}")
        
