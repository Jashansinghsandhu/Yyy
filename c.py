import logging
import random
import string
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
import httpx
from web3 import Web3
from eth_account import Account
import secrets # For secure token generation
import hashlib # For hashing PINs
import math 

# NEW FEATURE - AI Integration (Switched to Perplexity AI)
from openai import OpenAI
# NEW FEATURE - Added g4f for a free AI option
import g4f

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions, Bot, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
import atexit
from bip_utils import Bip44, Bip44Coins, Bip44Changes

# --- Bot Configuration ---
BOT_TOKEN = "8040367557:AAFp9JbYuhxm6-oDlIrpY8kDTFJtCJXPPjI"
BOT_OWNER_ID = 6083286836
MIN_BALANCE = 0.1
## NEW FEATURE - AI Integration ##
PERPLEXITY_API_KEY = "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" # I will add this
# NEW FEATURE - MEXC Price Integration
MEXC_API_KEY = "mx0vgltPHKyw92y4qZ" # I will add this
MEXC_API_SECRET = "5f4f81217f514a799e4d77842bcc4a26" # I will add this

# --- Escrow Configuration ---
# LEAVE THESE BLANK - I will add them manually
ESCROW_DEPOSIT_ADDRESS = "0xdda0e87f6c1344e07cfce9cefb12f3a286a0fb38"  # Your fixed BEP20 address for receiving escrow funds
ESCROW_WALLET_PRIVATE_KEY = "0bbaf8d35b64859555b1a6acc7909ac349bced46b2fcf2c8d616343fec138353" # The private key for the above address to send funds
ESCROW_DEPOSIT_NETWORK = "bsc"
ESCROW_DEPOSIT_TOKEN_CONTRACT = "0x55d398326f99059fF775485246999027B3197955" # USDT BEP20
ESCROW_DEPOSIT_TOKEN_DECIMALS = 18

## NEW FEATURE - Referral System Configuration ##
REFERRAL_DEPOSIT_COMMISSION_RATE = 0.005  # 0.5%
REFERRAL_BET_COMMISSION_RATE = 0.001      # 0.1%

# --- Persistent Storage Directory ---
DATA_DIR = "user_data"
ESCROW_DIR = "escrow_deals"
LOGS_DIR = "logs"
GROUPS_DIR = "group_data" # NEW: For group settings
RECOVERY_DIR = "recovery_data" # NEW: For recovery tokens
GIFT_CODE_DIR = "gift_codes" # NEW: For gift codes
STATE_FILE = "bot_state.json"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ESCROW_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(GROUPS_DIR, exist_ok=True) # NEW
os.makedirs(RECOVERY_DIR, exist_ok=True) # NEW
os.makedirs(GIFT_CODE_DIR, exist_ok=True) # NEW

# --- In-memory Data ---
user_wallets = {}
username_to_userid = {}
user_stats = {}
# REFACTOR: Centralized session/game management
game_sessions = {} # Replaces matches, mines_games, coin_flip_games, etc.
user_pending_invitations = {} # Kept for PvP flow
user_deposit_sessions = {}
escrow_deals = {} # To hold active escrow deals
group_settings = {} # NEW: To hold group configurations
recovery_data = {} # NEW: To hold recovery token data
gift_codes = {} # NEW: To hold gift code data

# --- Global Control Flag ---
bot_stopped = False

## NEW FEATURE - Bot Settings ##
bot_settings = {
    "daily_bonus_amount": 0.50,
    "maintenance_mode": False,
    "banned_users": [], # For permanent bans
    "tempbanned_users": [], # For temporary (withdrawal) bans
    "house_balance": 100_000_000_000_000.0, # NEW: House balance set to 100 Trillion
    "game_limits": {}, # NEW: For min/max bets per game
    "withdrawals_enabled": True, # NEW
    "deposits_enabled": True, # NEW
}

## NEW FEATURE - Achievements ##
ACHIEVEMENTS = {
    "wager_100": {"name": "🎲 Player", "description": "Wager a total of $100.", "emoji": "🎲", "type": "wager", "value": 100},
    "wager_1000": {"name": "💰 High Roller", "description": "Wager a total of $1,000.", "emoji": "💰", "type": "wager", "value": 1000},
    "wager_10000": {"name": "👑 Whale", "description": "Wager a total of $10,000.", "emoji": "👑", "type": "wager", "value": 10000},
    "wins_50": {"name": "👍 Winner", "description": "Win 50 games.", "emoji": "👍", "type": "wins", "value": 50},
    "wins_250": {"name": "🏆 Champion", "description": "Win 250 games.", "emoji": "🏆", "type": "wins", "value": 250},
    "pvp_wins_25": {"name": "⚔️ Duelist", "description": "Win 25 PvP matches.", "emoji": "⚔️", "type": "pvp_wins", "value": 25},
    "lucky_100x": {"name": "🌟 Lucky Star", "description": "Win a bet with a 100x or higher multiplier.", "emoji": "🌟", "type": "multiplier", "value": 100},
    "referral_master": {"name": "🤝 Connector", "description": "Refer 5 active users.", "emoji": "🤝", "type": "referrals", "value": 5},
}
## NEW FEATURE - Level System ##
LEVELS = [
    {"level": 0, "name": "None", "wager_required": 0, "reward": 0, "rakeback_percentage": 0.01},
    {"level": 1, "name": "Bronze", "wager_required": 10000, "reward": 15, "rakeback_percentage": 0.03},
    {"level": 2, "name": "Silver", "wager_required": 50000, "reward": 30, "rakeback_percentage": 0.04},
    {"level": 3, "name": "Gold", "wager_required": 100000, "reward": 60, "rakeback_percentage": 0.06},
    {"level": 4, "name": "Platinum I", "wager_required": 250000, "reward": 100, "rakeback_percentage": 0.07},
    {"level": 5, "name": "Platinum II", "wager_required": 500000, "reward": 200, "rakeback_percentage": 0.08},
    {"level": 6, "name": "Platinum III", "wager_required": 1000000, "reward": 400, "rakeback_percentage": 0.09},
    {"level": 7, "name": "Platinum IV", "wager_required": 2500000, "reward": 800, "rakeback_percentage": 0.09},
    {"level": 8, "name": "Platinum V", "wager_required": 5000000, "reward": 1600, "rakeback_percentage": 0.10},
    {"level": 9, "name": "Platinum VI", "wager_required": 10000000, "reward": 3200, "rakeback_percentage": 0.10},
    {"level": 10, "name": "Diamond I", "wager_required": 25000000, "reward": 6400, "rakeback_percentage": 0.11},
    {"level": 11, "name": "Diamond II", "wager_required": 50000000, "reward": 25600, "rakeback_percentage": 0.11},
    {"level": 12, "name": "Diamond III", "wager_required": 100000000, "reward": 51200, "rakeback_percentage": 0.12},
]
## NEW FEATURE - Language Support ##
# For simplicity, strings are in a dict. For larger bots, JSON files are better.
LANGUAGES = {
    "en": {
        "welcome": "🎰 <b>Welcome to Telegram Casino & Escrow Bot!</b> 🎰\n\n👋 Hello {first_name}!\n\n...",
        "daily_claim_success": "🎉 You have successfully claimed your daily bonus of ${amount:.2f}!",
        "daily_claim_wait": "⏳ You have already claimed your daily bonus. Please wait {hours}h {minutes}m before claiming again.",
        "achievement_unlocked": "🏅 <b>Achievement Unlocked!</b> 🏅\n\n"
                               "You have earned the <b>{emoji} {name}</b> badge!\n<i>{description}</i>"
        # ... more strings
    },
    "es": {
        "welcome": "🎰 <b>¡Bienvenido al Bot de Casino y Escrow de Telegram!</b> 🎰\n\n👋 ¡Hola {first_name}!\n\n...",
        "daily_claim_success": "🎉 ¡Has reclamado con éxito tu bono diario de ${amount:.2f}!",
        "daily_claim_wait": "⏳ Ya has reclamado tu bono diario. Por favor, espera {hours}h {minutes}m antes de volver a reclamar.",
        "achievement_unlocked": "🏅 <b>¡Logro Desbloqueado!</b> 🏅\n\n"
                               "¡Has ganado la insignia <b>{emoji} {name}</b>!\n<i>{description}</i>"
        # ... more strings
    }
}
DEFAULT_LANG = "en"

def get_text(key, lang_code, **kwargs):
    lang_code = lang_code if lang_code in LANGUAGES else DEFAULT_LANG
    text = LANGUAGES.get(lang_code, LANGUAGES[DEFAULT_LANG]).get(key, f"Missing translation for '{key}'")
    return text.format(**kwargs)


## NEW FEATURE ##
# --- Conversation Handler States ---
(SELECT_BOMBS, SELECT_BET_AMOUNT, SELECT_TARGET_SCORE, ASK_AI_PROMPT, CHOOSE_AI_MODEL,
 ADMIN_SET_BALANCE_USER, ADMIN_SET_BALANCE_AMOUNT, ADMIN_SET_DAILY_BONUS, ADMIN_SEARCH_USER,
 ADMIN_BROADCAST_MESSAGE, ADMIN_SET_HOUSE_BALANCE, ADMIN_LIMITS_CHOOSE_TYPE,
 ADMIN_LIMITS_CHOOSE_GAME, ADMIN_LIMITS_SET_AMOUNT,
 SETTINGS_RECOVERY_PIN, RECOVER_ASK_TOKEN, RECOVER_ASK_PIN,
 ADMIN_GIFT_CODE_AMOUNT, ADMIN_GIFT_CODE_CLAIMS) = range(19)

# --- GAME MULTIPLIERS AND CONFIGS ---

# Roulette configuration
ROULETTE_CONFIG = {
    "single_number": {"multiplier": 35, "count": 1},
    "red": {"multiplier": 2, "numbers": [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]},
    "black": {"multiplier": 2, "numbers": [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]},
    "even": {"multiplier": 2, "numbers": [2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36]},
    "odd": {"multiplier": 2, "numbers": [1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35]},
    "low": {"multiplier": 2, "numbers": list(range(1, 19))},
    "high": {"multiplier": 2, "numbers": list(range(19, 37))},
    "column1": {"multiplier": 3, "numbers": [1,4,7,10,13,16,19,22,25,28,31,34]},
    "column2": {"multiplier": 3, "numbers": [2,5,8,11,14,17,20,23,26,29,32,35]},
    "column3": {"multiplier": 3, "numbers": [3,6,9,12,15,18,21,24,27,30,33,36]},
}

# Tower game multiplier chart (4 columns, varying bombs per row)
TOWER_MULTIPLIERS = {
    1: {  # 1 bomb per row
        1: 1.33, 2: 1.78, 3: 2.37, 4: 3.16, 5: 4.21, 6: 5.61
    },
    2: {  # 2 bombs per row
        1: 2.00, 2: 4.00, 3: 8.00, 4: 16.00, 5: 32.00, 6: 64.00
    },
    3: {  # 3 bombs per row
        1: 4.00, 2: 16.00, 3: 64.00, 4: 256.00, 5: 1024.00, 6: 4096.00
    }
}

# Blackjack basic setup
CARD_VALUES = {
    'A': [1, 11], '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10
}
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

# --- MINES MULTIPLIER CHART ---
MINES_MULT_TABLE = {
    # 1 Bomb
    1: {1: 1.03, 2: 1.08, 3: 1.12, 4: 1.18, 5: 1.24, 6: 1.30, 7: 1.37, 8: 1.46, 9: 1.55, 10: 1.65, 11: 1.77, 12: 1.90, 13: 2.06, 14: 2.25, 15: 2.47, 16: 2.75, 17: 3.09, 18: 3.54, 19: 4.12, 20: 4.95, 21: 6.19, 22: 8.25, 23: 12.37, 24: 24.75},
    # 2 Bombs
    2: {1: 1.08, 2: 1.17, 3: 1.29, 4: 1.41, 5: 1.56, 6: 1.74, 7: 1.94, 8: 2.18, 9: 2.47, 10: 2.83, 11: 3.26, 12: 3.81, 13: 4.50, 14: 5.40, 15: 6.60, 16: 8.25, 17: 10.61, 18: 14.14, 19: 19.80, 20: 29.70, 21: 49.50, 22: 99.0, 23: 297.0},
    # Continue with existing multiplier table...
    3: {1: 1.12, 2: 1.29, 3: 1.48, 4: 1.71, 5: 2.00, 6: 2.35, 7: 2.79, 8: 3.35, 9: 4.07, 10: 5.00, 11: 6.26, 12: 7.96, 13: 10.35, 14: 13.80, 15: 18.97, 16: 27.11, 17: 40.66, 18: 65.06, 19: 113.85, 20: 227.70, 21: 596.25, 22: 2277.0},
    4: {1: 1.18, 2: 1.41, 3: 1.71, 4: 2.09, 5: 2.58, 6: 3.23, 7: 4.09, 8: 5.26, 9: 6.88, 10: 9.17, 11: 12.51, 12: 17.52, 13: 25.30, 14: 37.95, 15: 59.64, 16: 99.39, 17: 178.91, 18: 357.81, 19: 834.90, 20: 2504.70, 21: 12523.50},
    5: {1: 1.24, 2: 1.56, 3: 2.00, 4: 2.58, 5: 3.39, 6: 4.52, 7: 6.14, 8: 8.50, 9: 12.04, 10: 17.52, 11: 26.27, 12: 40.87, 13: 66.41, 14: 113.85, 15: 208.72, 16: 417.45, 17: 939.26, 18: 2504.70, 19: 8766.45, 20: 52598.70},
    # Add rest of existing table...
    # 6 Bombs
    6: {1: 1.30, 2: 1.74, 3: 2.35, 4: 3.23, 5: 4.52, 6: 6.46, 7: 9.44, 8: 14.17, 9: 21.89, 10: 35.03, 11: 58.38, 12: 102.17, 13: 189.75, 14: 379.50, 15: 834.90, 16: 2087.25, 17: 6261.75, 18: 25047.0, 19: 175329.0},
    # 7 Bombs
    7: {1: 1.37, 2: 1.94, 3: 2.79, 4: 4.09, 5: 6.14, 6: 9.44, 7: 14.95, 8: 24.47, 9: 41.60, 10: 73.95, 11: 138.66, 12: 277.33, 13: 600.87, 14: 1442.10, 15: 3965.77, 16: 13219.25, 17: 59486.62, 18: 475893.0},
    # 8 Bombs
    8: {1: 1.46, 2: 2.18, 3: 3.35, 4: 5.26, 5: 8.50, 6: 14.17, 7: 24.47, 8: 44.05, 9: 83.20, 10: 166.40, 11: 356.56, 12: 831.98, 13: 2163.15, 14: 6489.45, 15: 23794.65, 16: 118973.25, 17: 1070759.25},
    # 9 Bombs
    9: {1: 1.55, 2: 2.47, 3: 4.07, 4: 6.88, 5: 12.04, 6: 21.89, 7: 41.60, 8: 83.20, 9: 176.80, 10: 404.10, 11: 1010.26, 12: 2828.73, 13: 9193.39, 14: 36773.55, 15: 202254.52, 16: 2022545.25},
    # 10 Bombs
    10: {1: 1.65, 2: 2.83, 3: 5.00, 4: 9.17, 5: 17.52, 6: 35.03, 7: 73.95, 8: 166.40, 9: 404.10, 10: 1077.61, 11: 3232.84, 12: 11314.94, 13: 49301.40, 14: 294188.40, 15: 3236072.40},
    # 11 Bombs
    11: {1: 1.77, 2: 3.26, 3: 6.26, 4: 12.51, 5: 26.27, 6: 58.38, 7: 138.66, 8: 356.56, 9: 1010.26, 10: 3232.84, 11: 12123.15, 12: 56574.69, 13: 367735.50, 14: 4412826.0},
    # 12 Bombs
    12: {1: 1.90, 2: 3.81, 3: 7.96, 4: 17.52, 5: 40.87, 6: 102.17, 7: 277.33, 8: 831.98, 9: 2828.73, 10: 11314.94, 11: 56574.69, 12: 396022.85, 13: 5148297.0},
    # 13 Bombs
    13: {1: 2.06, 2: 4.50, 3: 10.35, 4: 25.30, 5: 66.41, 6: 189.75, 7: 600.87, 8: 2163.15, 9: 9193.39, 10: 49301.40, 11: 367735.50, 12: 5148297.0},
    # 14 Bombs
    14: {1: 2.25, 2: 5.40, 3: 13.80, 4: 37.95, 5: 113.85, 6: 379.50, 7: 1442.10, 8: 6489.45, 9: 36773.55, 10: 294188.40, 11: 4412826.0},
    # 15 Bombs
    15: {1: 2.47, 2: 6.60, 3: 18.97, 4: 59.64, 5: 208.72, 6: 834.90, 7: 3965.77, 8: 23794.65, 9: 202254.52, 10: 3236072.40},
    # 16 Bombs
    16: {1: 2.75, 2: 8.25, 3: 27.11, 4: 99.39, 5: 417.45, 6: 2087.25, 7: 13219.25, 8: 118973.25, 9: 2022545.25},
    # 17 Bombs
    17: {1: 3.09, 2: 10.61, 3: 40.66, 4: 178.91, 5: 939.26, 6: 6261.75, 7: 59486.62, 8: 1070759.25},
    # 18 Bombs
    18: {1: 3.54, 2: 14.14, 3: 65.06, 4: 357.81, 5: 2504.70, 6: 25047.0, 7: 475893.0},
    # 19 Bombs
    19: {1: 4.12, 2: 19.80, 3: 113.85, 4: 834.90, 5: 8766.45, 6: 175329.0},
    # 20 Bombs
    20: {1: 4.95, 2: 29.70, 3: 227.70, 4: 2504.70, 5: 52598.70},
    # 21 Bombs
    21: {1: 6.19, 2: 49.50, 3: 569.25, 4: 12523.50},
    # 22 Bombs
    22: {1: 8.25, 2: 99.00, 3: 2277.00},
    # 23 Bombs
    23: {1: 12.37, 2: 297.00},
    # 24 Bombs
    24: {1: 24.75}
}

# --- Provably Fair System & Game ID Generation ---
def generate_server_seed():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=64))

def generate_client_seed():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

def generate_unique_id(prefix='G'):
    timestamp = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{timestamp}-{random_part}"

def create_hash(server_seed, client_seed, nonce):
    import hashlib
    combined = f"{server_seed}:{client_seed}:{nonce}"
    return hashlib.sha256(combined.encode()).hexdigest()

def get_provably_fair_result(server_seed, client_seed, nonce, max_value):
    hash_result = create_hash(server_seed, client_seed, nonce)
    # Convert first 8 characters of hash to integer
    hex_value = int(hash_result[:8], 16)
    return (hex_value % max_value)
    
def generate_limbo_multiplier():
    """
    Generates a multiplier for the Limbo game using a power-law distribution.
    This function is calibrated so the probability of the result being <= 2.0x is 48%.
    
    The formula is derived from inverse transform sampling of a Pareto distribution.
    The core equation is: P(multiplier <= x) = 1 - (1 / x)^alpha
    Given P(multiplier <= 2) = 0.48, we solve for alpha:
    0.48 = 1 - (1/2)^alpha
    0.52 = 0.5^alpha
    log(0.52) = alpha * log(0.5)
    alpha = log(0.52) / log(0.5) ≈ 0.9434
    
    The inverse CDF (quantile function) is: x = (1 - u)^(-1/alpha)
    where u is a uniform random number [0, 1).
    """
    # 1. Define the core parameter `alpha` based on the user's constraint.
    # This value determines the "steepness" of the probability curve.
    alpha = math.log(0.52) / math.log(0.5)  # Result is approx. 0.9434

    # 2. Generate a uniform random float u in the interval [0, 1).
    # Using secrets.SystemRandom().random() for better cryptographic randomness.
    u = secrets.SystemRandom().random()

    # 3. Apply the inverse CDF formula to map the random float to a multiplier.
    # This formula ensures that the distribution of multipliers follows the desired probability curve.
    # The result is a number >= 1.0.
    multiplier = (1 - u) ** (-1 / alpha)
    
    # 4. We cap the multiplier at 999x as per the game's rules and round to 2 decimal places.
    # This prevents infinitely large multipliers and keeps the results clean.
    final_multiplier = max(1.0, min(multiplier, 999.0))
    
    return round(final_multiplier, 2)

# --- Persistent User Data Utilities ---
def normalize_username(username):
    if not username:
        return None
    username = username.lower()
    if not username.startswith("@"):
        username = "@" + username
    return username

def load_all_user_data():
    global user_wallets, username_to_userid, user_stats
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(DATA_DIR, fname), "r") as f:
                    data = json.load(f)
                    user_id = int(fname.split(".")[0])
                    user_wallets[user_id] = data.get("wallet", 0.0)
                    username = data.get("userinfo", {}).get("username")
                    if username:
                        username_to_userid[normalize_username(username)] = user_id
                    user_stats[user_id] = data
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Could not load data for {fname}: {e}")

def save_user_data(user_id):
    if user_id not in user_stats:
        logging.warning(f"Attempted to save data for non-existent user: {user_id}")
        return
    data = user_stats.get(user_id, {})
    data["wallet"] = user_wallets.get(user_id, 0.0)
    with open(os.path.join(DATA_DIR, f"{user_id}.json"), "w") as f:
        json.dump(data, f, default=str, indent=2)

def save_all_user_data():
    logging.info("Saving all user data...")
    for user_id in user_stats.keys():
        save_user_data(user_id)
    logging.info("All user data saved.")

## NEW FEATURE - Data Persistence ##
def save_bot_state():
    """Saves the entire bot state to a single JSON file."""
    logging.info("Shutting down... Saving bot state.")
    state = {
        'user_wallets': user_wallets,
        'username_to_userid': username_to_userid,
        'game_sessions': game_sessions,
        'user_pending_invitations': user_pending_invitations,
        'user_deposit_sessions': user_deposit_sessions,
        'escrow_deals': escrow_deals,
        'bot_stopped': bot_stopped,
        'CURRENT_ADDRESS_INDEX': CURRENT_ADDRESS_INDEX,
        'bot_settings': bot_settings # NEW
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, default=str, indent=2)
        logging.info("Bot state saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save bot state: {e}")
    save_all_user_data() # Also save individual user files as a backup
    save_all_escrow_deals()
    save_all_group_settings() # NEW
    save_all_recovery_data() # NEW
    save_all_gift_codes() # NEW

def load_bot_state():
    """Loads the bot state from a single JSON file."""
    global user_wallets, username_to_userid, user_stats, game_sessions, user_pending_invitations, user_deposit_sessions, escrow_deals, bot_stopped, CURRENT_ADDRESS_INDEX, bot_settings, group_settings, recovery_data, gift_codes

    # Load individual files first as a fallback
    load_all_user_data()
    load_all_escrow_deals()
    load_all_group_settings() # NEW
    load_all_recovery_data() # NEW
    load_all_gift_codes() # NEW

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            # Convert string keys back to int for wallets
            user_wallets.update({int(k): v for k, v in state.get('user_wallets', {}).items()})
            username_to_userid.update(state.get('username_to_userid', {}))
            game_sessions.update(state.get('game_sessions', {}))
            user_pending_invitations.update(state.get('user_pending_invitations', {}))
            user_deposit_sessions.update(state.get('user_deposit_sessions', {}))
            escrow_deals.update(state.get('escrow_deals', {}))
            bot_stopped = state.get('bot_stopped', False)
            CURRENT_ADDRESS_INDEX = state.get('CURRENT_ADDRESS_INDEX', 0)
            bot_settings.update(state.get('bot_settings', {})) # NEW
            logging.info("Bot state restored successfully from state file.")
        except (json.JSONDecodeError, Exception) as e:
            logging.error(f"Could not load bot state from {STATE_FILE}: {e}. Relying on individual files.")
    else:
        logging.info("No state file found. Starting with a fresh state from individual user/escrow files.")

def load_all_escrow_deals():
    global escrow_deals
    logging.info("Loading all escrow deals from files...")
    for fname in os.listdir(ESCROW_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(ESCROW_DIR, fname), "r") as f:
                    deal = json.load(f)
                    deal_id = deal.get("id")
                    if deal_id:
                        # Only load active deals into memory
                        if deal.get("status") not in ["completed", "cancelled_by_owner", "disputed", "release_failed"]:
                            escrow_deals[deal_id] = deal
            except Exception as e:
                logging.error(f"Could not load escrow deal from {fname}: {e}")
    logging.info(f"Loaded {len(escrow_deals)} active escrow deals.")

def save_escrow_deal(deal_id):
    deal = escrow_deals.get(deal_id)
    if not deal:
        logging.warning(f"Attempted to save non-existent escrow deal: {deal_id}")
        return
    try:
        with open(os.path.join(ESCROW_DIR, f"{deal_id}.json"), "w") as f:
            json.dump(deal, f, default=str, indent=2)
    except Exception as e:
        logging.error(f"Failed to save escrow deal {deal_id}: {e}")

def save_all_escrow_deals():
    logging.info("Saving all escrow deals...")
    for deal_id in escrow_deals.keys():
        save_escrow_deal(deal_id)
    logging.info("All escrow deals saved.")

## NEW FEATURE - Group Settings Persistence ##
def save_group_settings(chat_id):
    settings = group_settings.get(chat_id)
    if not settings:
        return
    try:
        with open(os.path.join(GROUPS_DIR, f"{chat_id}.json"), "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save group settings for {chat_id}: {e}")

def load_all_group_settings():
    global group_settings
    logging.info("Loading all group settings...")
    for fname in os.listdir(GROUPS_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(GROUPS_DIR, fname), "r") as f:
                    settings = json.load(f)
                    chat_id = int(fname.split(".")[0])
                    group_settings[chat_id] = settings
            except Exception as e:
                logging.error(f"Could not load group settings from {fname}: {e}")
    logging.info(f"Loaded settings for {len(group_settings)} groups.")

def save_all_group_settings():
    logging.info("Saving all group settings...")
    for chat_id in group_settings.keys():
        save_group_settings(chat_id)
    logging.info("All group settings saved.")

## NEW FEATURE - Recovery Data Persistence ##
def save_recovery_data(token_hash):
    data = recovery_data.get(token_hash)
    if not data:
        return
    try:
        with open(os.path.join(RECOVERY_DIR, f"{token_hash}.json"), "w") as f:
            json.dump(data, f, default=str, indent=2)
    except Exception as e:
        logging.error(f"Failed to save recovery data for token hash {token_hash}: {e}")

def load_all_recovery_data():
    global recovery_data
    logging.info("Loading all recovery data...")
    for fname in os.listdir(RECOVERY_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(RECOVERY_DIR, fname), "r") as f:
                    data = json.load(f)
                    token_hash = fname.split(".")[0]
                    # Convert expiry time back to datetime object
                    if 'lock_expiry' in data and data['lock_expiry']:
                        data['lock_expiry'] = datetime.fromisoformat(data['lock_expiry'])
                    recovery_data[token_hash] = data
            except Exception as e:
                logging.error(f"Could not load recovery data from {fname}: {e}")
    logging.info(f"Loaded {len(recovery_data)} recovery tokens.")

def save_all_recovery_data():
    logging.info("Saving all recovery data...")
    for token_hash in recovery_data.keys():
        save_recovery_data(token_hash)
    logging.info("All recovery data saved.")

## NEW FEATURE - Gift Code Persistence ##
def save_gift_code(code):
    data = gift_codes.get(code)
    if not data:
        return
    try:
        with open(os.path.join(GIFT_CODE_DIR, f"{code}.json"), "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save gift code {code}: {e}")

def load_all_gift_codes():
    global gift_codes
    logging.info("Loading all gift codes...")
    for fname in os.listdir(GIFT_CODE_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(GIFT_CODE_DIR, fname), "r") as f:
                    data = json.load(f)
                    code = fname.split(".")[0]
                    gift_codes[code] = data
            except Exception as e:
                logging.error(f"Could not load gift code from {fname}: {e}")
    logging.info(f"Loaded {len(gift_codes)} gift codes.")

def save_all_gift_codes():
    logging.info("Saving all gift codes...")
    for code in gift_codes.keys():
        save_gift_code(code)
    logging.info("All gift codes saved.")


atexit.register(save_bot_state)
load_bot_state()

# --- DECORATOR FOR MAINTENANCE MODE ---
def check_maintenance(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if bot_settings.get("maintenance_mode", False) and user.id != BOT_OWNER_ID:
            # Allow ongoing game interactions to continue
            if update.message and update.message.dice:
                active_pvb_game_id = context.chat_data.get(f"active_pvb_game_{user.id}")
                if active_pvb_game_id and active_pvb_game_id in game_sessions:
                    return await func(update, context, *args, **kwargs)

                chat_id = update.effective_chat.id
                for match_id, match_data in list(game_sessions.items()):
                    if match_data.get("chat_id") == chat_id and match_data.get("status") == 'active' and user.id in match_data.get("players", []):
                         return await func(update, context, *args, **kwargs)

            # Block new commands/interactions
            maintenance_text = (
                "🛠️ <b>Bot Under Maintenance</b> 🛠️\n\n"
                "The bot is currently undergoing scheduled maintenance to improve your experience. "
                "All games and commands are temporarily disabled.\n\n"
                "Ongoing matches can still be completed. We apologize for any inconvenience.\n\n"
                "Please contact the owner @jashanxjagy for any urgent support."
            )
            if update.message:
                await update.message.reply_text(maintenance_text, parse_mode=ParseMode.HTML)
            elif update.callback_query:
                await update.callback_query.answer("The bot is currently under maintenance.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- HELPER TO CHECK BET LIMITS ---
async def check_bet_limits(update: Update, bet_amount: float, game_name: str) -> bool:
    limits = bot_settings.get('game_limits', {}).get(game_name, {})
    min_bet = limits.get('min', MIN_BALANCE)
    max_bet = limits.get('max')

    if bet_amount < min_bet:
        await update.message.reply_text(f"Minimum bet for this game is ${min_bet:.2f}")
        return False
    if max_bet is not None and bet_amount > max_bet:
        await update.message.reply_text(f"Maximum bet for this game is ${max_bet:.2f}")
        return False
    return True

async def ensure_user_in_wallets(user_id: int, username: str = None, referrer_id: int = None, context: ContextTypes.DEFAULT_TYPE = None):
    # IMPROVEMENT: Always register user on any command
    if user_id not in user_stats:
        # If no username provided, try to fetch it
        if not username and context:
            try:
                chat_member = await context.bot.get_chat(user_id)
                username = chat_member.username
            except (BadRequest, Forbidden):
                logging.warning(f"Could not fetch username for new user {user_id}")

        user_wallets[user_id] = 0.0
        user_stats[user_id] = {
            "userinfo": {"user_id": user_id, "username": username or "", "join_date": str(datetime.now(timezone.utc)), "language": DEFAULT_LANG},
            "deposits": [], # Changed to list of dicts
            "withdrawals": [], # Changed to list of dicts
            "tips_received": {"count": 0, "amount": 0.0},
            "tips_sent": {"count": 0, "amount": 0.0},
            "bets": {"count": 0, "amount": 0.0, "wins": 0, "losses": 0, "pvp_wins": 0, "history": []},
            "rain_received": {"count": 0, "amount": 0.0},
            "wallet": 0.0,
            "pnl": 0.0,
            "last_update": str(datetime.now(timezone.utc)),
            "game_sessions": [],
            "escrow_deals": [],
            "referral": {
                "referrer_id": referrer_id,
                "referred_users": [],
                "commission_earned": 0.0
            },
            "achievements": [], # NEW
            "last_daily_claim": None, # NEW
            "recovery_token_hash": None, # NEW
            "last_weekly_claim": None, # NEW
            "last_monthly_claim": None, # NEW
            "last_rakeback_claim_wager": 0.0, # NEW
            "claimed_gift_codes": [], # NEW
            "claimed_level_rewards": [] # NEW: For level system
        }
        if username:
            username_to_userid[normalize_username(username)] = user_id

        if referrer_id:
            await ensure_user_in_wallets(referrer_id, context=context) # Pass context
            if 'referral' not in user_stats[referrer_id]:
                 user_stats[referrer_id]['referral'] = {"referrer_id": None, "referred_users": [], "commission_earned": 0.0}
            user_stats[referrer_id]['referral']['referred_users'].append(user_id)
            save_user_data(referrer_id)
            await check_and_award_achievements(referrer_id, None) # Check for referral achievements
        save_user_data(user_id)
        logging.info(f"New user registered: {username} ({user_id})")

    # Update username if it has changed
    current_username = user_stats[user_id]["userinfo"].get("username")
    if username and current_username != username:
        # Remove old username mapping if it exists
        if current_username and normalize_username(current_username) in username_to_userid:
            del username_to_userid[normalize_username(current_username)]
        user_stats[user_id]["userinfo"]["username"] = username
        username_to_userid[normalize_username(username)] = user_id
        save_user_data(user_id)

    return True

## NEW FEATURE - Achievement System ##
async def check_and_award_achievements(user_id, context, multiplier=0):
    if user_id not in user_stats:
        return

    stats = user_stats[user_id]
    user_achievements = stats.get("achievements", [])

    total_wagered = stats["bets"]["amount"]
    total_wins = stats["bets"]["wins"]
    pvp_wins = stats["bets"].get("pvp_wins", 0)
    referrals = len(stats.get("referral", {}).get("referred_users", []))

    for achievement_id, ach_data in ACHIEVEMENTS.items():
        if achievement_id in user_achievements:
            continue # Already has it

        unlocked = False
        if ach_data["type"] == "wager" and total_wagered >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "wins" and total_wins >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "pvp_wins" and pvp_wins >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "multiplier" and multiplier >= ach_data["value"]:
            unlocked = True
        elif ach_data["type"] == "referrals" and referrals >= ach_data["value"]:
            unlocked = True

        if unlocked:
            stats["achievements"].append(achievement_id)
            save_user_data(user_id)
            if context:
                lang = stats.get("userinfo", {}).get("language", DEFAULT_LANG)
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=get_text("achievement_unlocked", lang, emoji=ach_data["emoji"], name=ach_data["name"], description=ach_data["description"]),
                        parse_mode=ParseMode.HTML
                    )
                except (BadRequest, Forbidden):
                    logging.warning(f"Could not send achievement notification to user {user_id}")
## NEW FEATURE - Level System Logic ##
def get_user_level(user_id: int):
    """Determines a user's current level based on their total wagered amount."""
    if user_id not in user_stats:
        return LEVELS[0]
    
    wagered = user_stats[user_id].get("bets", {}).get("amount", 0.0)
    current_level = LEVELS[0]
    for level_data in reversed(LEVELS):
        if wagered >= level_data["wager_required"]:
            current_level = level_data
            break
    return current_level

async def check_and_award_level_up(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Checks for level-up, awards reward, and notifies the user."""
    if user_id not in user_stats:
        return

    current_level_data = get_user_level(user_id)
    level_num = current_level_data["level"]
    
    claimed_rewards = user_stats[user_id].get("claimed_level_rewards", [])

    if level_num > 0 and level_num not in claimed_rewards:
        reward_amount = current_level_data["reward"]
        user_wallets[user_id] += reward_amount
        user_stats[user_id].setdefault("claimed_level_rewards", []).append(level_num)
        save_user_data(user_id)
        
        # Notify the user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(f"🎉 <b>Level Up!</b> 🎉\n\n"
                      f"Congratulations! You have reached <b>Level {level_num} ({current_level_data['name']})</b>.\n"
                      f"You have been awarded a one-time bonus of <b>${reward_amount:.2f}</b>!"),
                parse_mode=ParseMode.HTML
            )
        except (BadRequest, Forbidden):
            logging.warning(f"Could not send level-up notification to user {user_id}")

async def process_referral_commission(user_id, amount, commission_type):
    if user_id not in user_stats or not user_stats[user_id].get('referral', {}).get('referrer_id'):
        return

    referrer_id = user_stats[user_id]['referral']['referrer_id']
    if referrer_id not in user_stats:
        return

    if commission_type == 'deposit':
        rate = REFERRAL_DEPOSIT_COMMISSION_RATE
    elif commission_type == 'bet':
        rate = REFERRAL_BET_COMMISSION_RATE
    else:
        return

    commission = amount * rate
    if commission > 0:
        await ensure_user_in_wallets(referrer_id)
        user_wallets[referrer_id] = user_wallets.get(referrer_id, 0.0) + commission
        user_stats[referrer_id]['referral']['commission_earned'] += commission
        save_user_data(referrer_id)
        logging.info(f"Awarded ${commission:.4f} commission to referrer {referrer_id} from user {user_id}'s {commission_type}.")

def update_stats_on_deposit(user_id, amount, tx_hash, method):
    stats = user_stats[user_id]
    deposit_record = {
        "amount": amount,
        "tx_hash": tx_hash,
        "method": method,
        "timestamp": str(datetime.now(timezone.utc))
    }
    stats["deposits"].append(deposit_record)
    save_user_data(user_id)
    # Process referral commission on deposit
    asyncio.create_task(process_referral_commission(user_id, amount, 'deposit'))

def update_stats_on_withdrawal(user_id, amount, tx_hash, method):
    stats = user_stats[user_id]
    withdrawal_record = {
        "amount": amount,
        "tx_hash": tx_hash,
        "method": method,
        "timestamp": str(datetime.now(timezone.utc))
    }
    stats["withdrawals"].append(withdrawal_record)
    save_user_data(user_id)

def update_stats_on_tip_received(user_id, amount):
    stats = user_stats[user_id]
    stats["tips_received"]["count"] += 1
    stats["tips_received"]["amount"] += amount
    save_user_data(user_id)

def update_stats_on_tip_sent(user_id, amount):
    stats = user_stats[user_id]
    stats["tips_sent"]["count"] += 1
    stats["tips_sent"]["amount"] += amount
    save_user_data(user_id)

def update_stats_on_bet(user_id, game_id, amount, win, pvp_win=False, multiplier=0, context=None):
    stats = user_stats[user_id]
    stats["bets"]["count"] += 1
    stats["bets"]["amount"] += amount
    
    # NEW: House balance update
    global bot_settings
    if win:
        winnings = amount * multiplier
        net_win = winnings - amount
        bot_settings["house_balance"] -= net_win
    else:
        bot_settings["house_balance"] += amount
    
    if win:
        stats["bets"]["wins"] += 1
        if pvp_win:
            stats["bets"]["pvp_wins"] = stats["bets"].get("pvp_wins", 0) + 1
    else:
        stats["bets"]["losses"] += 1

    if 'game_sessions' not in stats:
        stats['game_sessions'] = []
    stats['game_sessions'].append(game_id)
    
    # NEW: Add to wager history for weekly/monthly bonuses
    if 'history' not in stats['bets']:
        stats['bets']['history'] = []
    stats['bets']['history'].append({
        "amount": amount,
        "timestamp": str(datetime.now(timezone.utc))
    })

    save_user_data(user_id)
    # Process referral commission on bet
    asyncio.create_task(process_referral_commission(user_id, amount, 'bet'))
    # Check for achievements
    asyncio.create_task(check_and_award_achievements(user_id, context, multiplier))
    # NEW: Check for level up
    asyncio.create_task(check_and_award_level_up(user_id, context))

def update_stats_on_rain_received(user_id, amount):
    stats = user_stats[user_id]
    stats["rain_received"]["count"] += 1
    stats["rain_received"]["amount"] += amount
    save_user_data(user_id)

def update_pnl(user_id):
    stats = user_stats[user_id]
    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))
    stats["pnl"] = (total_withdrawals + user_wallets.get(user_id, 0.0)) - (total_deposits + stats["tips_received"]["amount"])
    save_user_data(user_id)

def get_all_registered_user_ids():
    return list(user_stats.keys())

@check_maintenance
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    ## NEW FEATURE ##
    # Handle deep linking for referrals and escrow
    referrer_id = None
    if context.args and len(context.args) > 0:
        deep_link_arg = context.args[0]
        if deep_link_arg.startswith("ref_"):
            try:
                referrer_id = int(deep_link_arg.replace("ref_", ""))
                if referrer_id == user.id: # Can't refer yourself
                    referrer_id = None
                else:
                    # Notify referrer
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 New referral! {user.mention_html()} has joined using your link.",
                        parse_mode=ParseMode.HTML
                    )
            except (ValueError, TypeError, BadRequest, Forbidden):
                referrer_id = None # Invalid referral ID or can't message

        elif deep_link_arg.startswith("escrow_"):
            deal_id = deep_link_arg.replace("escrow_", "")
            await handle_escrow_deep_link(update, context, deal_id)
            return

    await ensure_user_in_wallets(user.id, user.username, referrer_id, context)
    context.user_data['menu_owner_id'] = user.id # NEW: Set menu owner

    # Check if user is banned
    if user.id in bot_settings.get("banned_users", []):
        await update.message.reply_text("You have been banned from using this bot.")
        return

    keyboard = [
        [InlineKeyboardButton("💰 Deposit", callback_data="main_deposit"),
         InlineKeyboardButton("💸 Withdraw", callback_data="main_withdraw")],
        [InlineKeyboardButton("🎮 Games", callback_data="main_games"),
         InlineKeyboardButton("🛡️ Escrow", callback_data="main_escrow")],
        [InlineKeyboardButton("💼 Wallet", callback_data="main_wallet"),
         InlineKeyboardButton("📈 Leaderboard", callback_data="main_leaderboard")],
        [InlineKeyboardButton("🤝 Referral", callback_data="main_referral"),
         InlineKeyboardButton("🦄 Level", callback_data="main_level")], # MODIFIED
        [InlineKeyboardButton("🤖 AI Assistant", callback_data="main_ai"),
         InlineKeyboardButton("🆘 Support", callback_data="main_support")],
        [InlineKeyboardButton("❓ Help", callback_data="main_help"),
         InlineKeyboardButton("ℹ️ Info & Rules", callback_data="main_info")],
    ]

    # Add Settings button only in DMs
    if update.effective_chat.type == "private":
        keyboard.append([InlineKeyboardButton("⚙️ Settings", callback_data="main_settings")])


    # NEW: Add Admin Dashboard button for owner
    if user.id == BOT_OWNER_ID:
        keyboard.insert(0, [InlineKeyboardButton("👑 Admin Dashboard", callback_data="admin_dashboard")])


    welcome_text = (
        f"🎰 <b>Welcome to Telegram Casino & Escrow Bot!</b> 🎰\n\n"
        f"👋 Hello {user.first_name}!\n\n"
        f"🎲 Experience the thrill of casino games or secure your trades with our automated Escrow system.\n"
        f"✨ NEW: Chat with our <b>AI Assistant</b> for any questions or tasks!\n"
        f"💰 Current Balance: <b>${user_wallets.get(user.id, 0.0):.2f}</b>\n\n"
        f"Choose an option below to get started:"
    )

    # Send welcome message
    if update.message:
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif update.callback_query:
         await update.callback_query.edit_message_text(
            welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
@check_maintenance
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    # NEW: Check if the user is the owner of this menu
    menu_owner_id = context.user_data.get('menu_owner_id')
    if menu_owner_id and user.id != menu_owner_id:
        await query.answer("This menu is not for you.", show_alert=False)
        return

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if user.id in bot_settings.get("banned_users", []):
        await query.answer("You are banned.", show_alert=True)
        return

    if data == "main_deposit":
        # NEW: Check if deposits are enabled
        if not bot_settings.get("deposits_enabled", True):
            await query.answer("Deposits are temporarily disabled by the administrator.", show_alert=True)
            return
            
        session = user_deposit_sessions.get(user.id)
        if session:
            expiry_time = datetime.fromisoformat(session['expiry'])
            remaining = int((expiry_time - datetime.now(timezone.utc)).total_seconds())
            if remaining > 0:
                await query.edit_message_text(
                    f"You already have a pending deposit session!\n"
                    f"Deposit Address: <code>{session['address']}</code>\n"
                    f"Deposit Method: {DEPOSIT_METHODS[session['method']]['name']}\n"
                    f"Expires in: {remaining // 60}m {remaining % 60}s\n"
                    f"⚠️ Do not send any tokens after expiry.\n"
                    f"Please complete your deposit or wait for the timer to expire.",
                    parse_mode=ParseMode.HTML
                )
                return
            else:
                del user_deposit_sessions[user.id]

        keyboard = [
            [InlineKeyboardButton("BNB (BEP20)", callback_data="deposit_bnb")],
            [InlineKeyboardButton("USDT (BEP20)", callback_data="deposit_usdt_bep")],
            [InlineKeyboardButton("USDT (ERC20)", callback_data="deposit_usdt_erc")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ]
        await query.edit_message_text(
            "💰 <b>Select Deposit Method:</b>\n\n"
            "⚠️ You will receive a one-time unique deposit address, valid for 1 hour.\n"
            "Do NOT send tokens after expiry.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "main_withdraw":
        # NEW: Check if withdrawals are enabled
        if not bot_settings.get("withdrawals_enabled", True):
            await query.edit_message_text(
                "❌ <b>Withdrawals Disabled</b>\n\n"
                "Withdrawals are temporarily disabled by the administrator. "
                "Please contact support for more information.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
            )
            return

        if user.id in bot_settings.get("tempbanned_users", []):
            await query.edit_message_text(
                "❌ <b>Withdrawals Disabled</b>\n\n"
                "Your account is currently restricted from making withdrawals. "
                "Please contact support for more information.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
            )
            return

        await query.edit_message_text(
            "💸 <b>Withdrawals</b>\n\n"
            "For withdrawal requests, please contact the bot owner:\n"
            "👤 @jashanxjagy\n\n"
            "Include your user ID and withdrawal amount in your message.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
        )

    elif data == "main_games":
        await games_menu(update, context)

    elif data == "main_escrow":
        await escrow_command(update, context, from_callback=True)

    elif data == "main_wallet":
        balance = user_wallets.get(user.id, 0.0)
        stats = user_stats.get(user.id, {})
        total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
        total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))

        wallet_text = (
            f"💼 <b>Your Wallet</b>\n\n"
            f"💰 Balance: <b>${balance:.2f}</b>\n"
            f"🎲 Total Wagered: ${stats.get('bets', {}).get('amount', 0.0):.2f}\n"
            f"🏆 Wins: {stats.get('bets', {}).get('wins', 0)}\n"
            f"💔 Losses: {stats.get('bets', {}).get('losses', 0)}\n"
            f"📈 P&L: <b>${stats.get('pnl', 0.0):.2f}</b>\n"
            f"💵 Total Deposited: ${total_deposits:.2f}\n"
            f"💸 Total Withdrawn: ${total_withdrawals:.2f}"
        )

        await query.edit_message_text(
            wallet_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📜 My Game Matches", callback_data="my_matches_0")],
                [InlineKeyboardButton("🛡️ My Escrow Deals", callback_data="my_deals_0")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
            ])
        )

    ## NEW FEATURE ##
    elif data == "main_leaderboard":
        await leaderboard_command(update, context, from_callback=True)

    ## NEW FEATURE ##
    elif data == "main_referral":
        await referral_command(update, context, from_callback=True)

    ## NEW FEATURE - AI Integration ##
    elif data == "main_ai":
        return await start_ai_conversation(update, context)

    elif data == "main_support":
        await query.edit_message_text(
            "🆘 <b>Support</b>\n\n"
            "Need help or have questions?\n"
            "Contact the bot owner:\n\n"
            "👤 @jashanxjagy\n\n"
            "We're here to help you 24/7!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
        )

    elif data == "main_help":
        await help_command(update, context, from_callback=True)

    elif data == "main_info":
        info_text = (
            "ℹ️ <b>Casino Rules & Info</b>\n\n"
            "<b>🎰 General Rules:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• All games use provably fair system\n"
            "• No refunds on completed bets\n"
            "• Contact support for disputes\n\n"
            "<b>🛡️ Escrow Rules:</b>\n"
            "• Use /escrow to start a secure trade.\n"
            "• Seller deposits funds into bot's secure wallet.\n"
            "• Buyer confirms receipt of goods/services.\n"
            "• Seller releases funds to the buyer.\n"
            "• All transactions are on the blockchain.\n\n"
            "<b>⚠️ Responsible Gaming:</b>\n"
            "• Only bet what you can afford to lose\n"
            "• Set personal limits\n"
            "• Contact support if you need help"
        )
        await query.edit_message_text(
            info_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
        )

    ## NEW FEATURE ##
    elif data == "main_level":
        await level_command(update, context, from_callback=True)
        
    ## NEW FEATURE ##
    elif data == "main_settings":
        await settings_command(update, context)


    elif data == "back_to_main":
        await start_command_inline(query, context)

    elif data.startswith("my_matches"):
        page = int(data.split('_')[-1])
        await matches_command(update, context, from_callback=True, page=page)

    elif data.startswith("my_deals"):
        page = int(data.split('_')[-1])
        await deals_command(update, context, from_callback=True, page=page)


async def start_command_inline(query, context):
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    context.user_data['menu_owner_id'] = user.id # NEW: Set menu owner

    keyboard = [
        [InlineKeyboardButton("💰 Deposit", callback_data="main_deposit"),
         InlineKeyboardButton("💸 Withdraw", callback_data="main_withdraw")],
        [InlineKeyboardButton("🎮 Games", callback_data="main_games"),
         InlineKeyboardButton("🛡️ Escrow", callback_data="main_escrow")],
        [InlineKeyboardButton("💼 Wallet", callback_data="main_wallet"),
         InlineKeyboardButton("📈 Leaderboard", callback_data="main_leaderboard")],
        [InlineKeyboardButton("🤝 Referral", callback_data="main_referral"),
         InlineKeyboardButton("🦄 Level", callback_data="main_level")], # MODIFIED
        [InlineKeyboardButton("🤖 AI Assistant", callback_data="main_ai"),
         InlineKeyboardButton("🆘 Support", callback_data="main_support")],
        [InlineKeyboardButton("❓ Help", callback_data="main_help"),
         InlineKeyboardButton("ℹ️ Info & Rules", callback_data="main_info")],
    ]
    # Add Settings button only in DMs
    if query.message.chat.type == "private":
        keyboard.append([InlineKeyboardButton("⚙️ Settings", callback_data="main_settings")])

    # NEW: Add Admin Dashboard button for owner
    if user.id == BOT_OWNER_ID:
        keyboard.insert(0, [InlineKeyboardButton("👑 Admin Dashboard", callback_data="admin_dashboard")])

    welcome_text = (
        f"🎰 <b>Welcome to Telegram Casino & Escrow Bot!</b> 🎰\n\n"
        f"👋 Hello {user.first_name}!\n\n"
        f"🎲 Experience the thrill of casino games or secure your trades with our automated Escrow system.\n"
        f"✨ NEW: Chat with our <b>AI Assistant</b> for any questions or tasks!\n"
        f"💰 Current Balance: <b>${user_wallets.get(user.id, 0.0):.2f}</b>\n\n"
        f"Choose an option below to get started:"
    )

    await query.edit_message_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏠 House Games", callback_data="games_category_house")],
        [InlineKeyboardButton("😀 Emoji Games", callback_data="games_category_emoji")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]
    text = "🎮 <b>Game Categories</b>\n\nChoose a category to see the available games:"

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

## NEW FEATURE - Game Category Menu ##
@check_maintenance
async def games_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split('_')[-1] # house or emoji
    if category == "house":
        text = "🏠 <b>House Games</b>\n\nChoose a game to see how to play:"
        keyboard = [
            [InlineKeyboardButton("🃏 Blackjack", callback_data="game_blackjack"),
             InlineKeyboardButton("🎲 Dice Roll", callback_data="game_dice_roll")],
            [InlineKeyboardButton("🔮 Predict", callback_data="game_predict"),
             InlineKeyboardButton("🎯 Roulette", callback_data="game_roulette")],
            [InlineKeyboardButton("🎰 Slots", callback_data="game_slots"),
             InlineKeyboardButton("🏗️ Tower", callback_data="game_tower_start")],
            [InlineKeyboardButton("💣 Mines", callback_data="game_mines_start"),
             InlineKeyboardButton("🚀 Limbo", callback_data="game_limbo")], # NEW
            [InlineKeyboardButton("✂️ RPS", callback_data="game_rps"), # NEW
             InlineKeyboardButton("❌ Tic-Tac-Toe", callback_data="game_ttt")], # NEW
            [InlineKeyboardButton("🔙 Back to Categories", callback_data="main_games")]
        ]
    elif category == "emoji":
        text = "😀 <b>Emoji Games</b>\n\nChoose a game to see how to play:"
        keyboard = [
            [InlineKeyboardButton("🎲 Dice", callback_data="game_dice_bot")],
            [InlineKeyboardButton("🎯 Darts", callback_data="game_darts")],
            [InlineKeyboardButton("⚽ Football", callback_data="game_football")],
            [InlineKeyboardButton("🎳 Bowling", callback_data="game_bowling")],
            [InlineKeyboardButton("🔙 Back to Categories", callback_data="main_games")]
        ]
    else:
        return

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- GAME INFO CALLBACKS ---
@check_maintenance
async def game_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    await ensure_user_in_wallets(query.from_user.id, query.from_user.username, context=context)

    if data == "game_blackjack":
        await query.edit_message_text(
            "🃏 <b>Blackjack</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Get as close to 21 as possible\n"
            "• Beat the dealer without going over 21\n"
            "• Ace = 1 or 11, Face cards = 10\n\n"
            "<b>Commands:</b>\n"
            "• <code>/bj amount</code> - Start blackjack\n"
            "• Example: <code>/bj 5</code> or <code>/bj all</code>\n\n"
            "<b>Payouts:</b>\n"
            "• Win: 2x your bet\n"
            "• Blackjack: 2.5x your bet\n"
            "• Push: Get your bet back",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]])
        )

    elif data == "game_coin_flip":
        await query.edit_message_text(
            "🎰 <b>Coin Flip</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Choose Heads or Tails\n"
            "• Win: 2x multiplier\n"
            "• Keep winning to increase multiplier!\n\n"
            "<b>Commands:</b>\n"
            "• <code>/flip amount</code> - Start coin flip\n"
            "• Example: <code>/flip 1</code> or <code>/flip all</code>\n\n"
            "<b>Multiplier Chain:</b>\n"
            "• 1 win: 2x\n"
            "• 2 wins: 4x\n"
            "• 3 wins: 8x\n"
            "• And so on... 🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]])
        )

    elif data == "game_roulette":
        await query.edit_message_text(
            "🎯 <b>Roulette</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Choose number (0-36), color, or type\n\n"
            "<b>Commands:</b>\n"
            "• <code>/roul amount choice</code>\n"
            "• <code>/roulette amount choice</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/roul 1 5</code> (number 5)\n"
            "• <code>/roul all red</code> (red color)\n"
            "• <code>/roul 1 even</code> (even numbers)\n"
            "• <code>/roul 1 low</code> (1-18)\n"
            "• <code>/roul 1 high</code> (19-36)\n\n"
            "<b>Payouts:</b>\n"
            "• Single number: 35x\n"
            "• Red/Black, Even/Odd, High/Low: 2x\n"
            "• Columns: 3x",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]])
        )

    elif data == "game_dice_roll":
        await query.edit_message_text(
            "🎲 <b>Dice Roll</b>\n\n"
            "<b>How to play:</b>\n"
            f"• Minimum bet: ${MIN_BALANCE:.2f}\n"
            "• Choose number (1-6), even/odd, or high/low\n"

            "• Bot rolls real Telegram dice\n\n"
            "<b>Commands:</b>\n"
            "• <code>/dr amount choice</code>\n\n"
            "<b>Examples:</b>\n"
            "• <code>/dr 1 3</code> (number 3)\n"
            "• <code>/dr all even</code> (even numbers)\n"
            "• <code>/dr 1 high</code> (4,5,6)\n"
            "• <code>/dr 1 low</code> (1,2,3)\n\n"
            "<b>Payouts:</b>\n"
            "• Exact number: 5.96x\n"
            "• Even/Odd/High/Low: 1.96x",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]])
        )

    elif data == "game_slots":
        await query.edit_message_text(
            "🎰 <b>Slots</b>\n\n"
            "<b>How to play:</b>\n"
            "• Bot rolls real Telegram slot machine\n"
            "• Get 3 matching symbols to win\n\n"
            "<b>Commands:</b>\n"
            "• <code>/sl amount</code>\n"
            "• Example: <code>/sl 1</code> or <code>/sl all</code>\n\n"
            "<b>Payouts:</b>\n"
            "• 3 matching BAR, LEMON, or GRAPE: 14x\n"
            "• Triple 7s (JACKPOT): 28x",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]])
        )

    elif data == "game_predict":
        await query.edit_message_text(
            "🔮 <b>Predict Dice</b>\n\n"
            "<b>How to play:</b>\n"
            "• Predict if dice will be up (4-6) or down (1-3)\n"
            "• 2x payout on correct prediction\n\n"
            "<b>Commands:</b>\n"
            "• <code>/predict amount up</code>\n"
            "• <code>/predict all down</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]])
        )

    # PvP games
    elif data.startswith("game_"):
        game_name_map = {
            "football": "Football", "darts": "Darts", "bowling": "Bowling", "dice_bot": "Dice"
        }
        game_key = data.replace("game_", "")
        game_name = game_name_map.get(game_key, game_key.replace("_", " ").title())

        keyboard = [
            [InlineKeyboardButton(f"🤖 Play vs Bot", callback_data=f"pvb_start_{game_key}")],
            [InlineKeyboardButton(f"👤 Play vs Player", callback_data=f"pvp_info_{game_key}")],
            [InlineKeyboardButton("🔙 Back to Games", callback_data="main_games")]
        ]

        await query.edit_message_text(
            f"🎮 <b>{game_name}</b>\n\n"
            "Who do you want to play against?",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# --- NEW GAME IMPLEMENTATIONS ---

# 1. BLACKJACK GAME
@check_maintenance
async def blackjack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /bj amount\nExample: /bj 5 or /bj all")
        return

    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'blackjack'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    deck = create_deck()
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()

    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    game_id = generate_unique_id("BJ")
    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "blackjack",
        "user_id": user.id,
        "bet_amount": bet_amount,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": 0,
        "doubled": False
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)


    player_value = calculate_hand_value(player_hand)
    dealer_show_card = dealer_hand[0]

    hand_text = format_hand("Your hand", player_hand, player_value)
    dealer_text = f"Dealer shows: {dealer_show_card}\n"

    if player_value == 21:
        dealer_value = calculate_hand_value(dealer_hand)
        game_sessions[game_id]['status'] = 'completed'
        game_sessions[game_id]['win'] = True
        if dealer_value == 21:
            user_wallets[user.id] += bet_amount
            save_user_data(user.id)
            await update.message.reply_text(
                f"{hand_text}\n{format_hand('Dealer hand', dealer_hand, dealer_value)}\n"
                f"🤝 Push! Both have blackjack. Bet returned.\nGame ID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            winnings = bet_amount * 2.5
            user_wallets[user.id] += winnings
            update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=2.5, context=context)
            update_pnl(user.id)
            save_user_data(user.id)
            await update.message.reply_text(
                f"{hand_text}\n{dealer_text}\n"
                f"🎉 Blackjack! You win ${winnings:.2f}!\nGame ID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML
            )
        return

    keyboard = [
        [InlineKeyboardButton("👊 Hit", callback_data=f"bj_hit_{game_id}"),
         InlineKeyboardButton("✋ Stand", callback_data=f"bj_stand_{game_id}")],
    ]

    if len(player_hand) == 2 and user_wallets.get(user.id, 0.0) >= bet_amount:
        keyboard.append([InlineKeyboardButton("⬆️ Double Down", callback_data=f"bj_double_{game_id}")])

    await update.message.reply_text(
        f"🃏 <b>Blackjack Started!</b> (ID: <code>{game_id}</code>)\n\n"
        f"{hand_text}\n{dealer_text}\n"
        f"💰 Bet: ${bet_amount:.2f}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def create_deck():
    deck = [f"{rank}{suit}" for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck

def calculate_hand_value(hand):
    value = 0
    aces = 0
    for card in hand:
        rank = card[:-1]
        if rank == 'A':
            aces += 1
            value += 11
        elif rank in ['J', 'Q', 'K']:
            value += 10
        else:
            value += int(rank)
    while value > 21 and aces > 0:
        value -= 10
        aces -= 1
    return value

def format_hand(title, hand, value):
    cards_str = " ".join(hand)
    return f"{title}: {cards_str} (Value: {value})"

@check_maintenance
async def blackjack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if not query.data.startswith("bj_"):
        return

    parts = query.data.split("_")
    action = parts[1]
    game_id = parts[2]

    game = game_sessions.get(game_id)

    if not game:
        await query.edit_message_text("Game not found or already finished.")
        return

    # NEW: Game interaction security
    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return
        
    if game.get('status') != 'active':
        await query.edit_message_text("This game is already finished.")
        return


    if action == "hit":
        card = game["deck"].pop()
        game["player_hand"].append(card)
        player_value = calculate_hand_value(game["player_hand"])

        hand_text = format_hand("Your hand", game["player_hand"], player_value)
        dealer_text = f"Dealer shows: {game['dealer_hand'][0]}"

        if player_value > 21:
            game["status"] = 'completed'
            game["win"] = False
            update_stats_on_bet(user.id, game_id, game["bet_amount"], False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)
            await query.edit_message_text(
                f"🃏 <b>Blackjack</b> (ID: <code>{game_id}</code>)\n\n{hand_text}\n{dealer_text}\n\n"
                f"💥 Bust! You lose ${game['bet_amount']:.2f}",
                parse_mode=ParseMode.HTML
            )
        elif player_value == 21:
            await handle_dealer_turn(query, context, game_id)
        else:
            keyboard = [
                [InlineKeyboardButton("👊 Hit", callback_data=f"bj_hit_{game_id}"),
                 InlineKeyboardButton("✋ Stand", callback_data=f"bj_stand_{game_id}")]
            ]
            await query.edit_message_text(
                f"🃏 <b>Blackjack</b> (ID: <code>{game_id}</code>)\n\n{hand_text}\n{dealer_text}\n"
                f"💰 Bet: ${game['bet_amount']:.2f}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif action == "stand":
        await handle_dealer_turn(query, context, game_id)

    elif action == "double":
        if user_wallets.get(user.id, 0.0) < game["bet_amount"]:
            await query.answer("Not enough balance to double down!", show_alert=True)
            return

        user_wallets[user.id] -= game["bet_amount"]
        game["bet_amount"] *= 2
        game["doubled"] = True
        save_user_data(user.id)

        card = game["deck"].pop()
        game["player_hand"].append(card)
        player_value = calculate_hand_value(game["player_hand"])

        if player_value > 21:
            game["status"] = 'completed'
            game["win"] = False
            # On double down loss, the original bet amount is what's recorded for stats
            update_stats_on_bet(user.id, game_id, game["bet_amount"]/2, False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)
            hand_text = format_hand("Your hand", game["player_hand"], player_value)
            await query.edit_message_text(
                f"🃏 <b>Blackjack - Doubled Down</b> (ID: <code>{game_id}</code>)\n\n{hand_text}\n\n"
                f"💥 Bust! You lose ${game['bet_amount']:.2f}",
                parse_mode=ParseMode.HTML
            )
        else:
            await handle_dealer_turn(query, context, game_id)

async def handle_dealer_turn(query, context, game_id):
    game = game_sessions[game_id]
    user_id = game["user_id"]
    original_bet = game["bet_amount"] / 2 if game["doubled"] else game["bet_amount"]


    while calculate_hand_value(game["dealer_hand"]) < 17:
        game["dealer_hand"].append(game["deck"].pop())

    player_value = calculate_hand_value(game["player_hand"])
    dealer_value = calculate_hand_value(game["dealer_hand"])
    player_text = format_hand("Your hand", game["player_hand"], player_value)
    dealer_text = format_hand("Dealer hand", game["dealer_hand"], dealer_value)
    double_text = " - Doubled Down" if game["doubled"] else ""

    if dealer_value > 21:
        winnings = game["bet_amount"] * 2
        user_wallets[user_id] += winnings
        result = f"🎉 Dealer busts! You win ${winnings:.2f}!"
        game['win'] = True
        update_stats_on_bet(user_id, game_id, original_bet, True, multiplier=2, context=context)
    elif dealer_value > player_value:
        result = f"😢 Dealer wins with {dealer_value}. You lose ${game['bet_amount']:.2f}"
        game['win'] = False
        update_stats_on_bet(user_id, game_id, original_bet, False, context=context)
    elif player_value > dealer_value:
        winnings = game["bet_amount"] * 2
        user_wallets[user_id] += winnings
        result = f"🎉 You win! ${winnings:.2f}"
        game['win'] = True
        update_stats_on_bet(user_id, game_id, original_bet, True, multiplier=2, context=context)
    else:
        user_wallets[user_id] += game["bet_amount"]
        result = "🤝 Push! Bet returned."
        game['win'] = None # No win or loss

    update_pnl(user_id)
    save_user_data(user_id)
    game["status"] = 'completed'

    await query.edit_message_text(
        f"🃏 <b>Blackjack{double_text}</b> (ID: <code>{game_id}</code>)\n\n{player_text}\n{dealer_text}\n\n{result}",
        parse_mode=ParseMode.HTML
    )

# 2. COIN FLIP GAME (Enhanced)
@check_maintenance
async def coin_flip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if len(args) != 2:
        await update.message.reply_text("Usage: /flip amount or /flip all")
        return
    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet = user_wallets.get(user.id, 0.0)
        else:
            bet = float(bet_amount_str)
    except Exception:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet, 'coin_flip'):
        return

    if user_wallets.get(user.id, 0.0) < bet:
        await update.message.reply_text("You don't have enough balance.")
        return

    user_wallets[user.id] -= bet
    save_user_data(user.id)

    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    game_id = generate_unique_id("CF")

    game_sessions[game_id] = {
        "id": game_id,
        "game_type": "coin_flip",
        "user_id": user.id,
        "bet_amount": bet,
        "status": "active",
        "timestamp": str(datetime.now(timezone.utc)),
        "streak": 0,
        "server_seed": server_seed,
        "client_seed": client_seed,
        "nonce": 0
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)


    keyboard = [
        [InlineKeyboardButton("🪙 Heads", callback_data=f"flip_pick_{game_id}_Heads"),
         InlineKeyboardButton("🪙 Tails", callback_data=f"flip_pick_{game_id}_Tails")]
    ]
    await update.message.reply_text(
        f"🪙 <b>Coin Flip Started!</b> (ID: <code>{game_id}</code>)\n\n💰 Bet: ${bet:.2f}\nChoose Heads or Tails!\n\n"
        f"🎯 Current Multiplier: 2x",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@check_maintenance
async def coin_flip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    parts = query.data.split("_")
    action = parts[1]
    game_id = parts[2]

    game = game_sessions.get(game_id)
    if not game:
        await query.edit_message_text("No active coin flip game found or this is not your game.")
        return

    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return
        
    if game.get('status') != 'active':
        await query.edit_message_text("This game is already finished.")
        return


    if action == "pick":
        pick = parts[3]
        game["nonce"] += 1
        result_num = get_provably_fair_result(game["server_seed"], game["client_seed"], game["nonce"], 2)
        bot_choice = "Heads" if result_num == 0 else "Tails"

        if pick == bot_choice:
            game["streak"] += 1
            multiplier = 2 ** game["streak"]
            win_amount = game["bet_amount"] * multiplier
            keyboard = [
                [InlineKeyboardButton("🪙 Heads", callback_data=f"flip_pick_{game_id}_Heads"),
                 InlineKeyboardButton("🪙 Tails", callback_data=f"flip_pick_{game_id}_Tails")],
                [InlineKeyboardButton(f"💸 Cash Out (${win_amount:.2f})", callback_data=f"flip_cashout_{game_id}")]
            ]
            await query.edit_message_text(
                f"🎉 <b>Correct!</b> The coin landed on {pick}!\n\n"
                f"💰 Current Win: <b>${win_amount:.2f}</b>\n🔥 Streak: {game['streak']}\n"
                f"🎯 Next Multiplier: {multiplier * 2}x\n\nContinue playing or cash out?\nID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            game["status"] = 'completed'
            game["win"] = False
            update_stats_on_bet(user.id, game_id, game['bet_amount'], False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)
            await query.edit_message_text(
                f"❌ <b>Wrong!</b> You picked {pick}, but the coin landed on {bot_choice}.\n\n"
                f"💔 You lost your bet of ${game['bet_amount']:.2f}\n🎯 Your streak was: {game['streak']}\nID: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML
            )
            # del game_sessions[game_id] # FIX: Don't delete history

    elif action == "cashout":
        multiplier = 2 ** game["streak"]
        win_amount = game["bet_amount"] * multiplier
        user_wallets[user.id] += win_amount
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        update_stats_on_bet(user.id, game_id, game['bet_amount'], True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        await query.edit_message_text(
            f"💸 <b>Cashed Out!</b>\n\n🎉 You won <b>${win_amount:.2f}</b>!\n"
            f"🔥 Final streak: {game['streak']}\n📈 Final multiplier: {multiplier}x\nID: <code>{game_id}</code>",
            parse_mode=ParseMode.HTML
        )
        # del game_sessions[game_id] # FIX: Don't delete history
@check_maintenance
async def rps_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    parts = query.data.split("_")
    action, game_id = parts[1], parts[2]

    game = game_sessions.get(game_id)
    if not game or user.id != game.get('user_id') or game.get('status') != 'active':
        await query.edit_message_text("This game is not active or not for you.")
        return

    if action == "pick":
        player_choice = parts[3]
        bot_choice = random.choice(['rock', 'paper', 'scissors'])
        
        choices_map = {'rock': '🪨', 'paper': '📄', 'scissors': '✂️'}
        result_text = f"You chose {choices_map[player_choice]}, Bot chose {choices_map[bot_choice]}.\n\n"
        
        winner = None
        if player_choice == bot_choice:
            winner = 'tie'
        elif (player_choice == 'rock' and bot_choice == 'scissors') or \
             (player_choice == 'scissors' and bot_choice == 'paper') or \
             (player_choice == 'paper' and bot_choice == 'rock'):
            winner = 'player'
        else:
            winner = 'bot'

        if winner == 'player':
            game["streak"] += 1
            multiplier = 1.96  # Fixed multiplier for one win
            # Winnings accumulate
            current_win = game.get("current_win", 0.0) + (game["bet_amount"] * multiplier)
            game["current_win"] = current_win

            keyboard = [
                [
                    InlineKeyboardButton("🪨 Rock", callback_data=f"rps_pick_{game_id}_rock"),
                    InlineKeyboardButton("📄 Paper", callback_data=f"rps_pick_{game_id}_paper"),
                    InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_pick_{game_id}_scissors"),
                ],
                [InlineKeyboardButton(f"💸 Cash Out (${current_win:.2f})", callback_data=f"rps_cashout_{game_id}")]
            ]
            result_text += f"🎉 <b>You win this round!</b>\n"
            result_text += f"💰 Current Win: <b>${current_win:.2f}</b>\n🔥 Streak: {game['streak']}\n\nContinue or cash out?"
            await query.edit_message_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        
        elif winner == 'tie':
            result_text += "🤝 <b>It's a tie!</b>\nYour streak continues. Play again."
            # Keep cashout button if they have a winning streak
            keyboard = [
                [
                    InlineKeyboardButton("🪨 Rock", callback_data=f"rps_pick_{game_id}_rock"),
                    InlineKeyboardButton("📄 Paper", callback_data=f"rps_pick_{game_id}_paper"),
                    InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_pick_{game_id}_scissors"),
                ]
            ]
            if game["streak"] > 0:
                 keyboard.append([InlineKeyboardButton(f"💸 Cash Out (${game['current_win']:.2f})", callback_data=f"rps_cashout_{game_id}")])
            await query.edit_message_text(result_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        
        else: # Bot wins
            game["status"] = 'completed'
            game["win"] = False
            update_stats_on_bet(user.id, game_id, game['bet_amount'], False, context=context)
            update_pnl(user.id)
            save_user_data(user.id)
            result_text += f"😢 <b>You lose!</b>\nYour streak of {game['streak']} is over. You lost your initial bet of ${game['bet_amount']:.2f}."
            await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)

    elif action == "cashout":
        win_amount = game.get("current_win", 0.0)
        if win_amount <= 0:
            await query.answer("Nothing to cash out yet!", show_alert=True)
            return

        user_wallets[user.id] += win_amount
        game["status"] = 'completed'
        game["win"] = True
        # The effective multiplier is the total win amount divided by the initial bet
        effective_multiplier = win_amount / game["bet_amount"]
        game["multiplier"] = effective_multiplier
        
        update_stats_on_bet(user.id, game_id, game['bet_amount'], True, multiplier=effective_multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        
        result_text = (f"💸 <b>Cashed Out!</b>\n\n"
                       f"🎉 You won a total of <b>${win_amount:.2f}</b>!\n"
                       f"🔥 Final streak: {game['streak']}")
        await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)
        
# --- Tic-Tac-Toe Game Logic ---
def create_ttt_keyboard(game_id, board):
    keyboard = []
    for i in range(0, 9, 3):
        row = [InlineKeyboardButton(board[j] or " ", callback_data=f"ttt_move_{game_id}_{j}") for j in range(i, i + 3)]
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def check_ttt_winner(board):
    lines = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Horizontal
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Vertical
        [0, 4, 8], [2, 4, 6]             # Diagonal
    ]
    for line in lines:
        if board[line[0]] == board[line[1]] == board[line[2]] and board[line[0]] is not None:
            return board[line[0]]  # Return 'X' or 'O'
    if all(cell is not None for cell in board):
        return 'Tie'
    return None

def ttt_bot_move(board):
    """
    Determines the bot's next move in Tic-Tac-Toe.
    Strategy:
    1. Win if possible.
    2. Block opponent's win if they are about to win.
    3. Take the center if available.
    4. Take a corner if available.
    5. Take any available side.
    """
    # 1. Check for a winning move for the bot ('O')
    for i in range(9):
        if board[i] is None:
            board[i] = 'O'
            if check_ttt_winner(board) == 'O':
                board[i] = None  # Revert change
                return i
            board[i] = None

    # 2. Check to block the player's ('X') winning move
    for i in range(9):
        if board[i] is None:
            board[i] = 'X'
            if check_ttt_winner(board) == 'X':
                board[i] = None # Revert change
                return i
            board[i] = None

    # 3. Take the center
    if board[4] is None:
        return 4

    # 4. Take a corner
    corners = [0, 2, 6, 8]
    available_corners = [c for c in corners if board[c] is None]
    if available_corners:
        return random.choice(available_corners)

    # 5. Take a side
    sides = [1, 3, 5, 7]
    available_sides = [s for s in sides if board[s] is None]
    if available_sides:
        return random.choice(available_sides)
    
    return None # Should not happen in a normal game
@check_maintenance
async def ttt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    # PvB mode: /ttt amount
    if len(args) == 2:
        try:
            bet_amount_str = args[1].lower()
            if bet_amount_str == 'all':
                bet_amount = user_wallets.get(user.id, 0.0)
            else:
                bet_amount = float(bet_amount_str)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return

        if not await check_bet_limits(update, bet_amount, 'ttt_pvb'):
            return

        if user_wallets.get(user.id, 0.0) < bet_amount:
            await update.message.reply_text("You don't have enough balance.")
            return

        user_wallets[user.id] -= bet_amount
        save_user_data(user.id)

        game_id = generate_unique_id("TTB")
        game_sessions[game_id] = {
            "id": game_id, "game_type": "ttt_pvb", "user_id": user.id, "bet_amount": bet_amount,
            "status": "active", "timestamp": str(datetime.now(timezone.utc)),
            "board": [None] * 9, "turn": "player" # Player is always 'X' and goes first
        }
        if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
        user_stats[user.id]['game_sessions'].append(game_id)
        save_user_data(user.id)

        keyboard = create_ttt_keyboard(game_id, game_sessions[game_id]['board'])
        await update.message.reply_text(
            f"❌⭕️ <b>Tic-Tac-Toe vs Bot!</b> (ID: <code>{game_id}</code>)\n\n"
            f"💰 Bet: ${bet_amount:.2f}\n"
            f"You are 'X'. It's your turn.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    # PvP mode: /ttt @username amount
    elif len(args) == 3:
        opponent_username = normalize_username(args[1])
        try:
            bet_amount = float(args[2])
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return

        if not await check_bet_limits(update, bet_amount, 'ttt_pvp'):
            return
        
        opponent_id = username_to_userid.get(opponent_username)
        if not opponent_id:
            await update.message.reply_text(f"Opponent {opponent_username} not found.")
            return

        if user.id == opponent_id:
            await update.message.reply_text("You can't play against yourself.")
            return

        if user_wallets.get(user.id, 0.0) < bet_amount or user_wallets.get(opponent_id, 0.0) < bet_amount:
            await update.message.reply_text("One of the players doesn't have enough balance.")
            return
        
        game_id = generate_unique_id("TTP")
        players = [user.id, opponent_id]
        random.shuffle(players) # Randomize who goes first
        
        game_sessions[game_id] = {
            "id": game_id, "game_type": "ttt_pvp", "bet_amount": bet_amount, "status": "pending",
            "players": {players[0]: "X", players[1]: "O"}, # {user_id: symbol}
            "player_usernames": {user.id: user.username, opponent_id: opponent_username},
            "turn": players[0], # The first player in the shuffled list
            "board": [None] * 9, "host_id": user.id, "timestamp": str(datetime.now(timezone.utc)),
        }

        keyboard = [[InlineKeyboardButton("Accept", callback_data=f"ttt_accept_{game_id}"), InlineKeyboardButton("Decline", callback_data=f"ttt_decline_{game_id}")]]
        await update.message.reply_text(
            f"❌⭕️ Tic-Tac-Toe challenge from {user.mention_html()} to {opponent_username} for ${bet_amount:.2f}!\n"
            f"{opponent_username}, do you accept?",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("Usage:\n• vs Bot: `/ttt amount`\n• vs Player: `/ttt @username amount`")
        
@check_maintenance
async def ttt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    parts = query.data.split("_")
    action, game_id = parts[1], parts[2]

    game = game_sessions.get(game_id)
    if not game:
        await query.edit_message_text("This game has ended or is invalid.")
        return

    # --- Handle PvP Invite ---
    if action == "accept":
        if game["status"] != "pending" or user.id not in game["players"]:
            await query.answer("This is not for you or has already been actioned.", show_alert=True)
            return

        host_id = game["host_id"]
        opponent_id = [pid for pid in game["players"] if pid != host_id][0]

        if user.id != opponent_id:
            await query.answer("Only the challenged player can accept.", show_alert=True)
            return

        # Deduct funds and start game
        user_wallets[host_id] -= game["bet_amount"]
        user_wallets[opponent_id] -= game["bet_amount"]
        save_user_data(host_id); save_user_data(opponent_id)
        
        game["status"] = "active"
        if 'game_sessions' not in user_stats[host_id]: user_stats[host_id]['game_sessions'] = []
        if 'game_sessions' not in user_stats[opponent_id]: user_stats[opponent_id]['game_sessions'] = []
        user_stats[host_id]['game_sessions'].append(game_id)
        user_stats[opponent_id]['game_sessions'].append(game_id)
        save_user_data(host_id); save_user_data(opponent_id)

        turn_id = game["turn"]
        turn_username = game["player_usernames"][turn_id]
        
        await query.edit_message_text(
            f"❌⭕️ <b>Tic-Tac-Toe Started!</b> (ID: <code>{game_id}</code>)\n\n"
            f"It's @{turn_username}'s turn ('{game['players'][turn_id]}').",
            parse_mode=ParseMode.HTML,
            reply_markup=create_ttt_keyboard(game_id, game['board'])
        )
        return
        
    if action == "decline":
        if game["status"] == "pending" and user.id in game["players"]:
            game["status"] = "declined"
            await query.edit_message_text("Match declined.")
        return

    # --- Handle Game Moves ---
    if action == "move":
        # PvB move logic
        if game["game_type"] == "ttt_pvb":
            if user.id != game["user_id"] or game["turn"] != "player": return
            
            position = int(parts[3])
            if game["board"][position] is not None: return

            game["board"][position] = 'X'
            winner = check_ttt_winner(game["board"])

            if winner:
                # Handle game end immediately
                await handle_ttt_game_end(query, context, game_id, winner)
                return

            # Bot's turn
            game["turn"] = "bot"
            await query.edit_message_text(
                f"❌⭕️ <b>Tic-Tac-Toe vs Bot!</b> (ID: <code>{game_id}</code>)\n\nBot is thinking...",
                parse_mode=ParseMode.HTML,
                reply_markup=create_ttt_keyboard(game_id, game['board'])
            )
            await asyncio.sleep(1) # Dramatic effect

            bot_pos = ttt_bot_move(game["board"])
            if bot_pos is not None:
                game["board"][bot_pos] = 'O'
            
            winner = check_ttt_winner(game["board"])
            if winner:
                await handle_ttt_game_end(query, context, game_id, winner)
                return
            
            game["turn"] = "player"
            await query.edit_message_text(
                f"❌⭕️ <b>Tic-Tac-Toe vs Bot!</b> (ID: <code>{game_id}</code>)\n\nBot played. Your turn.",
                parse_mode=ParseMode.HTML,
                reply_markup=create_ttt_keyboard(game_id, game['board'])
            )

        # PvP move logic
        elif game["game_type"] == "ttt_pvp":
            if user.id != game["turn"]: return
            
            position = int(parts[3])
            if game["board"][position] is not None: return

            game["board"][position] = game["players"][user.id] # 'X' or 'O'
            winner = check_ttt_winner(game["board"])
            
            if winner:
                await handle_ttt_game_end(query, context, game_id, winner)
                return

            # Switch turn
            game["turn"] = [pid for pid in game["players"] if pid != user.id][0]
            turn_username = game["player_usernames"][game["turn"]]
            
            await query.edit_message_text(
                f"❌⭕️ <b>Tic-Tac-Toe Match!</b> (ID: <code>{game_id}</code>)\n\n"
                f"It's @{turn_username}'s turn ('{game['players'][game['turn']]}').",
                parse_mode=ParseMode.HTML,
                reply_markup=create_ttt_keyboard(game_id, game['board'])
            )

async def handle_ttt_game_end(query, context, game_id, winner_symbol):
    game = game_sessions.get(game_id)
    if not game: return

    game["status"] = "completed"
    final_text = f"❌⭕️ <b>Game Over!</b> (ID: <code>{game_id}</code>)\n\n"
    multiplier = 1.96

    if game["game_type"] == "ttt_pvb":
        user_id = game["user_id"]
        if winner_symbol == 'X': # Player wins
            winnings = game["bet_amount"] * multiplier
            user_wallets[user_id] += winnings
            final_text += f"🎉 You win! You get ${winnings:.2f}."
            update_stats_on_bet(user_id, game_id, game["bet_amount"], True, multiplier=multiplier, context=context)
        elif winner_symbol == 'O': # Bot wins
            final_text += f"😢 The bot wins! You lose ${game['bet_amount']:.2f}."
            update_stats_on_bet(user_id, game_id, game["bet_amount"], False, context=context)
        else: # Tie
            user_wallets[user_id] += game["bet_amount"] # Refund
            final_text += "🤝 It's a tie! Your bet has been returned."
        update_pnl(user_id)
        save_user_data(user_id)

    elif game["game_type"] == "ttt_pvp":
        if winner_symbol in ['X', 'O']:
            winner_id = [pid for pid, sym in game["players"].items() if sym == winner_symbol][0]
            loser_id = [pid for pid in game["players"] if pid != winner_id][0]
            winner_username = game["player_usernames"][winner_id]
            
            winnings = game["bet_amount"] * 2 # Total pot
            user_wallets[winner_id] += winnings
            final_text += f"🏆 @{winner_username} wins the match and gets ${winnings:.2f}!"
            update_stats_on_bet(winner_id, game_id, game["bet_amount"], True, pvp_win=True, multiplier=multiplier, context=context)
            update_stats_on_bet(loser_id, game_id, game["bet_amount"], False, context=context)
            update_pnl(winner_id); update_pnl(loser_id)
            save_user_data(winner_id); save_user_data(loser_id)
        else: # Tie
            final_text += "🤝 It's a tie! Both players get their bets back."
            for pid in game["players"]:
                user_wallets[pid] += game["bet_amount"]
                save_user_data(pid)

    await query.edit_message_text(final_text, parse_mode=ParseMode.HTML, reply_markup=create_ttt_keyboard(game_id, game['board']))

# 3. ROULETTE GAME
@check_maintenance
async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text.strip()
    args = message_text.replace('/roulette', '').replace('/roul', '').strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text(
            "Usage: /roul amount choice\n\nExamples:\n"
            "• /roul 1 5\n• /roul all red\n• /roul 1 even\n• /roul 1 low\n• /roul 1 high\n• /roul 1 column1"
        )
        return

    try:
        bet_amount_str = args[0].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    choice = args[1].lower()

    if not await check_bet_limits(update, bet_amount, 'roulette'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    valid_numbers = list(range(0, 37))
    valid_choices = ["red", "black", "even", "odd", "low", "high", "column1", "column2", "column3"]
    if choice.isdigit():
        if int(choice) not in valid_numbers:
            await update.message.reply_text("Number must be between 0 and 36.")
            return
        choice_type = "number"
    elif choice in valid_choices:
        choice_type = "special"
    else:
        await update.message.reply_text("Invalid choice. Use a number (0-36), red, black, etc.")
        return

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    winning_number = get_provably_fair_result(server_seed, client_seed, 1, 37)
    game_id = generate_unique_id("RL")

    win = False
    multiplier = 0
    if choice_type == "number":
        if int(choice) == winning_number:
            win = True
            multiplier = ROULETTE_CONFIG["single_number"]["multiplier"]
    elif choice in ROULETTE_CONFIG:
        config = ROULETTE_CONFIG[choice]
        if winning_number in config["numbers"]:
            win = True
            multiplier = config["multiplier"]

    if winning_number == 0: color = "🟢 Green"
    elif winning_number in ROULETTE_CONFIG["red"]["numbers"]: color = "🔴 Red"
    else: color = "⚫ Black"

    if win:
        winnings = bet_amount * multiplier
        user_wallets[user.id] += winnings
        result_text = f"🎉 You win ${winnings:.2f}! (Multiplier: {multiplier}x)"
        update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"😢 You lose ${bet_amount:.2f}. Better luck next time!"
        update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "roulette", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "win": win, "multiplier": multiplier, "choice": choice, "result": winning_number
    }
    update_pnl(user.id)
    save_user_data(user.id)

    await update.message.reply_text(
        f"🎯 <b>Roulette Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"🎰 Winning Number: <b>{winning_number}</b> {color}\n"
        f"🎲 Your Choice: {choice}\n💰 Your Bet: ${bet_amount:.2f}\n\n{result_text}",
        parse_mode=ParseMode.HTML
    )

# 4. DICE ROLL GAME
@check_maintenance
async def dice_roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 3:
        await update.message.reply_text("Usage: /dr amount choice\n\nExamples:\n• /dr 1 3\n• /dr all even\n• /dr 1 high")
        return

    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return
    choice = args[2].lower()

    if not await check_bet_limits(update, bet_amount, 'dice_roll'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    valid_numbers = ['1', '2', '3', '4', '5', '6']
    valid_types = ['even', 'odd', 'high', 'low']
    if choice not in valid_numbers and choice not in valid_types:
        await update.message.reply_text("Invalid choice. Use 1-6, even, odd, high, or low.")
        return

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    await update.message.reply_text(f"🎲 Rolling the dice...")
    dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji="🎲")
    dice_result = dice_msg.dice.value
    game_id = generate_unique_id("DR")

    win = False
    multiplier = 0 # NEW
    if choice in valid_numbers:
        if int(choice) == dice_result: win, multiplier = True, 5.96
    elif choice == "even":
        if dice_result in [2, 4, 6]: win, multiplier = True, 1.96
    elif choice == "odd":
        if dice_result in [1, 3, 5]: win, multiplier = True, 1.96
    elif choice == "high":
        if dice_result in [4, 5, 6]: win, multiplier = True, 1.96
    elif choice == "low":
        if dice_result in [1, 2, 3]: win, multiplier = True, 1.96

    if win:
        winnings = bet_amount * multiplier
        user_wallets[user.id] += winnings
        result_text = f"🎉 You win ${winnings:.2f}! (Multiplier: {multiplier}x)"
        update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"😢 You lose ${bet_amount:.2f}. Try again!"
        update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "dice_roll", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "win": win, "multiplier": multiplier, "choice": choice, "result": dice_result
    }
    update_pnl(user.id)
    save_user_data(user.id)

    await update.message.reply_text(
        f"🎲 <b>Dice Roll Result</b> (ID: <code>{game_id}</code>)\n\n🎯 Result: <b>{dice_result}</b>\n"
        f"🎲 Your Choice: {choice}\n💰 Your Bet: ${bet_amount:.2f}\n\n{result_text}",
        parse_mode=ParseMode.HTML
    )

# 5. TOWER GAME
@check_maintenance
async def tower_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    bombs = int(context.user_data['bombs'])

    try:
        bet_amount_str = update.message.text.lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    if not await check_bet_limits(update, bet_amount, 'tower'):
        return SELECT_BET_AMOUNT

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance. Please enter a lower amount or cancel.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    tower_config = []
    server_seed = generate_server_seed()
    client_seed = generate_client_seed()
    for row in range(6):
        bomb_positions = set()
        nonce = row + 1
        while len(bomb_positions) < bombs:
            pos_hash = get_provably_fair_result(server_seed, client_seed, nonce, 4)
            bomb_positions.add(pos_hash)
            nonce += 100
        tower_config.append(list(bomb_positions))

    game_id = generate_unique_id("TW")
    game_sessions[game_id] = {
        "id": game_id, "game_type": "tower", "user_id": user.id,
        "bet_amount": bet_amount, "bombs_per_row": bombs, "status": "active",
        "timestamp": str(datetime.now(timezone.utc)), "tower_config": tower_config,
        "current_row": 0, "server_seed": server_seed, "client_seed": client_seed
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)


    keyboard = create_tower_keyboard(game_id, 0, [], tower_config[0])
    await update.message.reply_text(
        f"🏗️ <b>Tower Game Started!</b> (ID: <code>{game_id}</code>)\n\n💰 Bet: ${bet_amount:.2f}\n"
        f"💣 Bombs per row: {bombs}\n🎯 Rows to complete: 6\n\n"
        f"📍 Current Row: 1/6\nPick a safe tile!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.clear()
    return ConversationHandler.END

def create_tower_keyboard(game_id, current_row, revealed_bombs, bomb_positions):
    keyboard = []
    row_buttons = []
    for pos in range(4):
        if pos in revealed_bombs: emoji = "💥"
        elif pos in bomb_positions and current_row == -1: emoji = "💣"
        else: emoji = "❓"
        row_buttons.append(InlineKeyboardButton(emoji, callback_data=f"tower_pick_{game_id}_{pos}"))
    keyboard.append(row_buttons)
    return keyboard

@check_maintenance
async def tower_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if not query.data.startswith("tower_"):
        return

    parts = query.data.split("_")
    action = parts[1]
    game_id = parts[2]

    game = game_sessions.get(game_id)

    if not game:
        await query.edit_message_text("Game not found, already finished, or not your game.")
        return

    # NEW: Game interaction security
    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return
        
    if game.get('status') != 'active':
        return # Don't edit message if game is over


    if action == "cashout":
        current_row = game["current_row"]
        if current_row == 0:
            await query.answer("You need to complete at least one row to cash out.", show_alert=True)
            return

        multiplier = TOWER_MULTIPLIERS[game["bombs_per_row"]][current_row]
        winnings = game["bet_amount"] * multiplier
        user_wallets[user.id] += winnings
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        update_stats_on_bet(user.id, game_id, game["bet_amount"], True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        await query.edit_message_text(
            f"💸 <b>Tower Cashed Out!</b> (ID: <code>{game_id}</code>)\n\n🎉 You won <b>${winnings:.2f}</b>!\n"
            f"🏗️ Rows completed: {current_row}/6\n📈 Final multiplier: {multiplier}x",
            parse_mode=ParseMode.HTML
        )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    if action != "pick": return

    try:
        position = int(parts[3])
    except (ValueError, IndexError):
        return

    current_row = game["current_row"]
    bombs_in_row = game["tower_config"][current_row]

    if position in bombs_in_row:
        game["status"] = 'completed'
        game["win"] = False
        update_stats_on_bet(user.id, game_id, game["bet_amount"], False, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        keyboard = create_tower_keyboard(game_id, -1, [position], bombs_in_row)
        await query.edit_message_text(
            f"💥 <b>Tower Collapsed!</b> (ID: <code>{game_id}</code>)\n\n💣 You hit a bomb at position {position + 1}!\n"
            f"💔 You lost ${game['bet_amount']:.2f}\n🏗️ Rows completed: {current_row}/6",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    game["current_row"] += 1
    new_row = game["current_row"]

    if new_row >= 6:
        multiplier = TOWER_MULTIPLIERS[game["bombs_per_row"]][6]
        winnings = game["bet_amount"] * multiplier
        user_wallets[user.id] += winnings
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        update_stats_on_bet(user.id, game_id, game["bet_amount"], True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        await query.edit_message_text(
            f"🏆 <b>Tower Completed!</b> (ID: <code>{game_id}</code>)\n\n🎉 MAXIMUM WIN: <b>${winnings:.2f}</b>!\n"
            f"🏗️ All 6 rows completed!\n📈 Final multiplier: {multiplier}x",
            parse_mode=ParseMode.HTML
        )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    multiplier = TOWER_MULTIPLIERS[game["bombs_per_row"]][new_row]
    potential_winnings = game["bet_amount"] * multiplier
    keyboard = create_tower_keyboard(game_id, new_row, [], game["tower_config"][new_row])
    keyboard.append([InlineKeyboardButton(f"💸 Cash Out (${potential_winnings:.2f})", callback_data=f"tower_cashout_{game_id}")])

    await query.edit_message_text(
        f"✅ <b>Safe tile!</b> (ID: <code>{game_id}</code>)\n\n🏗️ Row {new_row}/6 completed\n"
        f"💰 Current win: <b>${potential_winnings:.2f}</b>\n"
        f"📈 Current multiplier: {multiplier}x\n\nPick next tile or cash out:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# 6. SLOTS GAME
@check_maintenance
async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if len(args) != 2:
        await update.message.reply_text("Usage: /sl amount\nExample: /sl 5 or /sl all")
        return
    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'slots'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    await update.message.reply_text(f"🎰 Spinning the slots...")
    slot_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji="🎰")
    slot_value = slot_msg.dice.value
    game_id = generate_unique_id("SL")

    win = False
    multiplier = 0
    win_type = ""
    # FIX: Corrected slot machine logic based on Telegram API
    if slot_value == 64: # 777
        win, multiplier, win_type = True, 28, "🍀 JACKPOT - Triple 7s!"
    elif slot_value in [1, 22, 43]: # bar, grape, lemon
        win, multiplier, win_type = True, 14, "🎉 Triple Match!"

    if win:
        winnings = bet_amount * multiplier
        user_wallets[user.id] += winnings
        result_text = f"🎉 {win_type}\nYou win ${winnings:.2f}! (Multiplier: {multiplier}x)"
        update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=multiplier, context=context)
    else:
        result_text = f"😢 No match! You lose ${bet_amount:.2f}\nTry again for the jackpot!"
        update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "slots", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "win": win, "multiplier": multiplier, "result": slot_value
    }
    update_pnl(user.id)
    save_user_data(user.id)
    await update.message.reply_text(
        f"🎰 <b>Slots Result</b> (ID: <code>{game_id}</code>)\n\n💰 Your Bet: ${bet_amount:.2f}\n\n{result_text}",
        parse_mode=ParseMode.HTML
    )
@check_maintenance
async def limbo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 3:
        await update.message.reply_text("Usage: /lb <amount> <multiplier>\nExample: /lb 5 2.5")
        return

    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
        
        target_multiplier = float(args[2])
        if not 1.01 <= target_multiplier <= 999:
            await update.message.reply_text("Multiplier must be between 1.01 and 999.")
            return
    except ValueError:
        await update.message.reply_text("Invalid amount or multiplier.")
        return

    if not await check_bet_limits(update, bet_amount, 'limbo'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    game_id = generate_unique_id("LB")
    result_multiplier = generate_limbo_multiplier()

    win = result_multiplier >= target_multiplier

    if win:
        winnings = bet_amount * target_multiplier
        user_wallets[user.id] += winnings
        result_text = f"🎉 <b>You Win!</b>\nYour target was met. You win ${winnings:.2f}!"
        update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=target_multiplier, context=context)
    else:
        result_text = f"😢 <b>You Lose!</b>\nYour target was not met. You lose ${bet_amount:.2f}."
        update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "limbo", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "win": win, "multiplier": target_multiplier if win else 0, "target_multiplier": target_multiplier, "result_multiplier": result_multiplier
    }
    update_pnl(user.id)
    save_user_data(user.id)

    await update.message.reply_text(
        f"🚀 <b>Limbo Result</b> (ID: <code>{game_id}</code>)\n\n"
        f"📈 Your Target Multiplier: <b>{target_multiplier:.2f}x</b>\n"
        f"🎯 Result Multiplier: <b>{result_multiplier:.2f}x</b>\n\n"
        f"{result_text}",
        parse_mode=ParseMode.HTML
    )
    
@check_maintenance
async def rps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = update.message.text.strip().split()
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if len(args) != 2:
        await update.message.reply_text("Usage: /rps <amount>\nExample: /rps 5 or /rps all")
        return

    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount.")
        return

    if not await check_bet_limits(update, bet_amount, 'rps'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    game_id = generate_unique_id("RPS")
    game_sessions[game_id] = {
        "id": game_id, "game_type": "rps", "user_id": user.id, "bet_amount": bet_amount,
        "status": "active", "timestamp": str(datetime.now(timezone.utc)), "streak": 0, "current_win": 0.0
    }
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)

    keyboard = [
        [
            InlineKeyboardButton("🪨 Rock", callback_data=f"rps_pick_{game_id}_rock"),
            InlineKeyboardButton("📄 Paper", callback_data=f"rps_pick_{game_id}_paper"),
            InlineKeyboardButton("✂️ Scissors", callback_data=f"rps_pick_{game_id}_scissors"),
        ]
    ]
    await update.message.reply_text(
        f"🪨📄✂️ <b>Rock, Paper, Scissors!</b> (ID: <code>{game_id}</code>)\n\n"
        f"💰 Bet: ${bet_amount:.2f}\n"
        f"Make your choice!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- Play vs Bot Menu: vertical and more attractive ---
@check_maintenance
async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_emoji_game_command(update, context, "dice")
@check_maintenance
async def darts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_emoji_game_command(update, context, "darts")
@check_maintenance
async def football_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_emoji_game_command(update, context, "goal")
@check_maintenance
async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await generic_emoji_game_command(update, context, "bowl")

# --- Play vs Bot main logic (bot rolls real emoji) ---
async def play_vs_bot_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str, target_score: int):
    user = update.effective_user
    bet_amount = context.user_data['bet_amount']
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not await check_bet_limits(update, bet_amount, f'pvb_{game_type}'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You no longer have enough balance for this bet. Game cancelled.")
        return
    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    game_id = generate_unique_id("PVB")
    emoji_map = {"dice":"🎲", "darts":"🎯", "goal":"⚽", "bowl":"🎳"}

    await update.message.reply_text(
        f"🎮 {game_type.capitalize()} vs Bot started! (ID: <code>{game_id}</code>)\n"
        f"First to {target_score} points wins ${bet_amount*2:.2f}.\n"
        f"Bot is rolling first..."
    )
    await asyncio.sleep(1.5)
    bot_dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji=emoji_map[game_type])
    bot_roll = bot_dice_msg.dice.value
    await asyncio.sleep(1.5)

    await update.message.reply_text(f"Bot rolled {bot_roll}. Now your turn! Send the {emoji_map[game_type]} emoji in this chat.")

    game_sessions[game_id] = {
        "id": game_id, "game_type": f"pvb_{game_type}", "user_id": user.id,
        "bet_amount": bet_amount, "status": "active", "timestamp": str(datetime.now(timezone.utc)),
        "target_score": target_score, "current_round": 1,
        "user_score": 0, "bot_score": 0, "last_bot_roll": bot_roll,
        "history": [] # To store round results
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    save_user_data(user.id)
    
    context.chat_data[f"active_pvb_game_{user.id}"] = game_id


# --- /predict amount up/down game ---
@check_maintenance
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    args = update.message.text.strip().split()
    if len(args) != 3 or args[2].lower() not in ("up", "down"):
        await update.message.reply_text(
            "Usage: /predict amount up/down\nExample: /predict 1 up or /predict all up\n"
            "<b>Guess if the dice will be up (4-6) or down (1-3).</b>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        bet_amount_str = args[1].lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except Exception:
        await update.message.reply_text("Invalid amount.")
        return

    direction = args[2].lower()
    if not await check_bet_limits(update, bet_amount, 'predict'):
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    user_wallets[user.id] -= bet_amount
    await update.message.reply_text(f"Rolling the dice... 🎲")
    dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji="🎲")
    outcome = dice_msg.dice.value
    game_id = generate_unique_id("PRD")

    win = (direction == "up" and outcome in [4, 5, 6]) or (direction == "down" and outcome in [1, 2, 3])

    if win:
        winnings = bet_amount * 2
        user_wallets[user.id] += winnings
        result_text = f"Result: {outcome} 🎲\n🎉 You won! You receive ${winnings:.2f}."
        update_stats_on_bet(user.id, game_id, bet_amount, True, multiplier=2, context=context)
    else:
        result_text = f"Result: {outcome} 🎲\n😢 You lost! Better luck next time."
        update_stats_on_bet(user.id, game_id, bet_amount, False, context=context)

    game_sessions[game_id] = {
        "id": game_id, "game_type": "predict", "user_id": user.id,
        "bet_amount": bet_amount, "status": "completed", "timestamp": str(datetime.now(timezone.utc)),
        "win": win, "multiplier": 2 if win else 0, "choice": direction, "result": outcome
    }
    update_pnl(user.id)
    save_user_data(user.id)
    await update.message.reply_text(f"{result_text}\nID: <code>{game_id}</code>", parse_mode=ParseMode.HTML)

# --- MINES GAME FUNCTIONS ---
def get_mines_multiplier(num_mines, safe_picks):
    if safe_picks == 0: return 1.0
    try: return MINES_MULT_TABLE[num_mines][safe_picks]
    except KeyError: return 1.0

def mines_keyboard(game_id, reveal=False):
    game = game_sessions.get(game_id)
    if not game: return InlineKeyboardMarkup([])

    total_cells = game["total_cells"]
    num_per_row = 5
    buttons = []
    for i in range(1, total_cells + 1):
        if i in game["picks"]: emoji = "✅"
        elif reveal and i in game["mines"]: emoji = "💥"
        elif reveal: emoji = "💎"
        else: emoji = "❓"
        buttons.append(InlineKeyboardButton(emoji, callback_data=f"mines_pick_{game_id}_{i}"))

    keyboard = [buttons[i:i+num_per_row] for i in range(0, len(buttons), num_per_row)]
    if game["status"] == 'active' and game["picks"]:
        safe_picks = len(game["picks"])
        multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
        winnings = game["bet_amount"] * multiplier
        cashout_text = f"💸 Cashout (${winnings:.2f})"
        keyboard.append([InlineKeyboardButton(cashout_text, callback_data=f"mines_cashout_{game_id}")])
    return InlineKeyboardMarkup(keyboard)

@check_maintenance
async def mines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    num_mines = int(context.user_data['bombs'])

    try:
        bet_amount_str = update.message.text.lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid bet amount. Please enter a number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    if not await check_bet_limits(update, bet_amount, 'mines'):
        return SELECT_BET_AMOUNT

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance. Please enter a lower amount or cancel.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    total_cells = 25
    mine_numbers = set(random.sample(range(1, total_cells + 1), num_mines))
    game_id = generate_unique_id("MN")
    game_sessions[game_id] = {
        "id": game_id, "game_type": "mines", "user_id": user.id, "bet_amount": bet_amount,
        "status": "active", "timestamp": str(datetime.now(timezone.utc)), "mines": list(mine_numbers),
        "picks": [], "total_cells": total_cells, "num_mines": num_mines
    }
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if 'game_sessions' not in user_stats[user.id]: user_stats[user.id]['game_sessions'] = []
    user_stats[user.id]['game_sessions'].append(game_id)
    
    user_wallets[user.id] -= bet_amount
    save_user_data(user.id)

    initial_text = (
        f"💣 <b>Mines Game Started!</b> (ID: <code>{game_id}</code>)\n\nBet: <b>${bet_amount:.2f}</b>\nMines: <b>{num_mines}</b>\n\n"
        "Click the buttons to reveal tiles. Find gems to increase your multiplier. Avoid the bombs!\n"
        "You can cash out after any successful pick."
    )
    await update.message.reply_text(
        initial_text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id)
    )
    context.user_data.clear()
    return ConversationHandler.END

@check_maintenance
async def mines_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    parts = query.data.split("_")
    action = parts[1]
    game_id = parts[2]

    game = game_sessions.get(game_id)

    if not game:
        await query.edit_message_text("No active mines game found, it has ended, or it is not your game.", reply_markup=None)
        return

    # NEW: Game interaction security
    if user.id != game.get('user_id'):
        await query.answer("This is not your game!", show_alert=True)
        return

    if game.get("status") != 'active':
        # Don't edit message if game is over, just inform the user who tapped
        await query.answer("This game has already ended.", show_alert=True)
        return


    if action == "cashout":
        safe_picks = len(game["picks"])
        if safe_picks == 0:
            await query.answer("You need to make at least one pick to cash out.", show_alert=True)
            return

        multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
        winnings = game["bet_amount"] * multiplier
        user_wallets[user.id] += winnings
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        update_stats_on_bet(user.id, game_id, game['bet_amount'], win=True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        await query.edit_message_text(
            f"💸 <b>Cashed Out!</b> (ID: <code>{game_id}</code>)\n\nYou won <b>${winnings:.2f}</b> with {safe_picks} correct picks!\n"
            f"Multiplier: <b>{multiplier:.2f}x</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=mines_keyboard(game_id, reveal=True)
        )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    try:
        cell = int(parts[3])
    except (ValueError, IndexError): return

    if cell in game["picks"]:
        await query.answer("You have already picked this tile.", show_alert=True)
        return

    if cell in game["mines"]:
        game["status"] = 'completed'
        game["win"] = False
        update_stats_on_bet(user.id, game_id, game['bet_amount'], win=False, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        await query.edit_message_text(
            f"💥 <b>Boom!</b> You hit a mine at tile {cell}. (ID: <code>{game_id}</code>)\n\n"
            f"You lost your bet of <b>${game['bet_amount']:.2f}</b>.",
            parse_mode=ParseMode.HTML,
            reply_markup=mines_keyboard(game_id, reveal=True)
        )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    game["picks"].append(cell)
    safe_picks = len(game["picks"])
    multiplier = get_mines_multiplier(game["num_mines"], safe_picks)
    potential_winnings = game["bet_amount"] * multiplier

    if safe_picks == (game["total_cells"] - game["num_mines"]):
        game["status"] = 'completed'
        game["win"] = True
        game["multiplier"] = multiplier
        user_wallets[user.id] += potential_winnings
        update_stats_on_bet(user.id, game_id, game['bet_amount'], win=True, multiplier=multiplier, context=context)
        update_pnl(user.id)
        save_user_data(user.id)
        await query.edit_message_text(
            f"🎉 <b>MAX WIN!</b> (ID: <code>{game_id}</code>)\n\nYou found all {safe_picks} gems and won <b>${potential_winnings:.2f}</b>!\n"
            f"Final Multiplier: <b>{multiplier:.2f}x</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=mines_keyboard(game_id, reveal=True)
        )
        # del game_sessions[game_id] # FIX: Don't delete history
        return

    next_text = (
        f"✅ Safe! Tile {cell} was a gem. (ID: <code>{game_id}</code>)\n\n<b>Picks:</b> {safe_picks}/{game['total_cells'] - game['num_mines']}\n"
        f"<b>Current Multiplier:</b> {multiplier:.2f}x\n<b>Current Cashout:</b> ${potential_winnings:.2f}"
    )
    await query.edit_message_text(next_text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id))
    await query.answer(f"Safe! Current multiplier: {multiplier:.2f}x")

# --- /cancelall command (owner only, cancels all matches and notifies users) ---
async def cancel_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)
    cancelled = 0
    for game_id, game in list(game_sessions.items()):
        if game.get("status") == 'active' and 'players' in game: # Only cancel PvP games
            game["status"] = 'cancelled'
            for uid in game["players"]:
                user_wallets[uid] += game["bet_amount"]
                save_user_data(uid)
                try:
                    await context.bot.send_message(
                        chat_id=uid,
                        text=f"Your match {game_id} has been cancelled by the bot owner. Your bet has been refunded."
                    )
                except Exception: pass
            cancelled += 1
    await update.message.reply_text(
        f"Cancelled {cancelled} active PvP matches. Bets refunded to players."
    )

# --- STOP/RESUME/CANCEL ALL HANDLERS ---
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)
    ongoing_matches = [m for m in game_sessions.values() if m.get("status") == 'active' and 'players' in m]
    if ongoing_matches:
        await update.message.reply_text("There are ongoing matches. Please finish or use /cancelall before stopping.")
        return
    keyboard = [[InlineKeyboardButton("Yes", callback_data="stop_confirm_yes"), InlineKeyboardButton("No", callback_data="stop_confirm_no")]]
    await update.message.reply_text("Are you sure you want to stop the bot? This will pause new games.", reply_markup=InlineKeyboardMarkup(keyboard))

async def stop_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if user.id != BOT_OWNER_ID:
        await query.answer("Only the owner can confirm stop.", show_alert=True)
        return
    if query.data == "stop_confirm_yes":
        bot_stopped = True
        await query.edit_message_text("✅ Bot is now stopped. No new matches can be started.")
    else:
        await query.edit_message_text("Stop cancelled. Bot remains active.")

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_stopped
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)
    bot_stopped = False
    await update.message.reply_text("✅ Bot is resumed. New matches can be started.")

# --- BANK COMMAND ---
@check_maintenance
async def bank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    # FIX: Show the house balance from bot settings
    bank = bot_settings.get("house_balance", 0.0)
    await update.message.reply_text(f"🏦 <b>BOT BANK</b>\n\n"
                                    f"This is the designated house balance.\n"
                                    f"Current House Balance: <b>${bank:,.2f}</b>",
                                    parse_mode=ParseMode.HTML)

# --- RAIN COMMAND ---
@check_maintenance
async def rain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    args = update.message.text.strip().split()
    if len(args) != 3:
        await update.message.reply_text("Usage: /rain amount N (e.g. /rain 50 2)")
        return
    try:
        amount = float(args[1])
        N = int(args[2])
        if amount <= 0 or N <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid amount or number.")
        return

    if user_wallets.get(user.id, 0.0) < amount:
        await update.message.reply_text("You do not have enough funds to rain.")
        return

    # FIXED: Eligible users are all registered users except the rainer
    eligible = [uid for uid in user_stats.keys() if uid != user.id]

    if N > len(eligible):
        await update.message.reply_text(f"Not enough users to rain on! Found {len(eligible)}, need {N}.")
        return

    chosen = random.sample(eligible, N)
    portion = amount / N
    user_wallets[user.id] -= amount
    rained_on_users = []
    for uid in chosen:
        user_wallets[uid] = user_wallets.get(uid, 0) + portion
        await ensure_user_in_wallets(uid, context=context)
        update_stats_on_rain_received(uid, portion)
        update_pnl(uid)
        save_user_data(uid)
        username = user_stats.get(uid, {}).get("userinfo", {}).get("username", f"ID: {uid}")
        rained_on_users.append(f"@{username}" if username else f"ID: {uid}")
    save_user_data(user.id)
    rained_on_str = ", ".join(rained_on_users)
    await update.message.reply_text(f"🌧️ Rained ${amount:.2f} on {N} users!\nEach received ${portion:.2f}.\n\nRecipients: {rained_on_str}")

@check_maintenance
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    stats = user_stats[user.id]
    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))
    
    # NEW: Get user level
    level_data = get_user_level(user.id)
    
    text = (
        f"📊 <b>Your Stats</b>\n"
        f"👤 Username: @{stats.get('userinfo', {}).get('username','')}\n"
        f"🦄 Level: {level_data['level']} ({level_data['name']})\n" # ADDED
        f"💰 Balance: ${user_wallets.get(user.id, 0.0):.2f}\n"
        f"🎲 Total Bets: {stats.get('bets', {}).get('count', 0)} (Wins: {stats.get('bets', {}).get('wins', 0)}, Losses: {stats.get('bets', {}).get('losses', 0)})\n"
        f"💵 Deposits: {len(stats.get('deposits',[]))} (${total_deposits:.2f})\n"
        f"🏧 Withdrawals: {len(stats.get('withdrawals',[]))} (${total_withdrawals:.2f})\n"
        f"🎁 Tips Received: {stats.get('tips_received', {}).get('count', 0)} (${stats.get('tips_received', {}).get('amount', 0.0):.2f})\n"
        f"🎁 Tips Sent: {stats.get('tips_sent', {}).get('count', 0)} (${stats.get('tips_sent', {}).get('amount', 0.0):.2f})\n"
        f"🌧️ Rain Received: {stats.get('rain_received', {}).get('count', 0)} (${stats.get('rain_received', {}).get('amount', 0.0):.2f})\n"
        f"📈 PnL: ${stats.get('pnl', 0.0):.2f}\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# --- USERS (OWNER-ONLY) COMMAND ---
async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the owner can use this command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not user_stats:
        await update.message.reply_text("No users found in the database.")
        return

    context.user_data['users_page'] = 0
    await send_users_page(update, context)

async def send_users_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = context.user_data.get('users_page', 0)
    page_size = 5
    user_ids = list(user_stats.keys())
    start_index = page * page_size
    end_index = start_index + page_size

    paginated_user_ids = user_ids[start_index:end_index]

    if update.callback_query and not paginated_user_ids:
        await update.callback_query.answer("No more users.", show_alert=True)
        return

    msg = "<b>All User Stats (Page {}):</b>\n\n".format(page + 1)
    for uid in paginated_user_ids:
        stats = user_stats[uid]
        username = stats.get('userinfo', {}).get('username', 'N/A')
        pnl = stats.get('pnl', 0.0)
        msg += (
            f"👤 @{username} (ID: <code>{uid}</code>)\n"
            f"  - 💰 <b>Balance:</b> ${user_wallets.get(uid, 0):.2f}\n"
            f"  - 📈 <b>P&L:</b> ${pnl:.2f}\n"
            f"  - 🎲 <b>Bets:</b> {stats.get('bets',{}).get('count',0)} (W: {stats.get('bets',{}).get('wins',0)}, L: {stats.get('bets',{}).get('losses',0)})\n"
        )

    keyboard = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Previous", callback_data="users_prev"))
    if end_index < len(user_ids):
        row.append(InlineKeyboardButton("Next ➡️", callback_data="users_next"))
    if row:
        keyboard.append(row)

    # NEW: Back to admin dashboard button
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_dashboard")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def users_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID:
        await query.answer("This is an admin-only button.", show_alert=True)
        return

    await query.answer()
    action = query.data
    page = context.user_data.get('users_page', 0)

    if action == "users_next":
        context.user_data['users_page'] = page + 1
    elif action == "users_prev":
        context.user_data['users_page'] = max(0, page - 1)

    await send_users_page(update, context)

# --- New Games (Darts, Football, Bowling, Dice) ---
@check_maintenance
async def generic_emoji_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str):
    if bot_stopped:
        await update.message.reply_text("🚫 Bot is currently stopped. No new matches can be started.")
        return
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    message_text = update.message.text.strip().split()
    if len(message_text) != 4:
        await update.message.reply_text(f"Usage: /{game_type} @username amount ftX\nExample: /{game_type} @opponent 1 ft3")
        return

    opponent_username = normalize_username(message_text[1])
    amount_str = message_text[2].lower()
    ft_str = message_text[3].lower()

    if not opponent_username or opponent_username == normalize_username(user.username):
        await update.message.reply_text("Please specify a valid opponent's @username that is not yourself.")
        return

    if amount_str == "all":
        bet_amount = user_wallets.get(user.id, 0.0)
    else:
        try: bet_amount = float(amount_str)
        except ValueError:
            await update.message.reply_text("Invalid amount.")
            return

    if not await check_bet_limits(update, bet_amount, f'pvp_{game_type}'):
        return

    if not ft_str.startswith("ft"):
        await update.message.reply_text("Invalid format for points target (must be ftX, e.g., ft3).")
        return
    try: target_points = int(ft_str[2:])
    except ValueError:
        await update.message.reply_text("Invalid points target.")
        return

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance.")
        return

    opponent_id = username_to_userid.get(opponent_username)
    if not opponent_id:
        try:
            chat = await context.bot.get_chat(opponent_username)
            opponent_id = chat.id
            await ensure_user_in_wallets(opponent_id, chat.username, context=context)
        except Exception:
            await update.message.reply_text(f"Opponent {opponent_username} not found. Ask them to DM the bot or send /bal first.")
            return

    await ensure_user_in_wallets(opponent_id, opponent_username, context=context)
    if user_wallets.get(opponent_id, 0.0) < bet_amount:
        await update.message.reply_text(f"Opponent {opponent_username} does not have enough balance for this match.")
        return

    match_id = generate_unique_id("PVP")
    match_data = {
        "id": match_id, "game_type": f"pvp_{game_type}", "bet_amount": bet_amount, "target_points": target_points,
        "points": {user.id: 0, opponent_id: 0}, "emoji_buffer": {},
        "players": [user.id, opponent_id],
        "usernames": {user.id: normalize_username(user.username) or f"ID{user.id}", opponent_id: opponent_username},
        "status": "pending", "last_roller": None,
        "host_id": user.id, "chat_id": update.effective_chat.id,
        "timestamp": str(datetime.now(timezone.utc))
    }
    game_sessions[match_id] = match_data
    keyboard = [[InlineKeyboardButton("Accept", callback_data=f"accept_{match_id}"), InlineKeyboardButton("Decline", callback_data=f"decline_{match_id}")]]

    sent_message = await update.message.reply_text(
        f"New {game_type.capitalize()} match request!\nHost: {user.mention_html()} vs Opponent: {opponent_username}\n"
        f"Bet: ${bet_amount:.2f} | Target: First to {target_points} points.\n"
        f"{opponent_username}, tap Accept to join the match. (Match ID: <code>{match_id}</code>)",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

    try:
        await context.bot.pin_chat_message(chat_id=update.effective_chat.id, message_id=sent_message.message_id, disable_notification=True)
        match_data['pinned_message_id'] = sent_message.message_id
    except BadRequest as e:
        logging.warning(f"Failed to pin match message for match {match_id}: {e}")

@check_maintenance
async def pvb_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    await ensure_user_in_wallets(query.from_user.id, query.from_user.username, context=context)

    if data.startswith("pvb_start_"):
        game_type = data.replace("pvb_start_", "")
        context.user_data['game_type'] = game_type
        await query.edit_message_text(f"How much do you want to bet against the bot? (You can also type 'all')", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    elif data.startswith("pvp_info_"):
        game_type_map = {"dice_bot": "dice", "football": "goal", "darts": "darts", "bowling": "bowl"}
        game_type = game_type_map.get(data.replace("pvp_info_", ""), "dice")
        await query.edit_message_text(f"To play against a player, use:\n`/{game_type} @username amount ftX`", parse_mode=ParseMode.MARKDOWN_V2)

# --- BALANCE COMMAND ---
@check_maintenance
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    balance = user_wallets.get(user.id, 0.0)
    await update.message.reply_text(f"Your current wallet balance: ${balance:.2f}")

# --- NEW USER HISTORY COMMANDS ---
@check_maintenance
async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False, page=0):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_game_ids = user_stats[user.id].get("game_sessions", [])

    if not user_game_ids:
        text = "You haven't played any matches yet."
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Wallet", callback_data="main_wallet")]]) if from_callback else None
        if from_callback: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else: await update.message.reply_text(text, reply_markup=reply_markup)
        return

    all_games = [game_sessions[gid] for gid in reversed(user_game_ids) if gid in game_sessions]
    pending_games = [g for g in all_games if g.get("status") == "active"]
    completed_games = [g for g in all_games if g.get("status") != "active"]

    msg = ""
    # Display pending games first, always
    if pending_games:
        msg += "⏳ <b>Your Pending/Active Games:</b>\n\n"
        for game in pending_games:
            game_type = game['game_type'].replace('_', ' ').title()
            msg += (f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
                    f"<b>Bet:</b> ${game['bet_amount']:.2f} | <b>Status:</b> {game['status'].capitalize()}\n"
                    f"Use <code>/continue {game['id']}</code> to resume.\n"
                    "--------------------\n")

    # Paginated completed games
    page_size = 10
    start_index = page * page_size
    end_index = start_index + page_size
    paginated_completed = completed_games[start_index:end_index]

    msg += f"📜 <b>Your Completed Games (Page {page + 1}):</b>\n\n"
    if not paginated_completed:
        msg += "No completed games on this page.\n"

    for game in paginated_completed:
        game_type = game['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"

        # Determine win/loss/push status text
        if game.get('win') is True:
            win_status = "Win"
        elif game.get('win') is False:
            win_status = "Loss"
        else: # Covers push (None) or other statuses
            win_status = game['status'].capitalize()

        msg += f"<b>Bet:</b> ${game['bet_amount']:.2f} | <b>Result:</b> {win_status}\n"

        # Add game-specific details
        if game['game_type'] == 'blackjack':
            player_val = calculate_hand_value(game.get('player_hand', []))
            dealer_val = calculate_hand_value(game.get('dealer_hand', []))
            msg += f"<b>Hand:</b> {player_val} vs <b>Dealer:</b> {dealer_val}\n"
        elif game['game_type'] in ['mines', 'tower', 'coin_flip']:
            multiplier = game.get('multiplier', 0)
            msg += f"<b>Multiplier:</b> {multiplier:.2f}x\n"
        elif 'players' in game: # PvP
            p1_id, p2_id = game['players']
            p1_name = game['usernames'].get(p1_id, f"ID:{p1_id}")
            p2_name = game['usernames'].get(p2_id, f"ID:{p2_id}")
            score = f"{game['points'].get(p1_id, 0)} - {game['points'].get(p2_id, 0)}"
            msg += f"<b>Match:</b> {p1_name} vs {p2_name}\n<b>Score:</b> {score}\n"

        msg += "--------------------\n"

    # Pagination Keyboard
    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"my_matches_{page - 1}"))
    if end_index < len(completed_games):
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"my_matches_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔙 Back to Wallet", callback_data="main_wallet")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_callback:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_maintenance
async def deals_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False, page=0):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_deal_ids = user_stats[user.id].get("escrow_deals", [])

    if not user_deal_ids:
        text = "You have no escrow deals."
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Wallet", callback_data="main_wallet")]]) if from_callback else None
        if from_callback: await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else: await update.message.reply_text(text, reply_markup=reply_markup)
        return

    all_deals = []
    for deal_id in reversed(user_deal_ids):
        deal = escrow_deals.get(deal_id)
        if not deal and os.path.exists(os.path.join(ESCROW_DIR, f"{deal_id}.json")):
            with open(os.path.join(ESCROW_DIR, f"{deal_id}.json"), "r") as f: deal = json.load(f)
        if deal: all_deals.append(deal)

    page_size = 10
    start_index = page * page_size
    end_index = start_index + page_size
    paginated_deals = all_deals[start_index:end_index]

    msg = f"🛡️ <b>Your Escrow Deals (Page {page + 1}):</b>\n\n"
    if not paginated_deals:
        msg += "No deals on this page.\n"

    for deal in paginated_deals:
        seller_name = deal['seller'].get('username') or f"ID:{deal['seller']['id']}"
        buyer_name = deal['buyer'].get('username') or f"ID:{deal['buyer']['id']}"
        role = "Seller" if user.id == deal['seller']['id'] else "Buyer"
        msg += (f"<b>Deal ID:</b> <code>{deal['id']}</code>\n<b>Your Role:</b> {role}\n"
                f"<b>Amount:</b> ${deal['amount']:.2f} USDT\n<b>Seller:</b> @{seller_name}\n<b>Buyer:</b> @{buyer_name}\n"
                f"<b>Status:</b> {deal['status'].replace('_', ' ').capitalize()}\n--------------------\n")

    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"my_deals_{page - 1}"))
    if end_index < len(all_deals):
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"my_deals_{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔙 Back to Wallet", callback_data="main_wallet")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if from_callback: await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else: await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# --- OWNER HISTORY COMMANDS ---
async def he_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    all_deal_files = [f for f in os.listdir(ESCROW_DIR) if f.endswith('.json')]
    if not all_deal_files:
        await update.message.reply_text("No escrow deals found.")
        return
    all_deal_files.sort(reverse=True)
    msg = "📜 <b>All Escrow Deals History (Latest 20):</b>\n\n"
    count = 0
    for fname in all_deal_files:
        if count >= 20: break
        with open(os.path.join(ESCROW_DIR, fname), 'r') as f:
            deal = json.load(f)
            seller_name = deal.get('seller', {}).get('username', 'N/A')
            buyer_name = deal.get('buyer', {}).get('username', 'N/A')
            msg += (f"<b>ID:</b> <code>{deal['id']}</code> | <b>Status:</b> {deal.get('status', 'N/A').capitalize()}\n"
                    f"<b>Amount:</b> ${deal.get('amount', 0.0):.2f} | <b>Date:</b> {deal.get('timestamp', 'N/A').split('T')[0]}\n"
                    f"<b>Seller:</b> @{seller_name}, <b>Buyer:</b> @{buyer_name}\n--------------------\n")
            count += 1
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def hc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)

    all_games = sorted(game_sessions.values(), key=lambda x: x.get("timestamp", ""), reverse=True)
    if not all_games:
        await update.message.reply_text("No game matches found.")
        return

    # Show pending games first for the owner
    pending_games = [g for g in all_games if g.get("status") == "active"]
    completed_games = [g for g in all_games if g.get("status") != "active"]

    msg = ""
    if pending_games:
        msg += "⏳ <b>Owner View: Active/Pending Games:</b>\n\n"
        for game in pending_games[:10]: # Limit display
             game_type = game['game_type'].replace('_', ' ').title()
             msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
             if 'players' in game:
                p_names = [game['usernames'].get(pid, f"ID:{pid}") for pid in game['players']]
                msg += f"<b>Players:</b> {', '.join(p_names)}\n"
             else:
                uname = user_stats.get(game['user_id'], {}).get('userinfo',{}).get('username', 'N/A')
                msg += f"<b>Player:</b> @{uname}\n"
             msg += "--------------------\n"

    msg += "\n📜 <b>All Casino Matches History (Latest 20 Completed):</b>\n\n"
    for match in completed_games[:20]:
        game_type = match['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{match['id']}</code>\n"
        if 'players' in match: # PvP
            p1_id, p2_id = match['players']
            p1_name = match['usernames'].get(p1_id, f"ID:{p1_id}")
            p2_name = match['usernames'].get(p2_id, f"ID:{p2_id}")
            score = f"{match['points'].get(p1_id, 0)} - {match['points'].get(p2_id, 0)}"
            msg += f"<b>Match:</b> {p1_name} vs {p2_name}\n<b>Score:</b> {score} | "
        else: # Solo game
            uname = user_stats.get(match['user_id'], {}).get('userinfo',{}).get('username', 'N/A')
            msg += f"<b>Player:</b> @{uname} | "

        msg += (f"<b>Bet:</b> ${match['bet_amount']:.2f}\n"
                f"<b>Status:</b> {match.get('status', 'N/A').capitalize()}\n--------------------\n")
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@check_maintenance
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /info <unique_id>")
        return

    unique_id = context.args[0]
    msg = f"🔍 <b>Detailed Info for ID:</b> <code>{unique_id}</code>\n\n"

    # Check in game sessions
    if unique_id in game_sessions:
        game = game_sessions[unique_id]
        game_type = game['game_type'].replace('_', ' ').title()
        timestamp = datetime.fromisoformat(game['timestamp']).strftime('%Y-%m-%d %H:%M UTC')
        msg += (f"<b>Type:</b> Game Session\n"
                f"<b>Game:</b> {game_type}\n"
                f"<b>Bet:</b> ${game.get('bet_amount', 0):.2f}\n"
                f"<b>Status:</b> {game.get('status', 'N/A').title()}\n"
                f"<b>Date:</b> {timestamp}\n")

        if 'players' in game: # PvP
            p1_id, p2_id = game['players']
            p1_name = game['usernames'].get(p1_id, f"ID:{p1_id}")
            p2_name = game['usernames'].get(p2_id, f"ID:{p2_id}")
            score = f"{game['points'].get(p1_id, 0)} - {game['points'].get(p2_id, 0)}"
            msg += f"<b>Players:</b> {p1_name} vs {p2_name}\n<b>Score:</b> {score}\n"
        elif 'user_id' in game: # Solo or PvB
            uid = game['user_id']
            uname = user_stats.get(uid, {}).get('userinfo',{}).get('username', f'ID:{uid}')
            msg += f"<b>Player:</b> @{uname} (<code>{uid}</code>)\n"

        if game.get('win') is not None:
             msg += f"<b>Result:</b> {'Win' if game['win'] else 'Loss'}\n"
        if game.get('multiplier'):
             msg += f"<b>Multiplier:</b> {game['multiplier']}x\n"

        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    # Check in escrow deals
    deal_file = os.path.join(ESCROW_DIR, f"{unique_id}.json")
    deal = escrow_deals.get(unique_id)
    if not deal and os.path.exists(deal_file):
        with open(deal_file, 'r') as f: deal = json.load(f)

    if deal:
        seller, buyer = deal.get('seller', {}), deal.get('buyer', {})
        timestamp = datetime.fromisoformat(deal['timestamp']).strftime('%Y-%m-%d %H:%M UTC')
        msg += (f"<b>Type:</b> Escrow Deal\n"
               f"<b>Status:</b> {deal.get('status', 'N/A').upper()}\n<b>Amount:</b> ${deal.get('amount', 0):.2f} USDT\n"
               f"<b>Date:</b> {timestamp}\n\n"
               f"<b>Seller:</b>\n  - Username: @{seller.get('username', 'N/A')}\n  - ID: <code>{seller.get('id', 'N/A')}</code>\n\n"
               f"<b>Buyer:</b>\n  - Username: @{buyer.get('username', 'N/A')}\n  - ID: <code>{buyer.get('id', 'N/A')}</code>\n\n"
               f"<b>Deal Details:</b>\n<pre>{deal.get('details', 'No details provided.')}</pre>\n\n"
               f"<b>Deposit Tx Hash:</b>\n<code>{deal.get('deposit_tx_hash', 'N/A')}</code>\n\n"
               f"<b>Release Tx Hash:</b>\n<code>{deal.get('release_tx_hash', 'N/A')}</code>\n")
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    await update.message.reply_text("No game or escrow deal found with that ID.")

# --- MESSAGE LISTENER HANDLER ---
@check_maintenance
async def message_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return

    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_stats[user.id]['last_update'] = str(datetime.now(timezone.utc))

    # NEW: Check for new members in a group
    if update.message.new_chat_members:
        chat_id = update.effective_chat.id
        settings = group_settings.get(chat_id)
        if settings and settings.get("welcome_message"):
            for new_member in update.message.new_chat_members:
                welcome_text = settings["welcome_message"].format(
                    first_name=new_member.first_name,
                    last_name=new_member.last_name or "",
                    username=f"@{new_member.username}" if new_member.username else "",
                    mention=new_member.mention_html(),
                    chat_title=update.effective_chat.title
                )
                await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
        return


    if 'escrow_step' in context.user_data:
        await handle_escrow_conversation(update, context)
        return

    # Handle PvB games
    active_pvb_game_id = context.chat_data.get(f"active_pvb_game_{user.id}")
    if active_pvb_game_id and active_pvb_game_id in game_sessions:
        game = game_sessions[active_pvb_game_id]
        game_type = game['game_type'].replace("pvb_", "")
        emoji_map = {"dice":"🎲", "darts":"🎯", "goal":"⚽", "bowl":"🎳"}
        expected_emoji = emoji_map[game_type]

        if update.message.dice and update.message.dice.emoji == expected_emoji:
            user_roll = update.message.dice.value
            bot_roll = game["last_bot_roll"]

            win = False
            if game_type in ["dice", "bowl"]: win = user_roll > bot_roll
            elif game_type == "darts": win = user_roll == 6 or (abs(6-user_roll) < abs(6-bot_roll))
            elif game_type == "goal":
                user_scored, bot_scored = user_roll >= 4, bot_roll >= 4
                if user_scored and not bot_scored: win = True
                elif user_scored and bot_scored: win = user_roll > bot_roll
                else: win = False

            round_result = {"user": user_roll, "bot": bot_roll, "winner": None}
            if win:
                game["user_score"] += 1
                round_result["winner"] = "user"
                await update.message.reply_text(f"You rolled {user_roll}, Bot rolled {bot_roll}. You win this round!")
            elif user_roll == bot_roll:
                await update.message.reply_text(f"You both rolled {user_roll}. It's a tie! No point.")
            else:
                game["bot_score"] += 1
                round_result["winner"] = "bot"
                await update.message.reply_text(f"You rolled {user_roll}, Bot rolled {bot_roll}. Bot wins this round!")

            game["history"].append(round_result)
            game["current_round"] += 1

            # Check for game end
            if game["user_score"] >= game["target_score"]:
                winnings = game["bet_amount"] * 2
                user_wallets[user.id] += winnings
                game['status'] = 'completed'
                game['win'] = True
                update_stats_on_bet(user.id, game['id'], game['bet_amount'], True, context=context)
                await asyncio.sleep(1.5)
                await update.message.reply_text(f"🏆 Congratulations! You beat the bot ({game['user_score']}-{game['bot_score']}) and win ${winnings:.2f}!")
                del context.chat_data[f"active_pvb_game_{user.id}"]
            elif game["bot_score"] >= game["target_score"]:
                game['status'] = 'completed'
                game['win'] = False
                update_stats_on_bet(user.id, game['id'], game['bet_amount'], False, context=context)
                await asyncio.sleep(1.5)
                await update.message.reply_text(f"😔 Bot wins the match ({game['bot_score']}-{game['user_score']}). You lost ${game['bet_amount']:.2f}.")
                del context.chat_data[f"active_pvb_game_{user.id}"]
            else: # Continue game
                await asyncio.sleep(1.5)
                await update.message.reply_text(f"Score: You {game['user_score']} - {game['bot_score']} Bot. (First to {game['target_score']})\nBot is rolling...")
                await asyncio.sleep(1.5)
                next_bot_dice_msg = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji=expected_emoji)
                game["last_bot_roll"] = next_bot_dice_msg.dice.value
                await asyncio.sleep(1.5)
                await update.message.reply_text(f"Bot rolled {next_bot_dice_msg.dice.value}. Your turn!")
            update_pnl(user.id)
            save_user_data(user.id)
        return

    if update.message and update.message.dice and update.effective_chat and update.effective_chat.type in ["group", "supergroup"]:
        dice_obj = update.message.dice
        chat_id = update.effective_chat.id
        emoji = dice_obj.emoji

        for match_id, match_data in list(game_sessions.items()):
            if match_data.get("chat_id") == chat_id and match_data.get("status") == 'active' and user.id in match_data.get("players", []):
                gtype = match_data.get("game_type", "pvp_dice").replace("pvp_", "")
                players = match_data["players"]
                last_roller = match_data.get("last_roller")
                if last_roller is None:
                    if user.id != players[0]:
                        await update.message.reply_text("It's not your turn yet! Host should roll first.")
                        return
                elif user.id == last_roller:
                    await update.message.reply_text("Wait for your opponent to roll next.")
                    return

                allowed_emojis = {"dice": "🎲", "darts": "🎯", "goal": "⚽", "bowl": "🎳"}
                if emoji != allowed_emojis.get(gtype, "🎲"):
                    await update.message.reply_text(f"Only {allowed_emojis.get(gtype)} emoji allowed for this match!")
                    return

                match_data["emoji_buffer"][user.id] = dice_obj.value
                match_data["last_roller"] = user.id

                if len(match_data["emoji_buffer"]) == 2:
                    p1, p2 = players
                    v1, v2 = match_data["emoji_buffer"].get(p1), match_data["emoji_buffer"].get(p2)
                    text, winner_id, extra_info = "", None, ""

                    if gtype == "dice":
                        text += f"{match_data['usernames'][p1]} rolled {v1}, {match_data['usernames'][p2]} rolled {v2}.\n"
                        if v1 > v2: winner_id = p1
                        elif v2 > v1: winner_id = p2
                        else: extra_info = "🤝 It's a tie! No points this round."
                    elif gtype == "darts":
                        dist1, dist2 = abs(6 - v1), abs(6 - v2)
                        text += f"{match_data['usernames'][p1]}: {v1}, {match_data['usernames'][p2]}: {v2}.\n"
                        if dist1 < dist2: winner_id = p1
                        elif dist2 < dist1: winner_id = p2
                        else: extra_info = "🤝 Both hit the same distance! No points."
                    elif gtype == "goal":
                        p1_scored, p2_scored = v1 >= 4, v2 >= 4
                        text += f"{match_data['usernames'][p1]}: {'GOAL!' if p1_scored else 'No Goal'}, {match_data['usernames'][p2]}: {'GOAL!' if p2_scored else 'No Goal'}\n"
                        if p1_scored and not p2_scored: winner_id = p1
                        elif p2_scored and not p1_scored: winner_id = p2
                        elif p1_scored and p2_scored:
                            if v1 > v2: winner_id = p1
                            elif v2 > v1: winner_id = p2
                            else: extra_info = "🤝 Both scored with same power! No winner."
                        else: extra_info = "🤝 No winner this round."
                    elif gtype == "bowl":
                        text += f"{match_data['usernames'][p1]}: {v1} pins, {match_data['usernames'][p2]}: {v2} pins.\n"
                        if v1 > v2: winner_id = p1
                        elif v2 > v1: winner_id = p2
                        else: extra_info = "🤝 Tie!"

                    if winner_id:
                        match_data["points"][winner_id] += 1
                        text += f"🎉 {match_data['usernames'][winner_id]} wins this round!"
                    else:
                        text += extra_info

                    text += f"\n\nScore: {match_data['usernames'][p1]} {match_data['points'][p1]} - {match_data['points'][p2]} {match_data['points'][p2]}"

                    target = match_data["target_points"]
                    final_winner = None
                    if match_data["points"][p1] >= target: final_winner = p1
                    elif match_data["points"][p2] >= target: final_winner = p2

                    if final_winner:
                        loser_id = p2 if final_winner == p1 else p1
                        match_data.update({"status": "completed", "winner_id": final_winner})
                        user_wallets[final_winner] += match_data["bet_amount"] * 2
                        update_stats_on_bet(final_winner, match_id, match_data["bet_amount"], True, pvp_win=True, context=context)
                        update_stats_on_bet(loser_id, match_id, match_data["bet_amount"], False, context=context)
                        update_pnl(final_winner); update_pnl(loser_id)
                        save_user_data(final_winner); save_user_data(loser_id)
                        text += f"\n\n🏆 <b>{match_data['usernames'][final_winner]} wins the match and earns ${match_data['bet_amount']*2:.2f}!</b>"
                        # Unpin the message
                        if 'pinned_message_id' in match_data:
                            try: await context.bot.unpin_chat_message(chat_id, match_data['pinned_message_id'])
                            except Exception as e: logging.warning(f"Could not unpin message for match {match_id}: {e}")
                    else:
                        match_data["last_roller"] = None
                        text += f"\n\nNext turn: {match_data['usernames'][p2 if user.id == p1 else p1]} ({allowed_emojis[gtype]} emoji)."

                    match_data["emoji_buffer"] = {}
                    await asyncio.sleep(1.5)
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
                else:
                    other_id = [pid for pid in players if pid != user.id][0]
                    await asyncio.sleep(1.5)
                    await update.message.reply_text(f"Waiting for {match_data['usernames'][other_id]} to play.")
                return

# --- Clear user funds (owner only) ---
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the bot owner can use this command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)
    keyboard = [[InlineKeyboardButton("✅ Yes, clear all funds", callback_data="clear_confirm_yes"), InlineKeyboardButton("❌ No, cancel", callback_data="clear_confirm_no")]]
    await update.message.reply_text("⚠️ WARNING: This will reset all user balances to zero!\n\nAre you absolutely sure?", reply_markup=InlineKeyboardMarkup(keyboard))

async def clearall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the bot owner can use this command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)
    keyboard = [[InlineKeyboardButton("✅ Yes, erase ALL data", callback_data="clearall_confirm_yes"), InlineKeyboardButton("❌ No, cancel", callback_data="clearall_confirm_no")]]
    await update.message.reply_text("⚠️ EXTREME WARNING ⚠️\n\nThis will completely erase ALL user data, including all settings. This action is IRREVERSIBLE!\n\nAre you absolutely sure?", reply_markup=InlineKeyboardMarkup(keyboard))

async def clear_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global user_wallets, user_stats, username_to_userid, escrow_deals, game_sessions, group_settings, bot_settings, gift_codes, recovery_data
    query = update.callback_query
    await query.answer()
    user = query.from_user
    if user.id != BOT_OWNER_ID:
        await query.answer("Only the owner can confirm this action.", show_alert=True)
        return

    if query.data == "clear_confirm_yes":
        users_affected = 0
        for user_id in list(user_wallets.keys()):
            if user_wallets[user_id] > 0:
                user_wallets[user_id] = 0
                if user_id in user_stats:
                    update_pnl(user_id)
                    save_user_data(user_id)
                users_affected += 1
        await query.edit_message_text(f"✅ Done! Reset balances to zero for {users_affected} users.")
    elif query.data == "clearall_confirm_yes":
        backup_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, f"backup_all_data_{backup_time}.json")
        try:
            state_to_backup = {
                "wallets": user_wallets, "stats": user_stats, "usernames": username_to_userid,
                "escrow_deals": escrow_deals, "game_sessions": game_sessions, "group_settings": group_settings,
                "bot_settings": bot_settings, "recovery_data": recovery_data, "gift_codes": gift_codes
            }
            with open(backup_file, "w") as f:
                json.dump(state_to_backup, f, default=str, indent=2)
        except Exception as e:
            logging.error(f"Failed to create backup before clearing data: {e}")

        old_count = len(user_stats)
        # Clear all in-memory data
        user_wallets.clear(); user_stats.clear(); username_to_userid.clear(); escrow_deals.clear(); game_sessions.clear(); group_settings.clear(); recovery_data.clear(); gift_codes.clear()
        # Reset bot settings to default
        bot_settings = {
            "daily_bonus_amount": 0.50, "maintenance_mode": False, "banned_users": [],
            "tempbanned_users": [], "house_balance": 100_000_000_000_000.0, "game_limits": {},
            "withdrawals_enabled": True, "deposits_enabled": True
        }
        # Delete all data files
        for d in [DATA_DIR, ESCROW_DIR, GROUPS_DIR, RECOVERY_DIR, GIFT_CODE_DIR]:
            try:
                for fname in os.listdir(d):
                    if fname.endswith(".json"): os.remove(os.path.join(d, fname))
            except Exception as e: logging.error(f"Error deleting files in {d}: {e}")
        # Delete the main state file
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

        await query.edit_message_text(f"✅ All user data and settings cleared! Removed data for {old_count} users.\nA backup was saved to {backup_file}")
    else:
        await query.edit_message_text("Operation cancelled. No changes were made.")

# --- Tip, Help, Cashout, Cancel Handlers ---
@check_maintenance
async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    message_text = update.message.text.strip().split()
    target_user_id = None
    target_username = None

    if update.message.reply_to_message and len(message_text) == 2:
        try:
            tip_amount = float(message_text[1])
            target_user_id = update.message.reply_to_message.from_user.id
            target_username = update.message.reply_to_message.from_user.username
        except (ValueError, IndexError):
             await update.message.reply_text("Usage (reply to a message): /tip amount")
             return
    elif len(message_text) == 3:
        try:
            target_username_str = normalize_username(message_text[1])
            tip_amount = float(message_text[2])
            target_user_id = username_to_userid.get(target_username_str)
            if not target_user_id:
                try:
                    chat = await context.bot.get_chat(target_username_str)
                    target_user_id = chat.id
                    target_username = chat.username
                except Exception:
                    await update.message.reply_text(f"User {target_username_str} not found.")
                    return
            else:
                target_username = user_stats[target_user_id]['userinfo']['username']
        except (ValueError, IndexError):
            await update.message.reply_text("Usage: /tip @username amount")
            return
    else:
        await update.message.reply_text("Usage: /tip @username amount OR reply to a message with /tip amount")
        return

    if not target_user_id:
        await update.message.reply_text("Could not find the target user.")
        return

    is_owner = user.id == BOT_OWNER_ID
    if user.id == target_user_id and not is_owner:
        await update.message.reply_text("You cannot tip yourself.")
        return
    if tip_amount <= 0:
        await update.message.reply_text("Tip amount must be positive.")
        return

    if not is_owner and user_wallets.get(user.id, 0.0) < tip_amount:
        await update.message.reply_text("You don't have enough balance to tip this amount.")
        return

    if not is_owner: user_wallets[user.id] -= tip_amount
    await ensure_user_in_wallets(target_user_id, target_username, context=context)
    user_wallets[target_user_id] = user_wallets.get(target_user_id, 0.0) + tip_amount

    update_stats_on_tip_sent(user.id, tip_amount)
    update_stats_on_tip_received(target_user_id, tip_amount)
    update_pnl(user.id); update_pnl(target_user_id)
    save_user_data(user.id); save_user_data(target_user_id)

    tipped_user_mention = f"@{target_username}" if target_username else f"user (ID: {target_user_id})"
    await update.message.reply_text(f"You have successfully tipped {tipped_user_mention} ${tip_amount:.2f}.", parse_mode=ParseMode.HTML)
    try:
        await context.bot.send_message(chat_id=target_user_id, text=f"You have received a tip of ${tip_amount:.2f} from {user.mention_html()}!", parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.warning(f"Failed to send tip notification to {target_user_id}: {e}")

@check_maintenance
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    is_owner = user.id == BOT_OWNER_ID

    help_text = (
        "🎲 <b>Telegram Gambling & Escrow Bot</b> 🎲\n\n"
        "<b>🤖 AI Assistant:</b>\n"
        "• <code>/ai &lt;question&gt;</code> — Ask the AI anything (default: g4f).\n"
        "• <code>/p &lt;SYMBOL&gt;</code> — Get crypto price from MEXC (e.g., /p BTC).\n"
        "• Reply to a message with <code>/ai</code> to discuss it.\n\n"
        "<b>Solo Games:</b>\n"
        "• <b>Blackjack</b>: <code>/bj amount</code>\n"
        "• <b>Coin Flip</b>: <code>/flip amount</code>\n"
        "• <b>Roulette</b>: <code>/roul amount choice</code>\n"
        "• <b>Dice Roll</b>: <code>/dr amount choice</code>\n"
        "• <b>Tower</b>: Use <code>/tr</code> or the Games menu\n"
        "• <b>Slots</b>: <code>/sl amount</code>\n"
        "• <b>Mines</b>: Use <code>/mines</code> or the Games menu\n"
        "• <b>Predict</b>: <code>/predict amount up/down</code>\n"
        "• <b>Limbo</b>: <code>/lb amount multiplier</code>\n" # NEW
        "• <b>RPS</b>: <code>/rps amount</code>\n" # NEW
        "💡 You can use 'all' instead of an amount to bet your entire balance!\n\n"
        "<b>PvP & PvB Games:</b>\n"
        "• <b>Tic-Tac-Toe</b>: <code>/ttt @user amount</code> or <code>/ttt amount</code>\n" # NEW
        "• <b>Dice, Darts, Football, Bowling</b>\n"
        "<b>PvP & PvB Games:</b>\n"
        "• <b>Dice, Darts, Football, Bowling</b>\n"
        "  - vs Player: <code>/dice @user amount ftX</code>\n"
        "  - vs Bot: Use <code>/games</code> menu\n\n"
        "<b>Wallet & Social:</b>\n"
        "• <code>/deposit</code> or <code>/bal</code>\n"
        "• <code>/tip @user amount</code> or reply to a message\n"
        "• <code>/rain amount N</code> — Rain on N users\n"
        "• <code>/stats</code>, <code>/leaderboard</code>, <code>/leaderboardrf</code>\n\n"
        "<b>🎁 Bonuses:</b>\n"
        "• <code>/daily</code> — Claim your daily bonus!\n"
        "• <code>/weekly</code> — Claim weekly wager bonus (0.5%).\n"
        "• <code>/monthly</code> — Claim monthly wager bonus (0.3%).\n"
        "• <code>/rk</code> — Claim your instant rakeback (0.01%).\n"
        "• <code>/claim &lt;code&gt;</code> — Claim a gift code.\n\n"
        "<b>🛡️ History & Info:</b>\n"
        "• <code>/escrow</code>, <code>/deals</code>, <code>/matches</code>\n"
        "• <code>/active</code> — View your active games\n"
        "• <code>/info &lt;id&gt;</code> — Get details of any game/deal\n"
        "• <code>/continue &lt;id&gt;</code> — Resume an active game\n\n"
        "<b>⚙️ Other:</b>\n"
        "• <code>/referral</code>, <code>/achievements</code>\n"
        "• <code>/language</code> — Change bot language (en/es)\n"
        "• <code>/recover</code> — Start the account recovery process\n\n"
        "<b>Group Management:</b>\n"
        "• Reply with <code>/kick</code>, <code>/mute</code>, <code>/promote</code>, <code>/pin</code>, <code>/purge</code>, <code>/report</code>, <code>/translate</code>\n"
        "• <code>/lockall</code>, <code>/unlockall</code>\n"
        "• <code>/settings</code> — Configure the bot for your group (group admins only)\n\n"
        "<b>Minimum bet: ${:.2f}</b>\nContact @jashanxjagy for support.".format(MIN_BALANCE)
    )

    owner_help = (
        "\n\n👑 <b>Owner Commands:</b>\n"
        "• <code>/admin</code> — Open the admin dashboard.\n"
        "• <code>/setbal @user amount</code> — Manually set a user's balance.\n"
        "• <code>/user @username</code> — Get detailed user info.\n"
        "• <code>/users</code> — View all user stats (paginated)\n"
        "• <code>/activeall</code> — View all active games on the bot (paginated).\n"
        "• <code>/reset @username</code> — Reset a user's recovery token.\n"
        "• <code>/cancel &lt;id&gt;</code> — Cancel a match or deal\n"
        "• <code>/cancelall</code> — Cancel all active matches\n"
        "• <code>/stop</code> & <code>/resume</code> — Pause/resume new games\n"
        "• <code>/clear</code> — Reset all user balances to 0\n"
        "• <code>/clearall</code> — ⚠️ Erase all user data\n"
        "• <code>/he</code> (all escrow), <code>/hc</code> (all games) — History cmds\n"
        "• <code>/fundgas &lt;addr&gt; &lt;amt&gt;</code> — Fund a deposit address\n"
        "• <code>/export</code> — Export all user data as a JSON file."
    )

    if is_owner:
        help_text += owner_help

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]]) if from_callback else None

    if from_callback:
        await update.callback_query.edit_message_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
    else:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)

@check_maintenance
async def cashout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await ensure_user_in_wallets(user_id, update.effective_user.username, context=context)

    # Find active, cashout-able games for the user
    active_games = [g for g in game_sessions.values() if g.get('user_id') == user_id and g.get('status') == 'active' and g.get('game_type') in ['mines', 'tower', 'coin_flip']]

    if not active_games:
        await update.message.reply_text("No active games to cash out from. Use `/continue <id>` to resume a game.")
        return

    # For simplicity, cashout the most recent one. A better implementation might list them.
    game = sorted(active_games, key=lambda g: g['timestamp'], reverse=True)[0]
    game_id = game['id']

    # Create a fake query object to pass to the callback handlers since they expect one
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.message = message
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, *args, **kwargs):
            await self.message.reply_text(*args, **kwargs)

    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(update.effective_user, update.message)})()

    if game['game_type'] == 'mines':
        fake_update.callback_query.data = f'mines_cashout_{game_id}'
        await mines_pick_callback(fake_update, context)
    elif game['game_type'] == 'tower':
        fake_update.callback_query.data = f'tower_cashout_{game_id}'
        await tower_callback(fake_update, context)
    elif game['game_type'] == 'coin_flip':
        fake_update.callback_query.data = f'flip_cashout_{game_id}'
        await coin_flip_callback(fake_update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID:
        await update.message.reply_text("Only the bot owner can use this command.")
        return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    message_text = update.message.text.strip().split()
    if len(message_text) != 2:
        await update.message.reply_text("Usage: /cancel <match_id | deal_id>")
        return
    item_id = message_text[1]

    if item_id in game_sessions:
        game_data = game_sessions[item_id]
        if game_data.get("status") != "active":
            await update.message.reply_text("This game is not active.")
            return

        game_data["status"] = "cancelled"

        # Refund players
        if 'players' in game_data: # PvP
            bet_amount = game_data["bet_amount"]
            for player_id in game_data['players']:
                user_wallets[player_id] += bet_amount
                save_user_data(player_id)
                try: await context.bot.send_message(player_id, f"Match {item_id} cancelled by owner. Bet of ${bet_amount:.2f} refunded.")
                except Exception as e: logging.warning(f"Could not notify player {player_id}: {e}")
        elif 'user_id' in game_data: # Solo
            player_id = game_data['user_id']
            bet_amount = game_data['bet_amount']
            user_wallets[player_id] += bet_amount
            save_user_data(player_id)
            try: await context.bot.send_message(player_id, f"Your game {item_id} was cancelled by the owner. Your bet of ${bet_amount:.2f} has been refunded.")
            except Exception as e: logging.warning(f"Could not notify player {player_id}: {e}")

        await update.message.reply_text(f"Game {item_id} cancelled. Bets refunded.")
        return

    if item_id in escrow_deals:
        deal = escrow_deals[item_id]
        if deal['status'] in ['completed', 'cancelled_by_owner', 'disputed']:
             await update.message.reply_text(f"Deal {item_id} is already finalized.")
             return
        deal['status'] = 'cancelled_by_owner'
        if deal.get('deposit_tx_hash'):
            await update.message.reply_text(f"Deal {item_id} cancelled. Manually refund ${deal['amount']:.2f} to seller @{deal['seller']['username']}.")
        else:
            await update.message.reply_text(f"Deal {item_id} cancelled. No funds were deposited.")
        save_escrow_deal(item_id)
        try:
            await context.bot.send_message(deal['seller']['id'], f"Your escrow deal {item_id} has been cancelled by the bot owner.")
            await context.bot.send_message(deal['buyer']['id'], f"Your escrow deal {item_id} has been cancelled by the bot owner.")
        except Exception as e: logging.warning(f"Could not notify users about deal cancellation: {e}")
        return
    await update.message.reply_text("No active match or deal found with that ID.")

# --- DICE INVITE HANDLER (accept/decline) ---
@check_maintenance
async def match_invite_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    match_id = data.split("_", 1)[1]
    match_data = game_sessions.get(match_id)
    if not match_data:
        await query.edit_message_text("Match not found or already cancelled.")
        return

    opponent_id = match_data["players"][1]
    if user_id != opponent_id:
        await query.answer("Only the challenged opponent can accept/decline this match.", show_alert=True)
        return
    if match_data.get("status") != "pending":
        await query.edit_message_text("This match has already been actioned.")
        return

    if data.startswith("accept_"):
        await ensure_user_in_wallets(user_id, query.from_user.username, context=context)
        if user_wallets.get(user_id, 0.0) < match_data["bet_amount"]:
            await query.edit_message_text("You don't have enough balance for this bet. Match cancelled.")
            match_data["status"] = "cancelled"
            return

        user_wallets[match_data["host_id"]] -= match_data["bet_amount"]
        user_wallets[opponent_id] -= match_data["bet_amount"]
        save_user_data(match_data["host_id"]); save_user_data(opponent_id)
        match_data.update({"status": "active"})
        
        await ensure_user_in_wallets(match_data["host_id"], context=context)
        await ensure_user_in_wallets(opponent_id, context=context)
        if 'game_sessions' not in user_stats[match_data["host_id"]]: user_stats[match_data["host_id"]]['game_sessions'] = []
        if 'game_sessions' not in user_stats[opponent_id]: user_stats[opponent_id]['game_sessions'] = []
        user_stats[match_data["host_id"]]['game_sessions'].append(match_id)
        user_stats[opponent_id]['game_sessions'].append(match_id)
        save_user_data(match_data["host_id"]); save_user_data(opponent_id)

        await query.edit_message_text(
            f"Match Accepted! Game starts now.\n<b>Match ID:</b> {match_id}", parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=match_data["chat_id"],
            text=f"🎮 <b>{match_data['game_type'].replace('pvp_','').capitalize()} Match {match_id} Started!</b>\n"
                 f"{match_data['usernames'][match_data['host_id']]} vs {match_data['usernames'][match_data['players'][1]]}\n"
                 f"First to {match_data['target_points']} points wins ${match_data['bet_amount']*2:.2f}!\n"
                 f"{match_data['usernames'][match_data['host_id']]}, it's your turn.",
            parse_mode=ParseMode.HTML
        )
    else: # Decline
        match_data.update({"status": "declined"})
        await query.edit_message_text("Match declined. The match is cancelled.")

# --- Deposit Command Handler ---
BNB_CONTRACT = "0xB8c77482e45F1F44dE1745F52C74426C631bDD52"
USDT_ERC20_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDT_BEP20_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
DEPOSIT_API_KEY = "PGPXGH4Z6GAM71J7K3IMYN7M3JMN7IIR6F"
DEPOSIT_TIMEOUT_SECONDS = 3600

MASTER_PRIVATE_KEY = "0bbaf8d35b64859555b1a6acc7909ac349bced46b2fcf2c8d616343fec138353"
CURRENT_ADDRESS_INDEX = 0
CENTRAL_WALLET_ADDRESS = "0xdda0e87f6c1344e07cfce9cefb12f3a286a0fb38"

BSC_NODES = ["https://bsc-dataseed.binance.org/", "https://bsc-dataseed1.binance.org/"]
ETH_NODE = "https://linea-mainnet.infura.io/v3/25cdeb5b655744f2b6d88c998e55eace"

def get_working_web3_bsc():
    for node in BSC_NODES:
        try:
            w3 = Web3(Web3.HTTPProvider(node))
            if w3.is_connected():
                logging.info(f"Connected to BSC node: {node}")
                return w3
        except Exception as e:
            logging.warning(f"Failed to connect to BSC node {node}: {e}")
    logging.error("Could not connect to any BSC node")
    return None

try:
    w3_bsc = get_working_web3_bsc()
    w3_eth = Web3(Web3.HTTPProvider(ETH_NODE))
    if w3_bsc and w3_bsc.is_connected(): logging.info("Successfully connected to BSC")
    else: logging.error("Failed to connect to BSC")
    if w3_eth and w3_eth.is_connected(): logging.info("Successfully connected to ETH")
    else: logging.error("Failed to connect to ETH")
except Exception as e:
    logging.error(f"Failed to initialize Web3 connections: {e}")
    w3_bsc = w3_eth = None

ERC20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"payable":true,"stateMutability":"payable","type":"fallback"},{"anonymous":false,"inputs":[{"indexed":true,"name":"owner","type":"address"},{"indexed":true,"name":"spender","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}]')

DEPOSIT_METHODS = {
    "bnb": {"name": "BNB (BEP20)", "blockchain": "bsc", "contract": BNB_CONTRACT, "decimals": 18, "explorer": "https://bscscan.com"},
    "usdt_bep": {"name": "USDT (BEP20)", "blockchain": "bsc", "contract": USDT_BEP20_CONTRACT, "decimals": 18, "explorer": "https://bscscan.com"},
    "usdt_erc": {"name": "USDT (ERC20)", "blockchain": "eth", "contract": USDT_ERC20_CONTRACT, "decimals": 6, "explorer": "https://etherscan.io"}
}

def get_next_address_index():
    global CURRENT_ADDRESS_INDEX
    CURRENT_ADDRESS_INDEX += 1
    return CURRENT_ADDRESS_INDEX

def generate_deposit_address_for_user(user_id: int, method: str):
    bip44_ctx = Bip44.FromPrivateKey(bytes.fromhex(MASTER_PRIVATE_KEY), Bip44Coins.ETHEREUM).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT)
    address_index = get_next_address_index()
    child_ctx = bip44_ctx.AddressIndex(address_index)
    return child_ctx.PublicKey().ToAddress(), address_index

def get_private_key_for_address_index(address_index):
    bip44_ctx = Bip44.FromPrivateKey(bytes.fromhex(MASTER_PRIVATE_KEY), Bip44Coins.ETHEREUM).Purpose().Coin().Account(0).Change(Bip44Changes.CHAIN_EXT)
    return bip44_ctx.AddressIndex(address_index).PrivateKey().Raw().ToHex()

async def sweep_funds(address, address_index, method):
    blockchain = DEPOSIT_METHODS[method]["blockchain"]
    contract = DEPOSIT_METHODS[method]["contract"]
    logging.info(f"Attempting to sweep funds: address={address}, method={method}")
    w3 = w3_bsc if blockchain == "bsc" else w3_eth
    if w3 is None:
        logging.error(f"Web3 connection not available for {blockchain}"); return None

    try: private_key = get_private_key_for_address_index(address_index)
    except Exception as e: logging.error(f"Failed to get pk for index {address_index}: {e}"); return None

    try:
        if method.startswith("usdt"):
            token_contract = w3.eth.contract(address=Web3.to_checksum_address(contract), abi=ERC20_ABI)
            token_balance = token_contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
            bnb_balance = w3.eth.get_balance(Web3.to_checksum_address(address))
            logging.info(f"{address} has {token_balance/(10**DEPOSIT_METHODS[method]['decimals'])} {method} and {bnb_balance/1e18} BNB")
            estimated_gas_cost = 100000 * w3.eth.gas_price
            if token_balance > 0 and bnb_balance >= estimated_gas_cost:
                txn = token_contract.functions.transfer(Web3.to_checksum_address(CENTRAL_WALLET_ADDRESS), token_balance).build_transaction({
                    'chainId': 56 if blockchain == "bsc" else 1, 'gas': 100000, 'gasPrice': w3.eth.gas_price, 'nonce': w3.eth.get_transaction_count(Web3.to_checksum_address(address))})
                signed_txn = w3.eth.account.sign_transaction(txn, private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                logging.info(f"Swept {token_balance/(10**DEPOSIT_METHODS[method]['decimals'])} {method} from {address}, tx: {tx_hash.hex()}")
                return tx_hash.hex()
            elif token_balance > 0: logging.warning(f"Insufficient BNB for gas at {address}")
        else: # Native coins
            balance = w3.eth.get_balance(Web3.to_checksum_address(address))
            if balance > 1000000:
                gas_cost = 21000 * w3.eth.gas_price
                amount_to_sweep = int(balance * 0.96)
                logging.info(f"{address} has {balance/1e18} BNB. Sweeping {amount_to_sweep/1e18} BNB (96%)")
                if amount_to_sweep > gas_cost:
                    final_amount = amount_to_sweep - gas_cost
                    txn = {'nonce': w3.eth.get_transaction_count(Web3.to_checksum_address(address)), 'gasPrice': w3.eth.gas_price, 'gas': 21000,
                           'to': Web3.to_checksum_address(CENTRAL_WALLET_ADDRESS), 'value': final_amount, 'chainId': 56 if blockchain == "bsc" else 1}
                    signed_txn = w3.eth.account.sign_transaction(txn, private_key)
                    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                    logging.info(f"Swept {final_amount/1e18} BNB from {address}, tx: {tx_hash.hex()}")
                    return tx_hash.hex()
    except Exception as e: logging.error(f"Error sweeping funds from {address}: {e}", exc_info=True)
    return None

async def monitor_deposit(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    address, method, address_index, user_id = job.data["address"], job.data["method"], job.data.get("address_index"), job.user_id
    logging.info(f"Monitoring deposits for user {user_id}, address {address}, method {method}")

    if user_id not in user_deposit_sessions or not user_deposit_sessions[user_id]["active"]:
        logging.info(f"Deposit session for {user_id} is no longer active, removing job"); job.schedule_removal(); return

    blockchain, contract, decimals = DEPOSIT_METHODS[method]["blockchain"], DEPOSIT_METHODS[method]["contract"], DEPOSIT_METHODS[method]["decimals"]

    try:
        if method.startswith("usdt"):
            url = f"https://api.{'etherscan.io' if blockchain == 'eth' else 'bscscan.com'}/api?module=account&action=tokentx&contractaddress={contract}&address={address}&sort=desc&apikey={DEPOSIT_API_KEY}"
        else:
            url = f"https://api.{'bscscan.com' if blockchain == 'bsc' else 'etherscan.io'}/api?module=account&action=txlist&address={address}&sort=desc&apikey={DEPOSIT_API_KEY}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=30.0)
            data = response.json()

        if data["status"] == "1" and data["result"]:
            txs = data["result"]
            incoming_txs = [tx for tx in txs if tx["to"].lower() == address.lower() and int(tx.get("confirmations", 0)) >= 2]

            if incoming_txs:
                logging.info(f"Found {len(incoming_txs)} incoming transactions for address {address}")
                for tx in incoming_txs:
                    tx_hash = tx["hash"]
                    if "processed_txs" not in user_deposit_sessions[user_id]: user_deposit_sessions[user_id]["processed_txs"] = []
                    if tx_hash in user_deposit_sessions[user_id]["processed_txs"]: continue

                    usd_value = 0
                    if method == "bnb":
                        try:
                            price_url = "https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT"
                            price_response = await client.get(price_url, timeout=10.0)
                            bnb_price = float(price_response.json().get("price", 300))
                        except Exception as e: logging.error(f"Error fetching BNB price: {e}"); bnb_price = 300
                        amount_bnb = int(tx["value"]) / (10 ** decimals)
                        usd_value = amount_bnb * bnb_price
                    elif method.startswith("usdt"):
                        usd_value = int(tx["value"]) / (10 ** decimals)

                    if usd_value >= 0.1:
                        await ensure_user_in_wallets(user_id, context=context)
                        user_wallets[user_id] += usd_value
                        update_stats_on_deposit(user_id, usd_value, tx_hash, method)
                        update_pnl(user_id)
                        save_user_data(user_id)
                        user_deposit_sessions[user_id]["processed_txs"].append(tx_hash)
                        await context.bot.send_message(chat_id=user_id, text=f"💰 Deposit confirmed! ${usd_value:.2f} credited. New balance: ${user_wallets.get(user_id, 0.0):.2f}")
                        logging.info(f"User {user_id} deposited ${usd_value:.2f} via {method}, tx: {tx_hash}")
                        await asyncio.sleep(5)
                        if address_index is not None:
                            sweep_tx = await sweep_funds(address, address_index, method)
                            if sweep_tx: logging.info(f"Successfully swept funds from {address}, tx: {sweep_tx}")
                            else: logging.warning(f"Could not sweep funds from {address}")
                    else: logging.info(f"Deposit too small (${usd_value:.2f})")
        if address_index is not None and random.random() < 0.20:
            sweep_tx = await sweep_funds(address, address_index, method)
            if sweep_tx: logging.info(f"Successfully swept funds from {address} in periodic check, tx: {sweep_tx}")
    except Exception as e: logging.error(f"Error monitoring deposit for {user_id}: {e}", exc_info=True)

async def check_addresses_for_gas(context: ContextTypes.DEFAULT_TYPE):
    logging.info("Checking deposit addresses for insufficient gas")
    addresses_to_check = [{'user_id': uid, **s} for uid, s in user_deposit_sessions.items() if s.get("active") and s.get("method", "").startswith("usdt")]
    if not addresses_to_check: logging.info("No active token deposit addresses to check"); return

    for addr_info in addresses_to_check:
        address, method, user_id = addr_info["address"], addr_info["method"], addr_info["user_id"]
        if not w3_bsc: logging.error("Web3 connection not available"); continue
        try:
            token_contract = w3_bsc.eth.contract(address=Web3.to_checksum_address(DEPOSIT_METHODS[method]["contract"]), abi=ERC20_ABI)
            token_balance = token_contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
            bnb_balance = w3_bsc.eth.get_balance(Web3.to_checksum_address(address))
            estimated_gas_cost = 100000 * w3_bsc.eth.gas_price

            if token_balance > 0 and bnb_balance < estimated_gas_cost:
                token_amount, bnb_amount, needed_bnb = token_balance / (10**DEPOSIT_METHODS[method]["decimals"]), bnb_balance / 1e18, estimated_gas_cost / 1e18
                logging.warning(f"Address {address} has {token_amount} {method} but only {bnb_amount} BNB (needs {needed_bnb} BNB)")
                if BOT_OWNER_ID:
                    try: await context.bot.send_message(chat_id=BOT_OWNER_ID, text=f"⚠️ Gas Alert: {address} has {token_amount} {method} but needs {needed_bnb} BNB for gas.")
                    except Exception as e: logging.error(f"Failed to send gas alert to admin: {e}")
        except Exception as e: logging.error(f"Error checking address {address} for gas: {e}")

async def fund_gas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    args = update.message.text.strip().split()
    if len(args) != 3: await update.message.reply_text("Usage: /fundgas address amount_bnb"); return
    target_address, amount_bnb_str = args[1], args[2]
    try: amount_bnb = float(amount_bnb_str)
    except ValueError: await update.message.reply_text("Invalid amount."); return
    if not w3_bsc: await update.message.reply_text("Web3 connection not available."); return
    await update.message.reply_text(f"This is a manual operation for security.\nPlease send {amount_bnb} BNB from your central wallet to: {target_address}")

@check_maintenance
async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if update.effective_chat.type != "private":
        await update.message.reply_text("Please use /deposit in bot DM only.")
        return
    user_id = update.effective_user.id
    session = user_deposit_sessions.get(user_id)
    if session:
        expiry_time = datetime.fromisoformat(session['expiry'])
        if expiry_time > datetime.now(timezone.utc):
            remaining = int((expiry_time - datetime.now(timezone.utc)).total_seconds())
            await update.message.reply_text(f"You have a pending deposit session!\nAddress: <code>{session['address']}</code>\nExpires in: {remaining // 60}m {remaining % 60}s", parse_mode=ParseMode.HTML)
            return

    keyboard = [[InlineKeyboardButton("BNB (BEP20)", callback_data="deposit_bnb")], [InlineKeyboardButton("USDT (BEP20)", callback_data="deposit_usdt_bep")], [InlineKeyboardButton("USDT (ERC20)", callback_data="deposit_usdt_erc")]]
    await update.message.reply_text("Select deposit method:\n\n⚠️ You will receive a one-time address, valid for 1 hour.", reply_markup=InlineKeyboardMarkup(keyboard))

@check_maintenance
async def deposit_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user, method = query.from_user, query.data.replace("deposit_", "")
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if method not in DEPOSIT_METHODS: await query.answer("Invalid deposit method.", show_alert=True); return
    try: address, address_index = generate_deposit_address_for_user(user.id, method)
    except Exception as e: await query.edit_message_text(str(e)); return

    now, expiry = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(seconds=DEPOSIT_TIMEOUT_SECONDS)
    user_deposit_sessions[user.id] = {"address": address, "address_index": address_index, "method": method, "start_time": str(now), "expiry": str(expiry), "active": True, "processed_txs": []}

    os.makedirs("deposit_sessions", exist_ok=True)
    with open(f"deposit_sessions/{user.id}_{method}.json", "w") as f: json.dump(user_deposit_sessions[user.id], f)

    await query.edit_message_text(f"Your one-time deposit address (1 hour):\n<code>{address}</code>\nNetwork: {DEPOSIT_METHODS[method]['name']}\n\n⚠️ Do NOT send after expiry.", parse_mode=ParseMode.HTML)
    job_data = {"address": address, "method": method, "address_index": address_index}
    context.job_queue.run_repeating(monitor_deposit, interval=30, first=10, data=job_data, name=f"deposit_{user.id}", user_id=user.id)
    context.job_queue.run_once(expire_deposit_session, when=DEPOSIT_TIMEOUT_SECONDS, data={"user_id": user.id}, name=f"expire_{user.id}")

async def expire_deposit_session(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    if user_id in user_deposit_sessions:
        session = user_deposit_sessions[user_id]
        try:
            if "address_index" in session:
                sweep_tx = await sweep_funds(session["address"], session["address_index"], session["method"])
                if sweep_tx: logging.info(f"Final sweep for user {user_id}, tx: {sweep_tx}")
        except Exception as e: logging.error(f"Error during final sweep for user {user_id}: {e}")
        del user_deposit_sessions[user_id]

        session_file = f"deposit_sessions/{user_id}_{session.get('method', '')}.json"
        if os.path.exists(session_file): os.remove(session_file)

        for job in context.job_queue.get_jobs_by_name(f"deposit_{user_id}"): job.schedule_removal()
        try: await context.bot.send_message(chat_id=user_id, text="⏰ Your deposit session has expired.")
        except Exception as e: logging.error(f"Failed to notify user {user_id} about expiry: {e}")

# --- ESCROW SYSTEM ---
@check_maintenance
async def escrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not all([ESCROW_DEPOSIT_ADDRESS, ESCROW_WALLET_PRIVATE_KEY]):
        error_msg = "Escrow system is not configured by the owner yet."
        if from_callback: await update.callback_query.edit_message_text(error_msg)
        else: await update.message.reply_text(error_msg)
        return

    context.user_data['escrow_step'] = 'ask_amount'
    context.user_data['escrow_data'] = {'creator_id': user.id, 'creator_username': user.username}
    text = "🛡️ <b>New Escrow Deal</b>\n\nPlease enter the deal amount in USDT (BEP20)."
    keyboard = [[InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]
    if from_callback:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_maintenance
async def handle_escrow_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    step = context.user_data.get('escrow_step')
    deal_data = context.user_data.get('escrow_data', {})
    cancel_button = [[InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]

    if step == 'ask_amount':
        try:
            amount = float(update.message.text)
            if amount <= 0: raise ValueError
            deal_data['amount'] = amount
            context.user_data['escrow_step'] = 'ask_role'
            keyboard = [[InlineKeyboardButton("I am the Seller", callback_data="escrow_role_seller"), InlineKeyboardButton("I am the Buyer", callback_data="escrow_role_buyer")],
                        [InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]
            await update.message.reply_text(f"Amount set to ${amount:.2f} USDT.\nPlease select your role:", reply_markup=InlineKeyboardMarkup(keyboard))
        except (ValueError, TypeError):
            await update.message.reply_text("Invalid amount. Please enter a positive number.", reply_markup=InlineKeyboardMarkup(cancel_button))
            return

    elif step == 'ask_details':
        deal_data['details'] = update.message.text
        # REMOVED: ask_partner_method step. Forcing link creation.
        await create_and_finalize_escrow_deal(update, context, by_link=True)

    elif step == 'ask_withdrawal_address':
        address = update.message.text
        deal_id = context.user_data.pop('escrow_withdrawal_deal_id')
        if not Web3.is_address(address):
            await update.message.reply_text("That is not a valid BEP-20 address. Please try again.")
            context.user_data['escrow_withdrawal_deal_id'] = deal_id
            return
        escrow_deals[deal_id]['buyer']['withdrawal_address'] = address
        context.user_data.pop('escrow_step', None)
        await release_escrow_funds(update, context, deal_id)

@check_maintenance
async def escrow_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user, data = query.from_user, query.data.split('_')
    action = data[1]
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if action == 'role':
        role = data[2]
        context.user_data['escrow_data']['creator_role'] = role
        context.user_data['escrow_data']['partner_role'] = 'Buyer' if role == 'seller' else 'Seller'
        context.user_data['escrow_step'] = 'ask_details'
        cancel_button = [[InlineKeyboardButton("Cancel", callback_data="escrow_action_cancel_setup")]]
        await query.edit_message_text("Role selected. Now, please provide the deal details (e.g., 'Sale of item X').", reply_markup=InlineKeyboardMarkup(cancel_button))

    # REMOVED: partner action, as we now force link creation.

    elif action == 'confirm':
        deal_id, decision = data[2], data[3]
        deal = escrow_deals.get(deal_id)
        if not deal or (user.id != deal.get('buyer', {}).get('id') and user.id != deal.get('seller', {}).get('id')):
            await query.edit_message_text("This deal is not for you or has expired.")
            return
        if user.id == deal.get('creator_id'):
            await query.answer("Waiting for the other party to respond.", show_alert=True); return

        if decision == 'accept':
            deal['status'] = 'accepted_awaiting_deposit'
            save_escrow_deal(deal_id)
            seller_id, buyer_id = deal['seller']['id'], deal['buyer']['id']
            await query.edit_message_text(f"✅ You accepted the deal. Seller will now be prompted to deposit ${deal['amount']:.2f} USDT.")
            deposit_text = (f"✅ The other party accepted the deal!\n\n<b>Deal ID:</b> <code>{deal_id}</code>\n"
                            f"Please deposit exactly <code>{deal['amount']}</code> USDT (BEP20) to:\n<code>{ESCROW_DEPOSIT_ADDRESS}</code>\n\n"
                            f"⚠️ Send from your own wallet (NOT from an exchange). Have enough BNB for gas.")
            await context.bot.send_message(chat_id=seller_id, text=deposit_text, parse_mode='HTML')
            context.job_queue.run_repeating(monitor_escrow_deposit, interval=20, first=10, data={'deal_id': deal_id}, name=f"escrow_monitor_{deal_id}")
        else: # Decline
            deal['status'] = 'declined_by_partner'; save_escrow_deal(deal_id)
            await query.edit_message_text("You have declined the deal. It has been cancelled.")
            await context.bot.send_message(chat_id=deal['creator_id'], text=f"The other party has declined your escrow deal ({deal_id}).")

    elif action == 'action':
        if data[2] == "cancel" and data[3] == "setup":
             context.user_data.clear()
             await query.edit_message_text("Escrow setup cancelled.")
             await start_command_inline(query, context)
             return

        deal_id, decision = data[2], data[3]
        deal = escrow_deals.get(deal_id)
        if not deal or user.id not in [deal['seller']['id'], deal['buyer']['id']]: return

        if decision == 'release':
            if user.id != deal['seller']['id']: await query.answer("Only the seller can release funds.", show_alert=True); return
            if deal['status'] != 'funds_secured': await query.answer("Funds are not in a releasable state.", show_alert=True); return
            keyboard = [[InlineKeyboardButton("✅ Yes, Release Funds", callback_data=f"escrow_action_{deal_id}_releaseconfirm"), InlineKeyboardButton("❌ No, Cancel", callback_data=f"escrow_action_{deal_id}_releasecancel")]]
            await query.edit_message_text("Are you sure you want to release the funds to the buyer? This is irreversible.", reply_markup=InlineKeyboardMarkup(keyboard))
        elif decision == 'releaseconfirm':
            if user.id != deal['seller']['id']: return
            await query.edit_message_text("Action confirmed. Asking buyer for their withdrawal address.")
            context.user_data['escrow_step'] = 'ask_withdrawal_address'
            context.user_data['escrow_withdrawal_deal_id'] = deal_id
            await context.bot.send_message(chat_id=deal['buyer']['id'], text="The seller released the funds! Please provide your BEP-20 (BSC) wallet address to receive payment.")
        elif decision == 'releasecancel': await query.edit_message_text("Release cancelled.")
        elif decision == 'dispute':
            deal['status'] = 'disputed'; save_escrow_deal(deal_id)
            dispute_text = f"🚨 A dispute has been opened for deal <code>{deal_id}</code>. Contact @jashanxjagy for assistance."
            await query.edit_message_text(dispute_text, parse_mode="HTML")
            other_party_id = deal['buyer']['id'] if user.id == deal['seller']['id'] else deal['seller']['id']
            await context.bot.send_message(chat_id=other_party_id, text=dispute_text, parse_mode="HTML")
            await context.bot.send_message(BOT_OWNER_ID, text=f"New dispute for deal {deal_id}.")

async def create_and_finalize_escrow_deal(update: Update, context: ContextTypes.DEFAULT_TYPE, by_link=False):
    user = update.effective_user
    deal_data = context.user_data.get('escrow_data', {})
    if deal_data['creator_role'] == 'seller':
        deal_data['seller'] = {'id': user.id, 'username': user.username}
        deal_data['buyer'] = {'id': None, 'username': None} # Partner joins via link
    else:
        deal_data['buyer'] = {'id': user.id, 'username': user.username}
        deal_data['seller'] = {'id': None, 'username': None} # Partner joins via link

    deal_id = generate_unique_id("ESC")
    deal_data.update({'id': deal_id, 'status': 'pending_confirmation', 'timestamp': str(datetime.now(timezone.utc))})
    escrow_deals[deal_id] = deal_data
    save_escrow_deal(deal_id)

    await ensure_user_in_wallets(user.id, user.username, context=context)
    user_stats[user.id]['escrow_deals'].append(deal_id)
    save_user_data(user.id)

    context.user_data.pop('escrow_step', None); context.user_data.pop('escrow_data', None)

    buyer_username = deal_data.get('buyer', {}).get('username') or "TBD (via link)"
    seller_username = deal_data.get('seller', {}).get('username') or "TBD (via link)"
    deal_summary = (f"🛡️ <b>New Escrow Deal Created</b>\n\n<b>Deal ID:</b> <code>{deal_id}</code>\n"
                    f"<b>Amount:</b> ${deal_data['amount']:.2f} USDT\n<b>Seller:</b> @{seller_username}\n"
                    f"<b>Buyer:</b> @{buyer_username}\n<b>Details:</b> {deal_data['details']}")

    bot_username = (await context.bot.get_me()).username
    deal_link = f"https://t.me/{bot_username}?start=escrow_{deal_id}"

    reply_target = update.callback_query.message if update.callback_query else update.message
    await reply_target.reply_text(f"{deal_summary}\n\nShare this link with the other party to join:\n<code>{deal_link}</code>", parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def handle_escrow_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE, deal_id: str):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    deal = escrow_deals.get(deal_id)
    if not deal: await update.message.reply_text("This escrow deal link is invalid or has expired."); return

    is_joinable = (deal['creator_role'] == 'seller' and deal.get('buyer', {}).get('id') is None) or \
                  (deal['creator_role'] == 'buyer' and deal.get('seller', {}).get('id') is None)
    if not is_joinable or deal['status'] != 'pending_confirmation':
        await update.message.reply_text("This deal has already been accepted or is no longer valid."); return
    if user.id == deal['creator_id']:
        await update.message.reply_text("You cannot accept your own deal. Share the link with the other party."); return

    if deal['creator_role'] == 'seller': deal['buyer'] = {'id': user.id, 'username': user.username}
    else: deal['seller'] = {'id': user.id, 'username': user.username}
    user_stats[user.id]['escrow_deals'].append(deal_id)
    save_user_data(user.id)
    save_escrow_deal(deal_id)

    deal_summary = (f"🛡️ <b>You are joining an Escrow Deal</b>\n\n<b>Deal ID:</b> <code>{deal_id}</code>\n"
                    f"<b>Amount:</b> ${deal['amount']:.2f} USDT\n<b>Seller:</b> @{deal['seller']['username']}\n"
                    f"<b>Buyer:</b> @{deal['buyer']['username']}\n<b>Details:</b> {deal['details']}")
    keyboard = [[InlineKeyboardButton("✅ Accept Deal", callback_data=f"escrow_confirm_{deal_id}_accept"), InlineKeyboardButton("❌ Decline Deal", callback_data=f"escrow_confirm_{deal_id}_decline")]]
    await update.message.reply_text(f"{deal_summary}\n\nPlease confirm to proceed.", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def monitor_escrow_deposit(context: ContextTypes.DEFAULT_TYPE):
    deal_id = context.job.data["deal_id"]
    deal = escrow_deals.get(deal_id)
    if not deal or deal['status'] != 'accepted_awaiting_deposit':
        logging.info(f"Stopping monitor for deal {deal_id}, status is {deal.get('status', 'N/A')}"); context.job.schedule_removal(); return

    logging.info(f"Checking for escrow deposit for deal {deal_id}...")
    try:
        url = f"https://api.bscscan.com/api?module=account&action=tokentx&contractaddress={ESCROW_DEPOSIT_TOKEN_CONTRACT}&address={ESCROW_DEPOSIT_ADDRESS}&sort=desc&apikey={DEPOSIT_API_KEY}"
        async with httpx.AsyncClient() as client: response = await client.get(url, timeout=20.0); data = response.json()

        if data['status'] == '1' and data['result']:
            for tx in data['result']:
                if tx['to'].lower() == ESCROW_DEPOSIT_ADDRESS.lower() and tx['hash'] not in deal.get('processed_txs', []):
                    tx_amount_usdt = int(tx['value']) / (10**ESCROW_DEPOSIT_TOKEN_DECIMALS)
                    if tx_amount_usdt >= deal['amount']:
                        logging.info(f"Detected valid deposit for deal {deal_id}, tx: {tx['hash']}. Amount: {tx_amount_usdt} USDT.")
                        deal.update({'amount': tx_amount_usdt, 'status': 'funds_secured', 'deposit_tx_hash': tx['hash']})
                        if 'processed_txs' not in deal: deal['processed_txs'] = []
                        deal['processed_txs'].append(tx['hash'])
                        save_escrow_deal(deal_id)

                        seller_id, buyer_id = deal['seller']['id'], deal['buyer']['id']
                        seller_msg = (f"✅ Deposit of ${tx_amount_usdt:.2f} USDT confirmed for deal <code>{deal_id}</code>. Funds are secured.\n\n"
                                      f"You may now proceed with the buyer. Once they confirm receipt, use the button below to release the funds to them.")
                        buyer_msg = (f"✅ The seller has deposited ${tx_amount_usdt:.2f} USDT for deal <code>{deal_id}</code>. The funds are now secured by the bot.\n\n"
                                     f"Please proceed with the transaction. Let the seller know once you have received the goods/services as agreed.")

                        keyboard_seller = [[InlineKeyboardButton("✅ Release Funds to Buyer", callback_data=f"escrow_action_{deal_id}_release"), InlineKeyboardButton("🚨 Open Dispute", callback_data=f"escrow_action_{deal_id}_dispute")]]
                        keyboard_buyer = [[InlineKeyboardButton("🚨 Open Dispute", callback_data=f"escrow_action_{deal_id}_dispute")]]

                        await context.bot.send_message(seller_id, seller_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_seller))
                        await context.bot.send_message(buyer_id, buyer_msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard_buyer))
                        context.job.schedule_removal()
                        return
    except Exception as e: logging.error(f"Error monitoring escrow deposit for deal {deal_id}: {e}", exc_info=True)

async def release_escrow_funds(update: Update, context: ContextTypes.DEFAULT_TYPE, deal_id: str):
    deal = escrow_deals.get(deal_id)
    if not deal or deal['status'] != 'funds_secured': await update.message.reply_text("This deal is not ready for fund release."); return
    if not all([ESCROW_WALLET_PRIVATE_KEY, w3_bsc]):
        await update.message.reply_text("Escrow wallet not configured. Contacting admin.")
        await context.bot.send_message(BOT_OWNER_ID, f"FATAL: Attempted to release funds for deal {deal_id} but PK or web3 is missing!")
        return

    try:
        w3 = w3_bsc
        contract = w3.eth.contract(address=Web3.to_checksum_address(ESCROW_DEPOSIT_TOKEN_CONTRACT), abi=ERC20_ABI)
        amount_wei = int(deal['amount'] * (10**ESCROW_DEPOSIT_TOKEN_DECIMALS))
        to_address, from_address = Web3.to_checksum_address(deal['buyer']['withdrawal_address']), Web3.to_checksum_address(ESCROW_DEPOSIT_ADDRESS)
        tx = contract.functions.transfer(to_address, amount_wei).build_transaction({
            'chainId': 56, 'gas': 150000, 'gasPrice': w3.eth.gas_price, 'nonce': w3.eth.get_transaction_count(from_address)})
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=ESCROW_WALLET_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt.status == 1:
            deal.update({'status': 'completed', 'release_tx_hash': tx_hash.hex()}); save_escrow_deal(deal_id)
            explorer_url = f"https://bscscan.com/tx/{tx_hash.hex()}"
            success_msg = f"✅ Deal {deal_id} completed! ${deal['amount']:.2f} USDT sent to the buyer. Explorer: {explorer_url}"
            await context.bot.send_message(deal['seller']['id'], success_msg); await context.bot.send_message(deal['buyer']['id'], success_msg)
        else: raise Exception("Transaction failed on-chain.")
    except Exception as e:
        logging.error(f"FATAL ERROR releasing funds for deal {deal_id}: {e}", exc_info=True)
        deal['status'] = 'release_failed'; save_escrow_deal(deal_id)
        fail_msg = f"🚨 An error occurred releasing funds for deal {deal_id}. Contact @jashanxjagy immediately."
        await context.bot.send_message(deal['seller']['id'], fail_msg); await context.bot.send_message(deal['buyer']['id'], fail_msg)
        await context.bot.send_message(BOT_OWNER_ID, f"FATAL ERROR releasing funds for deal {deal_id}: {e}")

## NEW FEATURES ##
@check_maintenance
async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /continue <game_id>")
        return

    game_id = context.args[0]
    game = game_sessions.get(game_id)

    if not game or game.get('status') != 'active' or game.get('user_id') != user.id:
        await update.message.reply_text("Could not find an active game with that ID belonging to you.")
        return

    game_type = game['game_type']

    # Fake an update/query object to pass to the callback handlers
    class FakeQuery:
        def __init__(self, user, message):
            self.from_user = user
            self.message = message
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, *args, **kwargs):
            await self.message.reply_text(*args, **kwargs)

    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(user, update.message)})()

    if game_type == 'mines':
        text = f"💣 Resuming Mines Game (ID: <code>{game_id}</code>)..."
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=mines_keyboard(game_id))
    elif game_type == 'tower':
        text = f"🏗️ Resuming Tower Game (ID: <code>{game_id}</code>)..."
        keyboard = create_tower_keyboard(game_id, game['current_row'], [], game['tower_config'][game['current_row']])
        if game['current_row'] > 0:
            multiplier = TOWER_MULTIPLIERS[game["bombs_per_row"]][game["current_row"]]
            potential_winnings = game["bet_amount"] * multiplier
            keyboard.append([InlineKeyboardButton(f"💸 Cash Out (${potential_winnings:.2f})", callback_data=f"tower_cashout_{game_id}")])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    elif game_type == 'coin_flip':
        text = f"🪙 Resuming Coin Flip (ID: <code>{game_id}</code>)..."
        multiplier = 2 ** game["streak"]
        win_amount = game["bet_amount"] * multiplier
        keyboard = [
            [InlineKeyboardButton("🪙 Heads", callback_data=f"flip_pick_{game_id}_Heads"),
             InlineKeyboardButton("🪙 Tails", callback_data=f"flip_pick_{game_id}_Tails")],
        ]
        if game['streak'] > 0:
            keyboard.append([InlineKeyboardButton(f"💸 Cash Out (${win_amount:.2f})", callback_data=f"flip_cashout_{game_id}")])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    # FIX: Add blackjack continuation
    elif game_type == 'blackjack':
        text = f"🃏 Resuming Blackjack (ID: <code>{game_id}</code>)..."
        player_value = calculate_hand_value(game['player_hand'])
        dealer_show_card = game['dealer_hand'][0]
        hand_text = format_hand("Your hand", game['player_hand'], player_value)
        dealer_text = f"Dealer shows: {dealer_show_card}\n"
        keyboard = [
            [InlineKeyboardButton("👊 Hit", callback_data=f"bj_hit_{game_id}"),
             InlineKeyboardButton("✋ Stand", callback_data=f"bj_stand_{game_id}")],
        ]
        await update.message.reply_text(
            f"{text}\n\n{hand_text}\n{dealer_text}\n💰 Bet: ${game['bet_amount']:.2f}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("This game type cannot be continued.")

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to kick them.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You must be an admin with permission to kick users.")
            return

        target_user = update.message.reply_to_message.from_user
        target_member = await chat.get_member(target_user.id)
        if target_member.status in ['administrator', 'creator']:
            await update.message.reply_text("You cannot kick an administrator.")
            return

        await context.bot.ban_chat_member(chat.id, target_user.id)
        await context.bot.unban_chat_member(chat.id, target_user.id) # Unbanning immediately makes it a kick
        await update.message.reply_text(f"Kicked {target_user.mention_html()}.", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to kick user: {e.message}. I might be missing permissions or the target is an admin.")
    except Exception as e:
        logging.error(f"Error in kick_command: {e}")
        await update.message.reply_text("An error occurred.")

async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to promote them.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_promote_members and member.status != 'creator':
            await update.message.reply_text("You don't have permission to promote members.")
            return

        await context.bot.promote_chat_member(
            chat_id=chat.id,
            user_id=update.message.reply_to_message.from_user.id,
            can_pin_messages=True,
            can_manage_chat=True,
            can_delete_messages=True,
            can_restrict_members=True
        )
        await update.message.reply_text(f"Promoted {update.message.reply_to_message.from_user.mention_html()} to admin.", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to promote user: {e.message}. I might be missing permissions.")
    except Exception as e:
        logging.error(f"Error in promote_command: {e}")
        await update.message.reply_text("An error occurred.")

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to pin it.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_pin_messages and member.status != 'creator':
            await update.message.reply_text("You don't have permission to pin messages.")
            return

        await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to pin message: {e.message}. I might be missing permissions.")
    except Exception as e:
        logging.error(f"Error in pin_command: {e}")
        await update.message.reply_text("An error occurred.")

async def purge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        member = await chat.get_member(user.id)
        if not member.can_delete_messages and member.status != 'creator':
            await update.message.reply_text("You don't have permission to delete messages.")
            return

        bot_member = await chat.get_member(context.bot.id)
        if not bot_member.can_delete_messages:
            await update.message.reply_text("I don't have permission to delete messages. Please make me an admin with this right.")
            return

    except BadRequest as e:
        await update.message.reply_text(f"Could not verify permissions: {e.message}")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to start purging from there up to your command.")
        return

    start_message_id = update.message.reply_to_message.message_id
    end_message_id = update.message.message_id

    message_ids_to_delete = list(range(start_message_id, end_message_id + 1))

    try:
        # Telegram allows deleting up to 100 messages at once
        deleted_count = 0
        for i in range(0, len(message_ids_to_delete), 100):
            chunk = message_ids_to_delete[i:i + 100]
            if await context.bot.delete_messages(chat_id=chat.id, message_ids=chunk):
                deleted_count += len(chunk)

        purge_feedback = await update.message.reply_text(f"✅ Purged {deleted_count} messages.", quote=False)
        await asyncio.sleep(5) # Wait 5 seconds
        await purge_feedback.delete() # Delete the feedback message
    except BadRequest as e:
        await update.message.reply_text(f"Error purging messages: {e.message}. Messages might be too old (over 48h).", quote=False)
    except Exception as e:
        await update.message.reply_text(f"An unexpected error occurred: {e}", quote=False)

@check_maintenance
async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    sorted_users = sorted(user_stats.items(), key=lambda item: item[1].get('bets', {}).get('amount', 0.0), reverse=True)

    msg = "🏆 <b>Top 10 Players by Wager Amount</b> 🏆\n\n"
    for i, (uid, stats) in enumerate(sorted_users[:10]):
        username = stats.get('userinfo', {}).get('username', f'User-{uid}')
        wagered = stats.get('bets', {}).get('amount', 0.0)
        msg += f"{i+1}. @{username} - <b>${wagered:,.2f}</b>\n"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]]) if from_callback else None

    if from_callback:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_maintenance
async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"

    stats = user_stats[user.id]
    ref_info = stats.get('referral', {})

    msg = (f"🤝 <b>Your Referral Dashboard</b> 🤝\n\n"
           f"Share your unique link to earn commissions!\n\n"
           f"🔗 <b>Your Link:</b>\n<code>{referral_link}</code>\n\n"
           f"👥 <b>Total Referrals:</b> {len(ref_info.get('referred_users', []))}\n"
           f"💰 <b>Total Commission Earned:</b> ${ref_info.get('commission_earned', 0.0):.4f}\n\n"
           f"<b>Commission Rates:</b>\n"
           f"- <b>{REFERRAL_DEPOSIT_COMMISSION_RATE*100}%</b> on every deposit made by your referrals.\n"
           f"- <b>{REFERRAL_BET_COMMISSION_RATE*100}%</b> of every bet amount placed by your referrals.")

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]]) if from_callback else None

    if from_callback:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup, disable_web_page_preview=True)

## NEW FEATURE - /level and /levelall commands ##
def create_progress_bar(progress, total, length=10):
    """Creates a text-based progress bar."""
    filled_length = int(length * progress // total)
    bar = '■' * filled_length + '□' * (length - filled_length)
    return bar

@check_maintenance
async def level_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    
    current_level_data = get_user_level(user.id)
    wagered = user_stats[user.id].get("bets", {}).get("amount", 0.0)
    
    text = f"🦄 <b>Your Level: {current_level_data['level']} ({current_level_data['name']})</b>\n\n"
    
    # Check if user is at max level
    if current_level_data['level'] == LEVELS[-1]['level']:
        text += "🏆 You have reached the maximum level!\n"
        text += f"💰 Total Wagered: ${wagered:,.2f}"
    else:
        next_level_data = LEVELS[current_level_data['level'] + 1]
        wager_needed_for_next = next_level_data['wager_required']
        wager_of_current = current_level_data['wager_required']
        
        progress = wagered - wager_of_current
        total_for_level = wager_needed_for_next - wager_of_current
        
        progress_bar = create_progress_bar(progress, total_for_level)
        percentage = (progress / total_for_level) * 100
        
        text += f"<b>Progress to Level {next_level_data['level']} ({next_level_data['name']}):</b>\n"
        text += f"`{progress_bar}` ({percentage:.1f}%)\n\n"
        text += f"💰 <b>Wagered:</b> ${wagered:,.2f} / ${wager_needed_for_next:,.2f}\n"
        text += f"💸 <b>Rakeback:</b> {current_level_data['rakeback_percentage']}%"

    keyboard = [
        [InlineKeyboardButton("📜 View All Levels", callback_data="level_all")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]
    
    if from_callback:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

@check_maintenance
async def level_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    text = "🦄 <b>All Available Levels</b> 🦄\n\n"
    for level in LEVELS:
        text += (f"<b>Level {level['level']} ({level['name']})</b>\n"
                 f"  - Wager Required: ${level['wager_required']:,}\n"
                 f"  - One-time Reward: ${level['reward']:,}\n"
                 f"  - Rakeback Rate: {level['rakeback_percentage']}%\n"
                 "--------------------\n")
                 
    keyboard = [[InlineKeyboardButton("🔙 Back to My Level", callback_data="main_level")]]
    
    if from_callback:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("This is an owner-only command.")
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if not context.args:
        await update.message.reply_text("Usage: /user @username")
        return

    target_username = normalize_username(context.args[0])
    target_user_id = username_to_userid.get(target_username)

    if not target_user_id:
        try:
            chat = await context.bot.get_chat(target_username)
            target_user_id = chat.id
            await ensure_user_in_wallets(target_user_id, chat.username, context=context)
        except Exception:
            await update.message.reply_text(f"Could not find user {target_username}.")
            return

    if target_user_id not in user_stats:
        await update.message.reply_text(f"User {target_username} has not interacted with the bot yet.")
        return

    stats = user_stats[target_user_id]
    userinfo = stats.get('userinfo', {})
    join_date_str = userinfo.get('join_date', 'Not available')
    try:
        join_date = datetime.fromisoformat(join_date_str.split('.')[0]).strftime('%Y-%m-%d %H:%M')
    except:
        join_date = join_date_str

    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))
    
    # NEW: Get user level
    level_data = get_user_level(target_user_id)

    text = (
        f"👤 <b>User Info for @{userinfo.get('username','')}</b> (ID: <code>{target_user_id}</code>)\n"
        f"🗓️ Joined: {join_date} UTC\n"
        f"🦄 Level: {level_data['level']} ({level_data['name']})\n" # ADDED
        f"💰 Balance: ${user_wallets.get(target_user_id, 0.0):.2f}\n"
        f"📈 PnL: ${stats.get('pnl', 0.0):.2f}\n"
        f"🎲 Total Bets: {stats.get('bets', {}).get('count', 0)} (W: {stats.get('bets', {}).get('wins', 0)}, L: {stats.get('bets', {}).get('losses', 0)})\n"
        f"💸 Total Wagered: ${stats.get('bets', {}).get('amount', 0.0):.2f}\n"
        f"💵 Deposits: {len(stats.get('deposits',[]))} (${total_deposits:.2f})\n"
        f"🏧 Withdrawals: {len(stats.get('withdrawals',[]))} (${total_withdrawals:.2f})\n"
        f"🎁 Tips Received: {stats.get('tips_received', {}).get('count', 0)} (${stats.get('tips_received', {}).get('amount', 0.0):.2f})\n"
        f"🎁 Tips Sent: {stats.get('tips_sent', {}).get('count', 0)} (${stats.get('tips_sent', {}).get('amount', 0.0):.2f})\n"
        f"🌧️ Rain Received: {stats.get('rain_received', {}).get('count', 0)} (${stats.get('rain_received', {}).get('amount', 0.0):.2f})\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

## NEW FEATURE - AI Integration with Perplexity ##
@check_maintenance
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    prompt_text = ""
    # Check for reply context
    if update.message.reply_to_message and update.message.reply_to_message.text:
        command_parts = update.message.text.split()
        user_query = ' '.join(command_parts[1:])
        if not user_query: # If just /ai in reply
            user_query = "What do you think about this?"
        prompt_text = f"Considering the context of this message: '{update.message.reply_to_message.text}', respond to the following user query: {user_query}"
    # Check for direct command with prompt
    elif context.args:
        prompt_text = ' '.join(context.args)

    if not prompt_text:
        await update.message.reply_text(
            "How can I help you?\n\nUsage:\n"
            "• `/ai your question here`\n"
            "• Reply to a message with `/ai` to discuss it."
        )
        return

    # Default to g4f for the direct /ai command
    await process_ai_request(update, prompt_text,"g4f")

@check_maintenance
async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if not context.args:
        await update.message.reply_text("Usage: /p <SYMBOL>\nExample: /p BTC")
        return

    symbol = context.args[0].upper()
    pair = f"{symbol}USDT"

    # Use the 24hr ticker endpoint for more details
    url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={pair}"

    status_msg = await update.message.reply_text(f"📈 Fetching 24hr data for {pair} from MEXC...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        price = float(data['lastPrice'])
        price_change_percent = float(data['priceChangePercent']) * 100
        high_price = float(data['highPrice'])
        low_price = float(data['lowPrice'])
        volume = float(data['volume'])
        
        direction_emoji = "🔼" if price_change_percent >= 0 else "🔽"

        text = (
            f"📈 <b>{data['symbol']}</b> Price: <code>${price:,.8f}</code>\n\n"
            f"{direction_emoji} <b>24h Change:</b> {price_change_percent:+.2f}%\n"
            f"⬆️ <b>24h High:</b> ${high_price:,.8f}\n"
            f"⬇️ <b>24h Low:</b> ${low_price:,.8f}\n"
            f"📊 <b>24h Volume:</b> {volume:,.2f} {symbol}"
        )
        
        keyboard = [[InlineKeyboardButton("🔄 Update", callback_data=f"price_update_{pair}")]]

        await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    except httpx.HTTPStatusError as e:
        logging.error(f"MEXC API Error for /p command: {e.response.status_code} - {e.response.text}")
        try:
            error_data = e.response.json()
            error_msg = error_data.get('msg', 'Unknown MEXC error')
            if "Invalid symbol" in error_msg:
                 await status_msg.edit_text(f"❌ Invalid symbol: `{pair}`. Please check the ticker on MEXC.")
            else:
                 await status_msg.edit_text(f"An API error occurred: {error_msg}")
        except json.JSONDecodeError:
            await status_msg.edit_text(f"An unexpected API error occurred while fetching the price for {pair}.")
    except Exception as e:
        logging.error(f"Error in /p command: {e}")
        await status_msg.edit_text(f"An error occurred: {e}")
        
async def price_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Fetching latest price...")
    
    pair = query.data.split('_')[-1]
    symbol = pair.replace("USDT", "")
    url = f"https://api.mexc.com/api/v3/ticker/24hr?symbol={pair}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        price = float(data['lastPrice'])
        price_change_percent = float(data['priceChangePercent']) * 100
        high_price = float(data['highPrice'])
        low_price = float(data['lowPrice'])
        volume = float(data['volume'])
        
        direction_emoji = "🔼" if price_change_percent >= 0 else "🔽"

        text = (
            f"📈 <b>{data['symbol']}</b> Price: <code>${price:,.8f}</code>\n\n"
            f"{direction_emoji} <b>24h Change:</b> {price_change_percent:+.2f}%\n"
            f"⬆️ <b>24h High:</b> ${high_price:,.8f}\n"
            f"⬇️ <b>24h Low:</b> ${low_price:,.8f}\n"
            f"📊 <b>24h Volume:</b> {volume:,.2f} {symbol}"
        )
        
        keyboard = [[InlineKeyboardButton("🔄 Update", callback_data=f"price_update_{pair}")]]
        
        # Check if message content is different before editing to avoid errors
        if query.message.text != text:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.answer("Price is already up to date.")

    except Exception as e:
        logging.error(f"Error in price_update_callback: {e}")
        await query.answer(f"Failed to update price: {e}", show_alert=True)


async def process_ai_request(update: Update, prompt: str, model_choice: str):
    """Generic function to handle AI requests from different models."""
    status_msg = await update.message.reply_text(f"🤖 Thinking with {model_choice.title()}...", reply_to_message_id=update.message.message_id)

    try:
        if model_choice == "perplexity": # Updated name
            if PERPLEXITY_API_KEY and PERPLEXITY_API_KEY.startswith("pplx-"):
                client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
                messages = [{"role": "system", "content": "You are a helpful assistant integrated into a Telegram bot."}, {"role": "user", "content": prompt}]
                response = client.chat.completions.create(model="sonar", messages=messages) # Using a capable model
                ai_response = response.choices[0].message.content
            else:
                ai_response = "Perplexity AI is not configured correctly by the bot owner."

        elif model_choice == "g4f":
            ai_response = await g4f.ChatCompletion.create_async(
                model=g4f.models.default,
                messages=[{"role": "user", "content": prompt}],
            )

        else:
            ai_response = "Invalid AI model selected."

        await status_msg.edit_text(ai_response)

    except Exception as e:
        logging.error(f"AI ({model_choice}) Error: {e}")
        await status_msg.edit_text(f"An error occurred while contacting the AI: {e}")

## NEW FEATURE - Daily Bonus, Achievements, Language Commands ##
@check_maintenance
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    stats = user_stats[user.id]
    lang = stats.get("userinfo", {}).get("language", DEFAULT_LANG)
    last_claim_str = stats.get("last_daily_claim")

    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        time_since_claim = datetime.now(timezone.utc) - last_claim_time
        if time_since_claim < timedelta(hours=24):
            time_left = timedelta(hours=24) - time_since_claim
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            text = get_text("daily_claim_wait", lang, hours=hours, minutes=minutes)
            if from_callback:
                await update.callback_query.answer(text, show_alert=True)
            else:
                await update.message.reply_text(text)
            return

    bonus_amount = bot_settings.get("daily_bonus_amount", 0.50)
    user_wallets[user.id] += bonus_amount
    stats["last_daily_claim"] = str(datetime.now(timezone.utc))
    save_user_data(user.id)

    text = get_text("daily_claim_success", lang, amount=bonus_amount)
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Bonuses", callback_data="main_bonuses")]]) if from_callback else None

    if from_callback:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

@check_maintenance
async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    stats = user_stats[user.id]
    user_achievements = stats.get("achievements", [])

    if not user_achievements:
        text = "You have not earned any achievements yet. Keep playing to unlock them!"
    else:
        text = "🏅 <b>Your Achievements</b> 🏅\n\n"
        for ach_id in user_achievements:
            ach_data = ACHIEVEMENTS.get(ach_id)
            if ach_data:
                text += f"{ach_data['emoji']} <b>{ach_data['name']}</b> - <i>{ach_data['description']}</i>\n"

    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]]) if from_callback else None

    if from_callback:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

@check_maintenance
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    args = context.args

    if not args:
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")]
        ]
        await update.message.reply_text("Please choose your language:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    lang_code = args[0].lower()
    if lang_code in LANGUAGES:
        user_stats[user.id]["userinfo"]["language"] = lang_code
        save_user_data(user.id)
        await update.message.reply_text(f"Language set to {lang_code}.")
    else:
        await update.message.reply_text("Invalid language code. Available codes: en, es.")

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    lang_code = query.data.split('_')[1]
    await ensure_user_in_wallets(user.id, user.username, context=context)

    if lang_code in LANGUAGES:
        user_stats[user.id]["userinfo"]["language"] = lang_code
        save_user_data(user.id)
        await query.edit_message_text(f"Language set to {lang_code}.")
    else:
        await query.edit_message_text("Invalid language code.")

## NEW FEATURE - Admin Dashboard & Group Settings ##
async def admin_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    query = update.callback_query

    total_users = len(user_stats)
    total_balance = sum(user_wallets.values())
    active_games = len([g for g in game_sessions.values() if g.get('status') == 'active'])

    text = (
        f"👑 <b>Admin Dashboard</b> 👑\n\n"
        f"📊 <b>Bot Stats:</b>\n"
        f"  - Total Users: {total_users}\n"
        f"  - Total User Balance: ${total_balance:,.2f}\n"
        f"  - House Balance: ${bot_settings.get('house_balance', 0):,.2f}\n"
        f"  - Active Escrow Deals: {len(escrow_deals)}\n"
        f"  - Active Games: {active_games}\n\n"
        f"⚙️ <b>Bot Settings:</b>\n"
        f"  - Daily Bonus: ${bot_settings.get('daily_bonus_amount', 0.50):.2f}\n"
        f"  - Maintenance Mode: {'ON' if bot_settings.get('maintenance_mode') else 'OFF'}\n"
        f"  - Withdrawals: {'ON' if bot_settings.get('withdrawals_enabled', True) else 'OFF'}\n"
        f"  - Deposits: {'ON' if bot_settings.get('deposits_enabled', True) else 'OFF'}"
    )

    keyboard = [
        [InlineKeyboardButton("👥 User Management", callback_data="admin_users"), InlineKeyboardButton("🔍 Search User", callback_data="admin_search_user")],
        [InlineKeyboardButton("🏦 House Balance", callback_data="admin_set_house_balance"), InlineKeyboardButton("⚖️ Game Limits", callback_data="admin_limits")],
        [InlineKeyboardButton("⚙️ Bot Settings", callback_data="admin_bot_settings"), InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎁 Gift Codes", callback_data="admin_gift_codes")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]

    if query:
        if query.from_user.id != BOT_OWNER_ID: return
        await query.answer()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_bot_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID: return
    await query.answer()

    text = "⚙️ <b>Bot Settings</b>"
    keyboard = [
        [InlineKeyboardButton(f"Daily Bonus: ${bot_settings.get('daily_bonus_amount', 0.50):.2f}", callback_data="admin_set_daily_bonus")],
        [InlineKeyboardButton(f"Maintenance: {'ON' if bot_settings.get('maintenance_mode') else 'OFF'}", callback_data="admin_toggle_maintenance")],
        [InlineKeyboardButton(f"Withdrawals: {'Enabled' if bot_settings.get('withdrawals_enabled', True) else 'Disabled'}", callback_data="admin_toggle_withdrawals")],
        [InlineKeyboardButton(f"Deposits: {'Enabled' if bot_settings.get('deposits_enabled', True) else 'Disabled'}", callback_data="admin_toggle_deposits")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_dashboard")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID:
        await query.answer("This is an admin-only area.", show_alert=True)
        return

    await query.answer()
    action = query.data

    if action == "admin_dashboard":
        await admin_dashboard_command(update, context)
    elif action == "admin_users":
        await users_command(update, context)
    elif action == "admin_search_user":
        await query.edit_message_text("Please enter the @username or user ID of the user to search.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SEARCH_USER
    elif action == "admin_bot_settings":
        await admin_bot_settings_callback(update, context)
    elif action == "admin_set_house_balance":
        await query.edit_message_text("Please enter the new house balance amount.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SET_HOUSE_BALANCE
    elif action == "admin_limits":
        await query.edit_message_text("Select limit type to set:", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Set Minimum Bet", callback_data="admin_limit_type_min")],
            [InlineKeyboardButton("Set Maximum Bet", callback_data="admin_limit_type_max")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_dashboard")]
        ]))
        return ADMIN_LIMITS_CHOOSE_TYPE
    elif action == "admin_set_daily_bonus":
        await query.edit_message_text("Please enter the new daily bonus amount (e.g., 0.75).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_bot_settings")]]))
        return ADMIN_SET_DAILY_BONUS
    elif action == "admin_broadcast":
        await query.edit_message_text("Please send the message you want to broadcast to all users.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_BROADCAST_MESSAGE
    elif action == "admin_toggle_maintenance":
        bot_settings["maintenance_mode"] = not bot_settings.get("maintenance_mode", False)
        save_bot_state()
        await query.answer(f"Maintenance mode is now {'ON' if bot_settings['maintenance_mode'] else 'OFF'}")
        await admin_bot_settings_callback(update, context)
    elif action == "admin_toggle_withdrawals":
        bot_settings["withdrawals_enabled"] = not bot_settings.get("withdrawals_enabled", True)
        save_bot_state()
        await query.answer(f"Withdrawals are now {'ENABLED' if bot_settings['withdrawals_enabled'] else 'DISABLED'}")
        await admin_bot_settings_callback(update, context)
    elif action == "admin_toggle_deposits":
        bot_settings["deposits_enabled"] = not bot_settings.get("deposits_enabled", True)
        save_bot_state()
        await query.answer(f"Deposits are now {'ENABLED' if bot_settings['deposits_enabled'] else 'DISABLED'}")
        await admin_bot_settings_callback(update, context)
    elif action == "admin_gift_codes":
        await admin_gift_code_menu(update, context)

async def set_house_balance_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return ConversationHandler.END
    try:
        amount = float(update.message.text)
        if amount < 0: raise ValueError
        bot_settings['house_balance'] = amount
        save_bot_state()
        await update.message.reply_text(f"🏦 House balance set to ${amount:,.2f}.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.")
        return ADMIN_SET_HOUSE_BALANCE

    context.user_data.clear()
    await admin_dashboard_command(update, context)
    return ConversationHandler.END

async def admin_limits_choose_type_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID: return ConversationHandler.END
    await query.answer()

    limit_type = query.data.split('_')[-1] # min or max
    context.user_data['limit_type'] = limit_type
    all_games = [
        'blackjack', 'coin_flip', 'roulette', 'dice_roll', 'slots',
        'predict', 'tower', 'mines', 'pvp_dice', 'pvp_darts',
        'pvp_goal', 'pvp_bowl', 'limbo', 'rps', 'ttt_pvb', 'ttt_pvp' # NEW
    ]

    keyboard = []
    row = []
    for game in all_games:
        row.append(InlineKeyboardButton(game.replace('_', ' ').title(), callback_data=f"admin_limit_game_{game}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])

    await query.edit_message_text(f"Select a game to set the <b>{limit_type}imum</b> bet for:",
                                  reply_markup=InlineKeyboardMarkup(keyboard),
                                  parse_mode=ParseMode.HTML)
    return ADMIN_LIMITS_CHOOSE_GAME

async def admin_limits_choose_game_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID: return ConversationHandler.END
    await query.answer()

    game_name = query.data.split('_')[-1]
    context.user_data['limit_game'] = game_name
    limit_type = context.user_data['limit_type']

    await query.edit_message_text(f"Please enter the <b>{limit_type}imum</b> bet amount for <b>{game_name.replace('_', ' ').title()}</b>.",
                                  parse_mode=ParseMode.HTML,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
    return ADMIN_LIMITS_SET_AMOUNT

async def admin_limits_set_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return ConversationHandler.END

    try:
        amount = float(update.message.text)
        if amount < 0: raise ValueError

        game_name = context.user_data['limit_game']
        limit_type = context.user_data['limit_type']

        if game_name not in bot_settings['game_limits']:
            bot_settings['game_limits'][game_name] = {}

        bot_settings['game_limits'][game_name][limit_type] = amount
        save_bot_state()

        await update.message.reply_text(f"✅ Set <b>{limit_type}imum</b> bet for <b>{game_name.replace('_', ' ').title()}</b> to <b>${amount:,.2f}</b>.",
                                      parse_mode=ParseMode.HTML)

    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.")
        return ADMIN_LIMITS_SET_AMOUNT

    context.user_data.clear()
    await admin_dashboard_command(update, context)
    return ConversationHandler.END
async def set_daily_bonus_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return ConversationHandler.END
    try:
        amount = float(update.message.text)
        if amount < 0: raise ValueError

        bot_settings['daily_bonus_amount'] = amount
        save_bot_state()
        await update.message.reply_text(f"Daily bonus amount set to ${amount:.2f}.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_bot_settings")]]))
        return ADMIN_SET_DAILY_BONUS

    context.user_data.clear()
    # Fake a query to go back to the settings menu
    class FakeQuery:
        def __init__(self, user, message): self.from_user = user; self.message = message
        async def answer(self): pass
        async def edit_message_text(self, *args, **kwargs): await message.reply_text(*args, **kwargs)

    # --- FIX STARTS HERE ---
    # Create a fake update object to call the settings menu function
    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(update.effective_user, update.message)})()
    await admin_bot_settings_callback(fake_update, context)
    return ConversationHandler.END
    # --- FIX ENDS HERE ---

async def admin_search_user_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return ConversationHandler.END
    username_or_id = update.message.text
    target_user_id = None

    if username_or_id.isdigit():
        target_user_id = int(username_or_id)
    else:
        target_user_id = username_to_userid.get(normalize_username(username_or_id))

    if not target_user_id or target_user_id not in user_stats:
        await update.message.reply_text("User not found. Please try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SEARCH_USER

    context.user_data['admin_search_target'] = target_user_id
    await display_admin_user_panel(update, context, target_user_id)
    # --- FIX STARTS HERE ---
    return ConversationHandler.END
    # --- FIX ENDS HERE ---

async def admin_broadcast_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return ConversationHandler.END
    message_text = update.message.text
    all_user_ids = get_all_registered_user_ids()
    sent_count = 0
    failed_count = 0

    await update.message.reply_text(f"Starting broadcast to {len(all_user_ids)} users...")

    for user_id in all_user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode=ParseMode.HTML)
            sent_count += 1
        except (BadRequest, Forbidden) as e:
            logging.warning(f"Broadcast failed for user {user_id}: {e}")
            failed_count += 1
        await asyncio.sleep(0.1) # Avoid hitting rate limits

    await update.message.reply_text(f"Broadcast finished.\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}")

    context.user_data.clear()
    await admin_dashboard_command(update, context)
    return ConversationHandler.END

async def admin_search_user_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return ConversationHandler.END
    username_or_id = update.message.text
    target_user_id = None

    if username_or_id.isdigit():
        target_user_id = int(username_or_id)
    else:
        target_user_id = username_to_userid.get(normalize_username(username_or_id))

    if not target_user_id or target_user_id not in user_stats:
        await update.message.reply_text("User not found. Please try again.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_dashboard")]]))
        return ADMIN_SEARCH_USER

    context.user_data['admin_search_target'] = target_user_id
    await display_admin_user_panel(update, context, target_user_id)
    return ConversationHandler.END

async def display_admin_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int, page=0, history_type='matches'):
    stats = user_stats[target_user_id]
    userinfo = stats.get('userinfo', {})
    total_deposits = sum(d['amount'] for d in stats.get('deposits', []))
    total_withdrawals = sum(w['amount'] for w in stats.get('withdrawals', []))

    is_banned = target_user_id in bot_settings.get("banned_users", [])
    is_temp_banned = target_user_id in bot_settings.get("tempbanned_users", [])

    text = (
        f"👤 <b>Admin Panel for @{userinfo.get('username','')}</b> (ID: <code>{target_user_id}</code>)\n"
        f"💰 Balance: ${user_wallets.get(target_user_id, 0.0):.2f}\n"
        f"📈 PnL: ${stats.get('pnl', 0.0):.2f}\n"
        f"💵 Deposits: ${total_deposits:.2f} | 💸 Withdrawals: ${total_withdrawals:.2f}\n"
        f"🚫 Ban Status: {'Banned' if is_banned else 'Not Banned'}\n"
        f"⏳ Temp Ban (Withdrawal): {'Banned' if is_temp_banned else 'Not Banned'}\n"
    )

    # History section
    page_size = 5
    items = []
    if history_type == 'matches':
        items = [game_sessions.get(gid) for gid in reversed(stats.get("game_sessions", [])) if gid in game_sessions]
        text += "\n📜 <b>Match History:</b>\n"
    elif history_type == 'deposits':
        items = list(reversed(stats.get("deposits", [])))
        text += "\n📜 <b>Deposit History:</b>\n"
    elif history_type == 'withdrawals':
        items = list(reversed(stats.get("withdrawals", [])))
        text += "\n📜 <b>Withdrawal History:</b>\n"

    paginated_items = items[page*page_size : (page+1)*page_size]
    if not paginated_items:
        text += "No records found.\n"
    else:
        for item in paginated_items:
            if history_type == 'matches':
                game_type = item['game_type'].replace('_', ' ').title()
                win_status = "Win" if item.get('win') else "Loss"
                text += f" • {game_type} (${item['bet_amount']:.2f}) - {win_status} (<code>{item['id']}</code>)\n"
            elif history_type == 'deposits':
                 ts = datetime.fromisoformat(item['timestamp']).strftime('%Y-%m-%d')
                 text += f" • ${item['amount']:.2f} via {item['method']} ({ts})\n"
            elif history_type == 'withdrawals':
                 ts = datetime.fromisoformat(item['timestamp']).strftime('%Y-%m-%d')
                 text += f" • ${item['amount']:.2f} via {item['method']} ({ts})\n"

    # Keyboard
    keyboard = [
        [
            InlineKeyboardButton("Ban" if not is_banned else "Unban", callback_data=f"admin_user_{target_user_id}_ban"),
            InlineKeyboardButton("TempBan" if not is_temp_banned else "UnTempBan", callback_data=f"admin_user_{target_user_id}_tempban")
        ],
        [
            InlineKeyboardButton("Matches", callback_data=f"admin_user_{target_user_id}_history_matches_0"),
            InlineKeyboardButton("Deposits", callback_data=f"admin_user_{target_user_id}_history_deposits_0"),
            InlineKeyboardButton("Withdrawals", callback_data=f"admin_user_{target_user_id}_history_withdrawals_0")
        ]
    ]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"admin_user_{target_user_id}_history_{history_type}_{page-1}"))
    if (page+1)*page_size < len(items):
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"admin_user_{target_user_id}_history_{history_type}_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Dashboard", callback_data="admin_dashboard")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def admin_user_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID:
        await query.answer("This is an admin-only area.", show_alert=True)
        return

    await query.answer()

    parts = query.data.split('_')
    # admin_user_{user_id}_action
    # admin_user_{user_id}_history_{type}_{page}
    target_user_id = int(parts[2])
    action = parts[3]

    if action == 'ban':
        if target_user_id in bot_settings.get("banned_users", []):
            bot_settings["banned_users"].remove(target_user_id)
            await query.answer("User unbanned.")
        else:
            bot_settings.setdefault("banned_users", []).append(target_user_id)
            await query.answer("User banned.")
        save_bot_state()
    elif action == 'tempban':
        if target_user_id in bot_settings.get("tempbanned_users", []):
            bot_settings["tempbanned_users"].remove(target_user_id)
            await query.answer("User's withdrawal restrictions lifted.")
        else:
            bot_settings.setdefault("tempbanned_users", []).append(target_user_id)
            await query.answer("User temporarily banned from withdrawals.")
        save_bot_state()
    elif action == 'history':
        history_type = parts[4]
        page = int(parts[5])
        await display_admin_user_panel(update, context, target_user_id, page, history_type)
        return

    await display_admin_user_panel(update, context, target_user_id)


async def setbal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID: return
    await ensure_user_in_wallets(user.id, user.username, context=context)

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /setbal @username <amount>")
        return

    username, amount_str = args[0], args[1]
    target_user_id = username_to_userid.get(normalize_username(username))

    if not target_user_id:
        await update.message.reply_text(f"User {username} not found.")
        return

    try:
        amount = float(amount_str)
        user_wallets[target_user_id] = amount
        update_pnl(target_user_id)
        save_user_data(target_user_id)
        await update.message.reply_text(f"Balance for {username} set to ${amount:.2f}.")
    except ValueError:
        await update.message.reply_text("Invalid amount.")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a user's message to mute them.")
        return

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You must be an admin with permission to mute users.")
            return

        target_user = update.message.reply_to_message.from_user
        target_member = await chat.get_member(target_user.id)
        if target_member.status in ['administrator', 'creator']:
            await update.message.reply_text("You cannot mute an administrator.")
            return

        await context.bot.restrict_chat_member(chat.id, target_user.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text(f"Muted {target_user.mention_html()}.", parse_mode=ParseMode.HTML)
    except BadRequest as e:
        await update.message.reply_text(f"Failed to mute user: {e.message}. I might be missing permissions or the target is an admin.")
    except Exception as e:
        logging.error(f"Error in mute_command: {e}")
        await update.message.reply_text("An error occurred.")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to a message to report it to admins.")
        return

    try:
        admins = await context.bot.get_chat_administrators(chat.id)
        report_text = f"📢 Report from {user.mention_html()} in {chat.title}:\n\n<a href='{update.message.reply_to_message.link}'>Reported Message</a>"
        for admin in admins:
            if not admin.user.is_bot:
                try:
                    await context.bot.send_message(admin.user.id, report_text, parse_mode=ParseMode.HTML)
                except (Forbidden, BadRequest):
                    pass
        await update.message.reply_text("Reported to admins.")
    except Exception as e:
        logging.error(f"Error in report_command: {e}")
        await update.message.reply_text("An error occurred while reporting.")

async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        await update.message.reply_text("Reply to a text message to translate it.")
        return

    text_to_translate = update.message.reply_to_message.text
    # Using g4f for translation
    try:
        translated_text = await g4f.ChatCompletion.create_async(
            model=g4f.models.default,
            messages=[{"role": "user", "content": f"Translate the following text to English: '{text_to_translate}'"}],
        )
        await update.message.reply_text(f"<b>Translation:</b>\n{translated_text}", parse_mode=ParseMode.HTML, reply_to_message_id=update.message.reply_to_message.id)
    except Exception as e:
        await update.message.reply_text(f"Translation failed: {e}")

async def lockall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You don't have permission to change group settings.")
            return

        bot_member = await chat.get_member(context.bot.id)
        if not bot_member.can_restrict_members:
            await update.message.reply_text("I don't have permission to restrict members. Please make me an admin with this right.")
            return

        await context.bot.set_chat_permissions(chat.id, ChatPermissions(can_send_messages=False))
        await update.message.reply_text("🔒 Chat locked. Only admins can send messages.")
    except BadRequest as e:
        await update.message.reply_text(f"Failed to lock chat: {e.message}")
    except Exception as e:
        logging.error(f"Error in lockall_command: {e}")
        await update.message.reply_text("An error occurred.")

async def unlockall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    await ensure_user_in_wallets(user.id, user.username, context=context)

    try:
        member = await chat.get_member(user.id)
        if not member.can_restrict_members and member.status != 'creator':
            await update.message.reply_text("You don't have permission to change group settings.")
            return

        bot_member = await chat.get_member(context.bot.id)
        if not bot_member.can_restrict_members:
            await update.message.reply_text("I don't have permission to change permissions. Please make me an admin with this right.")
            return

        # Restore default permissions for all members
        await context.bot.set_chat_permissions(chat.id, ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_change_info=False, can_invite_users=True, can_pin_messages=False
        ))
        await update.message.reply_text("🔓 Chat unlocked. All members can send messages again.")
    except BadRequest as e:
        await update.message.reply_text(f"Failed to unlock chat: {e.message}")
    except Exception as e:
        logging.error(f"Error in unlockall_command: {e}")
        await update.message.reply_text("An error occurred.")

## NEW FEATURE - /active and /activeall commands ##
@check_maintenance
async def active_games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    
    active_games = [g for g in game_sessions.values() if g.get("status") == "active" and g.get("user_id") == user.id]

    if not active_games:
        await update.message.reply_text("You have no active games. Start one from the /games menu!")
        return

    msg = "<b>Your Active Games:</b>\n\n"
    for game in active_games:
        game_type = game['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
        msg += f"<b>Bet:</b> ${game['bet_amount']:.2f}\n"
        msg += f"Use <code>/continue {game['id']}</code> to resume.\n"
        msg += "--------------------\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def active_all_games_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID:
        return
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    context.user_data['active_games_page'] = 0
    await send_active_games_page(update, context)

async def send_active_games_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = context.user_data.get('active_games_page', 0)
    page_size = 10
    active_games = [g for g in game_sessions.values() if g.get("status") == "active"]

    start_index = page * page_size
    end_index = start_index + page_size
    paginated_games = active_games[start_index:end_index]

    if update.callback_query and not paginated_games:
        await update.callback_query.answer("No more active games.", show_alert=True)
        return

    msg = f"<b>All Active Games (Page {page + 1}/{ -(-len(active_games) // page_size) }):</b>\n\n"
    if not paginated_games:
        msg = "There are no active games on the bot."
    
    for game in paginated_games:
        game_type = game['game_type'].replace('_', ' ').title()
        msg += f"<b>Game:</b> {game_type} | <b>ID:</b> <code>{game['id']}</code>\n"
        if 'players' in game:
            p_names = [game['usernames'].get(pid, f"ID:{pid}") for pid in game['players']]
            msg += f"<b>Players:</b> {', '.join(p_names)}\n"
        else:
            uid = game['user_id']
            uname = user_stats.get(uid, {}).get('userinfo', {}).get('username', f'ID:{uid}')
            msg += f"<b>Player:</b> @{uname}\n"
        msg += f"<b>Bet:</b> ${game['bet_amount']:.2f}\n--------------------\n"

    keyboard = []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️ Previous", callback_data="activeall_prev"))
    if end_index < len(active_games):
        row.append(InlineKeyboardButton("Next ➡️", callback_data="activeall_next"))
    if row:
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def active_all_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != BOT_OWNER_ID:
        await query.answer("This is an admin-only button.", show_alert=True)
        return

    await query.answer()
    action = query.data
    page = context.user_data.get('active_games_page', 0)

    if action == "activeall_next":
        context.user_data['active_games_page'] = page + 1
    elif action == "activeall_prev":
        context.user_data['active_games_page'] = max(0, page - 1)

    await send_active_games_page(update, context)


## NEW FEATURE - Settings and Recovery System ##
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await ensure_user_in_wallets(user.id, user.username, context=context)

    keyboard = [
        [InlineKeyboardButton("🔐 Recovery Token", callback_data="settings_recovery")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]
    await query.edit_message_text(
        "⚙️ <b>Settings</b>\n\nManage your account settings here.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    action = query.data.split('_')[1]

    if action == "recovery":
        if user_stats[user.id].get("recovery_token_hash"):
            await query.edit_message_text(
                "You have already set up a recovery token. To reset it, please contact support or ask the owner to use `/reset @yourusername`.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main_settings")]])
            )
            return
        
        await query.edit_message_text(
            "🔐 <b>Recovery PIN Setup</b>\n\n"
            "Please enter a 6-digit PIN. This PIN will be required to use your recovery token. "
            "Do not forget it.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_settings")]])
        )
        return SETTINGS_RECOVERY_PIN

def hash_pin(pin: str) -> str:
    """Hashes a PIN using SHA256."""
    return hashlib.sha256(pin.encode()).hexdigest()

async def set_recovery_pin_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pin = update.message.text

    if not pin.isdigit() or len(pin) != 6:
        await update.message.reply_text(
            "Invalid PIN. Please enter exactly 6 digits.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="main_settings")]])
        )
        return SETTINGS_RECOVERY_PIN

    token = secrets.token_hex(20)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    recovery_data[token_hash] = {
        "user_id": user.id,
        "pin_hash": hash_pin(pin),
        "created_at": str(datetime.now(timezone.utc)),
        "failed_attempts": 0,
        "lock_expiry": None
    }
    user_stats[user.id]["recovery_token_hash"] = token_hash
    
    save_recovery_data(token_hash)
    save_user_data(user.id)

    await update.message.reply_text(
        "✅ <b>Recovery Token Generated!</b>\n\n"
        "Please save this token in a secure place. It is the ONLY way to recover your account.\n\n"
        "<code>" + token + "</code>\n\n"
        "You will need this token and your 6-digit PIN to use the /recover command.",
        parse_mode=ParseMode.HTML
    )
    class FakeQuery:
        def __init__(self, user, message): self.from_user = user; self.message = message
        async def answer(self): pass
        async def edit_message_text(self, *args, **kwargs): await message.reply_text(*args, **kwargs)
    
    fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(user, update.message)})()
    fake_update.callback_query.data = 'main_settings'
    await settings_command(fake_update, context)

    return ConversationHandler.END


async def recover_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        await update.message.reply_text("For security, please use the /recover command in a private chat with me.")
        return ConversationHandler.END
        
    await update.message.reply_text(
        "Please enter your recovery token.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_recovery")]])
    )
    return RECOVER_ASK_TOKEN

async def recover_token_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = update.message.text.strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    rec_data = recovery_data.get(token_hash)
    if not rec_data:
        await update.message.reply_text(
            "Invalid token. Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_recovery")]])
        )
        return RECOVER_ASK_TOKEN

    if rec_data.get('lock_expiry') and rec_data['lock_expiry'] > datetime.now(timezone.utc):
        time_left = rec_data['lock_expiry'] - datetime.now(timezone.utc)
        await update.message.reply_text(f"This token is locked due to too many failed attempts. Please try again in {time_left.seconds // 60} minutes.")
        return ConversationHandler.END

    context.user_data['recovery_token_hash'] = token_hash
    await update.message.reply_text(
        "Token found. Please enter your 6-digit PIN.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_recovery")]])
    )
    return RECOVER_ASK_PIN

async def recover_pin_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pin = update.message.text
    token_hash = context.user_data['recovery_token_hash']
    rec_data = recovery_data[token_hash]
    
    if rec_data['pin_hash'] != hash_pin(pin):
        rec_data['failed_attempts'] = rec_data.get('failed_attempts', 0) + 1
        if rec_data['failed_attempts'] >= 5:
            rec_data['lock_expiry'] = datetime.now(timezone.utc) + timedelta(hours=1)
            await update.message.reply_text("Incorrect PIN. Too many failed attempts. This token is now locked for 1 hour.")
            context.user_data.clear()
            save_recovery_data(token_hash)
            return ConversationHandler.END
        else:
            attempts_left = 5 - rec_data['failed_attempts']
            await update.message.reply_text(f"Incorrect PIN. You have {attempts_left} attempts left before this token is locked.")
            save_recovery_data(token_hash)
            return RECOVER_ASK_PIN

    # --- SUCCESSFUL RECOVERY ---
    old_user_id = rec_data['user_id']
    new_user = update.effective_user

    if old_user_id not in user_stats:
        await update.message.reply_text("Could not find the original account data. Please contact support.")
        context.user_data.clear()
        return ConversationHandler.END

    # Transfer data
    await ensure_user_in_wallets(new_user.id, new_user.username, context=context)
    user_stats[new_user.id] = user_stats[old_user_id]
    user_wallets[new_user.id] = user_wallets[old_user_id]

    user_stats[new_user.id]['userinfo']['user_id'] = new_user.id
    user_stats[new_user.id]['userinfo']['username'] = new_user.username
    user_stats[new_user.id]['userinfo']['recovered_from'] = old_user_id
    user_stats[new_user.id]['userinfo']['recovered_at'] = str(datetime.now(timezone.utc))

    # Transfer active games
    active_games_transferred = 0
    for game in game_sessions.values():
        if game.get("status") == "active" and game.get("user_id") == old_user_id:
            game["user_id"] = new_user.id
            active_games_transferred += 1
    
    # Clean up old user data
    if old_user_id in user_stats: del user_stats[old_user_id]
    if old_user_id in user_wallets: del user_wallets[old_user_id]
    old_username = username_to_userid.pop(normalize_username(rec_data.get("username", "")), None)
    
    if os.path.exists(os.path.join(DATA_DIR, f"{old_user_id}.json")):
        os.remove(os.path.join(DATA_DIR, f"{old_user_id}.json"))

    # Clean up recovery token
    del recovery_data[token_hash]
    if os.path.exists(os.path.join(RECOVERY_DIR, f"{token_hash}.json")):
        os.remove(os.path.join(RECOVERY_DIR, f"{token_hash}.json"))

    save_user_data(new_user.id)
    
    await update.message.reply_text(
        f"✅ <b>Recovery Successful!</b>\n\n"
        f"Welcome back, {new_user.mention_html()}! Your data and balance of ${user_wallets[new_user.id]:.2f} have been restored. "
        f"{active_games_transferred} active games were transferred to this account. Use /active to see them.",
        parse_mode=ParseMode.HTML
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_recovery_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Recovery process cancelled.")
    context.user_data.clear()
    await start_command_inline(query, context)
    return ConversationHandler.END

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != BOT_OWNER_ID:
        await update.message.reply_text("This is an owner-only command.")
        return
    
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in my DMs for security.")
        return
        
    await update.message.reply_text("Exporting all user data... This may take a moment.")
    
    export_data = {
        "user_stats": user_stats,
        "user_wallets": user_wallets
    }
    
    file_path = os.path.join(DATA_DIR, "export_all_users.json")
    try:
        with open(file_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)
        
        await update.message.reply_document(
            document=open(file_path, "rb"),
            caption=f"All user data as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            filename="all_user_data.json"
        )
        os.remove(file_path)
    except Exception as e:
        logging.error(f"Failed to export user data: {e}")
        await update.message.reply_text(f"An error occurred during export: {e}")

async def reset_recovery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != BOT_OWNER_ID: return
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /reset @username")
        return
        
    target_username = normalize_username(context.args[0])
    target_user_id = username_to_userid.get(target_username)
    
    if not target_user_id:
        await update.message.reply_text(f"User {target_username} not found in the bot's database.")
        return
        
    stats = user_stats.get(target_user_id)
    if not stats or not stats.get("recovery_token_hash"):
        await update.message.reply_text(f"User {target_username} does not have a recovery token set.")
        return
        
    token_hash = stats["recovery_token_hash"]
    
    # Remove from user_stats
    stats["recovery_token_hash"] = None
    save_user_data(target_user_id)
    
    # Remove from recovery_data
    if token_hash in recovery_data:
        del recovery_data[token_hash]
    
    # Remove file
    recovery_file = os.path.join(RECOVERY_DIR, f"{token_hash}.json")
    if os.path.exists(recovery_file):
        os.remove(recovery_file)
        
    await update.message.reply_text(f"Successfully reset the recovery token for {target_username}. They can now set a new one via the settings menu.")
    try:
        await context.bot.send_message(target_user_id, "Your account recovery token has been reset by the administrator. You can now set a new one in the settings menu.")
    except Exception as e:
        logging.warning(f"Could not notify user {target_user_id} about recovery reset: {e}")

@check_maintenance
async def claim_gift_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Usage: /claim <code>")
        return
        
    code = context.args[0]
    
    if code not in gift_codes:
        await update.message.reply_text("Invalid or expired gift code.")
        return
        
    code_data = gift_codes[code]
    
    if code_data["claims_left"] <= 0:
        await update.message.reply_text("This gift code has already been fully claimed.")
        return
        
    if user.id in code_data["claimed_by"]:
        await update.message.reply_text("You have already claimed this gift code.")
        return
        
    # All checks passed, award the user
    amount = code_data["amount"]
    user_wallets[user.id] += amount
    user_stats[user.id].setdefault("claimed_gift_codes", []).append(code)
    
    code_data["claims_left"] -= 1
    code_data["claimed_by"].append(user.id)
    
    save_user_data(user.id)
    save_gift_code(code)
    
    await update.message.reply_text(f"🎉 Success! You have claimed a gift code and received ${amount:.2f}!")

@check_maintenance
async def leaderboard_referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user_in_wallets(update.effective_user.id, update.effective_user.username, context=context)
    
    # Sort users by the number of people they have referred
    sorted_users = sorted(user_stats.items(), key=lambda item: len(item[1].get('referral', {}).get('referred_users', [])), reverse=True)

    msg = "🏆 <b>Top 10 Referrers</b> 🏆\n\n"
    for i, (uid, stats) in enumerate(sorted_users[:10]):
        username = stats.get('userinfo', {}).get('username', f'User-{uid}')
        ref_count = len(stats.get('referral', {}).get('referred_users', []))
        if ref_count > 0:
            msg += f"{i+1}. @{username} - <b>{ref_count} referrals</b>\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# --- Main Function ---)
def main():
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO,
                        handlers=[logging.FileHandler(os.path.join(LOGS_DIR, f"bot_{datetime.now().strftime('%Y%m%d')}.log")), logging.StreamHandler()])
    logging.info("Starting bot...")

    if not PERPLEXITY_API_KEY or not PERPLEXITY_API_KEY.startswith("pplx-"):
        logging.warning("PERPLEXITY_API_KEY is not set correctly. Perplexity features will be disabled.")

    if w3_bsc and w3_bsc.is_connected(): logging.info(f"BSC connected. Chain ID: {w3_bsc.eth.chain_id}")
    else: logging.warning("BSC connection failed")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # Conversation handlers
    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_set_house_balance$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_limits$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_set_daily_bonus$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_search_user$"),
            CallbackQueryHandler(admin_actions_callback, pattern="^admin_broadcast$"),
            CallbackQueryHandler(admin_gift_code_create_step1, pattern="^admin_gift_create$"),
        ],
        states={
            ADMIN_SET_HOUSE_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_house_balance_step)],
            ADMIN_LIMITS_CHOOSE_TYPE: [CallbackQueryHandler(admin_limits_choose_type_step, pattern="^admin_limit_type_")],
            ADMIN_LIMITS_CHOOSE_GAME: [CallbackQueryHandler(admin_limits_choose_game_step, pattern="^admin_limit_game_")],
            ADMIN_LIMITS_SET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_limits_set_amount_step)],
            ADMIN_SET_DAILY_BONUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_daily_bonus_step)],
            ADMIN_SEARCH_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_search_user_step)],
            ADMIN_BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_step)],
            ADMIN_GIFT_CODE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_code_create_step2)],
            ADMIN_GIFT_CODE_CLAIMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_code_create_step3)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_dashboard_command, pattern="^admin_dashboard$"),
            CallbackQueryHandler(admin_bot_settings_callback, pattern="^admin_bot_settings$"),
            CallbackQueryHandler(admin_gift_code_menu, pattern="^admin_gift_codes$"),
            # --- FIX STARTS HERE ---
            # Add a generic cancel handler that returns to the main admin dashboard
            # and properly ends the conversation. This will fix the stuck state issue.
            CallbackQueryHandler(admin_dashboard_command, pattern="^cancel_admin_action$"),
        ],
        # --- FIX ENDS HERE ---
        per_user=True,
        per_chat=True,
        conversation_timeout=timedelta(minutes=5).total_seconds()
    )

    game_setup_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_game_conversation, pattern="^game_(mines|tower)_start$"),
            CommandHandler("mines", start_game_conversation_from_command),
            CommandHandler("tr", start_game_conversation_from_command),
        ],
        states={
            SELECT_BOMBS: [CallbackQueryHandler(select_bombs_callback)],
            SELECT_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_bet_amount_step)],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_conversation, pattern="^cancel_game$")],
        per_message=False,
        conversation_timeout=timedelta(minutes=2).total_seconds()
    )

    pvb_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_pvb_conversation, pattern="^pvb_start_")],
        states={
            SELECT_BET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pvb_get_bet_amount)],
            SELECT_TARGET_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pvb_get_target_score)],
        },
        fallbacks=[CallbackQueryHandler(cancel_game_conversation, pattern="^cancel_game$")],
        per_message=False,
        conversation_timeout=timedelta(minutes=2).total_seconds()
    )
    ai_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ai_conversation, pattern="^main_ai$")],
        states={
            CHOOSE_AI_MODEL: [CallbackQueryHandler(choose_ai_model_callback)],
            ASK_AI_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_conversation_prompt)],
        },
        fallbacks=[CallbackQueryHandler(cancel_ai_conversation, pattern="^cancel_ai$")],
        per_message=False,
        conversation_timeout=timedelta(minutes=5).total_seconds()
    )
    
    recovery_settings_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_callback_handler, pattern="^settings_recovery$")],
        states={
            SETTINGS_RECOVERY_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_recovery_pin_step)]
        },
        fallbacks=[CallbackQueryHandler(settings_command, pattern="^main_settings$")],
        per_user=True,
        conversation_timeout=timedelta(minutes=2).total_seconds()
    )

    recovery_handler = ConversationHandler(
        entry_points=[CommandHandler("recover", recover_command)],
        states={
            RECOVER_ASK_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recover_token_step)],
            RECOVER_ASK_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recover_pin_step)],
        },
        fallbacks=[CallbackQueryHandler(cancel_recovery_conversation, pattern="^cancel_recovery$")],
        per_user=True,
        conversation_timeout=timedelta(minutes=3).total_seconds()
    )


    app.add_handler(CommandHandler("start", start_command, block=False))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler(["bj", "blackjack"], blackjack_command)); app.add_handler(CommandHandler("flip", coin_flip_command))
    app.add_handler(CommandHandler(["roul", "roulette"], roulette_command)); app.add_handler(CommandHandler("dr", dice_roll_command))
    app.add_handler(CommandHandler("sl", slots_command)); app.add_handler(CommandHandler("bank", bank_command))
    app.add_handler(CommandHandler("rain", rain_command)); app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command)); app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("darts", darts_command)); app.add_handler(CommandHandler("goal", football_command))
    app.add_handler(CommandHandler("bowl", bowling_command)); app.add_handler(CommandHandler("deposit", deposit_command))
    app.add_handler(CommandHandler("fundgas", fund_gas_command)); app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("clearall", clearall_command))
    app.add_handler(CommandHandler(["bal", "balance"], balance_command)); app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("cashout", cashout_command)); app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("stop", stop_command)); app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("cancelall", cancel_all_command)); app.add_handler(CommandHandler("predict", predict_command))
    app.add_handler(CommandHandler(["escrow", "esc"], escrow_command))
    app.add_handler(CommandHandler(["matches", "hc"], matches_command));
    app.add_handler(CommandHandler(["deals", "he"], deals_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("continue", continue_command))
    # New commands
    app.add_handler(CommandHandler("kick", kick_command)); app.add_handler(CommandHandler("promote", promote_command))
    app.add_handler(CommandHandler("pin", pin_command)); app.add_handler(CommandHandler("purge", purge_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("user", user_info_command))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("p", price_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("achievements", achievements_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("admin", admin_dashboard_command))
    app.add_handler(CommandHandler("setbal", setbal_command))
    app.add_handler(CommandHandler("games", games_menu)) # New alias
    app.add_handler(CommandHandler("active", active_games_command)) # NEW
    app.add_handler(CommandHandler("activeall", active_all_games_command)) # NEW
    app.add_handler(CommandHandler("reset", reset_recovery_command)) # NEW
    app.add_handler(CommandHandler("export", export_command)) # NEW
    app.add_handler(CommandHandler("claim", claim_gift_code_command)) # NEW
    app.add_handler(CommandHandler("leaderboardrf", leaderboard_referral_command)) # NEW
    app.add_handler(CommandHandler("weekly", weekly_bonus_command)) # NEW
    app.add_handler(CommandHandler("monthly", monthly_bonus_command)) # NEW
    app.add_handler(CommandHandler("rk", rakeback_command)) # NEW
    app.add_handler(CommandHandler("level", level_command)) # NEW
    app.add_handler(CommandHandler("levelall", level_all_command)) # NEW
    # New Group Management Commands
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("translate", translate_command))
    app.add_handler(CommandHandler("lockall", lockall_command))
    app.add_handler(CommandHandler("unlockall", unlockall_command))
    # ... inside main() function, with other CommandHandlers
    app.add_handler(CommandHandler("lb", limbo_command)) # NEW
    app.add_handler(CommandHandler("rps", rps_command)) # NEW
    app.add_handler(CommandHandler("ttt", ttt_command)) # NEW

    # ... with other CallbackQueryHandlers
    app.add_handler(CallbackQueryHandler(rps_callback, pattern=r"^rps_")) # NEW
    app.add_handler(CallbackQueryHandler(ttt_callback, pattern=r"^ttt_")) # NEW
    
    # REMOVED bonus_callback_handler as it's no longer in the main menu
    app.add_handler(admin_handler)
    app.add_handler(game_setup_handler)
    app.add_handler(pvb_handler)
    app.add_handler(ai_handler)
    app.add_handler(recovery_settings_handler)
    app.add_handler(recovery_handler)

    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^(main_|back_to_main|my_matches|my_deals)"))
    app.add_handler(CallbackQueryHandler(games_category_callback, pattern=r"^games_category_")) # NEW
    app.add_handler(CallbackQueryHandler(level_all_command, pattern=r"^level_all$")) # NEW
    app.add_handler(CallbackQueryHandler(price_update_callback, pattern=r"^price_update_")) # NEW
    app.add_handler(CallbackQueryHandler(game_info_callback, pattern=r"^game_")); app.add_handler(CallbackQueryHandler(blackjack_callback, pattern=r"^bj_"))
    app.add_handler(CallbackQueryHandler(coin_flip_callback, pattern=r"^flip_")); app.add_handler(CallbackQueryHandler(tower_callback, pattern=r"^tower_"))
    app.add_handler(CallbackQueryHandler(clear_confirm_callback, pattern=r"^(clear|clearall)_confirm_")); app.add_handler(CallbackQueryHandler(deposit_method_callback, pattern="^deposit_"))
    app.add_handler(CallbackQueryHandler(match_invite_callback, pattern=r"^(accept_|decline_)")); app.add_handler(CallbackQueryHandler(mines_pick_callback, pattern=r"^mines_"))
    app.add_handler(CallbackQueryHandler(stop_confirm_callback, pattern=r"^stop_confirm_")); app.add_handler(CallbackQueryHandler(pvb_menu_callback, pattern="^(pvb_|pvp_)"))
    app.add_handler(CallbackQueryHandler(escrow_callback_handler, pattern=r"^escrow_")); app.add_handler(CallbackQueryHandler(users_navigation_callback, pattern=r"^users_"))
    app.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))
    app.add_handler(CallbackQueryHandler(admin_actions_callback, pattern=r"^admin_(dashboard|users|bot_settings|toggle_maintenance|broadcast|set_house_balance|limits|gift_codes|toggle_withdrawals|toggle_deposits)"))
    app.add_handler(CallbackQueryHandler(admin_user_search_callback, pattern=r"^admin_user_"))
    app.add_handler(CallbackQueryHandler(settings_callback_handler, pattern=r"^settings_"))
    app.add_handler(CallbackQueryHandler(active_all_navigation_callback, pattern=r"^activeall_"))


    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_listener))
    app.add_handler(MessageHandler(filters.Dice.ALL & ~filters.FORWARDED, message_listener))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, message_listener)) # For welcome message

    if app.job_queue:
        app.job_queue.run_repeating(check_addresses_for_gas, interval=3600, first=10)
        # Recover jobs on restart from saved state
        for user_id, session in user_deposit_sessions.items():
            try:
                expiry_str = session.get("expiry")
                if isinstance(expiry_str, str):
                    expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                elif isinstance(expiry_str, datetime):
                     expiry = expiry_str
                else: continue

                if expiry > datetime.now(timezone.utc):
                    job_data = {"address": session["address"], "method": session["method"], "address_index": session["address_index"]}
                    app.job_queue.run_repeating(monitor_deposit, interval=30, first=10, data=job_data, name=f"deposit_{user_id}", user_id=user_id)
                    expiry_seconds = (expiry - datetime.now(timezone.utc)).total_seconds()
                    if expiry_seconds > 0:
                        app.job_queue.run_once(expire_deposit_session, when=expiry_seconds, data={"user_id": user_id}, name=f"expire_{user_id}")
                    logging.info(f"Recovered deposit session job for user {user_id}")
            except Exception as e: logging.error(f"Error recovering deposit job for user {user_id}: {e}")

        for deal_id, deal in escrow_deals.items():
            if deal.get("status") == "accepted_awaiting_deposit":
                logging.info(f"Recovered active escrow deal {deal_id}, restarting monitor.")
                app.job_queue.run_repeating(monitor_escrow_deposit, interval=20, first=10, data={'deal_id': deal_id}, name=f"escrow_monitor_{deal_id}")
    else:
        logging.warning("Job queue not available.")

    print("Bot started successfully with all new features!")
    print("Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

## NEW/IMPROVED CONVERSATION AND GAME FLOWS ##
@check_maintenance
async def start_game_conversation_from_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command = update.message.text.split()[0].lower()
    game_type = 'mines' if command == '/mines' else 'tower'
    context.user_data['game_type'] = game_type

    if game_type == 'mines':
        buttons = [[InlineKeyboardButton(str(i), callback_data=f"bombs_{i}") for i in range(row, row + 8)] for row in range(1, 25, 8)]
        text = "💣 Select the number of mines (1-24):"
    else: # tower
        buttons = [[InlineKeyboardButton(f"{i}", callback_data=f"bombs_{i}") for i in range(1, 4)]]
        text = "🏗️ Select the number of bombs per row (1-3):"

    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel_game")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_BOMBS

@check_maintenance
async def start_game_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    game_type = 'mines' if 'mines' in query.data else 'tower'
    context.user_data['game_type'] = game_type

    if game_type == 'mines':
        buttons = [[InlineKeyboardButton(str(i), callback_data=f"bombs_{i}") for i in range(row, row + 8)] for row in range(1, 25, 8)]
        text = "💣 Select the number of mines (1-24):"
    else: # tower
        buttons = [[InlineKeyboardButton(f"{i}", callback_data=f"bombs_{i}") for i in range(1, 4)]]
        text = "🏗️ Select the number of bombs per row (1-3):"

    buttons.append([InlineKeyboardButton("Cancel", callback_data="cancel_game")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_BOMBS

async def select_bombs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    bombs = query.data.split("_")[1]
    context.user_data['bombs'] = bombs
    await query.edit_message_text(f"Bombs set to {bombs}. Now, please enter your bet amount (or 'all').", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
    return SELECT_BET_AMOUNT

async def select_bet_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game_type = context.user_data['game_type']
    if game_type == 'mines':
        return await mines_command(update, context)
    elif game_type == 'tower':
        return await tower_command(update, context)

@check_maintenance
async def start_pvb_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    game_map = {"dice_bot": "dice", "football": "goal", "darts": "darts", "bowling": "bowl"}
    game_key = query.data.replace("pvb_start_", "")
    game_type = game_map.get(game_key, game_key)
    context.user_data['game_type'] = game_type

    await query.edit_message_text("Please enter your bet amount for this game (or 'all').", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
    return SELECT_BET_AMOUNT

async def pvb_get_bet_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    try:
        bet_amount_str = update.message.text.lower()
        if bet_amount_str == 'all':
            bet_amount = user_wallets.get(user.id, 0.0)
        else:
            bet_amount = float(bet_amount_str)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    await ensure_user_in_wallets(user.id, user.username, context=context)
    if not await check_bet_limits(update, bet_amount, f"pvb_{context.user_data['game_type']}"):
        return SELECT_BET_AMOUNT

    if user_wallets.get(user.id, 0.0) < bet_amount:
        await update.message.reply_text("You don't have enough balance. Please enter a lower amount.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_BET_AMOUNT

    context.user_data['bet_amount'] = bet_amount
    await update.message.reply_text("Bet amount set. Now, please enter the points target (e.g., ft1, ft3, ft5).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
    return SELECT_TARGET_SCORE

async def pvb_get_target_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = update.message.text.lower()
        if not text.startswith("ft") or not text[2:].isdigit():
            raise ValueError

        target_score = int(text[2:])
        if not 1 <= target_score <= 10:
            await update.message.reply_text("Please enter a valid target between ft1 and ft10.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
            return SELECT_TARGET_SCORE

    except (ValueError, IndexError):
        await update.message.reply_text("Invalid format. Please enter the target score as ftX (e.g., ft3).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_game")]]))
        return SELECT_TARGET_SCORE

    game_type = context.user_data['game_type']
    await play_vs_bot_game(update, context, game_type, target_score)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_game_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Game setup cancelled.")
    context.user_data.clear()
    await start_command_inline(query, context) # Go back to main menu
    return ConversationHandler.END

## NEW FEATURE - AI Conversation Flow ##
@check_maintenance
async def start_ai_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🧠 Perplexity (Online)", callback_data="ai_model_perplexity")],
        [InlineKeyboardButton("🆓 GPT4Free (Free)", callback_data="ai_model_g4f")],
        [InlineKeyboardButton("🔙 Cancel & Back to Menu", callback_data="cancel_ai")]
    ]
    await query.edit_message_text(
        "🤖 <b>AI Assistant</b>\n\nWhich AI model would you like to use?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_AI_MODEL

async def choose_ai_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    model_choice = query.data.split('_')[-1]
    context.user_data['ai_model'] = model_choice

    await query.edit_message_text(
        f"🤖 <b>AI Assistant ({model_choice.title()})</b>\n\nI'm ready to help! What's on your mind? Ask me anything.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel & Back to Menu", callback_data="cancel_ai")]])
    )
    return ASK_AI_PROMPT

async def ai_conversation_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    model_choice = context.user_data.get('ai_model')
    if not model_choice:
        await update.message.reply_text("An error occurred. Please start the AI assistant again.")
        context.user_data.clear()
        await start_command(update, context)
        return ConversationHandler.END

    prompt = update.message.text
    await process_ai_request(update, prompt, model_choice)

    # Prompt again for the next question
    await update.message.reply_text(
        "What else can I help you with?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel & Back to Menu", callback_data="cancel_ai")]])
    )
    return ASK_AI_PROMPT

async def cancel_ai_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await start_command_inline(query, context) # Go back to main menu
    return ConversationHandler.END

# --- NEW Bonus & Rakeback System ---
async def bonuses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="main_daily")],
        [InlineKeyboardButton("📅 Weekly Bonus", callback_data="bonus_weekly")],
        [InlineKeyboardButton("🗓️ Monthly Bonus", callback_data="bonus_monthly")],
        [InlineKeyboardButton("💰 Rakeback", callback_data="bonus_rakeback")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        "🎁 <b>Bonuses & Rakeback</b> 🎁\n\n"
        "Claim your rewards for playing! Choose an option below.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def bonus_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    action = query.data.split('_')[1]
    
    if action == "weekly":
        await weekly_bonus_command(update, context, from_callback=True)
    elif action == "monthly":
        await monthly_bonus_command(update, context, from_callback=True)
    elif action == "rakeback":
        await rakeback_command(update, context, from_callback=True)

@check_maintenance
async def weekly_bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    stats = user_stats[user.id]
    
    last_claim_str = stats.get("last_weekly_claim")
    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        if datetime.now(timezone.utc) - last_claim_time < timedelta(days=7):
            time_left = timedelta(days=7) - (datetime.now(timezone.utc) - last_claim_time)
            await update.message.reply_text(f"You've already claimed your weekly bonus. Try again in {time_left.days}d {time_left.seconds//3600}h.")
            return

    now = datetime.now(timezone.utc)
    one_week_ago = now - timedelta(days=7)
    wagered_last_week = sum(h['amount'] for h in stats.get('bets', {}).get('history', []) if datetime.fromisoformat(h['timestamp']) >= one_week_ago)
    
    bonus = wagered_last_week * 0.005 # 0.5%
    
    if bonus > 0:
        user_wallets[user.id] += bonus
        stats["last_weekly_claim"] = str(now)
        save_user_data(user.id)
        await update.message.reply_text(f"🎉 You've claimed your weekly bonus of ${bonus:.2f} (0.5% of ${wagered_last_week:.2f} wagered).")
    else:
        await update.message.reply_text("You haven't wagered anything in the last 7 days to claim a weekly bonus.")

@check_maintenance
async def monthly_bonus_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    stats = user_stats[user.id]
    
    last_claim_str = stats.get("last_monthly_claim")
    if last_claim_str:
        last_claim_time = datetime.fromisoformat(last_claim_str)
        if datetime.now(timezone.utc) - last_claim_time < timedelta(days=30):
            time_left = timedelta(days=30) - (datetime.now(timezone.utc) - last_claim_time)
            await update.message.reply_text(f"You've already claimed your monthly bonus. Try again in {time_left.days}d {time_left.seconds//3600}h.")
            return

    now = datetime.now(timezone.utc)
    one_month_ago = now - timedelta(days=30)
    wagered_last_month = sum(h['amount'] for h in stats.get('bets', {}).get('history', []) if datetime.fromisoformat(h['timestamp']) >= one_month_ago)
    
    bonus = wagered_last_month * 0.003 # 0.3%
    
    if bonus > 0:
        user_wallets[user.id] += bonus
        stats["last_monthly_claim"] = str(now)
        save_user_data(user.id)
        await update.message.reply_text(f"🎉 You've claimed your monthly bonus of ${bonus:.2f} (0.3% of ${wagered_last_month:.2f} wagered).")
    else:
        await update.message.reply_text("You haven't wagered anything in the last 30 days to claim a monthly bonus.")
@check_maintenance
async def rakeback_command(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user = update.effective_user
    await ensure_user_in_wallets(user.id, user.username, context=context)
    stats = user_stats[user.id]
    
    total_wagered = stats.get("bets", {}).get("amount", 0.0)
    last_claim_wager = stats.get("last_rakeback_claim_wager", 0.0)
    
    wagered_since_last_claim = total_wagered - last_claim_wager
    
    if wagered_since_last_claim <= 0:
        message = "You have no new wagers to claim rakeback on. Play some games!"
        if from_callback:
            await update.callback_query.answer(message, show_alert=True)
        else:
            await update.message.reply_text(message)
        return
        
    current_level = get_user_level(user.id)
    rakeback_percentage = current_level["rakeback_percentage"] / 100 # Convert from 1% to 0.01
    
    rakeback_amount = wagered_since_last_claim * rakeback_percentage
    
    user_wallets[user.id] += rakeback_amount
    stats["last_rakeback_claim_wager"] = total_wagered
    save_user_data(user.id)
    
    message = f"💰 You have claimed ${rakeback_amount:.4f} in rakeback from ${wagered_since_last_claim:.2f} wagered at a rate of {current_level['rakeback_percentage']}%."
    
    if from_callback:
        # Go back to the bonuses menu after claiming
        keyboard = [[InlineKeyboardButton("🔙 Back to Bonuses", callback_data="main_bonuses")]]
        await update.callback_query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(f"💰 You have claimed ${rakeback_amount:.4f} in rakeback from ${wagered_since_last_claim:.2f} wagered.")

# --- NEW Gift Code System ---
async def admin_gift_code_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "🎁 <b>Gift Code Management</b>\n\nExisting codes:\n"
    if not gift_codes:
        text += "No active gift codes."
    else:
        for code, data in gift_codes.items():
            text += f"• <code>{code}</code>: ${data['amount']:.2f}, {data['claims_left']}/{data['total_claims']} left\n"
            
    keyboard = [
        [InlineKeyboardButton("➕ Create New Code", callback_data="admin_gift_create")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_dashboard")]
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    
async def admin_gift_code_create_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Enter the amount (e.g., 5.50) for the new gift code.",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_gift_codes")]]))
    return ADMIN_GIFT_CODE_AMOUNT

async def admin_gift_code_create_step2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0: raise ValueError
        context.user_data['gift_code_amount'] = amount
        await update.message.reply_text("Amount set. Now enter the maximum number of times this code can be claimed.",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_gift_codes")]]))
        return ADMIN_GIFT_CODE_CLAIMS
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a positive number.")
        return ADMIN_GIFT_CODE_AMOUNT

async def admin_gift_code_create_step3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        claims = int(update.message.text)
        if claims <= 0: raise ValueError
        amount = context.user_data['gift_code_amount']
        
        code = f"GIFT-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
        gift_codes[code] = {
            "amount": amount,
            "total_claims": claims,
            "claims_left": claims,
            "claimed_by": [],
            "created_by": update.effective_user.id,
            "created_at": str(datetime.now(timezone.utc))
        }
        save_gift_code(code)
        
        await update.message.reply_text(f"✅ Gift code created successfully!\n\nCode: <code>{code}</code>\nAmount: ${amount:.2f}\nUses: {claims}")
        context.user_data.clear()
        
        # Fake query to go back to the menu
        class FakeQuery:
            def __init__(self, user, message): self.from_user = user; self.message = message
            async def answer(self): pass
            async def edit_message_text(self, *args, **kwargs): await message.reply_text(*args, **kwargs)
        fake_update = type('FakeUpdate', (), {'callback_query': FakeQuery(update.effective_user, update.message)})()
        await admin_gift_code_menu(fake_update, context)
        
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Invalid number. Please enter a positive integer.")
        return ADMIN_GIFT_CODE_CLAIMS

if __name__ == "__main__":
    main()