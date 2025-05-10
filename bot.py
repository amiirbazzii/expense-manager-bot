# bot.py
import logging
import os
import re # For parsing the /log command
from datetime import datetime, date, timedelta
import calendar # For month name to number
from typing import Optional # <--- ADD THIS IMPORT
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
import spacy

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
try:
    convex_client = ConvexClient(CONVEX_URL)
except Exception as e:
    print(f"Error initializing Convex client: {e}")
    print(f"Ensure CONVEX_URL ('{CONVEX_URL}') is correct and your Convex project is deployed.")
    exit()

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- spaCy Model Loading ---
try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("spaCy model en_core_web_sm loaded successfully.")
except OSError:
    logger.error("spaCy model en_core_web_sm not found. Please run 'python -m spacy download en_core_web_sm'")
    exit()


# --- Conversation Handler States for Registration ---
USERNAME, PASSWORD = range(2)

# --- Registration Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_telegram_id = str(update.message.from_user.id)
    logger.info(f"User {user_telegram_id} initiated /start command.")
    await update.message.reply_text(
        "Welcome to the Expense Bot! Let's get you registered.\n"
        "Please choose a username (at least 3 characters):"
    )
    return USERNAME

async def received_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = update.message.text
    if not username or len(username) < 3:
        await update.message.reply_text("Username must be at least 3 characters long. Please try again:")
        return USERNAME
    context.user_data['reg_username'] = username
    logger.info(f"Username received: {username} from user {update.message.from_user.id}")
    await update.message.reply_text(
        f"Great, username '{username}' noted. Now, please enter a password (at least 6 characters):"
    )
    return PASSWORD

async def received_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    password = update.message.text
    username = context.user_data.get('reg_username')
    telegram_chat_id = str(update.message.from_user.id)

    if not password or len(password) < 6:
        await update.message.reply_text("Password must be at least 6 characters. Please try again:")
        return PASSWORD

    logger.info(f"Password received for username: {username}. Attempting registration.")
    await update.message.reply_text("Attempting to register you... Please wait.")

    try:
        result = convex_client.mutation(
            "auth:registerUser",
            {
                "username": username,
                "password": password,
                "telegramChatId": telegram_chat_id
            }
        )
        logger.info(f"Convex registration result for {username}: {result}")
        if result and result.get("success"):
            await update.message.reply_text(
                f"Registration successful! Welcome, {result.get('username')}!\n"
                "You can now use:\n"
                "/log <amount> on <category> [for <description>] [on <date>]\n"
                "/summary [period]\n"
                "/summary <category> [period]"
            )
        else:
            error_message = result.get("error", "Registration failed. Please try again.")
            await update.message.reply_text(error_message)
    except Exception as e:
        logger.error(f"Error during Convex registration for {username}: {e}")
        if "Username already taken" in str(e):
            await update.message.reply_text(
                "This username is already taken. Please try /start again with a different username."
            )
        elif "Password must be at least 6 characters long" in str(e):
             await update.message.reply_text("Password must be at least 6 characters long. Please try again:")
             return PASSWORD
        else:
            await update.message.reply_text("An error occurred during registration. Please try again later.")
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"User {update.message.from_user.first_name} cancelled the registration.")
    await update.message.reply_text(
        "Registration cancelled. Type /start if you want to try again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    context.user_data.clear()
    return ConversationHandler.END

# --- Helper function to parse date string ---
def parse_date_to_timestamp(date_str: Optional[str]) -> int: # <--- CHANGE HERE
    """
    Parses a date string (e.g., "today", "yesterday", "2023-10-26", "next Friday")
    and returns a Unix timestamp in milliseconds.
    Defaults to today if date_str is None or parsing fails.
    """
    target_date = date.today() # Default to today

    if date_str: # Only process if date_str is not None and not empty
        date_str_lower = date_str.strip().lower()
        if not date_str_lower: # If after stripping it's empty, use today
            target_date = date.today()
        elif date_str_lower == "today":
            target_date = date.today()
        elif date_str_lower == "yesterday":
            target_date = date.today() - timedelta(days=1)
        else:
            doc = nlp(date_str_lower) # Process the lowercased, stripped string
            parsed_date_from_nlp = None
            for ent in doc.ents:
                if ent.label_ == "DATE":
                    # Attempt to parse common absolute date formats directly from entity text
                    # spaCy might give relative dates or more complex strings.
                    # A more robust solution would use dateutil.parser here.
                    try:
                        # Example: "2023-10-26" or "October 26, 2023"
                        # This is a simplification; spaCy's ent.text might not always be a clean date string.
                        # Consider dateutil.parser.parse(ent.text) for more robustness.
                        temp_date = datetime.strptime(ent.text, "%Y-%m-%d").date()
                        parsed_date_from_nlp = temp_date
                        break 
                    except ValueError:
                        try:
                            temp_date = datetime.strptime(ent.text, "%m/%d/%Y").date()
                            parsed_date_from_nlp = temp_date
                            break
                        except ValueError:
                             try: # "october 26" (assumes current year)
                                temp_date = datetime.strptime(ent.text, "%B %d").date().replace(year=date.today().year)
                                parsed_date_from_nlp = temp_date
                                break
                             except ValueError:
                                logger.warning(f"Could not parse DATE entity '{ent.text}' from '{date_str_lower}' using simple strptime. spaCy's raw interpretation might be relative.")
                                # If spaCy gives a relative date like "next Friday", this simple strptime will fail.
                                # For Phase 1, we might default to today if complex parsing fails.
                                pass # Fall through to default if specific parsing fails
            
            if parsed_date_from_nlp:
                target_date = parsed_date_from_nlp
            elif date_str_lower: # If NLP didn't yield a parseable absolute date, but we have a string
                logger.warning(f"Could not parse date string '{date_str_lower}' into an absolute date via NLP. Defaulting to today.")
                # target_date remains today (already set as default)

    dt_obj = datetime(target_date.year, target_date.month, target_date.day)
    return int(dt_obj.timestamp() * 1000)


# --- /log Command Handler ---
async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_chat_id = str(update.message.from_user.id)
    command_args = update.message.text.split('/log', 1)[1].strip() if '/log' in update.message.text else ""

    if not command_args:
        await update.message.reply_text(
            "Please provide expense details after /log.\n"
            "Format: /log <amount> on <category> [for <description>] [on <date>]"
        )
        return

    logger.info(f"User {telegram_chat_id} sent /log command with args: {command_args}")

    pattern = re.compile(
        r"^(.*?)\s+on\s+(.+?)(?:\s+for\s+(.+?))?(?:\s+on\s+([a-zA-Z0-9\s\-/]+.*))?$", # Made date part more greedy
        re.IGNORECASE
    )
    match = pattern.match(command_args)

    if not match:
        await update.message.reply_text(
            "Invalid format. Please use:\n"
            "/log <amount> on <category> [for <description>] [on <date>]\n"
            "Example: /log $10.50 on Coffee for Morning boost on today"
        )
        return

    amount_str, category_str, description_str, date_str = match.groups()
    
    logger.info(f"Parsed from regex: Amount='{amount_str}', Category='{category_str}', Desc='{description_str}', Date='{date_str}'")

    amount = None
    try:
        doc_amount = nlp(amount_str)
        parsed_amount_successfully = False
        for ent in doc_amount.ents:
            if ent.label_ == "MONEY" or ent.label_ == "CARDINAL": # CARDINAL for numbers without currency
                amount_val_str = ent.text.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                try:
                    amount = float(amount_val_str)
                    parsed_amount_successfully = True
                    break
                except ValueError:
                    logger.warning(f"Could not convert MONEY/CARDINAL entity '{ent.text}' to float.")
        
        if not parsed_amount_successfully: # Fallback if no suitable entity found or parsing entity failed
            amount_val_str = re.sub(r"[^\d\.]", "", amount_str) # Keep only digits and dot
            if amount_val_str:
                amount = float(amount_val_str)
            else:
                raise ValueError("No valid numeric amount found.")


        if amount <= 0:
            await update.message.reply_text("Amount must be a positive number.")
            return
    except ValueError as e:
        logger.error(f"Amount parsing error: {e} from input '{amount_str}'")
        await update.message.reply_text(f"Invalid amount: '{amount_str}'. Please enter a valid number.")
        return

    expense_timestamp = parse_date_to_timestamp(date_str.strip() if date_str else None)

    expense_data = {
        "telegramChatId": telegram_chat_id,
        "amount": amount,
        "category": category_str.strip(),
        "description": description_str.strip() if description_str else None,
        "date": expense_timestamp,
    }

    logger.info(f"Logging to Convex: {expense_data}")
    await update.message.reply_text("Logging your expense...")

    try:
        result = convex_client.mutation("expenses:logExpense", expense_data)
        if result and result.get("success"):
            logged_date_obj = datetime.fromtimestamp(expense_timestamp / 1000)
            await update.message.reply_text(
                f"✅ Expense logged successfully!\n"
                f"Amount: ${amount:.2f}\n" # Assuming USD, adjust if needed
                f"Category: {expense_data['category']}\n"
                f"Date: {logged_date_obj.strftime('%Y-%m-%d (%A)')}" # e.g., 2023-10-26 (Thursday)
                + (f"\nDescription: {expense_data['description']}" if expense_data['description'] else "")
            )
        else:
            error_msg = result.get("error", "Failed to log expense. Unknown error.") if result else "Failed to log expense. No response."
            await update.message.reply_text(f"⚠️ Error: {error_msg}")
    except Exception as e:
        logger.error(f"Error calling Convex logExpense mutation: {e}")
        await update.message.reply_text(f"⚠️ An error occurred while logging your expense: {str(e)}")


# --- Main Bot Logic ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    registration_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command), CommandHandler("register", start_command)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
    )
    application.add_handler(registration_conv_handler)
    application.add_handler(CommandHandler("log", log_command))

    logger.info("Bot starting with /log command enabled...")
    application.run_polling()

if __name__ == "__main__":
    main()
