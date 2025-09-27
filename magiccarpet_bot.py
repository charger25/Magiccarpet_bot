import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import TokenAccountOpts

# ================== CONFIG ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=72766c4b-5d3e-487a-b55c-4ad61b283e92"
TREASURY_ADDRESS = "ArgPD64dYazaTdx83gRaEFBHXTyjDrFbDXA1drC99tBH"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"  # USDT SPL

TOKEN_NAME = "Magic Carpet"
TOKEN_SYMBOL = "MAGPET"
AIRDROP_REWARD = 1000
REFERRAL_REWARD = 500
REFERRAL_BONUS_PERCENT = 0.10  # 10%
PRESALE_RATE = 0.00025  # $0.00025 per token

DATA_FILE = "data.json"
ADMINS = [123456789, 987654321]  # 👈 replace with your Telegram IDs

# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== DATABASE ==================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "payments": {}}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = load_data()

# ================== HELPERS ==================
def calculate_tokens(amount_usd: float) -> int:
    return int(amount_usd / PRESALE_RATE)

async def check_new_payments(app):
    """Background task: check USDT SPL payments to treasury"""
    client = AsyncClient(RPC_URL)
    treasury_pubkey = Pubkey.from_string(TREASURY_ADDRESS)

    while True:
        try:
            opts = TokenAccountOpts(mint=Pubkey.from_string(USDT_MINT))
            resp = await client.get_token_accounts_by_owner(treasury_pubkey, opts=opts)

            if resp.value:
                for acct in resp.value:
                    sig = acct.pubkey
                    if sig not in data["payments"]:
                        # Simulated payment detection
                        usdt_amount = 50  # Example: 50 USDT
                        tokens = calculate_tokens(usdt_amount)

                        user_id = list(data["users"].keys())[0] if data["users"] else None
                        if user_id:
                            user_id = int(user_id)
                            data["users"][str(user_id)]["balance"] += tokens
                            data["payments"][sig] = {
                                "user_id": user_id,
                                "usdt": usdt_amount,
                                "tokens": tokens,
                            }
                            save_data()

                            await app.bot.send_message(
                                chat_id=user_id,
                                text=f"🎉 Payment confirmed!\nYou received {tokens} {TOKEN_SYMBOL} "
                                     f"for {usdt_amount} USDT."
                            )

                            # Referral bonus
                            referrer_id = data["users"][str(user_id)].get("referrer")
                            if referrer_id:
                                bonus = int(tokens * REFERRAL_BONUS_PERCENT)
                                data["users"][str(referrer_id)]["balance"] += bonus
                                save_data()
                                await app.bot.send_message(
                                    chat_id=referrer_id,
                                    text=f"🎁 Referral Bonus!\nYou earned {bonus} {TOKEN_SYMBOL} "
                                         f"from your referral’s purchase."
                                )

        except Exception as e:
            logger.error(f"Payment check error: {e}")

        await asyncio.sleep(30)  # check every 30s

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "balance": AIRDROP_REWARD,
            "wallet": None,
            "referrer": None,
        }
        save_data()
        await update.message.reply_text(
            f"🎉 Welcome to {TOKEN_NAME} ({TOKEN_SYMBOL}) Airdrop!\n\n"
            f"You’ve received {AIRDROP_REWARD} {TOKEN_SYMBOL} for joining."
        )

        # Referral check
        if args:
            referrer_id = args[0]
            if referrer_id != str(user_id) and referrer_id in data["users"]:
                data["users"][referrer_id]["balance"] += REFERRAL_REWARD
                data["users"][str(user_id)]["referrer"] = referrer_id
                save_data()
                await context.bot.send_message(
                    chat_id=int(referrer_id),
                    text=f"🎉 You earned {REFERRAL_REWARD} {TOKEN_SYMBOL} for a referral!"
                )

    keyboard = [["Check Balance"], ["Buy Presale"], ["My Referral Link"], ["Set Wallet"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Choose an option below 👇", reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)

    if text == "Check Balance":
        balance = data["users"].get(user_id, {}).get("balance", 0)
        wallet = data["users"].get(user_id, {}).get("wallet", "❌ Not set")
        await update.message.reply_text(
            f"💰 Your balance: {balance} {TOKEN_SYMBOL}\n"
            f"🏦 Wallet: {wallet}"
        )

    elif text == "Buy Presale":
        await update.message.reply_text(
            f"💎 Presale Price: ${PRESALE_RATE} per {TOKEN_SYMBOL}\n\n"
            f"Send USDT (SPL) to:\n{TREASURY_ADDRESS}\n\n"
            "✅ Payments are verified automatically, tokens will be credited to you."
        )

    elif text == "My Referral Link":
        ref_link = f"https://t.me/{context.bot.username}?start={user_id}"
        await update.message.reply_text(
            f"🔗 Your referral link:\n{ref_link}\n\n"
            f"Earn {REFERRAL_REWARD} {TOKEN_SYMBOL} for each friend who joins!"
        )

    elif text == "Set Wallet":
        await update.message.reply_text("Please send your Solana wallet address.")

async def save_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    wallet = update.message.text.strip()
    if len(wallet) < 30:  # rough check
        await update.message.reply_text("❌ Invalid Solana address. Try again.")
        return
    data["users"][user_id]["wallet"] = wallet
    save_data()
    await update.message.reply_text(f"✅ Wallet address set: {wallet}")

# ================== ADMIN COMMANDS ==================
async def assign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /assign <telegram_id> <amount>")
        return
    user_id, amount = context.args
    user_id, amount = str(user_id), int(amount)
    if user_id not in data["users"]:
        await update.message.reply_text("❌ User not found.")
        return
    data["users"][user_id]["balance"] += amount
    save_data()
    await update.message.reply_text(f"✅ Assigned {amount} {TOKEN_SYMBOL} to {user_id}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    message = " ".join(context.args)
    for uid in data["users"].keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=message)
        except Exception as e:
            logger.error(f"Broadcast error to {uid}: {e}")
    await update.message.reply_text("✅ Broadcast sent.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("❌ You are not authorized.")
        return

    total_users = len(data["users"])
    total_tokens = sum(u["balance"] for u in data["users"].values())
    total_referrals = sum(1 for u in data["users"].values() if u["referrer"])
    total_usdt = sum(p["usdt"] for p in data["payments"].values())
    total_presale = sum(p["tokens"] for p in data["payments"].values())

    msg = (
        f"📊 {TOKEN_NAME} Stats\n"
        f"👥 Total Users: {total_users}\n"
        f"🎁 Airdrop Tokens Distributed: {total_tokens} {TOKEN_SYMBOL}\n"
        f"🔗 Total Referrals: {total_referrals}\n"
        f"💵 Total USDT Purchases: {total_usdt}\n"
        f"🎟️ Total Presale Tokens (Simulated): {total_presale} {TOKEN_SYMBOL}"
    )
    await update.message.reply_text(msg)

# ================== MAIN ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^(Check Balance|Buy Presale|My Referral Link|Set Wallet)$"), handle_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_wallet))

    # Admin
    app.add_handler(CommandHandler("assign", assign))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))

    # Start background payment checker
    app.job_queue.run_once(lambda ctx: asyncio.create_task(check_new_payments(app)), 1)

    app.run_polling()

if __name__ == "__main__":
    main()