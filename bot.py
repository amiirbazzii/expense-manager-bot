# bot.py
import logging
import os
import re
from datetime import datetime, date, timedelta
import calendar # For month name to number
from typing import Optional, Tuple
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

# --- Registration Command Handlers (Keep as is from previous steps) ---
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
                "password": password, # REMINDER: Ensure this is hashed in Convex (auth.ts)
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

# --- Helper function to parse date string for /log command ---
def parse_date_to_timestamp(date_str: Optional[str]) -> int:
    target_date = date.today()
    if date_str:
        date_str_lower = date_str.strip().lower()
        if not date_str_lower:
            target_date = date.today()
        elif date_str_lower == "today":
            target_date = date.today()
        elif date_str_lower == "yesterday":
            target_date = date.today() - timedelta(days=1)
        else:
            doc = nlp(date_str_lower)
            parsed_date_from_nlp = None
            for ent in doc.ents:
                if ent.label_ == "DATE":
                    try:
                        temp_date = datetime.strptime(ent.text, "%Y-%m-%d").date()
                        parsed_date_from_nlp = temp_date
                        break
                    except ValueError:
                        try:
                            temp_date = datetime.strptime(ent.text, "%m/%d/%Y").date()
                            parsed_date_from_nlp = temp_date
                            break
                        except ValueError:
                             try:
                                temp_date = datetime.strptime(ent.text, "%B %d").date().replace(year=date.today().year)
                                parsed_date_from_nlp = temp_date
                                break
                             except ValueError:
                                logger.warning(f"Could not parse DATE entity '{ent.text}' from '{date_str_lower}' using simple strptime.")
                                pass
            if parsed_date_from_nlp:
                target_date = parsed_date_from_nlp
            elif date_str_lower:
                logger.warning(f"Could not parse date string '{date_str_lower}' into an absolute date via NLP. Defaulting to today.")
    dt_obj = datetime(target_date.year, target_date.month, target_date.day)
    return int(dt_obj.timestamp() * 1000)

# --- /log Command Handler (Keep as is from previous steps) ---
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
        r"^(.*?)\s+on\s+(.+?)(?:\s+for\s+(.+?))?(?:\s+on\s+([a-zA-Z0-9\s\-/]+.*))?$",
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
            if ent.label_ == "MONEY" or ent.label_ == "CARDINAL":
                amount_val_str = ent.text.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                try:
                    amount = float(amount_val_str)
                    parsed_amount_successfully = True
                    break
                except ValueError:
                    logger.warning(f"Could not convert MONEY/CARDINAL entity '{ent.text}' to float.")
        if not parsed_amount_successfully:
            amount_val_str = re.sub(r"[^\d\.]", "", amount_str)
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
                f"Amount: ${amount:.2f}\n"
                f"Category: {expense_data['category']}\n"
                f"Date: {logged_date_obj.strftime('%Y-%m-%d (%A)')}"
                + (f"\nDescription: {expense_data['description']}" if expense_data['description'] else "")
            )
        else:
            error_msg = result.get("error", "Failed to log expense. Unknown error.") if result else "Failed to log expense. No response."
            await update.message.reply_text(f"⚠️ Error: {error_msg}")
    except Exception as e:
        logger.error(f"Error calling Convex logExpense mutation: {e}")
        await update.message.reply_text(f"⚠️ An error occurred while logging your expense: {str(e)}")


# --- Helper function to parse period string for /summary ---
def parse_period_to_date_range(period_str: Optional[str]) -> Tuple[int, int]:
    today = date.today()
    year = today.year
    month = today.month

    if not period_str or period_str.lower() == "this month":
        start_date = date(year, month, 1)
        _, last_day_of_month = calendar.monthrange(year, month)
        end_date = date(year, month, last_day_of_month)
    elif period_str.lower() == "last month":
        first_day_of_current_month = date(year, month, 1)
        last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
        start_date = date(last_day_of_last_month.year, last_day_of_last_month.month, 1)
        end_date = last_day_of_last_month
    else:
        parsed_specific_month = False
        try:
            dt_obj = datetime.strptime(period_str.strip(), "%B %Y")
            year, month = dt_obj.year, dt_obj.month
            parsed_specific_month = True
        except ValueError:
            try:
                dt_obj = datetime.strptime(period_str.strip(), "%B")
                month = dt_obj.month
                parsed_specific_month = True
            except ValueError:
                try:
                    year_month = period_str.strip().split('-')
                    if len(year_month) == 2:
                        year, month = int(year_month[0]), int(year_month[1])
                        parsed_specific_month = True
                    else:
                        raise ValueError("Not YYYY-MM")
                except (ValueError, IndexError):
                    try:
                        month_year = period_str.strip().split('/')
                        if len(month_year) == 2:
                             month, year = int(month_year[0]), int(month_year[1])
                             parsed_specific_month = True
                        else:
                            raise ValueError("Not MM/YYYY")
                    except (ValueError, IndexError):
                        logger.warning(f"Could not parse period string '{period_str}'. Defaulting to 'this month'.")
                        start_date = date(today.year, today.month, 1)
                        _, last_day_of_month = calendar.monthrange(today.year, today.month)
                        end_date = date(today.year, today.month, last_day_of_month)
                        # This assignment ensures the default is set if all parsing fails
                        parsed_specific_month = True # Treat as handled to avoid re-assigning start_date/end_date

        if parsed_specific_month: # This will be true if any parsing succeeded or if it defaulted
             # If it defaulted above, start_date and end_date are already set
            if not ('start_date' in locals() and 'end_date' in locals()): # Check if not already set by default case
                start_date = date(year, month, 1)
                _, last_day_of_month = calendar.monthrange(year, month)
                end_date = date(year, month, last_day_of_month)

    start_timestamp_ms = int(datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0).timestamp() * 1000)
    end_timestamp_ms = int(datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999).timestamp() * 1000)
    
    return start_timestamp_ms, end_timestamp_ms


# --- /summary Command Handler ---
async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_chat_id = str(update.message.from_user.id)
    args_str = update.message.text.split('/summary', 1)[1].strip() if '/summary' in update.message.text else ""
    
    logger.info(f"User {telegram_chat_id} sent /summary command with args: '{args_str}'")

    category: Optional[str] = None
    period_str: Optional[str] = None
    
    known_periods = ["this month", "last month"]
    found_known_period = False
    temp_args_str = args_str.lower() # Work with a lowercase copy for matching

    for kp in known_periods:
        if kp in temp_args_str:
            period_str = kp
            # Remove the known period from args_str to isolate potential category
            # Use regex replace for case-insensitivity and ensure only whole word match if possible
            # For simplicity, simple replace for now.
            # This might be problematic if category name contains "this month" etc.
            temp_args_str = temp_args_str.replace(kp, "").strip()
            if temp_args_str: 
                category = temp_args_str # What's left is category
            found_known_period = True
            break
    
    if not found_known_period:
        parts = args_str.split() # Use original args_str for splitting category
        if not parts:
            period_str = "this month"
        elif len(parts) == 1:
            # Try to parse as period first. If it defaults, assume it's a category.
            # This logic needs to be careful not to misinterpret a category as a period.
            parsed_start, parsed_end = parse_period_to_date_range(parts[0])
            default_start, default_end = parse_period_to_date_range("this month") # Get default range
            
            # If parse_period_to_date_range returns the default range for an input that isn't "this month",
            # it's likely the input was not a recognized period.
            if parsed_start == default_start and parsed_end == default_end and parts[0].lower() != "this month":
                 category = parts[0]
                 period_str = "this month"
            else:
                 period_str = parts[0]
        else: 
            # Try last two words as period
            potential_period_2_words = " ".join(parts[-2:])
            parsed_start_2, parsed_end_2 = parse_period_to_date_range(potential_period_2_words)
            default_start, default_end = parse_period_to_date_range("this month")

            if not (parsed_start_2 == default_start and parsed_end_2 == default_end and potential_period_2_words.lower() != "this month"):
                period_str = potential_period_2_words
                category = " ".join(parts[:-2]).strip() if len(parts[:-2]) > 0 else None
            else: 
                potential_period_1_word = parts[-1]
                parsed_start_1, parsed_end_1 = parse_period_to_date_range(potential_period_1_word)
                if not (parsed_start_1 == default_start and parsed_end_1 == default_end and potential_period_1_word.lower() != "this month"):
                    period_str = potential_period_1_word
                    category = " ".join(parts[:-1]).strip() if len(parts[:-1]) > 0 else None
                else: 
                    category = " ".join(parts).strip()
                    period_str = "this month"
    
    if not period_str: 
        period_str = "this month"
    if category and not category.strip():
        category = None

    logger.info(f"Refined summary request: Category='{category}', Period='{period_str}'")

    start_timestamp_ms, end_timestamp_ms = parse_period_to_date_range(period_str)
    
    display_period_start_dt = datetime.fromtimestamp(start_timestamp_ms/1000)
    display_period_end_dt = datetime.fromtimestamp(end_timestamp_ms/1000)
    
    display_period = f"{display_period_start_dt.strftime('%b %d, %Y')} to {display_period_end_dt.strftime('%b %d, %Y')}"
    # More user-friendly period display
    if period_str:
        if period_str.lower() == "this month":
            display_period = f"This Month ({display_period_start_dt.strftime('%B %Y')})"
        elif period_str.lower() == "last month":
            display_period = f"Last Month ({display_period_start_dt.strftime('%B %Y')})"
        # Check if the original period_str was just a month name or "Month Year"
        elif display_period_start_dt.day == 1 and \
             display_period_end_dt.day == calendar.monthrange(display_period_end_dt.year, display_period_end_dt.month)[1]:
            # It's a full month
            display_period = display_period_start_dt.strftime("%B %Y")


    query_args = {
        "telegramChatId": telegram_chat_id,
        "startDate": start_timestamp_ms,
        "endDate": end_timestamp_ms,
    }
    if category:
        query_args["category"] = category.strip()

    await update.message.reply_text(f"Fetching summary for {display_period}" + (f" in category '{category.strip()}'..." if category else "..."))

    try:
        # Corrected path to the Convex query function
        summary_result = convex_client.query("queries:getExpenseSummary", query_args) # <--- UPDATED HERE
        
        if summary_result:
            count = summary_result.get("count", 0)
            total_amount = summary_result.get("totalAmount", 0.0)
            
            response_message = f"📊 Expense Summary for {display_period}:\n"
            if summary_result.get("category"): # Use category from result for consistency
                response_message += f"Category: {summary_result['category']}\n"
            response_message += f"Total Expenses: {count}\n"
            response_message += f"Total Amount: ${total_amount:.2f}"

            await update.message.reply_text(response_message)
        else:
            await update.message.reply_text("Could not retrieve summary. No data found or an error occurred.")

    except Exception as e:
        logger.error(f"Error calling Convex getExpenseSummary query: {e}")
        # Provide more specific error if Convex returns one
        if "Function not found" in str(e):
             await update.message.reply_text(f"⚠️ Error: The summary function was not found on the server. Please check backend deployment.")
        else:
            await update.message.reply_text(f"⚠️ An error occurred while fetching your summary: {str(e)}")


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
    application.add_handler(CommandHandler("summary", summary_command))

    logger.info("Bot starting with /log and /summary commands enabled...")
    application.run_polling()

if __name__ == "__main__":
    main()
