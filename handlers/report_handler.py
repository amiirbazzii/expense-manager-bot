# handlers/report_handler.py
import logging
import csv
import io # For creating CSV in memory
from datetime import datetime, timezone
from typing import Optional
from telegram import Update, InputFile
from telegram.ext import ContextTypes

# Assuming parse_period_to_date_range is in parsing_utils
from utils.parsing_utils import parse_period_to_date_range

logger = logging.getLogger(__name__)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         convex_client: any, nlp_processor: any) -> None:
    """Handles the /report command to generate and send a CSV report of expenses."""
    telegram_chat_id = str(update.message.from_user.id)
    # For /report, the argument is primarily the period.
    # Example: /report this month, /report last month, /report October 2023
    period_str_arg = " ".join(context.args) if context.args else "this month" # Default to "this month"
    
    logger.info(f"User {telegram_chat_id} requested /report for period: '{period_str_arg}'")

    try:
        start_timestamp_ms, end_timestamp_ms = parse_period_to_date_range(period_str_arg, nlp_processor)
    except Exception as e:
        logger.error(f"Error parsing period for report: {e}")
        await update.message.reply_text("Sorry, I couldn't understand that period. Please try 'this month', 'last month', or a specific month like 'October 2023'.")
        return

    # For display and filename
    display_period_start_dt = datetime.fromtimestamp(start_timestamp_ms / 1000, tz=timezone.utc)
    display_period_end_dt = datetime.fromtimestamp(end_timestamp_ms / 1000, tz=timezone.utc)
    
    # Create a user-friendly period string for messages and filename
    filename_period_str = ""
    if period_str_arg.lower() == "this month":
        filename_period_str = display_period_start_dt.strftime("%Y-%m") + "_this_month"
    elif period_str_arg.lower() == "last month":
        filename_period_str = display_period_start_dt.strftime("%Y-%m") + "_last_month"
    else:
        # Try to make a concise string from the parsed period_str_arg or dates
        filename_period_str = period_str_arg.replace(" ", "_").replace("/", "-") if period_str_arg else display_period_start_dt.strftime("%Y-%m-%d") + "_to_" + display_period_end_dt.strftime("%Y-%m-%d")
    
    # Sanitize filename_period_str further if needed (remove special chars not good for filenames)
    filename_period_str = "".join(c if c.isalnum() or c in ['-', '_'] else '' for c in filename_period_str)


    await update.message.reply_text(f"Generating your expense report for {period_str_arg}...")

    try:
        query_args = {
            "telegramChatId": telegram_chat_id,
            "startDate": start_timestamp_ms,
            "endDate": end_timestamp_ms,
        }
        expenses_for_report = convex_client.query("queries:getExpensesForReport", query_args)

        if not expenses_for_report:
            await update.message.reply_text(f"No expenses found for the period: {period_str_arg}.")
            return

        # Create CSV in memory
        output = io.StringIO()
        csv_writer = csv.writer(output)
        
        # Write header row
        csv_writer.writerow(['Date', 'Category', 'Amount', 'Description'])
        
        # Write data rows
        for expense in expenses_for_report:
            try:
                # Convert timestamp (milliseconds) to human-readable date
                expense_date_str = datetime.fromtimestamp(expense['date'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            except (TypeError, ValueError):
                expense_date_str = "N/A" # Should not happen if data is clean
            
            csv_writer.writerow([
                expense_date_str,
                expense['category'],
                f"{expense['amount']:.2f}", # Format amount as string with 2 decimal places
                expense.get('description', '') # Use .get for description, default to empty string
            ])
        
        # Get CSV content from StringIO object
        csv_content = output.getvalue()
        output.close()
        
        # Send the CSV file
        # Convert string to bytes for InputFile
        csv_bytes = csv_content.encode('utf-8')
        
        # Create a filename for the report
        report_filename = f"expense_report_{filename_period_str}.csv"
        
        input_file = InputFile(io.BytesIO(csv_bytes), filename=report_filename)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=input_file,
            caption=f"Here's your expense report for {period_str_arg}."
        )
        logger.info(f"Sent CSV report to user {telegram_chat_id} for period '{period_str_arg}'")

    except Exception as e:
        logger.error(f"Error generating or sending report for user {telegram_chat_id}: {e}")
        if "User not found" in str(e):
            await update.message.reply_text("User not found. Please /start or /register first.")
        else:
            await update.message.reply_text(f"⚠️ An error occurred while generating your report: {str(e)}")

