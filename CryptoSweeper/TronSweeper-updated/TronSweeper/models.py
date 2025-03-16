from datetime import datetime
import json
from app import db

class BotConfig(db.Model):
    """Configuration for the TRON Sweeper Bot"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Required settings
    source_private_key = db.Column(db.String(256), nullable=False)
    source_address = db.Column(db.String(128), nullable=False)
    destination_address = db.Column(db.String(128), nullable=False)
    
    # Optional settings with defaults
    tron_network = db.Column(db.String(32), default='mainnet')
    tron_api_keys = db.Column(db.Text, default='')
    check_interval = db.Column(db.Integer, default=30)
    min_transfer_amount = db.Column(db.Float, default=0)
    
    # Token settings
    sweep_trx = db.Column(db.Boolean, default=True)
    sweep_trc20 = db.Column(db.Boolean, default=False)
    token_contracts = db.Column(db.Text, default='[]')  # JSON list of token contract addresses
    
    # Multi-chain support (future)
    blockchain = db.Column(db.String(32), default='tron')  # tron, bsc, etc.
    
    # Status tracking
    status = db.Column(db.String(256), default='Configured')
    is_running = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_token_contracts(self):
        """Get token contracts as a list"""
        try:
            return json.loads(self.token_contracts)
        except:
            return []
    
    def set_token_contracts(self, contracts):
        """Set token contracts from a list"""
        self.token_contracts = json.dumps(contracts)

    def __repr__(self):
        return f"<BotConfig {self.id} - {self.source_address[:8]}...>"

class TokenConfig(db.Model):
    """Configuration for token sweeping"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Token details
    contract_address = db.Column(db.String(128), nullable=False)
    symbol = db.Column(db.String(32), nullable=False)
    name = db.Column(db.String(128))
    decimals = db.Column(db.Integer, default=18)
    blockchain = db.Column(db.String(32), default='tron')  # tron, bsc, etc.
    token_type = db.Column(db.String(32), default='trc20')  # trc20, bep20, etc.
    
    # Sweeping settings
    min_transfer_amount = db.Column(db.Float, default=0)
    enabled = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<TokenConfig {self.symbol} ({self.contract_address[:8]}...)>"

class TransactionLog(db.Model):
    """Log of transfers performed by the bot"""
    id = db.Column(db.Integer, primary_key=True)
    
    # Transaction details
    txid = db.Column(db.String(128), nullable=False, unique=True)
    source_address = db.Column(db.String(128), nullable=False)
    destination_address = db.Column(db.String(128), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    
    # Token details
    token_address = db.Column(db.String(128), nullable=True)  # null for native coin (TRX)
    token_symbol = db.Column(db.String(32), default='TRX')
    blockchain = db.Column(db.String(32), default='tron')  # tron, bsc, etc.
    
    # Timestamps
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Transaction {self.txid[:8]}... {self.amount} {self.token_symbol}>"