# handlers/log_handler.py
import logging
import re
import json 
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler 
import requests 

from services.ai_categorization_service import get_ai_category_prediction
from utils.log_processing_utils import extract_amount_from_text, prepare_text_for_ai
from utils.parsing_utils import parse_date_to_timestamp 

logger = logging.getLogger(__name__)

LOG_CONFIRM_YES_PREFIX = "log_confirm_yes_" 
LOG_CONFIRM_NO_PREFIX = "log_confirm_no_"   
CAT_OVERRIDE_PREFIX = "cat_override_"       
CAT_CANCEL_LOG_PREFIX = "cat_cancel_log_"  

CATEGORY_CONFIDENCE_THRESHOLD = 0.60 

async def process_log_request( # Renamed from log_command_v2 for clarity
                         update: Update, 
                         context: ContextTypes.DEFAULT_TYPE,
                         full_text_to_parse: str, # New argument: the full text to process
                         convex_client: any, 
                         nlp_processor: any,
                         predefined_categories_for_buttons: dict, 
                         default_category_fallback: str, 
                         ai_service_url: str) -> None: 
    """
    Core logic for processing a log request, whether from /log command or command-less intent.
    """
    telegram_chat_id = str(update.message.from_user.id)

    if not full_text_to_parse: # Check the passed text
        await update.message.reply_text("No expense details provided to log.")
        return

    logger.info(f"User {telegram_chat_id} attempting to log: '{full_text_to_parse}'")
    doc = nlp_processor(full_text_to_parse) 
    
    amount, amount_text_for_removal = extract_amount_from_text(full_text_to_parse, doc)

    if amount is None or amount <= 0:
        await update.message.reply_text("Could not determine a valid positive amount from your message.")
        return

    expense_timestamp = parse_date_to_timestamp(None, full_text_to_parse, nlp_processor)
    
    description_for_ai_prediction = prepare_text_for_ai(full_text_to_parse, doc, amount_text_for_removal)
    
    final_description_for_expense = description_for_ai_prediction
    if len(final_description_for_expense) > 100: 
        final_description_for_expense = final_description_for_expense[:97] + "..."
    if not final_description_for_expense.strip(): 
        final_description_for_expense = "N/A"

    ai_predicted_category, ai_confidence = get_ai_category_prediction(description_for_ai_prediction, ai_service_url)

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
        "description": final_description_for_expense, 
        "date": expense_timestamp,
        "original_text_for_ai": description_for_ai_prediction, 
        "ai_suggested_category": ai_predicted_category, 
        "ai_confidence": ai_confidence
    }
    
    log_attempt_key = f"log_attempt_{update.message.message_id}"
    context.chat_data[log_attempt_key] = parsed_expense_details
    logger.info(f"Stored initial parsed expense data with key: {log_attempt_key}. Data: {parsed_expense_details}")

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
        
        confidence_display_str = f"{ai_confidence*100:.0f}%" if ai_confidence is not None else "N/A"
        display_ai_suggestion = f"'{ai_cat_str}' (Confidence: {confidence_display_str})" if ai_predicted_category else "unavailable"
        
        message_text_desc_hint = final_description_for_expense if final_description_for_expense != "N/A" else description_for_ai_prediction
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

# This is the actual command handler for /log
async def log_command_entry(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         convex_client: any, nlp_processor: any,
                         predefined_categories_for_buttons: dict, 
                         default_category_fallback: str, 
                         ai_service_url: str) -> None:
    # Extract text after the /log command itself
    full_text_after_log_command = update.message.text.split('/log', 1)[1].strip() if '/log' in update.message.text else ""
    if not full_text_after_log_command:
        await update.message.reply_text(
            "Please provide expense details after /log.\n"
            "Example: /log $20 for lunch yesterday"
        )
        return
    # Call the core processing function
    await process_log_request(update, context, full_text_after_log_command, 
                              convex_client, nlp_processor, predefined_categories_for_buttons,
                              default_category_fallback, ai_service_url)


# --- Callback Handlers (send_final_log_confirmation, handle_category_override_selection, handle_log_confirmation) ---
# These remain the same as in 
# For brevity, not repeated here. Ensure they are present and correct.
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

    full_expense_details: Optional[Dict[str, Any]] = context.chat_data.pop(log_attempt_key, None) 

    if not full_expense_details:
        logger.error(f"Final expense data was None after pop for key: {log_attempt_key}")
        await query.edit_message_text(text="Error: Could not retrieve expense details to log.")
        return

    if action == "yes":
        logger.info(f"User confirmed FINAL logging for key {log_attempt_key}. Full Details: {full_expense_details}")
        
        expense_to_log_payload = {
            "telegramChatId": full_expense_details["telegramChatId"],
            "amount": full_expense_details["amount"],
            "category": full_expense_details["category"], 
            "description": full_expense_details["description"], 
            "date": full_expense_details["date"],
        }
        try:
            log_result = convex_client.mutation("expenses:logExpense", expense_to_log_payload)
            if log_result and log_result.get("success"):
                logged_date_obj = datetime.fromtimestamp(full_expense_details['date'] / 1000)
                await query.edit_message_text(
                    text=f"✅ Expense logged successfully!\n"
                         f"Amount: ${full_expense_details['amount']:.2f}\n"
                         f"Category: {full_expense_details['category']}\n"
                         f"Description: {full_expense_details['description']}\n"
                         f"Date: {logged_date_obj.strftime('%Y-%m-%d (%A)')}"
                )
                
                feedback_payload = {
                    "telegramChatId": full_expense_details["telegramChatId"],
                    "original_text_for_ai": full_expense_details.get("original_text_for_ai", "N/A"),
                    "ai_predicted_category": full_expense_details.get("ai_suggested_category"), 
                    "ai_confidence": full_expense_details.get("ai_confidence"), 
                    "user_chosen_category": full_expense_details["category"], 
                }
                try:
                    feedback_result = convex_client.mutation("feedback_mutations:recordCategoryFeedback", feedback_payload)
                    if feedback_result and feedback_result.get("success"):
                        logger.info(f"Category feedback recorded successfully for log_attempt_key {log_attempt_key}.")
                    else:
                        logger.warning(f"Failed to record category feedback for log_attempt_key {log_attempt_key}. Result: {feedback_result}")
                except Exception as fb_e:
                    logger.error(f"Error calling Convex recordCategoryFeedback mutation: {fb_e}")

            else: 
                error_msg = log_result.get("error", "Failed to log expense.") if log_result else "Failed to log expense (no response)."
                await query.edit_message_text(text=f"⚠️ Error logging expense: {error_msg}")
        except Exception as e: 
            logger.error(f"Error calling Convex expenses:logExpense mutation after final confirmation: {e}")
            await query.edit_message_text(text=f"⚠️ An error occurred while logging your expense: {str(e)}")
    
    elif action == "no":
        logger.info(f"User cancelled FINAL logging for key {log_attempt_key}.")
        await query.edit_message_text(text="Logging cancelled. Feel free to try again with /log.")
    else:
        logger.warning(f"Unknown action in final log confirmation callback: {callback_data_full}")
        await query.edit_message_text(text="Sorry, I didn't understand that action.")

