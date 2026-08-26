"""MIT License

Copyright (c) [Year] TEAM PURVI BOTS

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


from pyrogram import Client, filters
from faker import Faker
from SWAGGYMUSIC import app

# Create a Faker instance
fake = Faker()




# Generate person info command handler
@app.on_message(filters.command("rand"))
def generate_info(client, message):
    # Generate fake data
    name = fake.name()
    address = fake.address()
    country = fake.country()
    phone_number = fake.phone_number()
    email = fake.email()
    city = fake.city()
    state = fake.state()
    zipcode = fake.zipcode()

    # Create a message with the fake data
    info_message = (
        f"**ғᴜʟʟ ηᴧϻє :** {name}\n"
        
        f"**ᴧᴅᴅʀєss :** {address}\n"
        
        f"**𝖢σᴜηᴛʀʏ :** {country}\n"
        
        f"** 𝖯ʜσηє ɴᴜϻʙєʀ :** {phone_number}\n"
        
        f"**𝖤ϻᴧɪʟ :** {email}\n"
        
        f"**𝖢ɪᴛʏ :** {city}\n"
        
        f"**sᴛᴧᴛє :** {state}\n"
        
        f"**𝖹ɪᴘᴄσᴅє :** {zipcode}"
        
    )

    # Send the fake data to the user
    message.reply_text(info_message)
