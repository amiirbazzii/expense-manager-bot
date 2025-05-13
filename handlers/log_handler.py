# handlers/log_handler.py
import logging
import re
import json 
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler 
import requests 

from utils.parsing_utils import parse_date_to_timestamp 

logger = logging.getLogger(__name__)

# Callback data prefixes
LOG_CONFIRM_YES_PREFIX = "log_confirm_yes_" 
LOG_CONFIRM_NO_PREFIX = "log_confirm_no_"   
CAT_OVERRIDE_PREFIX = "cat_override_"       
CAT_CANCEL_LOG_PREFIX = "cat_cancel_log_"  

CATEGORY_CONFIDENCE_THRESHOLD = 0.60 

# --- Helper to call AI Service ---
def get_ai_category_prediction(text_to_predict: str, ai_service_url: str) -> Tuple[Optional[str], Optional[float]]:
    """Calls the external AI service to get a category prediction."""
    if not text_to_predict.strip(): 
        logger.warning("Text for AI prediction is empty. Returning None.")
        return None, 0.0 

    endpoint = f"{ai_service_url.rstrip('/')}/predict_category"
    payload = {"text": text_to_predict}
    try:
        logger.info(f"Calling AI service at {endpoint} with payload: {payload}")
        response = requests.post(endpoint, json=payload, timeout=10) 
        response.raise_for_status() 
        
        data = response.json()
        predicted_category = data.get("predicted_category")
        confidence = data.get("confidence")
        logger.info(f"AI Service Response: Category='{predicted_category}', Confidence={confidence}")
        return predicted_category, confidence
    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling AI service at {endpoint}: {e}")
        return None, None 
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response from AI service: {e}. Response text: {response.text if 'response' in locals() else 'N/A'}")
        return None, None
    except Exception as e: 
        logger.error(f"Unexpected error during AI service call: {e}")
        return None, None


# --- Main Log Command (v2 - now with AI) ---
async def log_command_v2(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         convex_client: any, nlp_processor: any,
                         predefined_categories_for_buttons: dict, 
                         default_category_fallback: str, 
                         ai_service_url: str) -> None: 
    telegram_chat_id = str(update.message.from_user.id)
    full_text_after_log = update.message.text.split('/log', 1)[1].strip() if '/log' in update.message.text else ""

    if not full_text_after_log:
        await update.message.reply_text("Please provide expense details after /log...")
        return

    logger.info(f"User {telegram_chat_id} /log: '{full_text_after_log}'")
    doc = nlp_processor(full_text_after_log)
    
    amount: Optional[float] = None
    amount_text_for_removal = "" 
    
    for ent in doc.ents:
        if ent.label_ == "MONEY":
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
                    logger.info(f"Amount from MONEY: {amount}, Text for removal: '{amount_text_for_removal}'")
                    break 
            except ValueError: pass
    
    if amount is None:
        for ent in doc.ents:
            if ent.label_ == "CARDINAL":
                is_part_of_date = any(
                    date_ent.label_ == "DATE" and ent.start_char >= date_ent.start_char and ent.end_char <= date_ent.end_char
                    for date_ent in doc.ents
                )
                if is_part_of_date: continue
                try:
                    cleaned_cardinal_str = ent.text.replace(",", "").strip()
                    parsed_val = float(cleaned_cardinal_str)
                    if parsed_val > 0:
                        amount = parsed_val
                        potential_removal_text = ent.text
                        entity_start_char = ent.start_char
                        if entity_start_char > 0 and full_text_after_log[entity_start_char - 1] in "$€£":
                            potential_removal_text = full_text_after_log[entity_start_char - 1] + potential_removal_text
                        elif entity_start_char > 1 and full_text_after_log[entity_start_char - 2] in "$€£" and full_text_after_log[entity_start_char - 1].isspace():
                             potential_removal_text = full_text_after_log[entity_start_char - 2:entity_start_char] + potential_removal_text
                        amount_text_for_removal = potential_removal_text
                        logger.info(f"Amount from CARDINAL: {amount}, Text for removal: '{amount_text_for_removal}'")
                        break
                except ValueError: pass

    if amount is None: 
        money_match = re.search(r"([\$€£]?)\s*(\d+(?:[\.,]\d+)?(?:\d+)?)", full_text_after_log)
        if money_match:
            try:
                number_part = money_match.group(2)
                cleaned_amount_str = number_part.replace(",", "").strip()
                amount = float(cleaned_amount_str)
                amount_text_for_removal = money_match.group(0).strip() 
                logger.info(f"Amount from REGEX: {amount}, Text for removal: '{amount_text_for_removal}'")
            except ValueError: pass

    if amount is None or amount <= 0:
        await update.message.reply_text("Could not determine a valid positive amount.")
        return

    expense_timestamp = parse_date_to_timestamp(None, full_text_after_log, nlp_processor)

    text_for_ai = full_text_after_log
    logger.info(f"Initial text for AI/description: '{text_for_ai}'")

    if amount_text_for_removal:
        logger.info(f"Attempting to remove amount text: '{amount_text_for_removal}'")
        escaped_removal_text = re.escape(amount_text_for_removal)
        text_for_ai = re.sub(escaped_removal_text, '', text_for_ai, 1, flags=re.IGNORECASE)
        text_for_ai = re.sub(r'\s+', ' ', text_for_ai).strip() 
        logger.info(f"Text after amount removal: '{text_for_ai}'")
    
    date_entity_texts = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
    for date_txt in date_entity_texts:
        logger.info(f"Attempting to remove date text: '{date_txt}'")
        escaped_date = re.escape(date_txt)
        text_for_ai = re.sub(r'\b' + escaped_date + r'\b', '', text_for_ai, 1, flags=re.IGNORECASE)
        text_for_ai = re.sub(r'\s+', ' ', text_for_ai).strip()
        logger.info(f"Text after removing '{date_txt}': '{text_for_ai}'")
    
    text_for_ai = re.sub(r'^(on|for|at|spent|buy|bought|get|got|paid)\s+', '', text_for_ai, flags=re.IGNORECASE).strip()
    text_for_ai = re.sub(r'\s+(on|for|at)$', '', text_for_ai, flags=re.IGNORECASE).strip()
    text_for_ai = re.sub(r'\s+', ' ', text_for_ai).strip() 
    logger.info(f"Text after keyword/preposition cleanup: '{text_for_ai}'")
    
    description_candidate = text_for_ai if text_for_ai else "N/A"
    if len(description_candidate) > 100: description_candidate = description_candidate[:97] + "..."

    ai_predicted_category, ai_confidence = get_ai_category_prediction(description_candidate, ai_service_url)

    final_category = default_category_fallback 
    if ai_predicted_category:
        final_category = ai_predicted_category
    else: 
        logger.warning("AI service did not return a category. Using default fallback.")
        ai_confidence = 0.0 

    parsed_expense_details = {
        "telegramChatId": telegram_chat_id,
        "amount": amount,
        "category": final_category, 
        "description": description_candidate, 
        "date": expense_timestamp,
        "ai_suggested_category": ai_predicted_category, 
        "ai_confidence": ai_confidence
    }
    
    log_attempt_key = f"log_attempt_{update.message.message_id}"
    context.chat_data[log_attempt_key] = parsed_expense_details
    logger.info(f"Stored initial parsed expense data with key: {log_attempt_key}. Data: {parsed_expense_details}")

    # Corrected f-string for logging AI confidence
    confidence_log_str = f"{ai_confidence * 100:.0f}%" if ai_confidence is not None else "N/A"
    if ai_confidence is not None and ai_confidence >= CATEGORY_CONFIDENCE_THRESHOLD:
        logger.info(f"AI confidence ({confidence_log_str}) is high. Proceeding to final confirmation.")
        await send_final_log_confirmation(update, context, log_attempt_key, parsed_expense_details)
    else:
        logger.info(f"AI confidence ({confidence_log_str}) is low or AI failed. Asking user to confirm/select category.")
        keyboard_buttons = []
        ai_cat_str = str(ai_predicted_category) if ai_predicted_category is not None else ""

        if ai_predicted_category:
            keyboard_buttons.append(
                InlineKeyboardButton(f"✅ Use '{ai_cat_str}'", callback_data=f"{CAT_OVERRIDE_PREFIX}{ai_cat_str}_{log_attempt_key}")
            )
        
        suggestions_made = {ai_cat_str} if ai_predicted_category else set()
        
        if isinstance(predefined_categories_for_buttons, dict):
            common_cats_for_buttons = [
                cat for cat in ["Food & Drink", "Transport", "Shopping", "Utilities", default_category_fallback] 
                if cat not in suggestions_made and cat in predefined_categories_for_buttons
            ]
            for cat_suggestion in common_cats_for_buttons[:3]: 
                if cat_suggestion not in suggestions_made:
                    keyboard_buttons.append(
                        InlineKeyboardButton(f"{cat_suggestion}", callback_data=f"{CAT_OVERRIDE_PREFIX}{cat_suggestion}_{log_attempt_key}")
                    )
                    suggestions_made.add(cat_suggestion)
        
        default_cat_str = str(default_category_fallback)
        if default_cat_str not in suggestions_made:
             keyboard_buttons.append(
                InlineKeyboardButton(f"{default_cat_str}", callback_data=f"{CAT_OVERRIDE_PREFIX}{default_cat_str}_{log_attempt_key}")
            )

        keyboard_layout = [keyboard_buttons[i:i + 2] for i in range(0, len(keyboard_buttons), 2)]
        keyboard_layout.append([InlineKeyboardButton("❌ Cancel Log", callback_data=f"{CAT_CANCEL_LOG_PREFIX}{log_attempt_key}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard_layout)
        
        # Corrected f-string for displaying AI confidence
        confidence_display_str = f"{ai_confidence*100:.0f}%" if ai_confidence is not None else "N/A"
        display_ai_suggestion = f"'{ai_cat_str}' (Confidence: {confidence_display_str})" if ai_predicted_category else "unavailable"
        
        message_text_desc_hint = description_candidate if description_candidate != "N/A" else text_for_ai 
        if not message_text_desc_hint: message_text_desc_hint = "your input"


        message_text = (
            f"🤖 My AI suggests category: {display_ai_suggestion}.\n"
            f"For: '{message_text_desc_hint}'\n\n" 
            f"Please confirm or choose a different category:"
        )
        if not ai_predicted_category: 
             message_text = (
                f"🤖 My AI couldn't determine a category for: '{message_text_desc_hint}'.\n"
                f"Please choose a category:"
            )
        await update.message.reply_text(message_text, reply_markup=reply_markup)

async def send_final_log_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                      log_attempt_key: str, 
                                      expense_details: Dict[str, Any]):
    logger.info(f"Sending final log confirmation for key {log_attempt_key}. Details: {expense_details}")
    
    amount = expense_details.get("amount")
    category = expense_details.get("category")
    description = expense_details.get("description")
    expense_timestamp = expense_details.get("date")

    if None in [amount, category, description, expense_timestamp]:
        logger.error(f"Missing data in expense_details for final confirmation: {expense_details}")
        target_message = update.callback_query.message if update.callback_query else update.message
        if target_message:
            try:
                await target_message.edit_text("Error: Could not prepare expense details for final confirmation.")
            except Exception: 
                 await context.bot.send_message(chat_id=target_message.chat_id, text="Error: Could not prepare expense details for final confirmation.")
        return

    confirmation_message = (
        f"Please confirm this expense:\n\n"
        f"💰 Amount: ${amount:.2f}\n"
        f"🏷️ Category: {category}\n"
        f"📝 Description: {description}\n" 
        f"🗓️ Date: {datetime.fromtimestamp(expense_timestamp/1000).strftime('%Y-%m-%d (%A)')}\n\n"
        f"Is this correct?"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, Log It!", callback_data=f"{LOG_CONFIRM_YES_PREFIX}{log_attempt_key}"),
            InlineKeyboardButton("❌ No, Cancel", callback_data=f"{LOG_CONFIRM_NO_PREFIX}{log_attempt_key}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query: 
        await update.callback_query.edit_message_text(text=confirmation_message, reply_markup=reply_markup)
    elif update.message: 
        await update.message.reply_text(text=confirmation_message, reply_markup=reply_markup)


async def handle_category_override_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, convex_client: any) -> None:
    query = update.callback_query
    await query.answer()
    
    callback_data_full = query.data
    logger.info(f"Received category override callback: {callback_data_full}")

    chosen_category = None 
    log_attempt_key = None 

    if callback_data_full.startswith(CAT_OVERRIDE_PREFIX):
        data_after_prefix = callback_data_full[len(CAT_OVERRIDE_PREFIX):]
        key_marker_actual_start = "log_attempt_" 
        idx_key_marker_separator = data_after_prefix.rfind(f"_{key_marker_actual_start}")

        if idx_key_marker_separator != -1:
            chosen_category = data_after_prefix[:idx_key_marker_separator] 
            log_attempt_key = data_after_prefix[idx_key_marker_separator+1:] 
            logger.info(f"Parsed from CAT_OVERRIDE: chosen_category='{chosen_category}', log_attempt_key='{log_attempt_key}'")
        else:
            logger.error(f"Could not properly parse category and key from CAT_OVERRIDE_PREFIX data: {data_after_prefix}")
            await query.edit_message_text("Error processing your selection (key parsing failed).")
            return
            
    elif callback_data_full.startswith(CAT_CANCEL_LOG_PREFIX):
        log_attempt_key = callback_data_full[len(CAT_CANCEL_LOG_PREFIX):]
        if log_attempt_key in context.chat_data:
            context.chat_data.pop(log_attempt_key, None) 
        await query.edit_message_text("Logging cancelled as requested.")
        logger.info(f"User cancelled logging during category selection for key {log_attempt_key}.")
        return
    else:
        logger.warning(f"Unknown prefix in category override callback: {callback_data_full}")
        await query.edit_message_text("Invalid selection.")
        return

    if not log_attempt_key or log_attempt_key not in context.chat_data:
        logger.warning(f"Could not find pending log data for key: '{log_attempt_key}' in category override. chat_data keys: {list(context.chat_data.keys())}")
        await query.edit_message_text(text="Sorry, something went wrong or this request expired.")
        return

    pending_expense_details: Optional[Dict[str, Any]] = context.chat_data.get(log_attempt_key) 

    if not pending_expense_details:
        logger.error(f"Pending expense details None for key {log_attempt_key} in category override.")
        await query.edit_message_text(text="Error: Could not retrieve expense details.")
        return
    
    if chosen_category is not None: 
        logger.info(f"User selected category '{chosen_category}' for log attempt {log_attempt_key}.")
        pending_expense_details["category"] = chosen_category 
        await send_final_log_confirmation(update, context, log_attempt_key, pending_expense_details)
    else: 
        logger.error(f"Chosen category was None for log_attempt_key {log_attempt_key} after parsing callback data.")
        await query.edit_message_text("Error: No category was effectively selected.")


async def handle_log_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, convex_client: any) -> None:
    query = update.callback_query
    await query.answer() 

    callback_data_full = query.data
    logger.info(f"Received FINAL log confirmation callback: {callback_data_full}")

    log_attempt_key = None
    action = None

    if callback_data_full.startswith(LOG_CONFIRM_YES_PREFIX):
        action = "yes"
        log_attempt_key = callback_data_full[len(LOG_CONFIRM_YES_PREFIX):]
    elif callback_data_full.startswith(LOG_CONFIRM_NO_PREFIX):
        action = "no"
        log_attempt_key = callback_data_full[len(LOG_CONFIRM_NO_PREFIX):]

    if not log_attempt_key or log_attempt_key not in context.chat_data:
        logger.warning(f"Could not find final pending log data for key: '{log_attempt_key}'. chat_data keys: {list(context.chat_data.keys())}")
        await query.edit_message_text(text="Sorry, something went wrong or this request expired.")
        return

    expense_data_to_log: Optional[Dict[str, Any]] = context.chat_data.pop(log_attempt_key, None) 

    if not expense_data_to_log:
        logger.error(f"Final expense data was None after pop for key: {log_attempt_key}")
        await query.edit_message_text(text="Error: Could not retrieve expense details to log.")
        return

    if action == "yes":
        logger.info(f"User confirmed FINAL logging for key {log_attempt_key}. Data: {expense_data_to_log}")
        convex_payload = {
            "telegramChatId": expense_data_to_log["telegramChatId"],
            "amount": expense_data_to_log["amount"],
            "category": expense_data_to_log["category"],
            "description": expense_data_to_log["description"], 
            "date": expense_data_to_log["date"],
        }
        try:
            result = convex_client.mutation("expenses:logExpense", convex_payload)
            if result and result.get("success"):
                logged_date_obj = datetime.fromtimestamp(expense_data_to_log['date'] / 1000)
                await query.edit_message_text(
                    text=f"✅ Expense logged successfully!\n"
                         f"Amount: ${expense_data_to_log['amount']:.2f}\n"
                         f"Category: {expense_data_to_log['category']}\n"
                         f"Description: {expense_data_to_log['description']}\n"
                         f"Date: {logged_date_obj.strftime('%Y-%m-%d (%A)')}"
                )
            else:
                error_msg = result.get("error", "Failed to log expense.") if result else "Failed to log expense (no response)."
                await query.edit_message_text(text=f"⚠️ Error: {error_msg}")
        except Exception as e:
            logger.error(f"Error calling Convex logExpense mutation after final confirmation: {e}")
            await query.edit_message_text(text=f"⚠️ An error occurred while logging your expense: {str(e)}")
    
    elif action == "no":
        logger.info(f"User cancelled FINAL logging for key {log_attempt_key}.")
        await query.edit_message_text(text="Logging cancelled. Feel free to try again with /log.")
    else:
        logger.warning(f"Unknown action in final log confirmation callback: {callback_data_full}")
        await query.edit_message_text(text="Sorry, I didn't understand that action.")

