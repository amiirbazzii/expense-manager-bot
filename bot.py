# bot.py
import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from convex import ConvexClient
import spacy # We'll use this later for /log

# Load environment variables from .env file
load_dotenv(dotenv_path=".env.local") 

# --- Environment Variable Checks ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CONVEX_URL = os.getenv("CONVEX_URL")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in .env file. Please add it.")
if not CONVEX_URL:
    raise ValueError("CONVEX_URL not found in .env file. Please add it.")

# --- Convex Client Initialization ---
# Make sure your CONVEX_URL is correctly set in your .env file
# e.g., CONVEX_URL="https://your-project-name.convex.cloud"
try:
    convex_client = ConvexClient(CONVEX_URL)
except Exception as e:
    print(f"Error initializing Convex client: {e}")
    print(f"Ensure CONVEX_URL ('{CONVEX_URL}') is correct and your Convex project is deployed.")
    exit()


# --- spaCy Model Loading (for later use) ---
# nlp = spacy.load("en_core_web_sm") # We'll use this in the /log command

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Conversation Handler States for Registration ---
USERNAME, PASSWORD, REG_CONFIRMATION = range(3) # For registration conversation

# --- Registration Command Handler ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks for a username for registration."""
    user_telegram_id = str(update.message.from_user.id)
    logger.info(f"User {user_telegram_id} initiated /start command.")

    # Optional: Check if user is already registered by telegramChatId
    # For now, we'll always initiate registration on /start for simplicity in Phase 1
    # existing_user = convex_client.query("auth:getUserByTelegramId", {"telegramChatId": user_telegram_id}) # You'd need to create this query
    # if existing_user:
    #     await update.message.reply_text("Welcome back! You are already registered. Use /log to add expenses or /summary to view them.")
    #     return ConversationHandler.END

    await update.message.reply_text(
        "Welcome to the Expense Bot! Let's get you registered.\n"
        "Please choose a username (at least 3 characters):"
    )
    return USERNAME

async def received_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the username and asks for a password."""
    username = update.message.text
    if not username or len(username) < 3:
        await update.message.reply_text("Username must be at least 3 characters long. Please try again:")
        return USERNAME # Stay in the USERNAME state

    context.user_data['reg_username'] = username
    logger.info(f"Username received: {username} from user {update.message.from_user.id}")
    await update.message.reply_text(
        f"Great, username '{username}' noted. Now, please enter a password (at least 6 characters):"
    )
    return PASSWORD

async def received_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the password and attempts to register the user with Convex."""
    password = update.message.text
    username = context.user_data.get('reg_username')
    telegram_chat_id = str(update.message.from_user.id) # Get Telegram chat ID

    if not password or len(password) < 6:
        await update.message.reply_text("Password must be at least 6 characters. Please try again:")
        return PASSWORD # Stay in the PASSWORD state

    logger.info(f"Password received for username: {username}. Attempting registration.")
    await update.message.reply_text("Attempting to register you... Please wait.")

    try:
        # Call the Convex mutation to register the user
        result = convex_client.mutation(
            "auth:registerUser", # "auth" is the filename (auth.ts), "registerUser" is the function
            {
                "username": username,
                "password": password, # This will be hashed by the Convex function (ideally)
                "telegramChatId": telegram_chat_id # Store the telegram chat ID
            }
        )
        logger.info(f"Convex registration result for {username}: {result}")

        if result and result.get("success"):
            await update.message.reply_text(
                f"Registration successful! Welcome, {result.get('username')}!\n"
                "You can now use /log to add expenses and /summary to view them."
            )
            context.user_data.clear() # Clear registration data
            return ConversationHandler.END
        else:
            # This part might not be reached if Convex throws an error for "username taken"
            error_message = result.get("error", "Registration failed. Please try again later or contact support.")
            await update.message.reply_text(error_message)
            context.user_data.clear()
            return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error during Convex registration for {username}: {e}")
        # Check if the error message from Convex indicates username taken
        if "Username already taken" in str(e):
            await update.message.reply_text(
                "This username is already taken. Please try /start again with a different username."
            )
        else:
            await update.message.reply_text(
                "An error occurred during registration. Please try again later."
            )
        context.user_data.clear()
        return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the registration conversation."""
    logger.info(f"User {update.message.from_user.first_name} cancelled the registration.")
    await update.message.reply_text(
        "Registration cancelled. Type /start if you want to try again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Main Bot Logic ---
def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Registration Conversation Handler ---
    registration_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command), CommandHandler("register", start_command)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_password)],
            # REG_CONFIRMATION state could be added if you want a final "Yes/No" confirmation
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
         # per_user=True, per_chat=True # Ensure user_data is isolated
    )

    application.add_handler(registration_conv_handler)

    # Add other handlers here later (e.g., for /log, /summary)

    logger.info("Bot starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
