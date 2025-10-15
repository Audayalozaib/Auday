import os
import random
import configparser
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import CreateChatRequest
from auto_proxy import Proxy

# --- Configuration ---
# Replace with your own API ID and API Hash from my.telegram.org
API_ID = 28991146
API_HASH = '31b8f17f71c55f37620a6de5fee8a012'
BOT_TOKEN = '5086918397:AAEMV24UhaagNA4FfJkpLN5F3JAq-NJpxiM'

# Directory to store session files
SESSION_DIR = 'sessions'
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# --- Proxy Configuration ---
config = configparser.ConfigParser()
config.read('config.ini')
http_sources = config.get('HTTP', 'Sources').splitlines()
socks4_sources = config.get('SOCKS4', 'Sources').splitlines()
socks5_sources = config.get('SOCKS5', 'Sources').splitlines()

proxy_manager = Proxy(http_sources, socks4_sources, socks5_sources)
proxy_manager.init()
proxies = proxy_manager.proxies

# --- Bot Initialization ---
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# --- Main Menu ---
async def main_menu(conv, client):
    """Displays the main menu and handles user choices."""
    while True:
        await conv.send_message(
            'What would you like to do?',
            buttons=[
                [Button.inline('Create New Group', b'create_group')],
                [Button.inline('List Chats', b'list_chats')],
                [Button.inline('Disconnect', b'disconnect')]
            ]
        )
        press = await conv.wait_event(events.CallbackQuery)
        
        if press.data == b'create_group':
            await create_group_conversation(conv, client)
        elif press.data == b'list_chats':
            await list_chats_conversation(conv, client)
        elif press.data == b'disconnect':
            await client.log_out()
            await conv.send_message('Disconnected successfully.')
            break
        await press.answer()


# --- Conversation for Creating a Group ---
async def create_group_conversation(conv, client):
    """Handles the conversation for creating a new group."""
    await conv.send_message('Enter the name of the new group:')
    group_name = await conv.get_response()
    
    await conv.send_message('Enter the usernames of the members to add (comma-separated):')
    members_input = await conv.get_response()
    
    try:
        member_usernames = [uname.strip() for uname in members_input.text.split(',')]
        users = [await client.get_input_entity(uname) for uname in member_usernames]
        
        result = await client(CreateChatRequest(
            users=users,
            title=group_name.text
        ))
        
        await conv.send_message(f'Group "{group_name.text}" created successfully!')
        
    except Exception as e:
        await conv.send_message(f'An error occurred: {e}')


# --- Conversation for Listing Chats ---
async def list_chats_conversation(conv, client):
    """Handles the conversation for listing chats and viewing messages."""
    dialogs = await client.get_dialogs(limit=10)
    buttons = []
    for dialog in dialogs:
        buttons.append([Button.inline(dialog.name, data=f'chat_{dialog.id}')])
    
    await conv.send_message('Here are your 10 most recent chats:', buttons=buttons)
    
    press = await conv.wait_event(events.CallbackQuery)
    chat_id = int(press.data.decode().split('_')[1])
    
    messages = await client.get_messages(chat_id, limit=10)
    message_text = f'**Recent messages in {dialogs[0].name}:**\n\n'
    for message in reversed(messages):
        if message.text:
            sender = await message.get_sender()
            sender_name = sender.first_name if sender else "Unknown"
            message_text += f'**{sender_name}:** {message.text}\n'
            
    await conv.send_message(message_text)
    await press.answer()


# --- Command Handlers ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    """Handler for the /start command."""
    await event.respond(
        'Welcome! I can help you manage your Telegram accounts.',
        buttons=[
            [Button.text('Login to an Account', command='/login')],
        ]
    )
    raise events.StopPropagation

@bot.on(events.NewMessage(pattern='/login'))
async def login(event):
    """Handler for the /login command."""
    sender_id = event.sender_id
    session_file = os.path.join(SESSION_DIR, f'user_{sender_id}.session')

    proxy_info = None
    if proxies:
        proxy_type, proxy_address = random.choice(proxies)
        ip, port = proxy_address.split(':')
        proxy_info = (proxy_type, ip, int(port))

    client = TelegramClient(session_file, API_ID, API_HASH, proxy=proxy_info)
    await client.connect()

    if not await client.is_user_authorized():
        async with bot.conversation(sender_id) as conv:
            await conv.send_message('Please enter your phone number (with country code):')
            phone_number = await conv.get_response()

            try:
                sent_code = await client.send_code_request(phone_number.text)
                await conv.send_message('Please enter the code you received:')
                code = await conv.get_response()
                await client.sign_in(phone_number.text, code.text)

            except Exception as e:
                if 'password' in str(e).lower():
                    await conv.send_message('Please enter your two-step verification password:')
                    password = await conv.get_response()
                    await client.sign_in(password=password.text)
                else:
                    await conv.send_message(f'An error occurred: {e}')
                    return
    
    if await client.is_user_authorized():
        async with bot.conversation(sender_id) as conv:
            await conv.send_message('Login successful!')
            await main_menu(conv, client)
    
    await client.disconnect()


# --- Main Execution ---
if __name__ == '__main__':
    print("Bot is running...")
    bot.run_until_disconnected()
