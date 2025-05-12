# bot.py
import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
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
from handlers.command_handler import (
    log_command_v2, 
    summary_command, 
    details_command,
    category_command # Added category_command
)

# Load environment variables from .env.local file
load_dotenv(dotenv_path=".env.local")

# --- Global Initializations ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CONVEX_URL = os.getenv("CONVEX_URL")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in .env.local file. Please add it.")
if not CONVEX_URL:
    raise ValueError("CONVEX_URL not found in .env.local file. Please add it.")

try:
    convex_client = ConvexClient(CONVEX_URL)
except Exception as e:
    print(f"Error initializing Convex client: {e}")
    print(f"Ensure CONVEX_URL ('{CONVEX_URL}') is correct and your Convex project is deployed.")
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
    "Miscellaneous": ["misc", "miscellaneous", "other"],
}
DEFAULT_CATEGORY = "Miscellaneous" # Though not directly used by category_command, good to have defined

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

    async def wrapped_log_command(update, context):
        await log_command_v2(update, context, convex_client, nlp, PREDEFINED_CATEGORIES, DEFAULT_CATEGORY)
    async def wrapped_summary_command(update, context):
        await summary_command(update, context, convex_client, nlp)
    async def wrapped_details_command(update, context):
        await details_command(update, context, convex_client)
    async def wrapped_category_command(update, context): # New wrapper for /category
        await category_command(update, context, convex_client, nlp, PREDEFINED_CATEGORIES)


    application.add_handler(CommandHandler("log", wrapped_log_command))
    application.add_handler(CommandHandler("summary", wrapped_summary_command))
    application.add_handler(CommandHandler("details", wrapped_details_command))
    application.add_handler(CommandHandler("category", wrapped_category_command)) # Register /category

    logger.info("Bot starting (refactored structure with /category)...")
    application.run_polling()

if __name__ == "__main__":
    main()
