"""
Status normalization utilities for SafeExpress API responses
"""


def normalize_status(status: str) -> str:
    """
    Normalize status text to proper case format.
    
    Status mappings:
    - "delivered" or "DELIVERED" -> "Delivered"
    - "in-transit" or "IN-TRANSIT" -> "In-transit"
    - "lost" or "LOST" -> "LOST"
    - "out for delivery" -> "Out for Delivery"
    - Other statuses: Title case
    
    Args:
        status: Raw status text from API
        
    Returns:
        Normalized status string
    """
    if not status:
        return ""
    
    # Normalize to lowercase for comparison
    status_lower = status.lower().strip()
    
    # Define specific status mappings
    status_map = {
        "delivered": "Delivered",
        "in-transit": "In-transit",
        "in transit": "In-transit",
        "lost": "LOST",
        "out for delivery": "Out for Delivery",
        "not found": "NOT FOUND",
    }
    
    # Return mapped status if found, otherwise use title case
    return status_map.get(status_lower, status.title())
