# filepath: src/setup_session.py

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Get these from https://my.telegram.org
API_ID = int(input("Enter your API_ID: "))
API_HASH = input("Enter your API_HASH: ")

print("\nLogging in with your spare SIM card...")
with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n✅ Success! Here is your SESSION STRING. Keep it secret!")
    print("---------------------------------------------------------")
    print(client.session.save())
    print("---------------------------------------------------------\n")
    print("Copy the string above and put it in your GitHub Repository Secrets as 'TELETHON_SESSION'.")