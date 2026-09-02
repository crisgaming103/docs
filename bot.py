#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
╔══════════════════════════════════════════════════════════════╗
║   MARKCPM – PHOENIX HYBRID INJECTOR                           ║
║   VortexaCloud Edition - FIXED EVENT LOOP                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import sys
import json
import base64
import time
import asyncio
import aiohttp
import random
import warnings
import re
import os
import threading
from datetime import datetime
from aiohttp import web

# Telegram imports
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# Console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

# Dependency check
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
    import brotli
except ImportError:
    print("Missing dependencies! Run: pip install aiohttp pycryptodome brotli python-telegram-bot")
    sys.exit(1)

# ================================================================
#  CONFIGURATION
# ================================================================
# ⚠️ PALITAN MO ITO NG BAGONG TOKEN MULA SA @BotFather
BOT_TOKEN = "8838736873:AAF-0esSDwy-PRsmRmnyeKvo3JUlpWYEZwI"
 # HARDCODED (PALITAN!)

# ================================================================
#  PROXY SLOT (ilagay mo ang mga proxy mo dito, kung wala, iwanang walang laman)
# ================================================================
PROXY_LIST = [
    # "http://user:pass@proxy1.com:8080",
    # "socks5://proxy2.com:1080",
]

def get_random_proxy():
    return random.choice(PROXY_LIST) if PROXY_LIST else None

# ============================================================#  REST OF THE CONFIG
# ================================================================
FLANKER_VERSION = "3.0.0-PHOENIX"
FLANKER_SIGNATURE = "PH03N1X_C0R3"
FLANKER_DEVICE_PREFIX = "MARKCPM-DEVICE-"
DEVELOPER = "MARKMWEHEHE"

API_KEY = 'AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ'
CF_BASE = 'https://europe-west1-cpm-2-7cea1.cloudfunctions.net'
KEY_ADD = '12345678'
IV_ADD = '01234567'
VERSION = '1.3.2.3'
CLIENT_HASH = 'F05A72840B40DC4FAADF539C5E38062527AE6422'
OG_BASE = 'https://cpm-2.ogames.kz/api'
OG_KEY = '320b93f3e7f4410aa52ce24da363ad04'
BUNDLE_ID = 'com.olzhas.carparking.multyplayer2'
USER_AGENT = 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
FB_LOGIN = f'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}'

# ================================================================
#  GLOBAL STATE
# ================================================================
session = None
token = None
uid = None
email = None
password = None
is_farming = False
farming_task = None
stop_event = asyncio.Event()
last_balance = 0
last_status = "Idle"
chat_id = None

# ================================================================
#  CRYPTO ENGINE
# ================================================================
class PhoenixCrypto:
    def __init__(self, uid):
        self.uid = uid
        self.phoenix_key = (uid[:8] + KEY_ADD).encode()[:16]
        self.phoenix_iv = (uid[:8] + IV_ADD).encode()[:16]

    def phoenix_encrypt(self, plaintext):
        cipher = AES.new(self.phoenix_key, AES.MODE_CBC, self.phoenix_iv)
        encrypted = cipher.encrypt(pad(plaintext.encode(), 16))
        return base64.b64encode(encrypted).decode()

    def phoenix_decrypt(self, ciphertext):
        if not ciphertext:
            return None
        try:
            cipher = AES.new(self.phoenix_key, AES.MODE_CBC, self.phoenix_iv)
            decrypted = cipher.decrypt(base64.b64decode(ciphertext))
            return unpad(decrypted, 16).decode()
        except Exception:
            return None

    def phoenix_extract_value(self, data):
        if isinstance(data, (int, float)):
            return int(data)
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return self.phoenix_extract_value(parsed)
            except:
                pass
            if data.isdigit():
                return int(data)
            numbers = re.findall(r'\d+', data)
            if numbers:
                return int(numbers[0])
        if isinstance(data, list):
            for item in data:
                val = self.phoenix_extract_value(item)
                if val is not None:
                    return val
        if isinstance(data, dict):
            for key in ['coins', 'value', 'coin', 'amount', 'points', 'data']:
                if key in data:
                    val = self.phoenix_extract_value(data[key])
                    if val is not None:
                        return val
        return None

# ================================================================
#  UTILITIES
# ================================================================
def phoenix_gen_device():
    return FLANKER_DEVICE_PREFIX + ''.join(random.choice('0123456789abcdef') for _ in range(28))

def phoenix_headers(token):
    return {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json; charset=utf-8",
        "X-Unity-Version": "2022.3.62f2",
        "Authorization": f"Bearer {token}",
        "X-Client-Hash": CLIENT_HASH,
        "X-Phoenix-Signature": FLANKER_SIGNATURE,
        "X-Phoenix-Version": FLANKER_VERSION,
        "X-Phoenix-Developer": DEVELOPER,
    }

def phoenix_ogames_headers(token, uid, device_id=None):
    return {
        "X-Firebase-Token": token,
        "X-Client-Platform": "ANDROID",
        "X-Client-Version": VERSION,
        "X-Client-DeviceId": device_id or phoenix_gen_device(),
        "X-Api-Key": OG_KEY,
        "X-Client-Env": "prod",
        "X-Bundle-Id": BUNDLE_ID,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Client-Hash": CLIENT_HASH,
        "X-Phoenix-Tag": FLANKER_SIGNATURE,
        "X-Phoenix-Developer": DEVELOPER,
    }

# ================================================================
#  NETWORK OPERATIONS
# ================================================================
async def phoenix_cf_request(fn, payload, token, session, timeout=30, proxy=None):
    url = f"{CF_BASE}/{fn}"
    body = json.dumps({"data": payload})
    hdrs = phoenix_headers(token)

    for attempt in range(3):
        try:
            async with session.post(url, headers=hdrs, data=body,
                                   proxy=proxy or get_random_proxy(),
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status in (429, 500, 502, 503):
                    await asyncio.sleep(1 + attempt * 2)
                    continue
                if response.status == 404:
                    return None
                text = await response.text()
                try:
                    parsed = json.loads(text)
                    return parsed.get("result")
                except json.JSONDecodeError:
                    if attempt < 2:
                        await asyncio.sleep(1 + attempt * 2)
                        continue
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt < 2:
                await asyncio.sleep(1 + attempt * 2)
                continue
            if proxy:
                return await phoenix_cf_request(fn, payload, token, session, timeout, proxy=None)
            return None
    return None

async def phoenix_start_session(token, uid, session):
    device_id = phoenix_gen_device()
    oh = phoenix_ogames_headers(token, uid, device_id)
    proxy = get_random_proxy()
    try:
        await session.get(f"{OG_BASE}/check-service/v1/hash/check",
                         headers=oh, proxy=proxy,
                         timeout=aiohttp.ClientTimeout(total=15))
    except:
        pass
    try:
        await session.post(f"{OG_BASE}/check-service/v1/session/start",
                          headers=oh, json={}, proxy=proxy,
                          timeout=aiohttp.ClientTimeout(total=15))
    except:
        pass
    response = await phoenix_cf_request("MasterMainStartup23_1", "0", token, session, proxy=proxy)
    if response is None:
        response = await phoenix_cf_request("MasterMainStartup22_1", "0", token, session, proxy=proxy)
    return response

async def phoenix_login(email, password, session):
    proxy = get_random_proxy()
    try:
        async with session.post(FB_LOGIN, json={
            "email": email,
            "password": password,
            "returnSecureToken": True
        }, proxy=proxy,
        timeout=aiohttp.ClientTimeout(total=20)) as response:
            data = await response.json()
            if "idToken" in data:
                return {
                    "token": data["idToken"],
                    "uid": data["localId"],
                    "email": data.get("email", email)
                }
            else:
                return None
    except Exception:
        try:
            async with session.post(FB_LOGIN, json={
                "email": email,
                "password": password,
                "returnSecureToken": True
            }, timeout=aiohttp.ClientTimeout(total=20)) as response:
                data = await response.json()
                if "idToken" in data:
                    return {
                        "token": data["idToken"],
                        "uid": data["localId"],
                        "email": data.get("email", email)
                    }
                else:
                    return None
        except:
            return None

async def phoenix_get_coins(session, token, uid):
    headers = phoenix_headers(token)
    url = f"{CF_BASE}/GetCoins23_1"
    proxy = get_random_proxy()
    try:
        async with session.post(url, headers=headers, json={"data": None}, proxy=proxy) as response:
            if response.status == 200:
                result = await response.json()
                if "result" in result:
                    result_data = result["result"]
                    if isinstance(result_data, dict) and "data" in result_data:
                        encrypted_data = result_data["data"]
                        crypto = PhoenixCrypto(uid)
                        try:
                            decrypted_str = crypto.phoenix_decrypt(encrypted_data)
                            coins = crypto.phoenix_extract_value(decrypted_str)
                            if coins is not None:
                                return coins
                        except:
                            return None
        return None
    except:
        try:
            async with session.post(url, headers=headers, json={"data": None}) as response:
                if response.status == 200:
                    result = await response.json()
                    if "result" in result:
                        result_data = result["result"]
                        if isinstance(result_data, dict) and "data" in result_data:
                            encrypted_data = result_data["data"]
                            crypto = PhoenixCrypto(uid)
                            try:
                                decrypted_str = crypto.phoenix_decrypt(encrypted_data)
                                coins = crypto.phoenix_extract_value(decrypted_str)
                                if coins is not None:
                                    return coins
                            except:
                                return None
            return None
        except:
            return None

# ================================================================
#  HYBRID FARMING ENGINE
# ================================================================
async def phoenix_farm_engine(token, uid, session, stop_event, ctx, chat_id):
    crypto = PhoenixCrypto(uid)
    global last_balance, last_status

    all_combos_drag = [(a, b, c) for a in range(10) for b in range(1, 7) for c in range(10)]
    all_combos_combo = [(car, place, gear) for car in range(6) for place in range(1, 4) for gear in range(2)]

    await asyncio.sleep(2)

    while not stop_event.is_set():
        total_earned = 0

        # Drag Racing
        for i in range(0, len(all_combos_drag), 50):
            if stop_event.is_set():
                break
            batch = all_combos_drag[i:i+50]
            tasks = []
            for seq in batch:
                a, b, c = seq
                payload = f"{a},{b},{c}"
                encrypted = crypto.phoenix_encrypt(payload)
                proxy = get_random_proxy()
                tasks.append(asyncio.create_task(
                    session.post(f"{CF_BASE}/SetDragRacing23_1",
                                 headers=phoenix_headers(token),
                                 data=json.dumps({"data": encrypted}),
                                 proxy=proxy,
                                 timeout=aiohttp.ClientTimeout(total=30))
                ))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception) or res is None:
                    continue
                if res.status == 200:
                    try:
                        result = await res.json()
                        if "result" in result and isinstance(result["result"], dict):
                            enc = result["result"].get("data")
                            if enc:
                                dec = crypto.phoenix_decrypt(enc)
                                coins = crypto.phoenix_extract_value(dec)
                                if coins and coins > 0:
                                    total_earned += coins
                    except:
                        pass
            await asyncio.sleep(0.5)

        # Combo Farming
        completed = set()
        for round_num in range(1, 11):
            if stop_event.is_set():
                break
            pending = [combo for combo in all_combos_combo if combo not in completed]
            if not pending:
                break
            tasks = []
            for combo in pending:
                car, place, gear = combo
                payload = f"{car},{place},{gear}"
                encrypted = crypto.phoenix_encrypt(payload)
                proxy = get_random_proxy()
                tasks.append(asyncio.create_task(
                    phoenix_cf_request("SetDragRacing22_1", encrypted, token, session, proxy=proxy)
                ))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception) or res is None:
                    continue
                try:
                    arr = res if isinstance(res, list) else json.loads(res)
                    if len(arr) >= 2:
                        dec = crypto.phoenix_decrypt(arr[1]) if isinstance(arr[1], str) else None
                        if dec and dec.isdigit():
                            coins = int(dec)
                            if coins > 0:
                                total_earned += coins
                                completed.add(combo)
                except:
                    pass
            await asyncio.sleep(0.7 if round_num <= 3 else 1.5)

        # Update balance
        current = await phoenix_get_coins(session, token, uid)
        if current is not None:
            last_balance = current
        last_status = f"Earned {total_earned} in last cycle"

        if total_earned > 0:
            try:
                await ctx.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ Cycle complete!\n"
                         f"Earned: **{total_earned:,}** coins\n"
                         f"Current balance: **{last_balance:,}**",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass

        await asyncio.sleep(30)

# ================================================================
#  TELEGRAM HANDLERS
# ================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global chat_id
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "🔥 *MarkCPM – Phoenix Hybrid Injector*\n\n"
        "Commands:\n"
        "/login <email> <password> – Authenticate\n"
        "/farm – Start farming\n"
        "/stop – Stop farming\n"
        "/balance – Get current balance\n"
        "/status – Show bot status\n"
        "/help – Show this message\n\n"
        "Use /login first, then /farm.",
        parse_mode=ParseMode.MARKDOWN
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global session, token, uid, email, password, chat_id
    chat_id = update.effective_chat.id

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /login <email> <password>")
        return

    email = context.args[0]
    password = context.args[1]

    if session is None:
        session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))

    await update.message.reply_text("🔑 Authenticating...")
    auth = await phoenix_login(email, password, session)
    if auth is None:
        await update.message.reply_text("❌ Login failed. Check credentials.")
        return

    token = auth["token"]
    uid = auth["uid"]
    await update.message.reply_text(
        f"✅ Login successful!\nUID: `{uid[:16]}...`",
        parse_mode=ParseMode.MARKDOWN
    )

    await phoenix_start_session(token, uid, session)

    bal = await phoenix_get_coins(session, token, uid)
    if bal is not None:
        last_balance = bal
        await update.message.reply_text(f"💰 Current balance: {bal:,}")

async def farm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_farming, farming_task, stop_event, chat_id
    chat_id = update.effective_chat.id

    if token is None or uid is None:
        await update.message.reply_text("❌ You must login first: /login <email> <password>")
        return
    if is_farming:
        await update.message.reply_text("⚠️ Farming already in progress.")
        return

    stop_event.clear()
    is_farming = True
    await update.message.reply_text("🚀 Starting farming...\nUse /stop to terminate.")

    farming_task = asyncio.create_task(
        phoenix_farm_engine(token, uid, session, stop_event, context, chat_id)
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_farming, farming_task
    if not is_farming:
        await update.message.reply_text("⚠️ Not farming.")
        return

    stop_event.set()
    if farming_task:
        farming_task.cancel()
        try:
            await farming_task
        except asyncio.CancelledError:
            pass
    is_farming = False
    await update.message.reply_text("⏹️ Farming stopped.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_balance, token, uid, session
    if token is None or uid is None:
        await update.message.reply_text("❌ Login first.")
        return
    if session is None:
        await update.message.reply_text("❌ Session not initialized. Use /login")
        return
    bal = await phoenix_get_coins(session, token, uid)
    if bal is not None:
        last_balance = bal
        await update.message.reply_text(f"💰 Current balance: {bal:,}")
    else:
        await update.message.reply_text("❌ Could not fetch balance.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_farming, last_balance, last_status, token
    msg = "📊 *Status:*\n"
    msg += f"Farming: {'🟢 Active' if is_farming else '🔴 Idle'}\n"
    msg += f"Balance: **{last_balance:,}**\n"
    msg += f"Last cycle: {last_status}\n"
    msg += f"Logged in: {'Yes' if token else 'No'}"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ================================================================
#  WEB SERVER (runs in a separate thread with its own loop)
# ================================================================
async def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", lambda req: web.Response(text="OK"))
    app.router.add_get("/health", lambda req: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"✅ Web server started on port {port}")
    # Keep alive
    await asyncio.Event().wait()

def start_web_server_in_thread():
    """Run web server in a separate thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_web_server())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()

# ================================================================
#  MAIN
# ================================================================
def main():
    print("🚀 Starting MarkCPM bot with web server in thread...")
    # Start web server in a daemon thread
    thread = threading.Thread(target=start_web_server_in_thread, daemon=True)
    thread.start()

    # Build and run bot (this will block the main thread)
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("farm", farm))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("status", status))

    # Run polling (this is blocking and handles its own loop)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
