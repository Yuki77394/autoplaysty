from pyrogram import Client, filters
from gtts import gTTS
from SWAGGYMUSIC import app


@app.on_message(filters.command('tts'))
async def text_to_speech(client, message):
    try:
        # Check if the command has accompanying text
        if len(message.text.split()) < 2:
            await message.reply_text(
                "**ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴛᴇxᴛ ғᴏʀ ᴛᴛs.** \n\n**ᴜsᴀɢᴇ :** `/tts i love you`"
            )
            return

        # Extract text for TTS
        text = message.text.split(' ', 1)[1]

        # Generate the TTS audio
        tts = gTTS(text=text, lang='hi')
        file_name = "speech.mp3"
        tts.save(file_name)

        # Send the generated audio file
        await app.send_audio(chat_id=message.chat.id, audio=file_name)

    except Exception as e:
        # Handle errors gracefully
        await message.repl
        
