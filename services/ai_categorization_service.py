# services/ai_categorization_service.py
import logging
import json
from typing import Optional, Tuple
import requests

logger = logging.getLogger(__name__)

def get_ai_category_prediction(text_to_predict: str, ai_service_url: str) -> Tuple[Optional[str], Optional[float]]:
    """
    Calls the external AI service to get a category prediction.
    Returns:
        Tuple[Optional[str], Optional[float]]: (predicted_category, confidence_score)
                                                or (None, None) if an error occurs or no prediction.
    """
    if not text_to_predict or not text_to_predict.strip():
        logger.warning("Text for AI prediction is empty or whitespace only. Returning None.")
        return None, 0.0  # Return 0 confidence for empty/whitespace text

    endpoint = f"{ai_service_url.rstrip('/')}/predict_category"
    payload = {"text": text_to_predict}
    
    try:
        logger.info(f"Calling AI service at {endpoint} with payload: {payload}")
        response = requests.post(endpoint, json=payload, timeout=10)  # Added timeout
        response.raise_for_status()  # Raise HTTPError for bad responses (4XX or 5XX)
        
        data = response.json()
        predicted_category = data.get("predicted_category")
        confidence = data.get("confidence")
        
        # Basic validation of response
        if predicted_category is None or confidence is None:
            logger.warning(f"AI service response missing 'predicted_category' or 'confidence'. Response: {data}")
            return None, None
        if not isinstance(predicted_category, str) or not isinstance(confidence, (float, int)):
            logger.warning(f"AI service returned unexpected types. Category: {type(predicted_category)}, Conf: {type(confidence)}")
            return None, None # Or attempt conversion if safe

        logger.info(f"AI Service Response: Category='{predicted_category}', Confidence={confidence}")
        return predicted_category, float(confidence) # Ensure confidence is float

    except requests.exceptions.Timeout:
        logger.error(f"Timeout calling AI service at {endpoint}")
        return None, None
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error calling AI service at {endpoint}: {http_err}. Response: {response.text if 'response' in locals() else 'N/A'}")
        return None, None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request exception calling AI service at {endpoint}: {req_err}")
        return None, None
    except json.JSONDecodeError as json_err:
        logger.error(f"Error decoding JSON response from AI service: {json_err}. Response text: {response.text if 'response' in locals() else 'N/A'}")
        return None, None
    except Exception as e:  # Catch any other unexpected errors
        logger.error(f"Unexpected error during AI service call: {e}", exc_info=True)
        return None, None
