"""
TRON Sweeper module.
Contains the core logic for monitoring a wallet and sweeping funds.
Supports TRX and TRC20 token transfers.
"""

import time
import json
from typing import Dict, Any, List, Optional, Tuple, Union
from contextlib import nullcontext

from src.config import Config
from src.logger import get_logger
from src.tron_client import TronClient

class TronSweeper:
    """
    TronSweeper class that monitors a wallet for incoming TRX and tokens
    and transfers (sweeps) them to a destination address.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the TronSweeper with configuration
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.logger = get_logger()
        self.tron_client = TronClient(config)
        
        # Initialize balances
        self.last_trx_balance = self._get_current_trx_balance()
        self.token_balances = {}
        
        # Load token contracts
        self.token_contracts = []
        if hasattr(config, 'token_contracts') and config.token_contracts:
            try:
                self.token_contracts = json.loads(config.token_contracts)
                self.logger.info(f"Loaded {len(self.token_contracts)} token contracts for monitoring")
            except Exception as e:
                self.logger.error(f"Failed to parse token contracts: {e}")
        
        # Initialize token balances
        if hasattr(config, 'sweep_trc20') and config.sweep_trc20 and self.token_contracts:
            for token in self.token_contracts:
                try:
                    balance, _ = self.tron_client.get_token_balance(token, self.config.source_address)
                    self.token_balances[token] = balance
                    self.logger.info(f"Initial balance for token {token[:8]}...: {balance}")
                except Exception as e:
                    self.logger.error(f"Failed to get initial balance for token {token}: {e}")
        
        self.logger.info(f"Initialized TronSweeper with current TRX balance: {self.last_trx_balance} TRX")
        
        # Set default values for retries if not present in config
        if not hasattr(config, 'max_retries'):
            config.max_retries = 3
        if not hasattr(config, 'retry_delay'):
            config.retry_delay = 5
    
    def _get_current_trx_balance(self) -> float:
        """
        Get the current TRX balance of the source wallet
        
        Returns:
            Balance in TRX
        """
        return self.tron_client.get_account_balance(self.config.source_address)
    
    def _calculate_sweepable_trx_amount(self, current_balance: float, reserve_for_tokens: bool = False) -> float:
        """
        Calculate the amount of TRX that can be swept after considering fees and minimum transfer
        
        Args:
            current_balance: Current balance in TRX
            reserve_for_tokens: Whether to reserve extra TRX for token transfers
            
        Returns:
            Sweepable amount in TRX
        """
        # Get estimated fee for the transfer
        estimated_fee = self.tron_client.estimate_energy_cost()
        
        # If we need to reserve TRX for token operations, add buffer
        if reserve_for_tokens:
            # Reserve enough for a few token transfers (assuming 10 TRX per token transfer)
            token_reserves = len(self.token_contracts) * 10.0 if self.token_contracts else 0
            estimated_fee += token_reserves
        
        # Calculate sweepable amount
        # Need to keep enough TRX for the fee and respect minimum transfer amount
        sweepable_amount = current_balance - estimated_fee
        
        # Check if amount is above minimum transfer threshold
        if sweepable_amount < self.config.min_transfer_amount:
            return 0
        
        # Ensure we don't sweep to a negative balance
        if sweepable_amount <= 0:
            return 0
        
        return sweepable_amount
    
    def check_and_sweep_trx(self) -> Optional[Dict[str, Any]]:
        """
        Check for new TRX funds and sweep if needed
        
        Returns:
            Transaction result or None if no sweep was performed
        """
        self.logger.debug("Checking for new TRX funds...")
        
        try:
            # Get current balance
            current_balance = self._get_current_trx_balance()
            self.logger.debug(f"Current TRX balance: {current_balance} TRX")
            
            # Check if balance has increased since last check
            last_balance = getattr(self, 'last_trx_balance', 0)
            if current_balance <= last_balance:
                self.logger.debug(f"No new TRX detected. Current: {current_balance}, Last: {last_balance}")
                return None
                
            self.logger.info(f"New TRX detected! Current: {current_balance}, Last: {last_balance}")
            
            # Determine if we need to reserve TRX for token operations
            need_reserve = False
            if hasattr(self.config, 'sweep_trc20') and self.config.sweep_trc20 and self.token_contracts:
                need_reserve = True
            
            # Calculate amount to sweep - optimized for faster response
            sweepable_amount = self._calculate_sweepable_trx_amount(current_balance, need_reserve)
            
            if sweepable_amount > 0:
                self.logger.info(f"Sweeping {sweepable_amount} TRX to {self.config.destination_address}")
                
                # Perform the transfer with retries
                success = False
                errors = []
                result = None
                
                for attempt in range(1, self.config.max_retries + 1):
                    try:
                        tx_result = self.tron_client.transfer_trx(
                            self.config.destination_address,
                            sweepable_amount
                        )
                        
                        self.logger.info(f"TRX sweep successful! Transaction ID: {tx_result['txid']}")
                        success = True
                        result = tx_result
                        break
                    except Exception as e:
                        error_msg = f"Attempt {attempt}/{self.config.max_retries} failed: {str(e)}"
                        self.logger.warning(error_msg)
                        errors.append(error_msg)
                        
                        if attempt < self.config.max_retries:
                            self.logger.info(f"Retrying in {self.config.retry_delay} seconds...")
                            time.sleep(self.config.retry_delay)
                
                if not success:
                    error_details = "\n".join(errors)
                    self.logger.error(f"All TRX sweep attempts failed. Details:\n{error_details}")
                    return None
                
                return result
            else:
                self.logger.debug("No TRX funds to sweep at this time")
                return None
            
        except Exception as e:
            self.logger.error(f"Error while checking or sweeping TRX funds: {str(e)}")
            return None
        finally:
            # Update last known balance
            self.last_trx_balance = self._get_current_trx_balance()
    
    def check_and_sweep_tokens(self) -> List[Dict[str, Any]]:
        """
        Check for tokens and sweep if needed
        
        Returns:
            List of transaction results
        """
        if not (hasattr(self.config, 'sweep_trc20') and self.config.sweep_trc20):
            return []
        
        if not self.token_contracts:
            return []
        
        self.logger.debug(f"Checking {len(self.token_contracts)} tokens for sweeping...")
        
        results = []
        
        # Get token configs from the database if available
        token_configs = {}
        try:
            # Check if we're running in the Flask app context
            import sys
            if 'app' in sys.modules:
                try:
                    # We're likely running in a Flask app
                    from app import db, TokenConfig, app
                    
                    # Use app context if we have access to it
                    with app.app_context():
                        token_configs = {
                            tc.contract_address: tc 
                            for tc in db.session.query(TokenConfig)
                            .filter(TokenConfig.contract_address.in_(self.token_contracts), 
                                    TokenConfig.enabled == True)
                            .all()
                        }
                    self.logger.debug(f"Loaded {len(token_configs)} token configurations from database")
                except ImportError:
                    self.logger.debug("Could not import Flask app components")
            else:
                self.logger.debug("Not running in Flask app context")
        except Exception as e:
            self.logger.warning(f"Couldn't load token configurations from database: {e}")
            token_configs = {}
        
        for contract_address in self.token_contracts:
            try:
                # Skip if token is disabled in config
                if contract_address in token_configs and not token_configs[contract_address].enabled:
                    self.logger.debug(f"Skipping disabled token: {contract_address[:8]}...")
                    continue
                
                # Get token info and balance
                token_info = self.tron_client.get_token_info(contract_address)
                symbol = token_info.get('symbol', 'UNKNOWN')
                
                # Get current balance
                current_balance, decimals = self.tron_client.get_token_balance(contract_address, self.config.source_address)
                
                # Get last known balance
                last_balance = self.token_balances.get(contract_address, 0)
                
                self.logger.debug(f"Token {symbol} ({contract_address[:8]}...) balance: {current_balance}")
                
                # Check if balance has increased since last check - quick response to new tokens
                if current_balance <= last_balance:
                    self.logger.debug(f"No new {symbol} tokens detected. Current: {current_balance}, Last: {last_balance}")
                    continue
                
                self.logger.info(f"New {symbol} tokens detected! Current: {current_balance}, Last: {last_balance}")
                
                # Get token-specific minimum transfer amount if available
                min_transfer = 0
                if contract_address in token_configs and token_configs[contract_address].min_transfer_amount is not None:
                    min_transfer = token_configs[contract_address].min_transfer_amount
                    self.logger.debug(f"Using token-specific minimum transfer amount for {symbol}: {min_transfer}")
                
                if current_balance > min_transfer:
                    self.logger.info(f"Sweeping {current_balance} {symbol} to {self.config.destination_address}")
                    
                    # Perform the transfer with retries
                    success = False
                    errors = []
                    
                    for attempt in range(1, self.config.max_retries + 1):
                        try:
                            tx_result = self.tron_client.transfer_token(
                                self.config.destination_address,
                                current_balance,
                                contract_address
                            )
                            
                            self.logger.info(f"Token sweep successful! Transaction ID: {tx_result['txid']}")
                            results.append(tx_result)
                            success = True
                            break
                        except Exception as e:
                            error_msg = f"Attempt {attempt}/{self.config.max_retries} failed: {str(e)}"
                            self.logger.warning(error_msg)
                            errors.append(error_msg)
                            
                            if attempt < self.config.max_retries:
                                self.logger.info(f"Retrying in {self.config.retry_delay} seconds...")
                                time.sleep(self.config.retry_delay)
                    
                    if not success:
                        error_details = "\n".join(errors)
                        self.logger.error(f"All token sweep attempts failed. Details:\n{error_details}")
                
                # Update last known balance
                self.token_balances[contract_address] = current_balance
                
            except Exception as e:
                self.logger.error(f"Error processing token {contract_address}: {str(e)}")
        
        return results
    
    def check_and_sweep(self) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        Check for new funds and sweep if needed
        
        Returns:
            Transaction result(s) or None if no sweep was performed
        """
        self.logger.debug("Starting sweep check cycle...")
        
        results = []
        
        # First check and sweep TRX if enabled
        if not hasattr(self.config, 'sweep_trx') or self.config.sweep_trx:
            trx_result = self.check_and_sweep_trx()
            if trx_result:
                results.append(trx_result)
        
        # Then check and sweep tokens if enabled
        if hasattr(self.config, 'sweep_trc20') and self.config.sweep_trc20:
            token_results = self.check_and_sweep_tokens()
            results.extend(token_results)
        
        # Return results
        if not results:
            return None
        elif len(results) == 1:
            return results[0]
        else:
            return results
