# handlers/log_handler.py
import logging
import re
import json # For serializing data in callback
from datetime import datetime
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler # Added CallbackQueryHandler

# Assuming these are imported correctly in bot.py and passed here,
# or imported from utils if they become more self-contained.
from utils.parsing_utils import parse_date_to_timestamp, determine_category

logger = logging.getLogger(__name__)

# Callback data prefixes for inline buttons
LOG_CONFIRM_YES = "log_confirm_yes_"
LOG_CONFIRM_NO = "log_confirm_no_"

async def log_command_v2(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         convex_client: any, nlp_processor: any,
                         predefined_categories: dict, default_category: str) -> None:
    telegram_chat_id = str(update.message.from_user.id)
    # Use context.args to get text after /log, handles cases where /log itself might be part of the text.
    # However, the original split method is also fine if /log is always the command prefix.
    # For consistency with other commands that use context.args, let's consider it,
    # but the current split is okay if it works for all user inputs.
    # For now, keeping the original split:
    full_text_after_log = update.message.text.split('/log', 1)[1].strip() if '/log' in update.message.text else ""


    if not full_text_after_log:
        await update.message.reply_text(
            "Please provide expense details after /log.\n"
            "Example: /log $20 for lunch at the new cafe yesterday"
        )
        return

    logger.info(f"User {telegram_chat_id} sent /log command with text: '{full_text_after_log}'")
    doc = nlp_processor(full_text_after_log)
    
    logger.info(f"--- Amount Extraction for: '{full_text_after_log}' ---")
    logger.info(f"spaCy Entities: {[(ent.text, ent.label_, ent.start_char, ent.end_char) for ent in doc.ents]}")

    amount: Optional[float] = None
    amount_text_for_removal = ""

    for ent in doc.ents:
        if ent.label_ == "MONEY":
            logger.info(f"Processing MONEY entity: '{ent.text}' (start: {ent.start_char}, end: {ent.end_char})")
            try:
                cleaned_entity_text = ent.text.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                parsed_val = float(cleaned_entity_text)
                if parsed_val > 0:
                    amount = parsed_val
                    potential_removal_text = ent.text
                    entity_start_char = ent.start_char
                    if not any(c in potential_removal_text for c in "$€£"):
                        if entity_start_char > 0 and full_text_after_log[entity_start_char - 1] in "$€£":
                            potential_removal_text = full_text_after_log[entity_start_char - 1] + potential_removal_text
                        elif entity_start_char > 1 and full_text_after_log[entity_start_char - 2] in "$€£" and full_text_after_log[entity_start_char - 1].isspace():
                            potential_removal_text = full_text_after_log[entity_start_char - 2:entity_start_char] + potential_removal_text
                    amount_text_for_removal = potential_removal_text
                    logger.info(f"Found amount from MONEY entity: {amount}, text for removal: '{amount_text_for_removal}'")
                    break
            except ValueError:
                logger.warning(f"Could not convert MONEY entity text '{ent.text}' (cleaned: '{cleaned_entity_text}') to float.")
    
    if amount is None:
        logger.info("No MONEY entity parsed, trying CARDINAL.")
        for ent in doc.ents:
            if ent.label_ == "CARDINAL":
                logger.info(f"Processing CARDINAL entity: '{ent.text}' (start: {ent.start_char}, end: {ent.end_char})")
                is_part_of_date = False
                for date_ent in doc.ents:
                    if date_ent.label_ == "DATE" and ent.start_char >= date_ent.start_char and ent.end_char <= date_ent.end_char:
                        is_part_of_date = True
                        break
                logger.info(f"CARDINAL '{ent.text}' is_part_of_date: {is_part_of_date}")
                if is_part_of_date:
                    continue
                try:
                    cleaned_cardinal_str = ent.text.replace(",", "").strip()
                    parsed_val = float(cleaned_cardinal_str)
                    if parsed_val > 0:
                        amount = parsed_val
                        potential_removal_text = ent.text
                        entity_start_char = ent.start_char
                        if not any(c in potential_removal_text for c in "$€£"):
                            if entity_start_char > 0 and full_text_after_log[entity_start_char - 1] in "$€£":
                                potential_removal_text = full_text_after_log[entity_start_char - 1] + potential_removal_text
                            elif entity_start_char > 1 and full_text_after_log[entity_start_char - 2] in "$€£" and full_text_after_log[entity_start_char - 1].isspace():
                                potential_removal_text = full_text_after_log[entity_start_char - 2:entity_start_char] + potential_removal_text
                        amount_text_for_removal = potential_removal_text
                        logger.info(f"Found amount from CARDINAL entity: {amount}, text for removal: '{amount_text_for_removal}'")
                        break
                except ValueError:
                    logger.warning(f"Could not convert CARDINAL entity '{ent.text}' to float.")

    if amount is None:
        logger.info("No amount from spaCy MONEY/CARDINAL entities, trying regex fallback.")
        money_match = re.search(r"([\$€£]?)\s*(\d+(?:[\.,]\d+)?(?:\d+)?)", full_text_after_log)
        if money_match:
            logger.info(f"Regex fallback matched: '{money_match.group(0)}'")
            try:
                number_part = money_match.group(2)
                cleaned_amount_str = number_part.replace(",", "").strip()
                parsed_val = float(cleaned_amount_str)
                if parsed_val > 0:
                    amount = parsed_val
                    amount_text_for_removal = money_match.group(0).strip()
                    logger.info(f"Found amount from regex: {amount}, text for removal: '{amount_text_for_removal}'")
            except ValueError:
                logger.warning(f"Could not convert regex-found amount '{money_match.group(0)}' to float.")

    if amount is None or amount <= 0:
        logger.error(f"Final amount is None or not positive: {amount}. Input was: '{full_text_after_log}'")
        await update.message.reply_text("Could not determine a valid positive amount. Please include it clearly (e.g., $10.50 or 10.50).")
        return
    
    logger.info(f"--- End Amount Extraction: Amount={amount}, TextForRemoval='{amount_text_for_removal}' ---")

    expense_timestamp = parse_date_to_timestamp(None, full_text_after_log, nlp_processor)

    text_for_category_desc = full_text_after_log
    logger.info(f"Initial text for cat/desc: '{text_for_category_desc}'")

    if amount_text_for_removal:
        logger.info(f"Attempting to remove amount text: '{amount_text_for_removal}'")
        removal_pattern_parts = []
        if amount_text_for_removal and amount_text_for_removal[0].isalnum():
            removal_pattern_parts.append(r'\b')
        removal_pattern_parts.append(re.escape(amount_text_for_removal))
        if amount_text_for_removal and amount_text_for_removal[-1].isalnum():
            removal_pattern_parts.append(r'\b')
        removal_regex = "".join(removal_pattern_parts)
        
        text_for_category_desc = re.sub(removal_regex, '', text_for_category_desc, 1, flags=re.IGNORECASE).strip()
        text_for_category_desc = re.sub(r'\s+', ' ', text_for_category_desc).strip()
        logger.info(f"Text after amount removal: '{text_for_category_desc}'")

    date_entity_texts = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
    for date_txt in date_entity_texts:
        logger.info(f"Attempting to remove date text: '{date_txt}'")
        removal_pattern_parts = []
        if date_txt and date_txt[0].isalnum(): removal_pattern_parts.append(r'\b')
        removal_pattern_parts.append(re.escape(date_txt))
        if date_txt and date_txt[-1].isalnum(): removal_pattern_parts.append(r'\b')
        date_removal_regex = "".join(removal_pattern_parts)

        text_for_category_desc = re.sub(date_removal_regex, '', text_for_category_desc, 1, flags=re.IGNORECASE).strip()
        text_for_category_desc = re.sub(r'\s+', ' ', text_for_category_desc).strip()
        logger.info(f"Text after removing '{date_txt}': '{text_for_category_desc}'")

    text_for_category_desc = re.sub(r'^(on|for|at|spent|buy|bought|get|got)\s+', '', text_for_category_desc, flags=re.IGNORECASE).strip()
    text_for_category_desc = re.sub(r'\s+(on|for|at)$', '', text_for_category_desc, flags=re.IGNORECASE).strip()
    text_for_category_desc = re.sub(r'\s+', ' ', text_for_category_desc).strip()
    logger.info(f"Text after preposition cleanup: '{text_for_category_desc}'")

    category = determine_category(text_for_category_desc if text_for_category_desc else full_text_after_log, 
                                  nlp_processor, predefined_categories, default_category)
    
    description = text_for_category_desc if text_for_category_desc.strip() else "N/A"

    if category != default_category and category.lower() in description.lower():
        description = description.lower().replace(category.lower(), "", 1).strip()
        description = re.sub(r'^(on|for|at)\s+', '', description, flags=re.IGNORECASE).strip()
        description = description.capitalize() if description.strip() else "N/A"
    
    if not description.strip() or len(description.strip()) < 2 :
        temp_desc = full_text_after_log
        if amount_text_for_removal:
            ar_parts = []
            if amount_text_for_removal and amount_text_for_removal[0].isalnum(): ar_parts.append(r'\b')
            ar_parts.append(re.escape(amount_text_for_removal))
            if amount_text_for_removal and amount_text_for_removal[-1].isalnum(): ar_parts.append(r'\b')
            ar_regex = "".join(ar_parts)
            temp_desc = re.sub(ar_regex, '', temp_desc, 1, flags=re.IGNORECASE).strip()

        for date_txt in date_entity_texts:
            dr_parts = []
            if date_txt and date_txt[0].isalnum(): dr_parts.append(r'\b')
            dr_parts.append(re.escape(date_txt))
            if date_txt and date_txt[-1].isalnum(): dr_parts.append(r'\b')
            dr_regex = "".join(dr_parts)
            temp_desc = re.sub(dr_regex, '', temp_desc, 1, flags=re.IGNORECASE).strip()
        
        temp_desc = re.sub(r'\s+', ' ', temp_desc).strip()
        temp_desc = re.sub(r'^(on|for|at|spent|buy|bought|get|got)\s+', '', temp_desc, flags=re.IGNORECASE).strip()
        
        if temp_desc and len(temp_desc.strip()) > 2:
            description = temp_desc[:75].strip() + ("..." if len(temp_desc) > 75 else "")
        elif category != default_category :
            description = category 
        else:
            description = "Logged expense"
    
    description = description.strip()
    if not description:
        description = "Logged expense"

    # --- Store parsed data for confirmation ---
    # We need a unique ID for this pending log to pass in callback_data
    # For simplicity, we can use the message_id or a combination of chat_id and message_id
    # A more robust way might be a UUID, but let's use message_id for now.
    # Note: If multiple logs are initiated quickly, message_id might not be unique enough
    # if the bot processes them slowly. For a personal bot, this risk is lower.
    # A better way is to generate a unique ID and store the data against it.
    # For now, let's serialize the whole expense_data into the callback_data if it's small enough.
    # Telegram callback_data has a limit of 64 bytes. This is too small for all data.
    # So, we must store it in context.chat_data or context.user_data.

    pending_expense_data = {
        "telegramChatId": telegram_chat_id, # Already string
        "amount": amount, # float
        "category": category, # string
        "description": description.strip(), # string
        "date": expense_timestamp, # int (timestamp)
    }
    
    # Store in chat_data, keyed by a unique identifier (e.g., message_id of the original /log command)
    # This assumes one pending log per user at a time for simplicity.
    # If multiple /log commands can be pending, need a more robust keying system.
    # Let's use a simple key for now.
    pending_log_key = f"pending_log_{update.message.message_id}"
    context.chat_data[pending_log_key] = pending_expense_data
    logger.info(f"Stored pending expense data with key: {pending_log_key}")


    # --- Send Confirmation Message ---
    confirmation_message = (
        f"Please confirm this expense:\n\n"
        f"💰 Amount: ${amount:.2f}\n"
        f"🏷️ Category: {category}\n"
        f"📝 Description: {description.strip()}\n"
        f"🗓️ Date: {datetime.fromtimestamp(expense_timestamp/1000).strftime('%Y-%m-%d (%A)')}\n\n"
        f"Is this correct?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Log It!", callback_data=f"{LOG_CONFIRM_YES}{pending_log_key}"),
            InlineKeyboardButton("❌ No, Cancel", callback_data=f"{LOG_CONFIRM_NO}{pending_log_key}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(confirmation_message, reply_markup=reply_markup)
    logger.info(f"Sent confirmation message for key: {pending_log_key}")


async def handle_log_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, convex_client: any) -> None:
    """Handles the Yes/No callback from the log confirmation."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback

    callback_data_full = query.data
    logger.info(f"Received log confirmation callback: {callback_data_full}")

    pending_log_key = None
    action = None

    if callback_data_full.startswith(LOG_CONFIRM_YES):
        action = "yes"
        pending_log_key = callback_data_full[len(LOG_CONFIRM_YES):]
    elif callback_data_full.startswith(LOG_CONFIRM_NO):
        action = "no"
        pending_log_key = callback_data_full[len(LOG_CONFIRM_NO):]

    if not pending_log_key or pending_log_key not in context.chat_data:
        logger.warning(f"Could not find pending log data for key: {pending_log_key} or key is None.")
        await query.edit_message_text(text="Sorry, something went wrong or this request expired.")
        return

    expense_data: Optional[Dict[str, Any]] = context.chat_data.pop(pending_log_key, None) # Retrieve and remove

    if not expense_data: # Should have been caught by the 'in' check, but good to be safe
        logger.error(f"Expense data was None after pop for key: {pending_log_key}")
        await query.edit_message_text(text="Error: Could not retrieve expense details.")
        return

    if action == "yes":
        logger.info(f"User confirmed logging for key {pending_log_key}. Data: {expense_data}")
        try:
            result = convex_client.mutation("expenses:logExpense", expense_data) # expense_data is already prepared
            if result and result.get("success"):
                logged_date_obj = datetime.fromtimestamp(expense_data['date'] / 1000)
                await query.edit_message_text(
                    text=f"✅ Expense logged successfully!\n"
                         f"Amount: ${expense_data['amount']:.2f}\n"
                         f"Category: {expense_data['category']}\n"
                         f"Description: {expense_data['description']}\n"
                         f"Date: {logged_date_obj.strftime('%Y-%m-%d (%A)')}"
                )
            else:
                error_msg = result.get("error", "Failed to log expense.") if result else "Failed to log expense (no response)."
                await query.edit_message_text(text=f"⚠️ Error: {error_msg}")
        except Exception as e:
            logger.error(f"Error calling Convex logExpense mutation after confirmation: {e}")
            await query.edit_message_text(text=f"⚠️ An error occurred while logging your expense: {str(e)}")
    
    elif action == "no":
        logger.info(f"User cancelled logging for key {pending_log_key}.")
        await query.edit_message_text(text="Logging cancelled. Feel free to try again with /log.")
    else:
        logger.warning(f"Unknown action in log confirmation callback: {callback_data_full}")
        await query.edit_message_text(text="Sorry, I didn't understand that action.")

