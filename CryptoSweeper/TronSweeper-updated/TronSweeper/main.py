#!/usr/bin/env python3
"""
TRON Sweeper Bot
A bot that automatically monitors a TRON wallet and transfers received TRX and tokens to a destination wallet
"""
import os
import signal
import sys
import time
import json
import traceback
from src.logger import setup_logger, get_logger
from src.config import Config
from src.sweeper import TronSweeper

# Import Flask app and models
from app import app, db
import models

# Setup signal handlers
def signal_handler(sig, frame):
    """Handle termination signals gracefully"""
    logger = get_logger()
    logger.info("Received termination signal, shutting down...")
    update_bot_status("stopped", False)
    sys.exit(0)

def update_bot_status(status, running=None):
    """
    Update the bot status in the database
    
    Args:
        status: Status message
        running: Whether the bot is currently running
    """
    try:
        with app.app_context():
            # Get the first config record
            config = db.session.query(models.BotConfig).first()
            if config:
                if status:
                    config.status = status
                if running is not None:
                    config.is_running = running
                db.session.commit()
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to update bot status: {str(e)}")

def log_transaction(tx_result, config):
    """
    Log a successful transaction to the database
    
    Args:
        tx_result: Transaction result from the blockchain
        config: Bot configuration
    """
    try:
        if not tx_result:
            return
        
        with app.app_context():
            # Create transaction log
            tx_log = models.TransactionLog(
                txid=tx_result['txid'],
                source_address=config.source_address,
                destination_address=config.destination_address,
                amount=tx_result.get('amount', 0),
                token_address=tx_result.get('token_address'),
                token_symbol=tx_result.get('token_symbol', 'TRX'),
                blockchain=config.blockchain
            )
            db.session.add(tx_log)
            db.session.commit()
    except Exception as e:
        logger = get_logger()
        logger.error(f"Failed to log transaction: {str(e)}")
        logger.error(traceback.format_exc())

def main():
    """Main entry point for the TRON Sweeper Bot"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Setup logger
    logger = setup_logger()
    logger.info("Starting TRON Sweeper Bot")
    
    # Update status to starting
    update_bot_status("starting", True)
    
    try:
        # Use Flask app context for database operations
        with app.app_context():
            # Get configuration from database
            config = Config()
            
            # Log configuration
            logger.info(f"Loaded configuration from database")
            logger.info(f"Monitoring source wallet: {config.source_address}")
            logger.info(f"Destination wallet: {config.destination_address}")
            logger.info(f"Network: {config.tron_network}")
            logger.info(f"Blockchain: {config.blockchain}")
            logger.info(f"Check interval: {config.check_interval} seconds")
            logger.info(f"Minimum transfer amount: {config.min_transfer_amount} TRX")
            
            if config.sweep_trx:
                logger.info("TRX sweeping: ENABLED")
            else:
                logger.info("TRX sweeping: DISABLED")
                
            if config.sweep_trc20:
                token_contracts = json.loads(config.token_contracts or '[]')
                logger.info(f"TRC20 sweeping: ENABLED ({len(token_contracts)} tokens)")
            else:
                logger.info("TRC20 sweeping: DISABLED")
            
            # Initialize sweeper
            sweeper = TronSweeper(config)
            
            # Update status to running
            update_bot_status("running", True)
            
            # Main loop
            while True:
                try:
                    # Check and sweep funds
                    tx_results = sweeper.check_and_sweep()
                    
                    # Log transactions
                    if tx_results:
                        if isinstance(tx_results, list):
                            for tx_result in tx_results:
                                log_transaction(tx_result, config)
                        else:
                            log_transaction(tx_results, config)
                    
                    # Sleep before next check
                    time.sleep(config.check_interval)
                    
                    # Refresh configuration periodically
                    config = Config()
                    
                except Exception as e:
                    logger.error(f"Error during sweep operation: {str(e)}")
                    logger.error(traceback.format_exc())
                    update_bot_status(f"error: {str(e)}", True)
                    time.sleep(config.check_interval)
    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}")
        logger.error(traceback.format_exc())
        update_bot_status(f"failed: {str(e)}", False)
        sys.exit(1)

if __name__ == "__main__":
    main()