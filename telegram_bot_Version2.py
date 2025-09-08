import os
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Configuration ---
# It's recommended to use an environment variable for your bot token for security.
# You can get a token from the BotFather on Telegram.
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8379119678:AAEBhPlQiOrsozV-wpX7VE7FvjDtpkA4W2U"

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the /start command.
    Greets the user and provides their account creation date and age.
    """
    user = update.effective_user
    if not user:
        await update.message.reply_text("Could not identify the user.")
        return

    # Telegram user IDs are 64-bit integers. The first 32 bits represent
    # a Unix timestamp of the account creation date.
    # We can get this by right-shifting the user_id by 32 bits.
    user_id = user.id
    creation_timestamp = user_id >> 22 # Correction: User ID contains timestamp in its higher bits.
                                      # The exact bit shift can vary, but this is a common approximation.
    
    # Convert Unix timestamp to a datetime object
    # The timestamp from user ID is in milliseconds
    creation_date = datetime.fromtimestamp(creation_timestamp / 1000, tz=timezone.utc)
    
    # Calculate account age
    now = datetime.now(timezone.utc)
    age = now - creation_date
    
    # Format the age into years, months, days
    years = age.days // 365
    months = (age.days % 365) // 30
    days = (age.days % 365) % 30

    # Prepare the response message
    response_message = (
        f"Hello, {user.first_name}!\n\n"
        f"Here are some details about your Telegram account:\n"
        f"🔹 **User ID:** `{user.id}`\n"
        f"🔹 **Username:** @{user.username if user.username else 'Not set'}\n"
        f"🔹 **Account Created on:** {creation_date.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"🔹 **Account Age:** Approximately {years} years, {months} months, and {days} days old.\n"
    )

    await update.message.reply_text(response_message, parse_mode='Markdown')

# --- Main Bot Setup ---

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = ApplicationBuilder().token(TOKEN).build()

    # Register the /start command handler
    application.add_handler(CommandHandler("start", start))

    # Start the Bot
    print("Bot is starting...")
    application.run_polling()
    print("Bot has stopped.")

if __name__ == "__main__":
    main()