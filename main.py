"""
Simple FastAPI Application for Excel Processing
Finds LR numbers with NA in Delivery Format column
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import pandas as pd
import base64 

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import requests
from typing import Dict, Any

from fastapi.middleware.cors import CORSMiddleware
from delay_analyzer import (
    analyze_delays, 
    DelayAnalysisResponse,
    analyze_delays_by_lsp,
    LSPDelayAnalysisResponse
)

from excel_processor import ExcelProcessor
from config import OUTPUT_DIR, LR_NUMBER_LENGTH, BATCH_SIZE, MAX_CONCURRENT_REQUESTS
from tracking_api import track_multiple_lr_numbers
import io

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="LR Number Lookup System",
    description="Find LR numbers with NA in Delivery Format column",
    version="2.0.0"
)


# Added later additional middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LRNumbersResponse(BaseModel):
    """Response model for LR numbers"""
    total_records: int
    na_count: int
    valid_lr_numbers: List[str]
    invalid_lr_numbers: List[str]
    first_valid_lr_number: Optional[str] = None
    processing_info: Optional[dict] = None
    statuses_updated: Optional[int] = None
    output_file: Optional[str] = None


class ProcessingConfig(BaseModel):
    """Configuration for parallel processing"""
    batch_size: int = 50  # Process 50 LR numbers at a time
    max_concurrent: int = 10  # Max 10 concurrent operations


async def process_lr_batch(lr_numbers: List[str], batch_size: int = 50) -> dict:
    """
    Process LR numbers in batches for parallel operations
    
    Args:
        lr_numbers: List of LR numbers to process
        batch_size: Size of each batch
        
    Returns:
        Processing statistics
    """
    total_count = len(lr_numbers)
    num_batches = (total_count + batch_size - 1) // batch_size
    
    logger.info(f"Processing {total_count} LR numbers in {num_batches} batches of {batch_size}")
    
    # Split into batches
    batches = []
    for i in range(0, total_count, batch_size):
        batch = lr_numbers[i:i + batch_size]
        batches.append(batch)
    
    return {
        "total_lr_numbers": total_count,
        "num_batches": num_batches,
        "batch_size": batch_size,
        "batches_created": len(batches)
    }


class TokenResponse(BaseModel):
    msg: str
    error: str
    status: str
    result: str


def generate_safexpress_token() -> Dict[str, Any]:
    """
    Generate authentication token from SafExpress API.
    
    Returns:
        dict: Response containing the token and status information
    """
    url = 'https://dgapi.safexpress.com/sfxweb/waybillinvoicetracking/v1/getpropeliauth2token'
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,es;q=0.7',
        'dnt': '1',
        'origin': 'https://www.safexpress.com',
        'priority': 'u=1, i',
        'referer': 'https://www.safexpress.com/',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.RequestException as e:
        return {
            "msg": "",
            "error": str(e),
            "status": "error",
            "result": "failed"
        }

# API endpoint
@app.get("/api/generate-token", response_model=TokenResponse)
async def get_safexpress_token():
    """
    Generate SafExpress authentication token.
    
    Returns:
        TokenResponse: Contains the authentication token and status
    """
    token_data = generate_safexpress_token()
    
    if token_data.get('result') == 'success':
        return JSONResponse(content=token_data, status_code=200)
    else:
        return JSONResponse(content=token_data, status_code=500)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "LR Number Lookup System",
        "version": "2.0.0",
        "endpoints": {
            "POST /process": "Upload Excel file and get LR numbers with NA delivery format",
            "GET /docs": "API documentation"
        }
    }


@app.post("/process", response_model=LRNumbersResponse)
async def process_excel(file: UploadFile = File(..., description="Excel file to process")):
    """
    Process Excel file, track LR numbers, update statuses, and return updated file
    
    Args:
        file: Excel file upload
        
    Returns:
        Processing results with download link to updated Excel file
    """
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )
    
    try:
        # Save uploaded file temporarily
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        temp_file_path = temp_dir / file.filename
        
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"File uploaded: {file.filename}")
        
        # Read Excel file, enforcing string for LrNumber to avoid scientific notation
        df = pd.read_excel(temp_file_path, dtype={'LrNumber': str})
        logger.info(f"Loaded {len(df)} rows")

        # Finding missing delivery formats
        missing_delivery_mask = df['Delivery Format'].isna()
        all_lr_numbers = df.loc[missing_delivery_mask, 'LrNumber'].astype(str).tolist()
        
        # Validate LR numbers by length
        valid_lr_numbers = [lr for lr in all_lr_numbers if len(lr) == LR_NUMBER_LENGTH]
        invalid_lr_numbers = [lr for lr in all_lr_numbers if len(lr) != LR_NUMBER_LENGTH]
        
        logger.info(f"Total LR numbers: {len(all_lr_numbers)}, Valid: {len(valid_lr_numbers)}, Invalid: {len(invalid_lr_numbers)}")
        
        # Track statuses for valid LR numbers in parallel
        if valid_lr_numbers:
            logger.info(f"Fetching statuses for {len(valid_lr_numbers)} LR numbers...")
            tracking_results = await track_multiple_lr_numbers(
                valid_lr_numbers,
                max_concurrent=MAX_CONCURRENT_REQUESTS
            )
            
            # Update Excel file with statuses
            statuses_updated = 0
            for lr_number, result in tracking_results.items():
                status = result.get('status', 'ERROR')
                
                # Find rows with this LR number and update Current Status
                lr_mask = (df['LrNumber'].astype(str) == lr_number) & missing_delivery_mask
                if lr_mask.any():
                    df.loc[lr_mask, 'Current Status'] = status
                    # Convert Delivery Format to string to avoid dtype warning
                    df['Delivery Format'] = df['Delivery Format'].astype(str)
                    df.loc[lr_mask, 'Delivery Format'] = 'done'
                    statuses_updated += 1
                    logger.info(f"Updated LR {lr_number}: {status}")
            
            # Save updated Excel file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{Path(file.filename).stem}_updated_{timestamp}.xlsx"
            output_path = OUTPUT_DIR / output_filename
            
            df.to_excel(output_path, index=False)
            logger.info(f"Saved updated file to: {output_path}")
        else:
            statuses_updated = 0
            output_path = None
        
        # Process batches info
        processing_info = await process_lr_batch(
            valid_lr_numbers, 
            batch_size=BATCH_SIZE
        )
        processing_info['max_concurrent'] = MAX_CONCURRENT_REQUESTS
        processing_info['valid_lr_count'] = len(valid_lr_numbers)
        processing_info['invalid_lr_count'] = len(invalid_lr_numbers)
        processing_info['lr_number_length_required'] = LR_NUMBER_LENGTH
        processing_info['statuses_fetched'] = len(tracking_results) if valid_lr_numbers else 0
        
        # Clean up temp file
        try:
            temp_file_path.unlink()
        except:
            pass    
        
        return LRNumbersResponse(
            total_records=len(df),
            na_count=len(all_lr_numbers),
            valid_lr_numbers=valid_lr_numbers,
            invalid_lr_numbers=invalid_lr_numbers,
            first_valid_lr_number=valid_lr_numbers[0] if valid_lr_numbers else None,
            processing_info=processing_info,
            statuses_updated=statuses_updated,
            output_file=str(output_path) if output_path else None
        )
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")





class FileUploadBase64(BaseModel):
    file: str  # base64 encoded file content
    filename: str  # original filename




# Add NEW endpoint for base64 input from Power Automate
@app.post("/process-base64", response_model=LRNumbersResponse)
async def process_excel_base64(data: FileUploadBase64):
    """
    Process Excel file from base64 encoded content (for Power Automate)
    
    Args:
        data: JSON with base64 encoded file and filename
        
    Returns:
        Processing results with download link to updated Excel file
    """
    # Validate file type
    if not data.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )
    
    try:
        # Decode base64 to bytes
        try:
            file_content = base64.b64decode(data.file)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 encoding: {str(e)}"
            )
        
        # Save uploaded file temporarily
        temp_dir = Path("temp_uploads")
        temp_dir.mkdir(exist_ok=True)
        temp_file_path = temp_dir / data.filename
        
        with open(temp_file_path, "wb") as buffer:
            buffer.write(file_content)
        
        logger.info(f"File uploaded: {data.filename}")
        
        # Read Excel file, enforcing string for LrNumber to avoid scientific notation
        df = pd.read_excel(temp_file_path, dtype={'LrNumber': str})
        logger.info(f"Loaded {len(df)} rows")

        # Finding missing delivery formats
        missing_delivery_mask = df['Delivery Format'].isna()
        all_lr_numbers = df.loc[missing_delivery_mask, 'LrNumber'].astype(str).tolist()
        
        # Validate LR numbers by length
        valid_lr_numbers = [lr for lr in all_lr_numbers if len(lr) == LR_NUMBER_LENGTH]
        invalid_lr_numbers = [lr for lr in all_lr_numbers if len(lr) != LR_NUMBER_LENGTH]
        
        logger.info(f"Total LR numbers: {len(all_lr_numbers)}, Valid: {len(valid_lr_numbers)}, Invalid: {len(invalid_lr_numbers)}")
        
        # Track statuses for valid LR numbers in parallel
        if valid_lr_numbers:
            logger.info(f"Fetching statuses for {len(valid_lr_numbers)} LR numbers...")
            tracking_results = await track_multiple_lr_numbers(
                valid_lr_numbers,
                max_concurrent=MAX_CONCURRENT_REQUESTS
            )
            
            # Update Excel file with statuses
            statuses_updated = 0
            for lr_number, result in tracking_results.items():
                status = result.get('status', 'ERROR')
                
                # Find rows with this LR number and update Current Status
                lr_mask = (df['LrNumber'].astype(str) == lr_number) & missing_delivery_mask
                if lr_mask.any():
                    df.loc[lr_mask, 'Current Status'] = status
                    # Convert Delivery Format to string to avoid dtype warning
                    df['Delivery Format'] = df['Delivery Format'].astype(str)
                    df.loc[lr_mask, 'Delivery Format'] = 'done'
                    statuses_updated += 1
                    logger.info(f"Updated LR {lr_number}: {status}")
            
            # Save updated Excel file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{Path(data.filename).stem}_updated_{timestamp}.xlsx"
            output_path = OUTPUT_DIR / output_filename
            
            df.to_excel(output_path, index=False)
            logger.info(f"Saved updated file to: {output_path}")
        else:
            statuses_updated = 0
            output_path = None
        
        # Process batches info
        processing_info = await process_lr_batch(
            valid_lr_numbers, 
            batch_size=BATCH_SIZE
        )
        processing_info['max_concurrent'] = MAX_CONCURRENT_REQUESTS
        processing_info['valid_lr_count'] = len(valid_lr_numbers)
        processing_info['invalid_lr_count'] = len(invalid_lr_numbers)
        processing_info['lr_number_length_required'] = LR_NUMBER_LENGTH
        processing_info['statuses_fetched'] = len(tracking_results) if valid_lr_numbers else 0
        
        # Clean up temp file
        try:
            temp_file_path.unlink()
        except:
            pass    
        
        return LRNumbersResponse(
            total_records=len(df),
            na_count=len(all_lr_numbers),
            valid_lr_numbers=valid_lr_numbers,
            invalid_lr_numbers=invalid_lr_numbers,
            first_valid_lr_number=valid_lr_numbers[0] if valid_lr_numbers else None,
            processing_info=processing_info,
            statuses_updated=statuses_updated,
            output_file=str(output_path) if output_path else None
        )
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")



# NEW ENDPOINT: Base64 version for Power Automate
@app.post("/analyze-delays-base64", response_model=DelayAnalysisResponse, response_model_exclude_none=False)
async def analyze_delay_file_base64(data: FileUploadBase64):
    """
    Upload an Excel file (as base64) to analyze shipment delays.
    For Power Automate integration.
    
    Expected columns:
    - Current Status (or Status)
    - Delay by [unit] (any column containing "delay by")
    
    Returns:
    - JSON structure with delay analysis categorized by status and delay duration
    """
    try:
        # Decode base64 to bytes
        try:
            file_content = base64.b64decode(data.file)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 encoding: {str(e)}"
            )
        
        # Determine file type and read accordingly
        if data.filename.endswith('.xlsx') or data.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(file_content))
        elif data.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload .xlsx, .xls, or .csv file"
            )
        
        # Analyze delays using the logic from delay_analyzer.py
        result = analyze_delays(df)
        
        html_table = build_html_table(result)
        result["html_table"] = html_table

        # write the table HTML into file to test
        with open("testAnalyzedTable.html", "w", encoding="utf-8") as f:
            f.write(result["html_table"])

        print(f"Result Returned from delay analyzation API (base64): {result}")
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    



    
def build_html_table(response_json: dict) -> str:
    headers = response_json["headers"]
    rows = response_json["data"]
    totals = response_json.get("totals")

    def safe(val):
        return "-" if val is None else val

    html = """
<table width="100%" cellpadding="8" cellspacing="0"
style="border-collapse:collapse;font-family:Arial,sans-serif;
font-size:13px;border:1px solid #cccccc;">
"""

    # Header row
    html += "<tr style='background-color:#2f80ed;color:#ffffff;font-weight:bold;'>"
    for h in headers:
        html += f"""
        <th style="border:1px solid #cccccc;text-align:center;">
            {h}
        </th>
        """
    html += "</tr>"

    # Data rows with zebra striping
    for i, row in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#f9fafb"
        html += f"<tr style='background-color:{bg};'>"
        html += f"<td style='border:1px solid #cccccc;font-weight:500;'>{row['status']}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_1_day'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_2_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_3_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_4_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_5_plus_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;font-weight:bold;'>{row['grand_total']}</td>"
        html += "</tr>"

    # Totals row
    if totals:
        html += """
<tr style="background-color:#fff3cd;font-weight:bold;">
"""
        html += f"<td style='border:1px solid #cccccc;'>{totals['status']}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_1_day'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_2_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_3_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_4_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_5_plus_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;color:#b45309;'>{totals['grand_total']}</td>"
        html += "</tr>"

    html += "</table>"
    return html



def build_lsp_html_table(response_json: dict) -> str:
    headers = response_json["headers"]
    rows = response_json["data"]
    totals = response_json.get("totals")

    def safe(val):
        return "-" if val is None else val

    html = """
<table width="100%" cellpadding="8" cellspacing="0"
style="border-collapse:collapse;font-family:Arial,sans-serif;
font-size:13px;border:1px solid #cccccc;">
"""

    # Header
    html += "<tr style='background-color:#27ae60;color:#ffffff;font-weight:bold;'>"
    for h in headers:
        html += f"""
        <th style="border:1px solid #cccccc;text-align:center;">
            {h}
        </th>
        """
    html += "</tr>"

    # Data rows
    for i, row in enumerate(rows):
        bg = "#ffffff" if i % 2 == 0 else "#f9fafb"
        html += f"<tr style='background-color:{bg};'>"
        html += f"<td style='border:1px solid #cccccc;font-weight:500;'>{row['lsp_name']}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_1_day'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_2_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_3_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_4_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(row['delay_by_5_plus_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;font-weight:bold;'>{row['grand_total']}</td>"
        html += "</tr>"

    # Totals row
    if totals:
        html += """
<tr style="background-color:#e6fffa;font-weight:bold;">
"""
        html += f"<td style='border:1px solid #cccccc;'>{totals['lsp_name']}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_1_day'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_2_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_3_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_4_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;'>{safe(totals['delay_by_5_plus_days'])}</td>"
        html += f"<td style='border:1px solid #cccccc;text-align:center;color:#065f46;'>{totals['grand_total']}</td>"
        html += "</tr>"

    html += "</table>"
    return html



@app.post("/analyze-delays", response_model=DelayAnalysisResponse, response_model_exclude_none=False)
async def analyze_delay_file(file: UploadFile = File(...)):
    """
    Upload an Excel file to analyze shipment delays.
    
    Expected columns:
    - Current Status (or Status)
    - Delay by [unit] (any column containing "delay by")
    
    Returns:
    - JSON structure with delay analysis categorized by status and delay duration
    """
    try:
        # Read the uploaded file
        contents = await file.read()
        
        # Determine file type and read accordingly
        if file.filename.endswith('.xlsx') or file.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(contents))
        elif file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload .xlsx, .xls, or .csv file"
            )
        
        # Analyze delays using the logic from delay_analyzer.py
        result = analyze_delays(df)
        
        html_table = build_html_table(result)
        result["html_table"] = html_table


# write the table HTML into file to test
        with open("testAnalyzedTable.html", "w", encoding="utf-8") as f:
            f.write(result["html_table"])

        print(f"Resut Returned from first delay analyzation API : {result}")
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@app.post("/analyze-delays-by-lsp", response_model=LSPDelayAnalysisResponse, response_model_exclude_none=False)
async def analyze_delay_by_lsp_file(file: UploadFile = File(...)):
    """
    Upload an Excel file to analyze shipment delays grouped by LSP company.
    
    Expected columns:
    - LSPName (logistics service provider company name)
    - Delay by [unit] (any column containing "delay by")
    
    Returns:
    - JSON structure with delay analysis categorized by LSP company and delay duration
    """
    try:
        # Read the uploaded file
        contents = await file.read()
        
        # Determine file type and read accordingly
        if file.filename.endswith('.xlsx') or file.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(contents))
        elif file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload .xlsx, .xls, or .csv file"
            )
        
        # Analyze delays by LSP using the logic from delay_analyzer.py
        result = analyze_delays_by_lsp(df)
        
        html_table = build_lsp_html_table(result)
        result["html_table"] = html_table

# write the table HTML into file to test
        with open("testLSPTable.html", "w", encoding="utf-8") as f:
            f.write(result["html_table"])

        print(f"Resut Returned from LSP delay analyzation API : {result}")
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")



@app.post("/analyze-delays-by-lsp-base64", response_model=LSPDelayAnalysisResponse, response_model_exclude_none=False)
async def analyze_delay_by_lsp_file_base64(data: FileUploadBase64):
    """
    Upload an Excel file (as base64) to analyze shipment delays grouped by LSP company.
    For Power Automate integration.
    
    Expected columns:
    - LSPName (logistics service provider company name)
    - Delay by [unit] (any column containing "delay by")
    
    Returns:
    - JSON structure with delay analysis categorized by LSP company and delay duration
    """
    try:
        # Decode base64 to bytes
        try:
            file_content = base64.b64decode(data.file)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 encoding: {str(e)}"
            )
        
        # Determine file type and read accordingly
        if data.filename.endswith('.xlsx') or data.filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(file_content))
        elif data.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload .xlsx, .xls, or .csv file"
            )
        
        # Analyze delays by LSP using the logic from delay_analyzer.py
        result = analyze_delays_by_lsp(df)
        
        html_table = build_lsp_html_table(result)
        result["html_table"] = html_table

        # write the table HTML into file to test
        with open("testLSPTable.html", "w", encoding="utf-8") as f:
            f.write(result["html_table"])

        print(f"Result Returned from LSP delay analyzation API (base64): {result}")
        return result
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")





if __name__ == "__main__":
    import uvicorn
    
    # Create necessary directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path("temp_uploads").mkdir(exist_ok=True)
    
    # Run the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
