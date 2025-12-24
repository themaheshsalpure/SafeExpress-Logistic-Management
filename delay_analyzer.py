import pandas as pd
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class DelayData(BaseModel):
    """Model for individual status delay data"""
    model_config = ConfigDict(
        # Ensure None/null values are included in JSON output
        use_enum_values=True,
        validate_assignment=True
    )
    
    status: str
    delay_by_1_day: Optional[int] = None
    delay_by_2_days: Optional[int] = None
    delay_by_3_days: Optional[int] = None
    delay_by_4_days: Optional[int] = None
    delay_by_5_plus_days: Optional[int] = None
    grand_total: int


class DelayAnalysisResponse(BaseModel):
    """Model for the complete delay analysis response"""
    model_config = ConfigDict(
        # Ensure None/null values are included in JSON output
        use_enum_values=True,
        validate_assignment=True
    )
    
    headers: List[str]
    data: List[DelayData]
    totals: DelayData


# Predefined list of statuses to always include in the response
# These will appear in the specified order, even if they don't exist in the data
PREDEFINED_STATUSES = [
    "In transit",
    "CCF - HOLD",
    "Out for Delivery",
    "Delay due to road conditions",
    "LOST",
    "Service issue - Leh",
    "Attempted Short - Refused"
]


# Predefined list of LSP companies to always include in the response
# These will appear in the specified order, even if they don't exist in the data
PREDEFINED_LSP_COMPANIES = [
    "Safexpress Private Limited",
    "Mass Cargo Private Limited",
    "Delhivery Private Limited",
    "Allcargo logistics limited"
]


class LSPDelayData(BaseModel):
    """Model for individual LSP company delay data"""
    model_config = ConfigDict(
        # Ensure None/null values are included in JSON output
        use_enum_values=True,
        validate_assignment=True
    )
    
    lsp_name: str
    delay_by_1_day: Optional[int] = None
    delay_by_2_days: Optional[int] = None
    delay_by_3_days: Optional[int] = None
    delay_by_4_days: Optional[int] = None
    delay_by_5_plus_days: Optional[int] = None
    grand_total: int


class LSPDelayAnalysisResponse(BaseModel):
    """Model for the complete LSP delay analysis response"""
    model_config = ConfigDict(
        # Ensure None/null values are included in JSON output
        use_enum_values=True,
        validate_assignment=True
    )
    
    headers: List[str]
    data: List[LSPDelayData]
    totals: LSPDelayData


def categorize_delay(delay_value):
    """
    Categorize delay into buckets.
    Handles numeric values (positive = delayed, negative/zero = early/on-time).
    
    Args:
        delay_value: Number of days delayed (positive) or early (negative)
        
    Returns:
        str: Delay category bucket name or None if not delayed
    """
    if pd.isna(delay_value):
        return None
    
    # Try to parse as numeric value
    try:
        delay_num = float(delay_value)
        if delay_num <= 0:
            return None
        elif delay_num == 1:
            return "delay_by_1_day"
        elif delay_num == 2:
            return "delay_by_2_days"
        elif delay_num == 3:
            return "delay_by_3_days"
        elif delay_num == 4:
            return "delay_by_4_days"
        else:  # >= 5
            return "delay_by_5_plus_days"
    except (ValueError, TypeError):
        return None


def clean_delay_column(df: pd.DataFrame, delay_col: str) -> pd.DataFrame:
    """
    Clean and convert delay column to numeric values.
    
    Args:
        df: Pandas DataFrame containing the shipment data
        delay_col: Name of the delay column
        
    Returns:
        pd.DataFrame: DataFrame with cleaned delay column
    """
    # Convert to numeric, coercing errors to NaN
    df[delay_col] = pd.to_numeric(df[delay_col], errors='coerce')
    return df


def find_required_columns(df: pd.DataFrame) -> tuple:
    """
    Find the delay and status columns in the dataframe.
    
    Args:
        df: Pandas DataFrame containing the shipment data
        
    Returns:
        tuple: (delay_column_name, status_column_name)
        
    Raises:
        ValueError: If required columns are not found
    """
    delay_col = None
    status_col = None
    
    for col in df.columns:
        col_lower = str(col).lower().strip()
        # Look for exact match "delay by" (not "delay by bucket")
        if col_lower == 'delay by' or (col_lower.startswith('delay by') and 'bucket' not in col_lower):
            # Prefer columns without "bucket" in the name
            if 'bucket' not in col_lower:
                delay_col = col
        if 'current status' in col_lower or col_lower == 'status':
            status_col = col
    
    # If still not found, try to find any column with "delay by" (excluding bucket)
    if delay_col is None:
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if 'delay by' in col_lower and 'bucket' not in col_lower:
                delay_col = col
                break
    
    if delay_col is None or status_col is None:
        raise ValueError(
            f"Required columns not found. Found columns: {df.columns.tolist()}. "
            f"Need 'Delay by' column (not 'Delay by Bucket') and 'Current Status' or 'Status' column."
        )
    
    return delay_col, status_col


def process_status_delays(status_df: pd.DataFrame, delay_columns: List[str]) -> Dict:
    """
    Process delay data for a specific status.
    
    Args:
        status_df: DataFrame filtered for a specific status
        delay_columns: List of delay category column names
        
    Returns:
        dict: Row data with counts for each delay category
    """
    row_data = {
        "delay_by_1_day": None,
        "delay_by_2_days": None,
        "delay_by_3_days": None,
        "delay_by_4_days": None,
        "delay_by_5_plus_days": None,
        "grand_total": 0
    }
    
    # Count for each delay category
    for delay_cat in delay_columns:
        count = len(status_df[status_df['delay_category'] == delay_cat])
        if count > 0:
            row_data[delay_cat] = count
            row_data['grand_total'] += count
    
    return row_data


def analyze_delays(df: pd.DataFrame) -> Dict:
    """
    Main function to analyze the delay data and create the JSON structure.
    
    Args:
        df: Pandas DataFrame containing shipment data with delay and status columns
        
    Returns:
        dict: Structured delay analysis with headers, data rows, and totals
        
    Raises:
        ValueError: If required columns are not found or data is invalid
    """
    # Find the delay and status columns
    delay_col, status_col = find_required_columns(df)
    
    # Debug: Print column info
    print(f"Found columns - Delay: '{delay_col}', Status: '{status_col}'")
    print(f"Sample delay values: {df[delay_col].head(10).tolist()}")
    
    # Clean and convert delay column to numeric
    df = clean_delay_column(df, delay_col)
    
    # Add delay category column by parsing numeric values
    df['delay_category'] = df[delay_col].apply(categorize_delay)
    
    # Filter only rows with valid delay categories (positive delays only)
    df_delayed = df[df['delay_category'].notna()].copy()
    
    print(f"Total rows with valid delay categories: {len(df_delayed)}")
    print(f"Delay categories found: {df_delayed['delay_category'].value_counts().to_dict()}")
    
    if len(df_delayed) == 0:
        # Return empty structure if no delayed shipments
        return {
            "headers": [
                "Current Status",
                "Delay by 1 Day",
                "Delay by 2 Days",
                "Delay by 3 Days",
                "Delay by 4 Days",
                "Delay by >= 5 Days",
                "Grand Total"
            ],
            "data": [],
            "totals": {
                "status": "Grand Total",
                "delay_by_1_day": None,
                "delay_by_2_days": None,
                "delay_by_3_days": None,
                "delay_by_4_days": None,
                "delay_by_5_plus_days": None,
                "grand_total": 0
            }
        }
    
    # Get unique statuses
    # Get unique statuses from the FULL dataset
    data_statuses = set(df[status_col].dropna().unique())
    
    # Combine predefined statuses with any additional statuses from data
    # Predefined statuses come first in their specified order
    all_statuses = PREDEFINED_STATUSES.copy()
    
    # Add any statuses from data that aren't in the predefined list
    for status in sorted(data_statuses):
        if status not in all_statuses:
            all_statuses.append(status)
    
    # Initialize result structure
    delay_columns = [
        "delay_by_1_day",
        "delay_by_2_days", 
        "delay_by_3_days",
        "delay_by_4_days",
        "delay_by_5_plus_days"
    ]
    
    result_data = []
    totals = {col: 0 for col in delay_columns}
    totals['grand_total'] = 0
    
    # Process each status (including predefined ones that may not exist in data)
    for status in all_statuses:
        # Filter delayed shipments for this status
        status_df = df_delayed[df_delayed[status_col] == status]
        
        row_data = process_status_delays(status_df, delay_columns)
        row_data['status'] = status
        
        # Include ALL statuses (predefined + from data)
        result_data.append(row_data)
        
        # Update totals (only count non-zero values)
        for delay_cat in delay_columns:
            if row_data[delay_cat] is not None:
                totals[delay_cat] += row_data[delay_cat]
        totals['grand_total'] += row_data['grand_total']
    
    # Convert totals to match the response format (None for zero values)
    for key in delay_columns:
        if totals[key] == 0:
            totals[key] = None
    
    # Create the final response
    response = {
        "headers": [
            "Current Status",
            "Delay by 1 Day",
            "Delay by 2 Days",
            "Delay by 3 Days",
            "Delay by 4 Days",
            "Delay by >= 5 Days",
            "Grand Total"
        ],
        "data": result_data,
        "totals": {
            "status": "Grand Total",
            **totals
        }
    }
    
    return response


def analyze_delays_by_lsp(df: pd.DataFrame) -> Dict:
    delay_col = None
    lsp_col = None
    
    for col in df.columns:
        col_lower = str(col).lower().strip()
        if col_lower == 'delay by' or (col_lower.startswith('delay by') and 'bucket' not in col_lower):
            if 'bucket' not in col_lower:
                delay_col = col
        if col_lower == 'lspname' or ('lsp' in col_lower and 'name' in col_lower):
            lsp_col = col
    
    if delay_col is None:
        for col in df.columns:
            col_lower = str(col).lower().strip()
            if 'delay by' in col_lower and 'bucket' not in col_lower:
                delay_col = col
                break
    
    if delay_col is None or lsp_col is None:
        raise ValueError(f"Required columns not found. Found columns: {df.columns.tolist()}. Need 'Delay by' column and 'LSPName' column.")
    
    df = clean_delay_column(df, delay_col)
    df['delay_category'] = df[delay_col].apply(categorize_delay)
    df_delayed = df[df['delay_category'].notna()].copy()
    
    if len(df_delayed) == 0:
        return {
            "headers": ["LSP Name", "Delay by 1 Day", "Delay by 2 Days", "Delay by 3 Days", "Delay by 4 Days", "Delay by >= 5 Days", "Grand Total"],
            "data": [],
            "totals": {"lsp_name": "Grand Total", "delay_by_1_day": None, "delay_by_2_days": None, "delay_by_3_days": None, "delay_by_4_days": None, "delay_by_5_plus_days": None, "grand_total": 0}
        }
    
    # Get unique LSP companies from the data only (no predefined list)
    data_lsps = df[lsp_col].dropna().unique()
    all_lsps = sorted(data_lsps)
    
    delay_columns = ["delay_by_1_day", "delay_by_2_days", "delay_by_3_days", "delay_by_4_days", "delay_by_5_plus_days"]
    result_data = []
    totals = {col: 0 for col in delay_columns}
    totals['grand_total'] = 0
    
    for lsp in all_lsps:
        lsp_df = df_delayed[df_delayed[lsp_col] == lsp]
        row_data = {"delay_by_1_day": None, "delay_by_2_days": None, "delay_by_3_days": None, "delay_by_4_days": None, "delay_by_5_plus_days": None, "grand_total": 0}
        
        for delay_cat in delay_columns:
            count = len(lsp_df[lsp_df['delay_category'] == delay_cat])
            if count > 0:
                row_data[delay_cat] = count
                row_data['grand_total'] += count
        
        row_data['lsp_name'] = lsp
        result_data.append(row_data)
        
        for delay_cat in delay_columns:
            if row_data[delay_cat] is not None:
                totals[delay_cat] += row_data[delay_cat]
        totals['grand_total'] += row_data['grand_total']
    
    for key in delay_columns:
        if totals[key] == 0:
            totals[key] = None
    
    return {
        "headers": ["LSP Name", "Delay by 1 Day", "Delay by 2 Days", "Delay by 3 Days", "Delay by 4 Days", "Delay by >= 5 Days", "Grand Total"],
        "data": result_data,
        "totals": {"lsp_name": "Grand Total", **totals}
    }
