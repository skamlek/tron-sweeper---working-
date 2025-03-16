"""
TRON client module for blockchain interactions.
Handles all TRON-related operations including account queries and transactions.
Supports native TRX and TRC20 token transfers.
"""

import time
import random
from typing import Dict, Any, List, Optional, Union, Tuple

from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider
from tronpy.contract import Contract

from src.config import Config
from src.logger import get_logger

class TronClient:
    """
    TronClient class for interacting with the TRON blockchain
    """
    
    # TRX precision (1 TRX = 1,000,000 SUN)
    TRX_PRECISION = 1_000_000
    
    # Network configurations
    NETWORKS = {
        'mainnet': 'https://api.trongrid.io',
        'shasta': 'https://api.shasta.trongrid.io',
        'nile': 'https://nile.trongrid.io'
    }
    
    # TRC20 standard methods
    TRC20_ABI = [
        {
            'constant': True,
            'inputs': [{'name': 'owner', 'type': 'address'}],
            'name': 'balanceOf',
            'outputs': [{'name': 'balance', 'type': 'uint256'}],
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'decimals',
            'outputs': [{'name': '', 'type': 'uint8'}],
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'symbol',
            'outputs': [{'name': '', 'type': 'string'}],
            'type': 'function'
        },
        {
            'constant': True,
            'inputs': [],
            'name': 'name',
            'outputs': [{'name': '', 'type': 'string'}],
            'type': 'function'
        },
        {
            'constant': False,
            'inputs': [
                {'name': 'to', 'type': 'address'},
                {'name': 'value', 'type': 'uint256'}
            ],
            'name': 'transfer',
            'outputs': [{'name': '', 'type': 'bool'}],
            'type': 'function'
        }
    ]
    
    def __init__(self, config: Config):
        """
        Initialize the TRON client
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.logger = get_logger()
        
        # Set up API providers with API keys if available
        if config.tron_api_keys:
            self.api_keys = config.tron_api_keys
            self.logger.info(f"Using {len(self.api_keys)} API key(s) for TRON API")
            
            # Create HTTP provider with API key
            headers = {"TRON-PRO-API-KEY": self._get_random_api_key()}
            self.provider = HTTPProvider(endpoint_uri=config.tron_node_url, headers=headers)
        else:
            self.api_keys = []
            self.logger.warning("No API keys provided. Rate limits may apply.")
            self.provider = HTTPProvider(endpoint_uri=config.tron_node_url)
        
        # Create TRON client
        self.client = Tron(provider=self.provider)
        
        # Load private key
        self.private_key = PrivateKey(bytes.fromhex(config.source_private_key))
        
        # Check if source address matches private key
        derived_address = self.private_key.public_key.to_base58check_address()
        if derived_address != config.source_address:
            self.logger.warning(
                f"Provided source address ({config.source_address}) doesn't match "
                f"the address derived from private key ({derived_address})"
            )
    
    def _get_random_api_key(self) -> str:
        """
        Get a random API key from the available keys
        
        Returns:
            A random API key
        """
        if not self.api_keys:
            return ""
        return random.choice(self.api_keys)
    
    def _refresh_api_key(self) -> None:
        """Refresh the API key used in the provider's headers"""
        if self.api_keys:
            self.provider.headers["TRON-PRO-API-KEY"] = self._get_random_api_key()
    
    def _convert_sun_to_trx(self, sun_amount: int) -> float:
        """
        Convert SUN to TRX
        
        Args:
            sun_amount: Amount in SUN
            
        Returns:
            Amount in TRX
        """
        return sun_amount / self.TRX_PRECISION
    
    def _convert_trx_to_sun(self, trx_amount: float) -> int:
        """
        Convert TRX to SUN
        
        Args:
            trx_amount: Amount in TRX
            
        Returns:
            Amount in SUN
        """
        return int(trx_amount * self.TRX_PRECISION)
    
    def _convert_token_to_human_readable(self, token_amount: int, decimals: int) -> float:
        """
        Convert token amount from raw units to human-readable format
        
        Args:
            token_amount: Amount in raw token units
            decimals: Token decimals
            
        Returns:
            Amount in human-readable format
        """
        return token_amount / (10 ** decimals)
    
    def _convert_human_readable_to_token(self, human_amount: float, decimals: int) -> int:
        """
        Convert token amount from human-readable format to raw units
        
        Args:
            human_amount: Amount in human-readable format
            decimals: Token decimals
            
        Returns:
            Amount in raw token units
        """
        return int(human_amount * (10 ** decimals))
    
    def get_account_balance(self, address: str) -> float:
        """
        Get the TRX balance of an account
        
        Args:
            address: TRON account address
            
        Returns:
            Balance in TRX
        """
        try:
            account = self.client.get_account(address)
            balance_in_sun = account.get("balance", 0)
            return self._convert_sun_to_trx(balance_in_sun)
        except Exception as e:
            self.logger.error(f"Failed to get account balance: {str(e)}")
            # Try with a different API key if available
            self._refresh_api_key()
            raise
    
    def get_token_info(self, contract_address: str) -> Dict[str, Any]:
        """
        Get token information from a TRC20 contract
        
        Args:
            contract_address: TRC20 token contract address
            
        Returns:
            Dictionary with token information
        """
        try:
            # Get TRC20 contract
            contract = self.client.get_contract(contract_address)
            
            # Get token information
            name = contract.functions.name()
            symbol = contract.functions.symbol()
            decimals = contract.functions.decimals()
            
            return {
                "contract_address": contract_address,
                "name": name,
                "symbol": symbol,
                "decimals": decimals
            }
        except Exception as e:
            self.logger.error(f"Failed to get token info for {contract_address}: {str(e)}")
            # Try with a different API key if available
            self._refresh_api_key()
            raise
    
    def get_token_balance(self, contract_address: str, address: str) -> Tuple[float, int]:
        """
        Get the token balance of an account
        
        Args:
            contract_address: TRC20 token contract address
            address: TRON account address
            
        Returns:
            Tuple of (human-readable balance, decimals)
        """
        try:
            # Get TRC20 contract
            contract = self.client.get_contract(contract_address)
            
            # Get token balance
            balance = contract.functions.balanceOf(address)
            decimals = contract.functions.decimals()
            
            # Convert to human-readable format
            human_balance = self._convert_token_to_human_readable(balance, decimals)
            
            return human_balance, decimals
        except Exception as e:
            self.logger.error(f"Failed to get token balance for {contract_address}: {str(e)}")
            # Try with a different API key if available
            self._refresh_api_key()
            raise
    
    def estimate_energy_cost(self, is_token: bool = False) -> float:
        """
        Estimate the energy cost for a transfer in TRX
        
        Args:
            is_token: Whether this is a token transfer (requires more energy)
            
        Returns:
            Estimated cost in TRX
        """
        # Typical cost for a simple TRX transfer is around 0.3 TRX
        # Token transfers require more energy, typically around 5-10 TRX
        return 10.0 if is_token else 0.5
    
    def transfer_trx(self, to_address: str, amount_trx: float) -> Dict[str, Any]:
        """
        Transfer TRX from source wallet to destination
        
        Args:
            to_address: Destination address
            amount_trx: Amount to transfer in TRX
            
        Returns:
            Transaction details
        """
        try:
            # Convert TRX to SUN
            amount_sun = self._convert_trx_to_sun(amount_trx)
            
            # Create and sign transaction
            txn = (
                self.client.trx.transfer(self.config.source_address, to_address, amount_sun)
                .build()
                .sign(self.private_key)
            )
            
            # Broadcast transaction
            result = txn.broadcast()
            
            # Check if transaction was successful
            if not result.get("result", False):
                error_msg = f"Transaction failed: {result}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            # Format result
            tx_id = result.get("txid", "")
            return {
                "txid": tx_id,
                "amount_trx": amount_trx,
                "from_address": self.config.source_address,
                "to_address": to_address,
                "token_symbol": "TRX",
                "token_address": None,
                "timestamp": int(time.time())
            }
        except Exception as e:
            self.logger.error(f"Transfer failed: {str(e)}")
            # Try with a different API key if available
            self._refresh_api_key()
            raise
    
    def transfer_token(self, to_address: str, amount: float, contract_address: str) -> Dict[str, Any]:
        """
        Transfer TRC20 tokens from source wallet to destination
        
        Args:
            to_address: Destination address
            amount: Amount to transfer in token units
            contract_address: Token contract address
            
        Returns:
            Transaction details
        """
        try:
            # Get token info
            contract = self.client.get_contract(contract_address)
            decimals = contract.functions.decimals()
            symbol = contract.functions.symbol()
            
            # Convert human-readable amount to token units
            token_amount = self._convert_human_readable_to_token(amount, decimals)
            
            # Create and sign transaction
            txn = (
                contract.functions.transfer(to_address, token_amount)
                .with_owner(self.config.source_address)
                .fee_limit(100_000_000)  # 100 TRX limit for gas
                .build()
                .sign(self.private_key)
            )
            
            # Broadcast transaction
            result = txn.broadcast()
            
            # Check if transaction was successful
            if not result.get("result", False):
                error_msg = f"Token transfer failed: {result}"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            # Format result
            tx_id = result.get("txid", "")
            return {
                "txid": tx_id,
                "amount_trx": amount,  # This is actually token amount
                "from_address": self.config.source_address,
                "to_address": to_address,
                "token_symbol": symbol,
                "token_address": contract_address,
                "timestamp": int(time.time())
            }
        except Exception as e:
            self.logger.error(f"Token transfer failed: {str(e)}")
            # Try with a different API key if available
            self._refresh_api_key()
            raise
