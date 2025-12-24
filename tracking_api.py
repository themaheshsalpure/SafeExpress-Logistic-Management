"""
Tracking API module for SafeExpress shipment status
Calls the tracking API and parses status responses
"""
import asyncio
import aiohttp
import json
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

from config import (
    TRACKING_API_URL, 
    TRACKING_API_TIMEOUT, 
    TRACKING_API_TOKEN,
    TRACKING_USER_AGENT,
    LOST_THRESHOLD_DAYS,
    MAX_RETRIES,
    RETRY_DELAY,
    RETRY_BACKOFF_FACTOR
)
from status_normalizer import normalize_status

logger = logging.getLogger(__name__)


async def fetch_tracking_status(session: aiohttp.ClientSession, lr_number: str, retry_count: int = 0) -> Dict:
    """
    Fetch tracking status for a single LR number from API
    
    Args:
        session: aiohttp session
        lr_number: LR number to track
        
    Returns:
        Dictionary with status information
    """
    try:
        # Prepare headers
        headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,es;q=0.7',
            'content-type': 'application/json',
            'origin': 'https://www.safexpress.com',
            'referer': 'https://www.safexpress.com/',
            'token': TRACKING_API_TOKEN,
            'user-agent': TRACKING_USER_AGENT,
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site'
        }
        
        # Prepare body in the correct format
        body = {
            "docNo": [lr_number],
            "docType": "WB"
        }
        
        # Make API call
        async with session.post(
            TRACKING_API_URL,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=TRACKING_API_TIMEOUT)
        ) as response:
            if response.status == 200:
                try:
                    # Read response text first to capture content on error
                    text = await response.text()
                    
                    # Check if response is empty
                    if not text or not text.strip():
                        raise ValueError("Empty response from API")
                    
                    # Check content type
                    if response.content_type and 'json' not in response.content_type.lower():
                        logger.warning(f"Unexpected content-type for LR {lr_number}: {response.content_type}")
                    
                    # Parse text as JSON
                    data = json.loads(text)
                    
                    return parse_tracking_response(data, lr_number)
                except (json.JSONDecodeError, ValueError) as e:
                    # Retry on JSON parse errors (often caused by empty responses from rate limiting)
                    if retry_count < MAX_RETRIES:
                        delay = RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** retry_count)
                        logger.warning(f"JSON parse error for LR {lr_number}: {type(e).__name__}, retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})")
                        logger.warning(f"Response text (first 200 chars): {text[:200] if 'text' in locals() else 'N/A'}")
                        await asyncio.sleep(delay)
                        return await fetch_tracking_status(session, lr_number, retry_count + 1)
                    # After all retries exhausted
                    logger.error(f"Failed to parse JSON for LR {lr_number} after {MAX_RETRIES} retries: {e}")
                    logger.error(f"Response text (first 1000 chars): {text[:1000] if 'text' in locals() else 'N/A'}")
                    logger.error(f"Content-Type: {response.content_type}")
                    logger.error(f"Full exception: {type(e).__name__}: {str(e)}", exc_info=True)
                    return {
                        "lr_number": lr_number,
                        "status": "ERROR",
                        "error": f"JSON parse error after retries: {type(e).__name__}"
                    }
                except Exception as e:
                    logger.error(f"Unexpected error parsing response for LR {lr_number}: {type(e).__name__} - {str(e)}", exc_info=True)
                    return {
                        "lr_number": lr_number,
                        "status": "ERROR",
                        "error": f"Parse error: {type(e).__name__} - {str(e)}"
                    }
            else:
                logger.error(f"API error for LR {lr_number}: HTTP {response.status}")
                return {
                    "lr_number": lr_number,
                    "status": "ERROR",
                    "error": f"HTTP {response.status}"
                }
    except asyncio.TimeoutError:
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** retry_count)
            logger.warning(f"Timeout for LR {lr_number}, retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})")
            await asyncio.sleep(delay)
            return await fetch_tracking_status(session, lr_number, retry_count + 1)
        logger.error(f"Timeout for LR {lr_number} after {MAX_RETRIES} retries (timeout: {TRACKING_API_TIMEOUT}s)")
        return {
            "lr_number": lr_number,
            "status": "ERROR",
            "error": "API Timeout (after retries)"
        }
    except aiohttp.ClientError as e:
        if retry_count < MAX_RETRIES:
            delay = RETRY_DELAY * (RETRY_BACKOFF_FACTOR ** retry_count)
            logger.warning(f"HTTP client error for LR {lr_number}: {type(e).__name__}, retrying in {delay}s (attempt {retry_count + 1}/{MAX_RETRIES})")
            await asyncio.sleep(delay)
            return await fetch_tracking_status(session, lr_number, retry_count + 1)
        logger.error(f"HTTP client error for LR {lr_number} after {MAX_RETRIES} retries: {type(e).__name__} - {str(e)}")
        return {
            "lr_number": lr_number,
            "status": "ERROR",
            "error": f"HTTP Error: {type(e).__name__} (after retries)"
        }
    except Exception as e:
        logger.error(f"Unexpected error fetching status for LR {lr_number}: {type(e).__name__} - {str(e)}", exc_info=True)
        return {
            "lr_number": lr_number,
            "status": "ERROR",
            "error": f"{type(e).__name__}: {str(e)}"
        }


def parse_tracking_response(data: Dict, lr_number: str) -> Dict:
    """
    Parse the tracking API response and determine final status
    
    Args:
        data: API response JSON
        lr_number: LR number
        
    Returns:
        Dictionary with parsed status
    """
    try:
        logger.info(f"Parsing response for LR {lr_number}: {data}")
        
        if data.get("status") != "Ok":
            error_msg = data.get("message", "Invalid API response")
            logger.error(f"API returned non-OK status for LR {lr_number}: {error_msg}")
            return {
                "lr_number": lr_number,
                "status": "NOT FOUND",
                "error": error_msg
            }
        
        tracking_data = data.get("data", {}).get("tracking", [])
        if not tracking_data:
            logger.warning(f"No tracking data for LR {lr_number}")
            return {
                "lr_number": lr_number,
                "status": "NOT FOUND",
                "error": "No tracking data"
            }
        
        # Get the first tracking entry
        tracking = tracking_data[0]
        statuses = tracking.get("status", [])
        
        if not statuses:
            logger.warning(f"No status information for LR {lr_number}")
            return {
                "lr_number": lr_number,
                "status": "NOT FOUND",
                "error": "No status information"
            }
        
        # Get the latest status (last item in the list)
        latest_status = statuses[-1]
        status_text = normalize_status(latest_status.get("status", ""))
        track_date_str = latest_status.get("trackDate", "")
        
        logger.info(f"LR {lr_number}: Latest status = {status_text}, Date = {track_date_str}")
        
        # Parse date
        track_date = None
        if track_date_str:
            try:
                track_date = datetime.strptime(track_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logger.warning(f"Could not parse date '{track_date_str}' for LR {lr_number}: {e}")
        
        # Check if In-transit for too long (mark as LOST)
        if status_text == "In-transit" and track_date:
            days_in_transit = (datetime.now() - track_date).days
            if days_in_transit > LOST_THRESHOLD_DAYS:
                logger.info(f"LR {lr_number}: In-transit for {days_in_transit} days, marking as LOST")
                status_text = "LOST"
        
        return {
            "lr_number": lr_number,
            "status": status_text,
            "track_date": track_date_str,
            "mode": latest_status.get("mode", ""),
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Error parsing response for LR {lr_number}: {e}", exc_info=True)
        return {
            "lr_number": lr_number,
            "status": "ERROR",
            "error": f"Parse error: {str(e)}"
        }


async def track_multiple_lr_numbers(lr_numbers: list, max_concurrent: int = 10) -> Dict[str, Dict]:
    """
    Track multiple LR numbers in parallel
    
    Args:
        lr_numbers: List of LR numbers to track
        max_concurrent: Maximum concurrent API calls
        
    Returns:
        Dictionary mapping LR numbers to their status
    """
    results = {}
    
    # Create semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_with_semaphore(session, lr_num):
        async with semaphore:
            return await fetch_tracking_status(session, lr_num)
    
    # Create aiohttp session
    async with aiohttp.ClientSession() as session:
        # Create tasks for all LR numbers
        tasks = [fetch_with_semaphore(session, lr_num) for lr_num in lr_numbers]
        
        # Execute all tasks concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build results dictionary
        for response in responses:
            if isinstance(response, Exception):
                logger.error(f"Exception in tracking: {response}")
                continue
            
            lr_num = response.get("lr_number")
            if lr_num:
                results[lr_num] = response
    
    return results
