# utils/parsing_utils.py
import logging
from datetime import datetime, date, timedelta
import calendar
from typing import Optional, Tuple, Dict, List

logger = logging.getLogger(__name__)

def parse_date_to_timestamp(date_str: Optional[str], text_for_nlp: str, nlp_processor: any) -> int:
    """
    Parses a date string or extracts date from text_for_nlp using spaCy.
    Returns a Unix timestamp in milliseconds.
    Defaults to today if no date is found.
    """
    target_date = date.today() # Default to today

    if date_str:
        date_str_lower = date_str.strip().lower()
        if date_str_lower == "today":
            target_date = date.today()
        elif date_str_lower == "yesterday":
            target_date = date.today() - timedelta(days=1)
        else:
            try:
                target_date = datetime.strptime(date_str_lower, "%Y-%m-%d").date()
            except ValueError:
                try:
                    target_date = datetime.strptime(date_str_lower, "%m/%d/%Y").date()
                except ValueError:
                    logger.warning(f"Could not parse explicit date_str '{date_str_lower}' with simple formats.")
                    pass # Fall through to NLP

    if target_date == date.today() or not date_str:
        doc = nlp_processor(text_for_nlp)
        parsed_date_from_nlp = None
        for ent in doc.ents:
            if ent.label_ == "DATE":
                ent_text_lower = ent.text.lower()
                if "today" in ent_text_lower:
                    parsed_date_from_nlp = date.today()
                    break
                elif "yesterday" in ent_text_lower:
                    parsed_date_from_nlp = date.today() - timedelta(days=1)
                    break
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
                            pass
        if parsed_date_from_nlp:
            target_date = parsed_date_from_nlp
        elif not date_str:
             logger.warning(f"No clear date found in text '{text_for_nlp}' via NLP. Defaulting to today.")

    dt_obj = datetime(target_date.year, target_date.month, target_date.day)
    return int(dt_obj.timestamp() * 1000)

def determine_category(text: str, nlp_processor: any, predefined_categories: Dict[str, List[str]], default_category: str) -> str:
    """Determines category based on keywords in the text."""
    text_lower = text.lower()
    doc = nlp_processor(text_lower)
    lemmatized_keywords_in_text = [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]

    for category, keywords in predefined_categories.items():
        for keyword in keywords:
            if keyword in lemmatized_keywords_in_text:
                if " " in keyword and keyword in text_lower:
                    return category
                elif " " not in keyword:
                    return category
    return default_category

def parse_period_to_date_range(period_str: Optional[str], nlp_processor: any) -> Tuple[int, int]:
    """
    Parses a period string (e.g., "this month", "last month", "October", "2023-05", "May 2023")
    and returns a tuple of (start_timestamp_ms, end_timestamp_ms).
    Defaults to "this month" if period_str is None or parsing fails.
    nlp_processor is passed for potential future use in more advanced period parsing.
    """
    today = date.today()
    year = today.year
    month = today.month
    
    # Default to current month
    start_date = date(year, month, 1)
    _, last_day_of_month = calendar.monthrange(year, month)
    end_date = date(year, month, last_day_of_month)

    if period_str:
        period_str_lower = period_str.strip().lower()
        if not period_str_lower: # Empty string after strip
             pass # Use default (current month)
        elif period_str_lower == "this month":
            pass # Use default (current month)
        elif period_str_lower == "last month":
            first_day_of_current_month = date(year, month, 1)
            last_day_of_last_month = first_day_of_current_month - timedelta(days=1)
            start_date = date(last_day_of_last_month.year, last_day_of_last_month.month, 1)
            end_date = last_day_of_last_month
        else:
            parsed_specific_month = False
            try:
                dt_obj = datetime.strptime(period_str.strip(), "%B %Y") # "October 2023"
                year, month = dt_obj.year, dt_obj.month
                parsed_specific_month = True
            except ValueError:
                try:
                    dt_obj = datetime.strptime(period_str.strip(), "%B") # "October" (current year)
                    month = dt_obj.month
                    # Year remains current year (already set)
                    parsed_specific_month = True
                except ValueError:
                    try:
                        year_month_parts = period_str.strip().split('-') # "2023-10"
                        if len(year_month_parts) == 2:
                            year, month = int(year_month_parts[0]), int(year_month_parts[1])
                            parsed_specific_month = True
                        else: raise ValueError("Not YYYY-MM")
                    except (ValueError, IndexError):
                        try:
                            month_year_parts = period_str.strip().split('/') # "10/2023"
                            if len(month_year_parts) == 2:
                                 month, year = int(month_year_parts[0]), int(month_year_parts[1])
                                 parsed_specific_month = True
                            else: raise ValueError("Not MM/YYYY")
                        except (ValueError, IndexError):
                            logger.warning(f"Could not parse period string '{period_str}'. Defaulting to 'this month'.")
                            # Default values are already set, so just pass

            if parsed_specific_month:
                start_date = date(year, month, 1)
                _, last_day_of_month = calendar.monthrange(year, month)
                end_date = date(year, month, last_day_of_month)

    start_timestamp_ms = int(datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0).timestamp() * 1000)
    end_timestamp_ms = int(datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999999).timestamp() * 1000)
    
    return start_timestamp_ms, end_timestamp_ms
