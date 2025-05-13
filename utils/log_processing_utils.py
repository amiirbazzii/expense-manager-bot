# utils/log_processing_utils.py
import logging
import re
from typing import Optional, Tuple, List, Any # Added Any for nlp_processor
from spacy.tokens import Doc # For type hinting spaCy Doc

logger = logging.getLogger(__name__)

def extract_amount_from_text(full_text: str, doc: Doc) -> Tuple[Optional[float], str]:
    """
    Extracts amount from the full text using spaCy entities and regex fallback.
    Returns:
        Tuple[Optional[float], str]: (extracted_amount, text_portion_representing_amount_for_removal)
    """
    amount: Optional[float] = None
    amount_text_for_removal = ""
    
    logger.info(f"--- Amount Extraction (util) for: '{full_text}' ---")
    logger.info(f"spaCy Entities (util): {[(ent.text, ent.label_, ent.start_char, ent.end_char) for ent in doc.ents]}")

    # 1. Try MONEY entity
    for ent in doc.ents:
        if ent.label_ == "MONEY":
            logger.info(f"Processing MONEY entity (util): '{ent.text}'")
            try:
                cleaned_entity_text = ent.text.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
                parsed_val = float(cleaned_entity_text)
                if parsed_val > 0:
                    amount = parsed_val
                    potential_removal_text = ent.text
                    entity_start_char = ent.start_char
                    if not any(c in potential_removal_text for c in "$€£"):
                        if entity_start_char > 0 and full_text[entity_start_char - 1] in "$€£":
                            potential_removal_text = full_text[entity_start_char - 1] + potential_removal_text
                        elif entity_start_char > 1 and full_text[entity_start_char - 2] in "$€£" and full_text[entity_start_char - 1].isspace():
                            potential_removal_text = full_text[entity_start_char - 2:entity_start_char] + potential_removal_text
                    amount_text_for_removal = potential_removal_text
                    logger.info(f"Amount from MONEY (util): {amount}, Text for removal: '{amount_text_for_removal}'")
                    return amount, amount_text_for_removal # Return as soon as found
            except ValueError:
                logger.warning(f"Could not convert MONEY entity text '{ent.text}' (cleaned: '{cleaned_entity_text}') to float.")
    
    # 2. If no MONEY, try CARDINAL
    logger.info("No MONEY entity parsed (util), trying CARDINAL.")
    for ent in doc.ents:
        if ent.label_ == "CARDINAL":
            logger.info(f"Processing CARDINAL entity (util): '{ent.text}'")
            is_part_of_date = any(
                date_ent.label_ == "DATE" and ent.start_char >= date_ent.start_char and ent.end_char <= date_ent.end_char
                for date_ent in doc.ents
            )
            if is_part_of_date:
                logger.info(f"CARDINAL '{ent.text}' is part of a date, skipping.")
                continue
            try:
                cleaned_cardinal_str = ent.text.replace(",", "").strip()
                parsed_val = float(cleaned_cardinal_str)
                if parsed_val > 0:
                    amount = parsed_val
                    potential_removal_text = ent.text
                    entity_start_char = ent.start_char
                    if entity_start_char > 0 and full_text[entity_start_char - 1] in "$€£":
                        potential_removal_text = full_text[entity_start_char - 1] + potential_removal_text
                    elif entity_start_char > 1 and full_text[entity_start_char - 2] in "$€£" and full_text[entity_start_char - 1].isspace():
                         potential_removal_text = full_text[entity_start_char - 2:entity_start_char] + potential_removal_text
                    amount_text_for_removal = potential_removal_text
                    logger.info(f"Amount from CARDINAL (util): {amount}, Text for removal: '{amount_text_for_removal}'")
                    return amount, amount_text_for_removal # Return as soon as found
            except ValueError:
                logger.warning(f"Could not convert CARDINAL entity '{ent.text}' to float.")

    # 3. Regex fallback if still no amount
    logger.info("No amount from spaCy MONEY/CARDINAL entities (util), trying regex fallback.")
    money_match = re.search(r"([\$€£]?)\s*(\d+(?:[\.,]\d+)?(?:\d+)?)", full_text)
    if money_match:
        logger.info(f"Regex fallback matched (util): '{money_match.group(0)}'")
        try:
            number_part = money_match.group(2)
            cleaned_amount_str = number_part.replace(",", "").strip()
            parsed_val = float(cleaned_amount_str)
            if parsed_val > 0:
                amount = parsed_val
                amount_text_for_removal = money_match.group(0).strip()
                logger.info(f"Amount from REGEX (util): {amount}, Text for removal: '{amount_text_for_removal}'")
                return amount, amount_text_for_removal # Return
        except ValueError:
            logger.warning(f"Could not convert regex-found amount '{money_match.group(0)}' to float.")

    logger.info(f"--- End Amount Extraction (util): Amount={amount}, TextForRemoval='{amount_text_for_removal}' ---")
    return amount, amount_text_for_removal


def prepare_text_for_ai(full_text: str, doc: Doc, amount_text_to_remove: str) -> str:
    """
    Cleans the full_text by removing amount, date entities, and common keywords
    to prepare it as a description candidate for the AI service.
    """
    text_for_ai = full_text
    logger.info(f"Initial text for AI/description (util): '{text_for_ai}'")

    if amount_text_to_remove:
        logger.info(f"Attempting to remove amount text (util): '{amount_text_to_remove}'")
        escaped_removal_text = re.escape(amount_text_to_remove)
        text_for_ai = re.sub(escaped_removal_text, '', text_for_ai, 1, flags=re.IGNORECASE)
        text_for_ai = re.sub(r'\s+', ' ', text_for_ai).strip()
        logger.info(f"Text after amount removal (util): '{text_for_ai}'")
    
    date_entity_texts = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
    for date_txt in date_entity_texts:
        logger.info(f"Attempting to remove date text (util): '{date_txt}'")
        escaped_date = re.escape(date_txt)
        text_for_ai = re.sub(r'\b' + escaped_date + r'\b', '', text_for_ai, 1, flags=re.IGNORECASE)
        text_for_ai = re.sub(r'\s+', ' ', text_for_ai).strip()
        logger.info(f"Text after removing '{date_txt}' (util): '{text_for_ai}'")
    
    text_for_ai = re.sub(r'^(on|for|at|spent|buy|bought|get|got|paid)\s+', '', text_for_ai, flags=re.IGNORECASE).strip()
    text_for_ai = re.sub(r'\s+(on|for|at)$', '', text_for_ai, flags=re.IGNORECASE).strip()
    text_for_ai = re.sub(r'\s+', ' ', text_for_ai).strip()
    logger.info(f"Text after keyword/preposition cleanup (util): '{text_for_ai}'")
    
    return text_for_ai if text_for_ai else "N/A" # Return "N/A" if string becomes empty
