# utils/intent_recognition_utils.py
import logging
from typing import Optional, Any # For nlp_processor type
from spacy.tokens import Doc # For type hinting spaCy Doc

logger = logging.getLogger(__name__)

# Define intent types as constants
INTENT_LOG_EXPENSE = "LOG_EXPENSE"
INTENT_QUERY_SUMMARY = "QUERY_SUMMARY" # Example for future expansion
INTENT_QUERY_DETAILS = "QUERY_DETAILS" # Example for future expansion
INTENT_UNKNOWN = "UNKNOWN"

# Keywords suggesting an expense logging action
LOGGING_KEYWORDS = [
    "spent", "paid", "bought", "got", "cost", "expense", "charge", "used", "purchased"
    # Add more Farsi keywords if you plan to support them here
]

# Keywords suggesting a query (examples, can be expanded)
QUERY_KEYWORDS = [
    "how much", "show me", "what did i spend", "summary", "details", "report", "category spending"
]

def get_message_intent(text: str, nlp_processor: Any) -> str:
    """
    Analyzes the raw message text to determine user intent.
    For Phase 3, focuses on identifying INTENT_LOG_EXPENSE.
    Returns an intent string (e.g., INTENT_LOG_EXPENSE) or INTENT_UNKNOWN.
    """
    if not text or not text.strip():
        return INTENT_UNKNOWN

    text_lower = text.lower()
    doc: Doc = nlp_processor(text_lower) # Process with spaCy

    # --- Heuristic 1: Presence of monetary amounts ---
    has_money_entity = any(ent.label_ == "MONEY" for ent in doc.ents)
    # Check for cardinals that might be amounts (e.g., "5 for coffee")
    # Be careful not to misinterpret cardinals in dates or other contexts.
    has_potential_amount_cardinal = False
    if not has_money_entity:
        for ent in doc.ents:
            if ent.label_ == "CARDINAL":
                # Simple check: if the cardinal is just a number and not part of a date entity.
                is_part_of_date = any(
                    date_ent.label_ == "DATE" and ent.start_char >= date_ent.start_char and ent.end_char <= date_ent.end_char
                    for date_ent in doc.ents
                )
                if not is_part_of_date and ent.text.isdigit(): # Simple check if it's a number
                    has_potential_amount_cardinal = True
                    break
    
    has_amount_indicator = has_money_entity or has_potential_amount_cardinal
    logger.debug(f"Intent check for '{text_lower}': HasAmount={has_amount_indicator} (MONEY: {has_money_entity}, CARDINAL: {has_potential_amount_cardinal})")


    # --- Heuristic 2: Presence of logging keywords ---
    found_logging_keyword = False
    # Check lemmas for better matching
    lemmatized_tokens = [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]
    for keyword in LOGGING_KEYWORDS:
        if keyword in lemmatized_tokens or keyword in text_lower: # Check both lemma and raw text
            found_logging_keyword = True
            logger.debug(f"Intent check: Found logging keyword '{keyword}'")
            break
    
    # --- Heuristic 3: Absence of strong query keywords (simple check) ---
    # This is a very basic way to avoid misinterpreting queries as logs.
    # More sophisticated intent classification would be needed for robust differentiation.
    is_likely_query = False
    for q_keyword in QUERY_KEYWORDS:
        if q_keyword in text_lower:
            is_likely_query = True
            logger.debug(f"Intent check: Found query keyword '{q_keyword}'")
            break

    # --- Decision Logic (simple for now) ---
    # If it has an amount and a logging keyword, and isn't clearly a query, assume log.
    if has_amount_indicator and found_logging_keyword and not is_likely_query:
        logger.info(f"Intent recognized for '{text}': {INTENT_LOG_EXPENSE}")
        return INTENT_LOG_EXPENSE
    
    # If it has an amount but no strong logging keyword, it's ambiguous.
    # For now, we won't treat this as a log unless a keyword is present.
    # Could be refined later (e.g., if it has amount AND date, it's more likely a log).

    logger.info(f"Intent recognized for '{text}': {INTENT_UNKNOWN}")
    return INTENT_UNKNOWN

if __name__ == '__main__':
    # Example usage for testing this module directly
    # You would need to initialize nlp = spacy.load("en_core_web_sm") here for testing
    # For now, this block is for illustration.
    # nlp_test = spacy.load("en_core_web_sm")
    # test_phrases = [
    #     "spent $20 on lunch yesterday",
    #     "paid 15 for coffee",
    #     "got groceries for 50 dollars",
    #     "how much did I spend on food?",
    #     "show me my report for last month",
    #     "10 dollars for taxi", # Might be ambiguous without a strong verb
    #     "movie tickets 25" # Also ambiguous
    # ]
    # for phrase in test_phrases:
    #     intent = get_message_intent(phrase, nlp_test)
    #     print(f"'{phrase}' -> Intent: {intent}")
    pass
