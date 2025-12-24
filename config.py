"""
Configuration settings for the Logistics Status Update System
"""
import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Output directory for updated Excel files
OUTPUT_DIR = Path(r"D:\1 - Ashihs work\Logistic Projects\Lr Number search and update code\Mark 1\output file")

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# SafeExpress tracking URL
SAFEXPRESS_URL = "https://www.safexpress.com/"

# Tracking API Configuration
TRACKING_API_URL = "https://dgapi.safexpress.com/sfxweb/waybillinvoicetracking/v1/trackingbytype"  # Fixed URL - removed 'k' at end
TRACKING_API_TIMEOUT = 30  # seconds
TRACKING_API_TOKEN = "eyJraWQiOiJ4ZStWNmxscE9XWHM4NitFZ1JhWTdSTkIwdzhFZGNWR1UwZm5qWWw3bkNzPSIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiI1YzFscnBoNzYxNW92czE2c245cnBwdmwzYSIsInRva2VuX3VzZSI6ImFjY2VzcyIsInNjb3BlIjoic2VydmVyXC9ib29raW5ncG9kIiwiYXV0aF90aW1lIjoxNzY2NTgxOTQxLCJpc3MiOiJodHRwczpcL1wvY29nbml0by1pZHAuYXAtc291dGgtMS5hbWF6b25hd3MuY29tXC9hcC1zb3V0aC0xXzJrR25OTFQwMiIsImV4cCI6MTc2NjY2ODM0MSwiaWF0IjoxNzY2NTgxOTQxLCJ2ZXJzaW9uIjoyLCJqdGkiOiJjMmM0MjI3Ni05YTcwLTQ4MTMtOThhOS05MGRmYjYxNDhjZmMiLCJjbGllbnRfaWQiOiI1YzFscnBoNzYxNW92czE2c245cnBwdmwzYSJ9.gdTAw3IvwHlC-BVRIDK9batNacPJTWz8o46BczzSo0YrGPIOOMMRHxwoIBetc0yjLcD-75tmgnqxx1QyxN9OpGyRMKRkqvisBngZ6Ls8m-f8r9Fz5rHZG3qQui6wSvpg_-ynwapjdgSutkRHjCMYQUovJLLfciiLNEy5RnD45fKhm49SJqUM8GdsP5BNvHSouGysZEgfugMq-AYFQO9L41eYlf_KoAtjHaHazcr0O4lpjfYmicxZWLfc2eWr3AsDj4LQ9Bpawo1sB1GornRuQ1on-8mq836AW-E7dUYffu80cZ6wWcx1qmmYHbZf2QoWok09FWmYW5nO18KlRilUuA"
TRACKING_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

# Status Detection
LOST_THRESHOLD_DAYS = 30  # Mark IN-TRANSIT shipments as LOST if older than this many days

# Web scraping settings
BROWSER_TIMEOUT = 30000  # 30 seconds in milliseconds
PAGE_LOAD_TIMEOUT = 20000  # 20 seconds
ELEMENT_TIMEOUT = 10000  # 10 seconds

# Rate limiting settings (to avoid being blocked)
REQUEST_DELAY_MIN = 2  # Minimum delay between requests in seconds
REQUEST_DELAY_MAX = 4  # Maximum delay between requests in seconds

# Browser pool settings
BROWSER_POOL_SIZE = 3  # Number of browsers to keep in pool

# LR Number Validation
LR_NUMBER_LENGTH = 12  # Valid LR numbers must be exactly 12 characters

# Batch Processing Configuration
BATCH_SIZE = 25  # Number of LR numbers to process in each batch
MAX_CONCURRENT_REQUESTS = 5  # Maximum concurrent operations (reduced to avoid API rate limiting)
BATCH_DELAY = 5  # Seconds to wait between batches to avoid overwhelming server

# API Retry Configuration
MAX_RETRIES = 3  # Maximum number of retry attempts for failed API calls
RETRY_DELAY = 1  # Initial delay in seconds before retry (will use exponential backoff)
RETRY_BACKOFF_FACTOR = 2  # Multiply delay by this factor on each retry

# Excel column names (as specified in requirements)
EXCEL_COLUMNS = {
    "PLANT": "Plant",
    "WH": "WH",
    "SHIPTOPARTY": "SHIPTOPARTY",
    "SHIPTONAME": "SHIPTONAME",
    "SHIPTOCITY": "SHIPTOCITY",
    "SHIPTOSTATE": "SHIPTOSTATE",
    "SHIPTOPINCODE": "SHIPTOPINCODE",
    "INVOICE_DATE": "InvoiceDate",
    "INV_MONTH": "Inv Month",
    "INVOICE_NO_ERP": "Invoice No. ERP",
    "INVOICE_QTY": "Invoice Qty",
    "LR_NUMBER": "LrNumber",
    "LR_DATE": "LRDate",
    "LSP_NAME": "LSPName",
    "EDD": "EDD",
    "DELIVERY_FORMAT": "Delivery Format",
    "CURRENT_STATUS": "Current Status",
    "REMARKS": "Remarks",
    "CATEGORY": "Category",
    "CCF_TYPE": "CCF Type",
    "REVISED_EDD": "Revised EDD",
    "DELAY_BY": "Delay by",
    "DELAY_BY_BUCKET": "Delay by Bucket"
}

# Required columns for processing
REQUIRED_COLUMNS = [
    EXCEL_COLUMNS["LR_NUMBER"],
    EXCEL_COLUMNS["DELIVERY_FORMAT"],
    EXCEL_COLUMNS["CURRENT_STATUS"]
]

# Logging settings
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
