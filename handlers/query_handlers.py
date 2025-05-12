# handlers/query_handlers.py
import logging
import re # Though not heavily used here, kept for consistency if minor parsing added
from datetime import datetime, timezone, date # Added date
import calendar
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from utils.parsing_utils import parse_period_to_date_range # Assuming this doesn't need nlp for now for these

logger = logging.getLogger(__name__)

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          convex_client: any, nlp_processor: any) -> None: # nlp_processor kept for parse_period
    telegram_chat_id = str(update.message.from_user.id)
    args_str = update.message.text.split('/summary', 1)[1].strip() if '/summary' in update.message.text else ""
    
    logger.info(f"User {telegram_chat_id} sent /summary command with args: '{args_str}'")

    category: Optional[str] = None
    period_str: Optional[str] = None
    
    known_periods = ["this month", "last month"]
    found_known_period = False
    temp_args_str = args_str.lower() 

    for kp in known_periods:
        if kp in temp_args_str:
            period_str = kp
            temp_args_str = temp_args_str.replace(kp, "").strip()
            if temp_args_str: 
                category = temp_args_str 
            found_known_period = True
            break
    
    if not found_known_period:
        parts = args_str.split() 
        if not parts:
            period_str = "this month"
        elif len(parts) == 1:
            parsed_start, parsed_end = parse_period_to_date_range(parts[0], nlp_processor)
            default_start, default_end = parse_period_to_date_range("this month", nlp_processor)
            if parsed_start == default_start and parsed_end == default_end and parts[0].lower() != "this month":
                 category = parts[0]
                 period_str = "this month"
            else:
                 period_str = parts[0]
        else: 
            potential_period_2_words = " ".join(parts[-2:])
            parsed_start_2, parsed_end_2 = parse_period_to_date_range(potential_period_2_words, nlp_processor)
            default_start, default_end = parse_period_to_date_range("this month", nlp_processor)

            if not (parsed_start_2 == default_start and parsed_end_2 == default_end and potential_period_2_words.lower() != "this month"):
                period_str = potential_period_2_words
                category = " ".join(parts[:-2]).strip() if len(parts[:-2]) > 0 else None
            else: 
                potential_period_1_word = parts[-1]
                parsed_start_1, parsed_end_1 = parse_period_to_date_range(potential_period_1_word, nlp_processor)
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

    start_timestamp_ms, end_timestamp_ms = parse_period_to_date_range(period_str, nlp_processor)
    
    display_period_start_dt = datetime.fromtimestamp(start_timestamp_ms/1000)
    display_period_end_dt = datetime.fromtimestamp(end_timestamp_ms/1000)
    
    display_period = f"{display_period_start_dt.strftime('%b %d, %Y')} to {display_period_end_dt.strftime('%b %d, %Y')}"
    if period_str:
        if period_str.lower() == "this month":
            display_period = f"This Month ({display_period_start_dt.strftime('%B %Y')})"
        elif period_str.lower() == "last month":
            display_period = f"Last Month ({display_period_start_dt.strftime('%B %Y')})"
        elif display_period_start_dt.day == 1 and \
             (lambda y, m: hasattr(calendar, 'monthrange') and display_period_end_dt.day == calendar.monthrange(y, m)[1])(display_period_end_dt.year, display_period_end_dt.month):
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
        summary_result = convex_client.query("queries:getExpenseSummary", query_args)
        
        if summary_result:
            count = summary_result.get("count", 0)
            total_amount = summary_result.get("totalAmount", 0.0)
            
            response_message = f"📊 Expense Summary for {display_period}:\n"
            if summary_result.get("category"):
                response_message += f"Category: {summary_result['category']}\n"
            response_message += f"Total Expenses: {count}\n"
            response_message += f"Total Amount: ${total_amount:.2f}"

            await update.message.reply_text(response_message)
        else:
            await update.message.reply_text("Could not retrieve summary. No data found or an error occurred.")
    except Exception as e:
        logger.error(f"Error calling Convex getExpenseSummary query: {e}")
        if "Function not found" in str(e):
             await update.message.reply_text(f"⚠️ Error: The summary function was not found on the server. Please check backend deployment.")
        else:
            await update.message.reply_text(f"⚠️ An error occurred while fetching your summary: {str(e)}")


async def details_command(update: Update, context: ContextTypes.DEFAULT_TYPE,
                          convex_client: any) -> None:
    telegram_chat_id = str(update.message.from_user.id)
    args = context.args 

    limit = 5 
    if args:
        try:
            limit = int(args[0])
            if not (1 <= limit <= 50) : 
                await update.message.reply_text("Please provide a limit between 1 and 50.")
                return
        except ValueError:
            await update.message.reply_text("Invalid limit. Please provide a number (e.g., /details 10).")
            return
        except IndexError: 
            pass 
    
    logger.info(f"User {telegram_chat_id} requested /details with limit: {limit}")
    await update.message.reply_text(f"Fetching your last {limit} expenses...")

    try:
        query_args = {"telegramChatId": telegram_chat_id, "limit": limit}
        recent_expenses = convex_client.query("queries:getRecentExpenses", query_args)

        if recent_expenses:
            if not recent_expenses: 
                await update.message.reply_text("You have no expenses logged yet.")
                return

            response_message = f"📜 Your Last {len(recent_expenses)} Expenses:\n"
            response_message += "------------------------------------\n"
            for expense in recent_expenses:
                try:
                    expense_date_obj = datetime.fromtimestamp(expense['date'] / 1000, tz=timezone.utc)
                    expense_date_str = expense_date_obj.strftime('%Y-%m-%d (%a)')
                except (TypeError, ValueError): 
                    expense_date_str = "N/A"
                
                desc = expense.get('description', 'N/A') or "N/A" 
                
                response_message += (
                    f"🗓️ Date: {expense_date_str}\n"
                    f"💰 Amount: ${expense['amount']:.2f}\n"
                    f"🏷️ Category: {expense['category']}\n"
                    f"📝 Desc: {desc}\n"
                    f"------------------------------------\n"
                )
            await update.message.reply_text(response_message)
        else: 
            await update.message.reply_text("Could not retrieve recent expenses. No data found or an error occurred.")
    except Exception as e:
        logger.error(f"Error calling Convex getRecentExpenses query: {e}")
        if "Limit must be between 1 and 50" in str(e): 
            await update.message.reply_text(str(e))
        elif "User not found" in str(e):
            await update.message.reply_text("User not found. Please /start or /register first.")
        else:
            await update.message.reply_text(f"⚠️ An error occurred while fetching your recent expenses: {str(e)}")


async def category_command(update: Update, context: ContextTypes.DEFAULT_TYPE,
                           convex_client: any, nlp_processor: any,
                           predefined_categories: dict) -> None: # predefined_categories needed for parsing
    telegram_chat_id = str(update.message.from_user.id)
    args_text = " ".join(context.args) if context.args else ""
    
    logger.info(f"User {telegram_chat_id} sent /category command with args: '{args_text}'")

    if not args_text:
        await update.message.reply_text(
            "Please specify a category and optionally a period.\n"
            "Example: /category Food & Drink\n"
            "Example: /category Shopping last month"
        )
        return
    
    target_category: Optional[str] = None
    period_str: Optional[str] = "this month" 
    
    words = args_text.split()
    current_best_match_category = None
    longest_match_len = 0
    remaining_words_for_period = list(words) # Make a mutable copy

    for i in range(len(words), 0, -1): # Check for longer phrases first
        potential_cat_phrase = " ".join(words[:i]).lower()
        for cat_name_key in predefined_categories.keys(): # Iterate over defined category names
            if cat_name_key.lower() == potential_cat_phrase:
                if len(potential_cat_phrase) > longest_match_len: # Found a predefined category name
                    current_best_match_category = cat_name_key # Use the actual casing
                    longest_match_len = len(potential_cat_phrase)
                    remaining_words_for_period = words[i:]
                    break # Found the best match for this length
        if current_best_match_category: # If a match was found for this phrase length, stop.
            break
            
    if current_best_match_category:
        target_category = current_best_match_category
        if remaining_words_for_period:
            period_str = " ".join(remaining_words_for_period).strip()
        # If remaining_words_for_period is empty, period_str remains "this month"
    else:
        # Fallback: if no predefined category name matches, assume first word is category
        if words:
            target_category = words[0].capitalize() 
            if len(words) > 1:
                period_str = " ".join(words[1:]).strip()
        else:
            await update.message.reply_text("Please specify a category.")
            return
            
    if not target_category:
        await update.message.reply_text("Could not determine the category. Please specify clearly.")
        return

    logger.info(f"Parsed /category request: Category='{target_category}', Period='{period_str}'")

    start_timestamp_ms, end_timestamp_ms = parse_period_to_date_range(period_str, nlp_processor)
    
    display_period_start_dt = datetime.fromtimestamp(start_timestamp_ms/1000)
    display_period_end_dt = datetime.fromtimestamp(end_timestamp_ms/1000)
    
    display_period = f"{display_period_start_dt.strftime('%b %d, %Y')} to {display_period_end_dt.strftime('%b %d, %Y')}"
    if period_str:
        if period_str.lower() == "this month":
            display_period = f"This Month ({display_period_start_dt.strftime('%B %Y')})"
        elif period_str.lower() == "last month":
            display_period = f"Last Month ({display_period_start_dt.strftime('%B %Y')})"
        elif display_period_start_dt.day == 1 and \
             (lambda y, m: hasattr(calendar, 'monthrange') and display_period_end_dt.day == calendar.monthrange(y, m)[1])(display_period_end_dt.year, display_period_end_dt.month):
            display_period = display_period_start_dt.strftime("%B %Y")

    query_args = {
        "telegramChatId": telegram_chat_id,
        "startDate": start_timestamp_ms,
        "endDate": end_timestamp_ms,
        "category": target_category.strip(),
    }

    await update.message.reply_text(f"Fetching summary for category '{target_category.strip()}' in {display_period}...")

    try:
        summary_result = convex_client.query("queries:getExpenseSummary", query_args)
        
        if summary_result:
            count = summary_result.get("count", 0)
            total_amount = summary_result.get("totalAmount", 0.0)
            result_category = summary_result.get("category", target_category)
            
            response_message = f"📊 Expense Summary for Category: {result_category}\n"
            response_message += f"Period: {display_period}\n"
            response_message += f"Total Expenses: {count}\n"
            response_message += f"Total Amount: ${total_amount:.2f}"

            if count == 0:
                response_message += "\n\nNo expenses found for this category in the specified period."

            await update.message.reply_text(response_message)
        else:
            await update.message.reply_text("Could not retrieve summary. No data found or an error occurred.")
    except Exception as e:
        logger.error(f"Error calling Convex getExpenseSummary query for /category: {e}")
        if "User not found" in str(e):
            await update.message.reply_text("User not found. Please /start or /register first.")
        else:
            await update.message.reply_text(f"⚠️ An error occurred while fetching your category summary: {str(e)}")

