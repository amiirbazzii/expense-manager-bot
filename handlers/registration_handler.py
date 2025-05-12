# handlers/registration_handler.py
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

# These will be imported from bot.py or a config module
# For now, assume they are accessible or passed if needed.
# from bot import convex_client, logger # Example if importing directly

logger = logging.getLogger(__name__)

# Conversation states
USERNAME, PASSWORD = range(2)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, convex_client: any) -> int:
    user_telegram_id = str(update.message.from_user.id)
    logger.info(f"User {user_telegram_id} initiated /start command for registration.")
    
    # Optional: Check if user already registered (e.g., via a query to Convex)
    # try:
    #     # This query would need to be defined in Convex, e.g., in auth.ts or queries.ts
    #     # existing_user = convex_client.query("queries:getUserByTelegramId", {"telegramChatId": user_telegram_id})
    #     # if existing_user:
    #     #     await update.message.reply_text(f"Welcome back, {existing_user['username']}! You are already registered.")
    #     #     return ConversationHandler.END
    # except Exception as e:
    #     logger.warning(f"Could not check existing user for {user_telegram_id}: {e}")

    await update.message.reply_text(
        "Welcome to the Expense Bot! Let's get you registered.\n"
        "Please choose a username (at least 3 characters):"
    )
    return USERNAME

async def received_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

async def received_password(update: Update, context: ContextTypes.DEFAULT_TYPE, convex_client: any) -> int:
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
                "You can now log expenses, e.g.: /log $20 for lunch yesterday\n"
                "And query using: /summary [period]"
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
