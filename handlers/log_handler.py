# handlers/log_handler.py
import logging
import re
from datetime import datetime
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

# Assuming these are imported correctly in bot.py and passed here,
# or imported from utils if they become more self-contained.
from utils.parsing_utils import parse_date_to_timestamp, determine_category

logger = logging.getLogger(__name__)

async def log_command_v2(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         convex_client: any, nlp_processor: any,
                         predefined_categories: dict, default_category: str) -> None:
    telegram_chat_id = str(update.message.from_user.id)
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
        if amount_text_for_removal[0].isalnum():
            removal_pattern_parts.append(r'\b')
        removal_pattern_parts.append(re.escape(amount_text_for_removal))
        if amount_text_for_removal[-1].isalnum():
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
            if amount_text_for_removal[0].isalnum(): ar_parts.append(r'\b')
            ar_parts.append(re.escape(amount_text_for_removal))
            if amount_text_for_removal[-1].isalnum(): ar_parts.append(r'\b')
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

    expense_data = {
        "telegramChatId": telegram_chat_id,
        "amount": amount,
        "category": category,
        "description": description,
        "date": expense_timestamp,
    }

    logger.info(f"Logging to Convex (log_handler): {expense_data}")
    await update.message.reply_text(f"Trying to log: ${amount:.2f} for '{description}' in '{category}' on {datetime.fromtimestamp(expense_timestamp/1000).strftime('%Y-%m-%d')}...")

    try:
        result = convex_client.mutation("expenses:logExpense", expense_data)
        if result and result.get("success"):
            logged_date_obj = datetime.fromtimestamp(expense_timestamp / 1000)
            await update.message.reply_text(
                f"✅ Expense logged successfully!\n"
                f"Amount: ${amount:.2f}\n"
                f"Category: {expense_data['category']}\n"
                f"Description: {expense_data['description']}\n"
                f"Date: {logged_date_obj.strftime('%Y-%m-%d (%A)')}"
            )
        else:
            error_msg = result.get("error", "Failed to log expense.") if result else "Failed to log expense (no response)."
            await update.message.reply_text(f"⚠️ Error: {error_msg}")
    except Exception as e:
        logger.error(f"Error calling Convex logExpense mutation (log_handler): {e}")
        await update.message.reply_text(f"⚠️ An error occurred while logging your expense: {str(e)}")

