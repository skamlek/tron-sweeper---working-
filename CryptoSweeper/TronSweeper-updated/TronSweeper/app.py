import os
import threading
import time
import logging
import json
import zipfile
import io
import traceback
from datetime import datetime

from flask import Flask, render_template, jsonify, request, flash, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize declarative base for SQLAlchemy
class Base(DeclarativeBase):
    pass

# Initialize SQLAlchemy
db = SQLAlchemy(model_class=Base)

# Initialize Flask app
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize database with app
db.init_app(app)

# Import models after initializing db
from models import BotConfig, TransactionLog, TokenConfig

# Create tables (make sure DB schema is updated)
with app.app_context():
    db.create_all()

# Global variables for bot status
bot_thread = None
bot_running = False
bot_status = "Stopped"
bot_last_check = None

# Helper functions
def get_bot_status():
    global bot_running, bot_status, bot_last_check
    return {
        "running": bot_running,
        "status": bot_status,
        "last_check": bot_last_check
    }

def update_bot_status(status, running=None):
    global bot_status, bot_running, bot_last_check
    bot_status = status
    if running is not None:
        bot_running = running
    bot_last_check = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def start_bot():
    global bot_thread, bot_running
    if bot_running:
        return False
    
    # Get the latest config
    config = BotConfig.query.order_by(BotConfig.id.desc()).first()
    if not config:
        update_bot_status("No configuration found", False)
        return False
    
    # Update the running status in the database
    config.is_running = True
    config.status = "Starting..."
    config.updated_at = datetime.now()
    db.session.commit()
    
    # Start the bot in a separate thread
    update_bot_status("Starting...", True)
    bot_thread = threading.Thread(target=run_bot_thread)
    bot_thread.daemon = True
    bot_thread.start()
    
    return True

def stop_bot():
    global bot_running
    if not bot_running:
        return False
    
    update_bot_status("Stopping...", False)
    return True

def run_bot_thread():
    import json
    import sys
    import traceback
    from src.logger import setup_logger
    
    logger = setup_logger()
    logger.info("Starting TRON Sweeper Bot from web interface")
    
    update_bot_status("Running", True)
    
    try:
        # Import the bot-related modules here to avoid circular imports
        from src.config import Config
        from src.sweeper import TronSweeper
        
        # Load configuration
        try:
            with app.app_context():
                config = Config()
                
                # Update config in database
                db_config = BotConfig.query.order_by(BotConfig.id.desc()).first()
                if db_config:
                    db_config.status = "Running"
                    db_config.is_running = True
                    db_config.updated_at = datetime.now()
                    db.session.commit()
                
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
                
                update_bot_status(f"Monitoring {config.source_address[:8]}...{config.source_address[-8:]}", True)
                
                # Initialize sweeper
                sweeper = TronSweeper(config)
                
                # Main loop
                while bot_running:
                    try:
                        # Check and sweep
                        results = sweeper.check_and_sweep()
                        
                        # Log transaction(s) if successful
                        if results:
                            with app.app_context():
                                # Handle single transaction result
                                if isinstance(results, dict) and results.get('txid'):
                                    log = TransactionLog(
                                        txid=results['txid'],
                                        source_address=results.get('from_address', config.source_address),
                                        destination_address=results.get('to_address', config.destination_address),
                                        amount=results.get('amount_trx', 0),
                                        token_address=results.get('token_address'),
                                        token_symbol=results.get('token_symbol', 'TRX'),
                                        blockchain=config.blockchain,
                                        timestamp=datetime.fromtimestamp(results.get('timestamp', time.time()))
                                    )
                                    db.session.add(log)
                                
                                # Handle multiple transaction results
                                elif isinstance(results, list):
                                    for result in results:
                                        if result and isinstance(result, dict) and result.get('txid'):
                                            log = TransactionLog(
                                                txid=result['txid'],
                                                source_address=result.get('from_address', config.source_address),
                                                destination_address=result.get('to_address', config.destination_address),
                                                amount=result.get('amount_trx', 0),
                                                token_address=result.get('token_address'),
                                                token_symbol=result.get('token_symbol', 'TRX'),
                                                blockchain=config.blockchain,
                                                timestamp=datetime.fromtimestamp(result.get('timestamp', time.time()))
                                            )
                                            db.session.add(log)
                                
                                # Commit all transaction logs
                                db.session.commit()
                                
                                # Update bot status with last transaction info
                                if isinstance(results, dict):
                                    token_symbol = results.get('token_symbol', 'TRX')
                                    amount = results.get('amount_trx', 0)
                                    update_bot_status(f"Swept {amount} {token_symbol}", True)
                                elif isinstance(results, list) and results:
                                    token_symbol = results[-1].get('token_symbol', 'TRX')
                                    amount = results[-1].get('amount_trx', 0)
                                    update_bot_status(f"Swept {amount} {token_symbol} and {len(results)-1} other asset(s)", True)
                        
                        # Sleep before next check (optimized for ultra-fast response)
                        # Use a short sleep interval to check bot_running status more frequently
                        sleep_interval = min(1, config.check_interval)  # 1 second or less
                        remaining_time = config.check_interval
                        
                        while remaining_time > 0 and bot_running:
                            sleep_time = min(sleep_interval, remaining_time)
                            time.sleep(sleep_time)
                            remaining_time -= sleep_time
                        
                        # Refresh configuration periodically
                        with app.app_context():
                            config = Config()
                            
                    except Exception as e:
                        logger.error(f"Error during sweep operation: {str(e)}")
                        logger.error(traceback.format_exc())
                        update_bot_status(f"Error: {str(e)[:50]}...", True)
                        
                        # Update status in database
                        with app.app_context():
                            db_config = BotConfig.query.order_by(BotConfig.id.desc()).first()
                            if db_config:
                                db_config.status = f"Error: {str(e)[:100]}"
                                db_config.updated_at = datetime.now()
                                db.session.commit()
                        
                        time.sleep(config.check_interval)
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            logger.error(traceback.format_exc())
            update_bot_status(f"Configuration error: {str(e)[:50]}...", False)
            
            # Update status in database
            with app.app_context():
                db_config = BotConfig.query.order_by(BotConfig.id.desc()).first()
                if db_config:
                    db_config.status = f"Configuration error: {str(e)[:100]}"
                    db_config.is_running = False
                    db_config.updated_at = datetime.now()
                    db.session.commit()
            
            return
    
    except Exception as e:
        logger.error(f"Critical error in bot thread: {str(e)}")
        logger.error(traceback.format_exc())
        update_bot_status(f"Critical error: {str(e)[:50]}...", False)
        
        # Update status in database
        with app.app_context():
            db_config = BotConfig.query.order_by(BotConfig.id.desc()).first()
            if db_config:
                db_config.status = f"Critical error: {str(e)[:100]}"
                db_config.is_running = False
                db_config.updated_at = datetime.now() 
                db.session.commit()
    
    finally:
        update_bot_status("Stopped", False)
        logger.info("TRON Sweeper Bot stopped")
        
        # Update status in database
        with app.app_context():
            db_config = BotConfig.query.order_by(BotConfig.id.desc()).first()
            if db_config:
                db_config.status = "Stopped"
                db_config.is_running = False
                db_config.updated_at = datetime.now()
                db.session.commit()

# Routes
@app.route('/')
def index():
    config = BotConfig.query.order_by(BotConfig.id.desc()).first()
    status = get_bot_status()
    return render_template('index.html', config=config, status=status)

@app.route('/transactions')
def transactions():
    tx_logs = TransactionLog.query.order_by(TransactionLog.timestamp.desc()).limit(100).all()
    return render_template('transactions.html', transactions=tx_logs)

@app.route('/api/status')
def api_status():
    return jsonify(get_bot_status())

@app.route('/api/start', methods=['POST'])
def api_start():
    if start_bot():
        return jsonify({"success": True, "message": "Bot started successfully"})
    else:
        return jsonify({"success": False, "message": "Bot is already running or no configuration found"})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    if stop_bot():
        return jsonify({"success": True, "message": "Bot stopped successfully"})
    else:
        return jsonify({"success": False, "message": "Bot is not running"})

@app.route('/api/token/update', methods=['POST'])
def api_token_update():
    """API endpoint to update token configuration"""
    if not request.is_json:
        return jsonify({"success": False, "message": "Request must be JSON"}), 400
    
    data = request.get_json()
    token_id = data.get('token_id')
    field = data.get('field')
    value = data.get('value')
    
    if not all([token_id, field]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    # Find the token configuration
    token = TokenConfig.query.get(token_id)
    if not token:
        return jsonify({"success": False, "message": "Token not found"}), 404
    
    # Update the field
    if field == 'enabled':
        token.enabled = bool(value)
    elif field == 'min_transfer_amount':
        try:
            token.min_transfer_amount = float(value)
        except ValueError:
            return jsonify({"success": False, "message": "Invalid amount value"}), 400
    else:
        return jsonify({"success": False, "message": "Invalid field name"}), 400
    
    # Save changes
    db.session.commit()
    
    return jsonify({
        "success": True, 
        "message": f"Token {token.symbol} updated successfully",
        "token": {
            "id": token.id,
            "symbol": token.symbol,
            "enabled": token.enabled,
            "min_transfer_amount": token.min_transfer_amount
        }
    })

@app.route('/download')
def download_project():
    """Generate a zip file with the entire project for local setup"""
    memory_file = io.BytesIO()
    
    # Define essential project files and directories to include
    essential_dirs = [
        'src',
        'templates',
        'static'
    ]
    
    essential_files = [
        'app.py',
        'main.py',
        'models.py',
        'requirements.txt',
        'README.md'
    ]
    
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add essential directories
        for directory in essential_dirs:
            if os.path.exists(directory):
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        # Skip unnecessary files
                        if file.endswith('.pyc') or '__pycache__' in root:
                            continue
                            
                        file_path = os.path.join(root, file)
                        try:
                            # Add with relative path
                            zf.write(file_path, file_path)
                            logger.info(f"Added {file_path} to zip")
                        except Exception as e:
                            logger.error(f"Error adding {file_path} to zip: {str(e)}")
        
        # Add essential files at root level
        for file in essential_files:
            if os.path.exists(file):
                try:
                    zf.write(file, file)
                    logger.info(f"Added {file} to zip")
                except Exception as e:
                    logger.error(f"Error adding {file} to zip: {str(e)}")
        
        # Create a README.txt file with setup instructions if README.md doesn't exist
        if not os.path.exists('README.md'):
            setup_instructions = """# TRON Sweeper Bot

## Setup Instructions

1. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set up your database:
   - Create a PostgreSQL database
   - Set the DATABASE_URL environment variable

3. Run the application:
   ```
   python main.py
   ```

4. Access the web interface at http://localhost:5000
"""
            zf.writestr('README.md', setup_instructions)
            logger.info("Added generated README.md to zip")
            
        # Create a requirements.txt file if it doesn't exist
        if not os.path.exists('requirements.txt'):
            requirements = """flask
flask-sqlalchemy
psycopg2-binary
tronpy
gunicorn
email-validator
"""
            zf.writestr('requirements.txt', requirements)
            logger.info("Added generated requirements.txt to zip")
    
    # Reset the file pointer to the beginning of the file
    memory_file.seek(0)
    
    # Return the zip file
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='tron_sweeper_bot.zip'
    )

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        # Validate form data
        source_private_key = request.form.get('source_private_key', '').strip()
        source_address = request.form.get('source_address', '').strip()
        destination_address = request.form.get('destination_address', '').strip()
        
        if not (source_private_key and source_address and destination_address):
            flash('All required fields must be filled', 'danger')
            return redirect(url_for('config'))
        
        # Get optional token-related settings with defaults
        sweep_trx = request.form.get('sweep_trx') == 'on'  # checkbox
        sweep_trc20 = request.form.get('sweep_trc20') == 'on'  # checkbox
        
        # Handle token contract addresses
        token_contracts = []
        if sweep_trc20:
            # Get token contracts from form (comma-separated)
            token_contracts_str = request.form.get('token_contracts', '').strip()
            if token_contracts_str:
                # Convert comma-separated list to JSON array
                token_contracts = [addr.strip() for addr in token_contracts_str.split(',') if addr.strip()]
        
        # Create new config
        config = BotConfig(
            source_private_key=source_private_key,
            source_address=source_address,
            destination_address=destination_address,
            tron_network=request.form.get('tron_network', 'mainnet'),
            tron_api_keys=request.form.get('tron_api_keys', ''),
            check_interval=int(request.form.get('check_interval', 30)),
            min_transfer_amount=float(request.form.get('min_transfer_amount', 0)),
            blockchain=request.form.get('blockchain', 'tron'),
            sweep_trx=sweep_trx,
            sweep_trc20=sweep_trc20,
            token_contracts=json.dumps(token_contracts),
            status="Configured",
            is_running=False
        )
        
        db.session.add(config)
        db.session.commit()
        
        # Add token configs if provided and TRC20 sweeping is enabled
        if sweep_trc20 and token_contracts:
            with app.app_context():
                from src.config import Config
                from src.tron_client import TronClient
                
                try:
                    # Initialize Config and TronClient to fetch token info
                    cfg = Config()
                    client = TronClient(cfg)
                    
                    # Fetch and save token info for each contract
                    for contract in token_contracts:
                        try:
                            # Check if token already exists in database
                            existing_token = db.session.query(TokenConfig).filter_by(
                                contract_address=contract,
                                blockchain='tron'
                            ).first()
                            
                            if not existing_token:
                                # Get token info from blockchain
                                token_info = client.get_token_info(contract)
                                
                                # Create token config
                                token_config = TokenConfig(
                                    contract_address=contract,
                                    symbol=token_info.get('symbol', 'UNKNOWN'),
                                    name=token_info.get('name', 'Unknown Token'),
                                    decimals=token_info.get('decimals', 18),
                                    blockchain='tron',
                                    token_type='trc20',
                                    enabled=True
                                )
                                
                                db.session.add(token_config)
                        except Exception as e:
                            logger.error(f"Error fetching token info for {contract}: {str(e)}")
                    
                    # Commit token configs
                    db.session.commit()
                    
                except Exception as e:
                    logger.error(f"Error adding token configurations: {str(e)}")
        
        flash('Configuration saved successfully', 'success')
        return redirect(url_for('index'))
    
    # GET request
    config = BotConfig.query.order_by(BotConfig.id.desc()).first()
    tokens = TokenConfig.query.filter_by(blockchain='tron', enabled=True).all()
    return render_template('config.html', config=config, tokens=tokens)

# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)