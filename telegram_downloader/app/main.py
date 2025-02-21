import json
import os, sys
import asyncio
import time

import downloader

from datetime import datetime

from rich import print as pprint
from telethon import TelegramClient, utils
from telethon.errors import SessionPasswordNeededError

from dotenv import load_dotenv

# DEBUG:
import tracemalloc

tracemalloc.start()

#######################
load_dotenv()
api_id = int(os.getenv('id').strip())
api_hash = os.getenv('hash')
if not os.getenv('phone') and not os.getenv('channels'):
    print('[*] Error .env file not configured.')
    sys.exit()
phone = os.getenv('phone')
channels = os.getenv('channels')
if ',' in channels:
    channels = channels.split(',')
else: #Should work with single channel too.
    channels = (channels,)
watch = os.getenv('watch')
print(f"API ID: {api_id}")
print(f"API Hash: {api_hash}")
print(f"Phone: {phone}")
#######################
pprint("[*]", os.getcwd(), 'channels:', channels, __name__)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, bytes):
            return list(o)
        return json.JSONEncoder.default(self, o)

NO_CHANNEL = 0  # WILL PROMPT FOR TARGET IF 0.
######  A V A I L A B L E   M O D E S  ######
DOWNLOAD_ALL_FILES = 1
EXTRACT_ALL_LINKS = 2
DOWNLOAD_ALL_FILES_FROM_THE_LINKS = 3
######  A V A I L A B L E   N A M I N G  C O N V E N T I O N S ######
SHA256_PLUS_EXT = 1
ORIGINAL_FILENAMES = 2
ORIGINAL_FILENAMES_AND_SHA256 = 3

_statix = {  # IT WILL USE VALUES FROM THE OVERRIDES OR GO BACK TO DEFAULT ONES.
    "id":           api_id,  # API ID for user account
    "hash":         api_hash,  # API Hash for user account
    "phone":        phone,  # Your phone number
    "chan":         NO_CHANNEL,  # Channel to interact with:
    # String: Assumes a username, phone number, or invite link.
    # Integer: Assumes a user ID, group ID, or channel ID, THAT IS NOT WORKING NOW.
    "mode":         DOWNLOAD_ALL_FILES,
    "naming":       ORIGINAL_FILENAMES_AND_SHA256
}
MAX_TASKS = 3
semaphore = asyncio.Semaphore(MAX_TASKS)

async def telegram_dldr(channel_override: str = _statix['chan'], phone_override: str = _statix['phone'],
                        hash_override: str = _statix['hash'], mode_override: int = _statix['mode'],
                        naming_override: int = _statix['naming']):
    async with semaphore:
        start = time.time()

        if not channel_override and not _statix['chan']:
            print('[*] WARNING : INTERACTIVE MODE IS BEING USED!')
            ctx = input('Provide the target channel:')
            _statix['chan'] = ctx if not ctx.isnumeric() else int(ctx)

        allowed_modes, allowed_naming = (1, 2, 3), (1, 2, 3)

        if not mode_override and not _statix['mode']:
            print('[*] WARNING : INTERACTIVE MODE IS BEING USED!')
            mode = int(input('''Please select the mode:
            1. Download all files.
            2. Extract all links.
            3. Download all files from the links
            '''))
            if mode in allowed_modes:
                _statix['mode'] = mode
            else:
                raise ValueError(f'[*] ERROR: Mode not in allowed modes - {allowed_modes}')

        if not naming_override and not _statix['naming']:
            print('[*] WARNING : INTERACTIVE MODE IS BEING USED!')
            naming = int(input('''Please select the FILE naming convention:
        1.sha256 + extension.
        2.original filenames.
        3.original filenames + sha256 + extension.
        '''))
            if naming in allowed_naming:
                _statix['naming'] = naming
            else:
                raise ValueError(f'[*] ERROR: Naming convention not in allowed modes - {allowed_modes}')

        # Initialize the Telegram Client for user account
        async with TelegramClient(
                session=f"./session.{api_id}.session", # Needs to match the API ID
                api_id=_statix["id"],
                api_hash=_statix["hash"]
        ) as client:
            me = await client.get_me()
            pprint(me)
            print(utils.get_display_name(me))
            # Start client and authenticate
            if not await client.is_user_authorized():
                try:
                    await client.send_code_request(_statix["phone"])
                    code = input("Enter the login code sent to your Telegram account: ")
                    await client.sign_in(phone=_statix["phone"], code=code)
                except SessionPasswordNeededError:
                    password = input("Enter your 2FA password: ")
                    await client.sign_in(password=password)

            # Print user info
            me = await client.get_me()
            pprint(f"Logged in as: {me.username or me.first_name}")

            # Interact with a channel
            my_chan = await client.get_entity(channel_override or _statix["chan"])
            pprint(f"Channel info: {my_chan.title} (ID: {my_chan.id})")

            latest_message = await client.get_messages(my_chan, limit=1)
            if latest_message:
                max_id = latest_message[0].id
                print(f"Max Post ID: {max_id}")

            # Assuming downloader.Start has an async version
            await downloader.Start(client, my_chan, _statix)

        end = time.time()
        dif = end - start
        print(f"Time: {dif:.2f} seconds")

async def main():
    while True:
        for channel in channels:
            try:
                await telegram_dldr(channel_override=channel)
                print(f"Jobs completed at {datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                print('Job failed.', e)
            await asyncio.sleep(60)  # Changed to await to ensure asynchronous wait

if __name__ == '__main__':
    asyncio.run(main())