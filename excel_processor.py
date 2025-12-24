"""
Simple Excel processor to find NA values in Delivery Format column
"""
import pandas as pd
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class ExcelProcessor:
    """Process Excel files to find LR numbers with NA delivery format"""
    
    def __init__(self, file_path: str):
        """
        Initialize processor
        
        Args:
            file_path: Path to Excel file
        """
        self.file_path = file_path
        self.df: Optional[pd.DataFrame] = None
        
    async def load_excel(self) -> bool:
        """
        Load Excel file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Loading Excel file: {self.file_path}")
            self.df = pd.read_excel(self.file_path)
            logger.info(f"Loaded {len(self.df)} rows")
            logger.info(f"Columns: {list(self.df.columns)}")
            return True
        except Exception as e:
            logger.error(f"Error loading Excel file: {e}")
            return False
    
    async def get_na_lr_numbers(self) -> List[str]:
        """
        Get LR numbers where Delivery Format is NA
        
        Returns:
            List of LR numbers
        """
        if self.df is None:
            logger.error("Excel file not loaded")
            return []
        
        # Check if required columns exist
        if 'Delivery Format' not in self.df.columns:
            logger.error("'Delivery Format' column not found")
            return []
        
        if 'LrNumber' not in self.df.columns:
            logger.error("'LrNumber' column not found")
            return []
        
        # Filter rows where Delivery Format is NA
        na_rows = self.df[self.df['Delivery Format'] == 'NA']
        
        # Get LR numbers
        lr_numbers = na_rows['LrNumber'].tolist()
        
        logger.info(f"Found {len(lr_numbers)} LR numbers with NA Delivery Format")
        return lr_numbers
    
    async def get_first_na_lr_number(self) -> Optional[str]:
        """
        Get the first LR number where Delivery Format is NA
        
        Returns:
            LR number or None if not found
        """
        lr_numbers = await self.get_na_lr_numbers()
        
        if lr_numbers:
            return lr_numbers[0]
        return None
