# bot.py
import logging
import os
from dotenv import load_dotenv
from telegram import Update # Added Update import
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes # Explicitly ensuring ContextTypes is available if not already covered
)
from convex import ConvexClient
import spacy
from typing import Dict, List 

# Import handlers and states
from handlers.registration_handler import (
    start_command as registration_start_command,
    received_username as registration_received_username,
    received_password as registration_received_password,
    cancel_registration as registration_cancel,
    USERNAME as REG_USERNAME, 
    PASSWORD as REG_PASSWORD  
)
# Import the refactored log processing function and the entry point for /log command
from handlers.log_handler import (
    process_log_request, # Core logic
    log_command_entry,   # For /log command
    handle_log_confirmation, 
    handle_category_override_selection
)
from handlers.query_handlers import summary_command, details_command, category_command
from handlers.report_handler import report_command
from utils.intent_recognition_utils import get_message_intent, INTENT_LOG_EXPENSE # Import intent utils

# Load environment variables from .env.local file
load_dotenv(dotenv_path=".env.local") 

# --- Global Initializations ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CONVEX_URL = os.getenv("CONVEX_URL")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL") 

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in .env.local file. Please add it.")
if not CONVEX_URL:
    raise ValueError("CONVEX_URL not found in .env.local file. Please add it.")
if not AI_SERVICE_URL: 
    raise ValueError("AI_SERVICE_URL not found in .env.local file. Please add it.")

try:
    convex_client = ConvexClient(CONVEX_URL)
except Exception as e:
    print(f"Error initializing Convex client: {e}")
    exit()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__) 

try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("spaCy model en_core_web_sm loaded successfully.")
except OSError:
    logger.error("spaCy model en_core_web_sm not found. Please run 'python -m spacy download en_core_web_sm'")
    exit()

PREDEFINED_CATEGORIES: Dict[str, List[str]] = {
    "Food & Drink": ["food", "restaurant", "lunch", "dinner", "breakfast", "coffee", "tea", "groceries", "snack", "drinks", "meal", "takeaway", "delivery"],
    "Transport": ["transport", "bus", "train", "taxi", "uber", "lyft", "metro", "subway", "gas", "fuel", "parking", "flight", "car"],
    "Shopping": ["shopping", "clothes", "electronics", "gifts", "books", "online shopping", "amazon", "store"],
    "Utilities": ["utilities", "rent", "mortgage", "electricity", "water", "internet", "phone", "gas bill"],
    "Entertainment": ["entertainment", "movie", "cinema", "concert", "game", "show", "event", "bar", "pub", "party"],
    "Health & Wellness": ["health", "wellness", "doctor", "pharmacy", "medicine", "gym", "fitness", "hospital"],
    "Education": ["education", "school", "college", "university", "course", "books", "tuition"],
    "Travel": ["travel", "holiday", "vacation", "hotel", "accommodation", "trip"],
    "Rent": ["rent", "rental"],
    "Home": ["home", "household", "repair"],
    "Sanitary": ["sanitary", "hygiene", "toiletries"],
    "Selfcare": ["selfcare", "haircut", "salon", "spa", "personal care"],
    "Gift": ["gift", "present"],
    "Installment": ["installment", "loan payment", "credit payment"],
    "Investment": ["investment", "stocks", "gold", "crypto"],
    "Other": ["other", "misc", "miscellaneous"], 
    "Miscellaneous": ["misc", "miscellaneous"], 
}
DEFAULT_CATEGORY = "Other" 

LOG_CONFIRM_YES_PREFIX = "log_confirm_yes_"
LOG_CONFIRM_NO_PREFIX = "log_confirm_no_"
CAT_OVERRIDE_PREFIX = "cat_override_" 
CAT_CANCEL_LOG_PREFIX = "cat_cancel_log_"

# --- New Message Handler for Command-less Intent ---
async def handle_plain_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles plain text messages to determine intent."""
    if not update.message or not update.message.text:
        return 

    user_text = update.message.text
    logger.info(f"Received plain text message from {update.message.from_user.id}: '{user_text}'")

    intent = get_message_intent(user_text, nlp) 

    if intent == INTENT_LOG_EXPENSE:
        logger.info(f"Intent recognized as LOG_EXPENSE for: '{user_text}'")
        await process_log_request(
            update, context, user_text, 
            convex_client, nlp, PREDEFINED_CATEGORIES, DEFAULT_CATEGORY, AI_SERVICE_URL
        )
    else:
        logger.info(f"Intent UNKNOWN or not a log attempt for: '{user_text}'. Ignoring.")


# --- Main Application Setup ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    async def wrapped_registration_start(update, context):
        return await registration_start_command(update, context, convex_client)
    async def wrapped_registration_password(update, context):
        return await registration_received_password(update, context, convex_client)

    registration_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", wrapped_registration_start), CommandHandler("register", wrapped_registration_start)],
        states={
            REG_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, registration_received_username)],
            REG_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_registration_password)],
        },
        fallbacks=[CommandHandler("cancel", registration_cancel)],
    )
    application.add_handler(registration_conv_handler)

    async def wrapped_log_command_entry(update, context): 
        await log_command_entry(update, context, convex_client, nlp, PREDEFINED_CATEGORIES, DEFAULT_CATEGORY, AI_SERVICE_URL)
    
    async def wrapped_summary_command(update, context):
        await summary_command(update, context, convex_client, nlp)
    
    async def wrapped_details_command(update, context):
        await details_command(update, context, convex_client)
    
    async def wrapped_category_command(update, context):
        await category_command(update, context, convex_client, nlp, PREDEFINED_CATEGORIES)
    
    async def wrapped_report_command(update, context):
        await report_command(update, context, convex_client, nlp)
    
    async def wrapped_handle_log_confirmation(update, context):
        await handle_log_confirmation(update, context, convex_client)
    
    async def wrapped_handle_category_override_selection(update, context):
        await handle_category_override_selection(update, context, convex_client)

    # Add Command Handlers
    application.add_handler(CommandHandler("log", wrapped_log_command_entry)) 
    application.add_handler(CommandHandler("summary", wrapped_summary_command))
    application.add_handler(CommandHandler("details", wrapped_details_command))
    application.add_handler(CommandHandler("category", wrapped_category_command))
    application.add_handler(CommandHandler("report", wrapped_report_command))
    
    # Add CallbackQueryHandlers
    application.add_handler(CallbackQueryHandler(wrapped_handle_log_confirmation, pattern=f"^{LOG_CONFIRM_YES_PREFIX}|^^{LOG_CONFIRM_NO_PREFIX}"))
    application.add_handler(CallbackQueryHandler(wrapped_handle_category_override_selection, pattern=f"^{CAT_OVERRIDE_PREFIX}|^^{CAT_CANCEL_LOG_PREFIX}"))

    # Add MessageHandler for plain text (must be after CommandHandlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plain_message))

    logger.info("Bot starting (with command-less log intent recognition)...")
    application.run_polling()

if __name__ == "__main__":
    main()
