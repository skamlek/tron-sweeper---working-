"""
Configuration module for TRON Sweeper Bot.
Loads configuration from database instead of environment variables.
"""

import json
import os
from typing import List, Optional, Dict, Any, Union
import importlib.util

class Config:
    """Configuration class for the TRON Sweeper Bot"""
    
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        """
        Initialize configuration from database record or dictionary
        
        Args:
            config_dict: Dictionary containing configuration values (optional)
        """
        if config_dict is None:
            # Try to load from database
            config_dict = self._load_from_database()
        
        if not config_dict:
            raise ValueError("No configuration found in database")
        
        # Required settings
        self.source_private_key = self._get_required_value(config_dict, 'source_private_key')
        self.source_address = self._get_required_value(config_dict, 'source_address')
        self.destination_address = self._get_required_value(config_dict, 'destination_address')
        
        # Optional settings with defaults
        self.tron_network = config_dict.get('tron_network', 'mainnet')
        if self.tron_network not in ['mainnet', 'shasta', 'nile']:
            raise ValueError(f"Invalid TRON network: {self.tron_network}. Must be one of: mainnet, shasta, nile")
        
        # API configuration
        self.tron_node_url = None  # Will be determined based on network
        self.tron_api_keys = self._parse_api_keys(config_dict.get('tron_api_keys', ''))
        
        # Blockchain type - for future multi-chain support
        self.blockchain = config_dict.get('blockchain', 'tron')
        
        # Token sweep configuration
        self.sweep_trx = config_dict.get('sweep_trx', True)
        self.sweep_trc20 = config_dict.get('sweep_trc20', False)
        self.token_contracts = config_dict.get('token_contracts', '[]')
        
        # Operation settings
        try:
            self.check_interval = int(config_dict.get('check_interval', 30))
            if self.check_interval < 1:
                raise ValueError("check_interval must be at least 1 second")
        except ValueError:
            raise ValueError("check_interval must be a valid integer")
        
        try:
            self.min_transfer_amount = float(config_dict.get('min_transfer_amount', 0))
            if self.min_transfer_amount < 0:
                raise ValueError("min_transfer_amount cannot be negative")
        except ValueError:
            raise ValueError("min_transfer_amount must be a valid number")
        
        # Retry settings
        try:
            self.max_retries = int(config_dict.get('max_retries', 3))
            if self.max_retries < 0:
                raise ValueError("max_retries cannot be negative")
        except ValueError:
            raise ValueError("max_retries must be a valid integer")
        
        try:
            self.retry_delay = int(config_dict.get('retry_delay', 5))
            if self.retry_delay < 1:
                raise ValueError("retry_delay must be at least 1 second")
        except ValueError:
            raise ValueError("retry_delay must be a valid integer")
    
    def _load_from_database(self) -> Dict[str, Any]:
        """
        Load configuration from database
        
        Returns:
            Dictionary of configuration values
        """
        try:
            # Dynamically import models to avoid circular imports
            if importlib.util.find_spec("models") is not None:
                from models import BotConfig
                from app import db
                
                # Get the first configuration record
                config = db.session.query(BotConfig).first()
                
                if config:
                    # Convert SQLAlchemy model to dictionary
                    config_dict = {column.name: getattr(config, column.name) 
                                for column in config.__table__.columns}
                    return config_dict
            
            return {}
        except Exception as e:
            raise ValueError(f"Failed to load configuration from database: {str(e)}")
    
    def _get_required_value(self, config_dict: Dict[str, Any], key: str) -> str:
        """Get a required configuration value or raise an exception"""
        value = config_dict.get(key)
        if not value:
            raise ValueError(f"Required configuration value '{key}' is not set")
        return value
    
    def _parse_api_keys(self, api_keys_str: str) -> List[str]:
        """Parse comma-separated API keys into a list"""
        if not api_keys_str:
            return []
        return [key.strip() for key in api_keys_str.split(',') if key.strip()]
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary
        
        Returns:
            Dictionary of configuration values
        """
        # Filter out None values and sensitive fields
        config_dict = {k: v for k, v in self.__dict__.items() 
                      if not k.startswith('_') and v is not None and k != 'source_private_key'}
        return config_dict
