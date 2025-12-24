# SafeExpress-Logistic-Management


# LR Number Tracking System

FastAPI application for tracking SafeExpress logistics shipments and analyzing delivery delays.

## Installation

```bash
pip install -r requirements.txt
```

## Running the Application

```bash
python main.py
```

The server will start at `http://localhost:8000`

## 📖 Interactive API Documentation

Once the server is running, access the interactive API testing page:

**Swagger UI:** `http://localhost:8000/docs`

This page allows you to:
- View all available endpoints
- Test APIs directly from your browser
- See request/response schemas
- Try out different parameters

## API Endpoints

### 1. **GET /** - Root Endpoint
Returns API information and available endpoints.

**URL:** `http://localhost:8000/`

---

### 2. **GET /api/generate-token** - Generate SafeExpress Token
Generates authentication token for SafeExpress API.

**URL:** `http://localhost:8000/api/generate-token`

**Response:**
```json
{
  "msg": "",
  "error": "",
  "status": "success",
  "result": "token_string_here"
}
```

---

### 3. **POST /process** - Track LR Numbers
Upload an Excel file to track LR numbers and update their delivery status.

**URL:** `http://localhost:8000/process`

**Request:** Upload Excel file with columns:
- `LrNumber` - LR tracking number
- `Delivery Format` - Delivery format status
- `Current Status` - Current shipment status

**Response:**
```json
{
  "total_records": 100,
  "na_count": 50,
  "valid_lr_numbers": ["123456789012", "..."],
  "statuses_updated": 50,
  "output_file": "path/to/updated_file.xlsx"
}
```

**What it does:**
- Finds rows with `NA` in "Delivery Format" column
- Fetches tracking status for each LR number
- Updates "Current Status" and "Delivery Format" columns
- Returns updated Excel file

---

### 4. **POST /analyze-delays** - Analyze Delays by Status
Analyzes shipment delays grouped by current status.

**URL:** `http://localhost:8000/analyze-delays`

**Request:** Upload Excel file with columns:
- `Current Status` or `Status`
- `Delay by` - Number of days delayed

**Response:**
```json
{
  "headers": ["Current Status", "Delay by 1 Day", "Delay by 2 Days", ...],
  "data": [
    {
      "status": "In transit",
      "delay_by_1_day": 10,
      "delay_by_2_days": 5,
      "grand_total": 25
    }
  ],
  "totals": {...},
  "html_table": "<table>...</table>"
}
```

---

### 5. **POST /analyze-delays-by-lsp** - Analyze Delays by LSP Company
Analyzes shipment delays grouped by logistics service provider.

**URL:** `http://localhost:8000/analyze-delays-by-lsp`

**Request:** Upload Excel file with columns:
- `LSPName` - Logistics service provider name
- `Delay by` - Number of days delayed

**Response:**
```json
{
  "headers": ["LSP Name", "Delay by 1 Day", "Delay by 2 Days", ...],
  "data": [
    {
      "lsp_name": "Safexpress Private Limited",
      "delay_by_1_day": 15,
      "delay_by_2_days": 8,
      "grand_total": 45
    }
  ],
  "totals": {...},
  "html_table": "<table>...</table>"
}
```

---

## API Documentation

Interactive API documentation is available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

## Configuration

Edit `config.py` to customize:
- Output directory path
- API timeout settings
- Batch processing parameters
- LR number validation rules
