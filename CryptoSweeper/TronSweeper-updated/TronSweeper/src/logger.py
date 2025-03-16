"""
Logging module for TRON Sweeper Bot.
Provides standardized logging functionality.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

def setup_logger(log_level: str = None) -> logging.Logger:
    """
    Set up and configure the logger.
    
    Args:
        log_level: Optional log level override from environment
        
    Returns:
        Configured logger instance
    """
    # Get log level from environment or use default
    if log_level is None:
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        print(f"Invalid log level: {log_level}, defaulting to INFO")
        numeric_level = logging.INFO
    
    # Create logger
    logger = logging.getLogger('tron_sweeper')
    logger.setLevel(numeric_level)
    
    # Clear existing handlers if any
    if logger.handlers:
        logger.handlers.clear()
    
    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Create file handler if LOG_FILE is set
    log_file = os.getenv('LOG_FILE')
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to set up file logging: {str(e)}")
    
    return logger

def get_logger() -> logging.Logger:
    """
    Get the configured logger or create one if not exists.
    
    Returns:
        Logger instance
    """
    logger = logging.getLogger('tron_sweeper')
    if not logger.handlers:
        return setup_logger()
    return logger
