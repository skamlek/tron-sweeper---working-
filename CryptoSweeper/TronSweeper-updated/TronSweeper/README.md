# TRON Sweeper Bot

## Overview
A Python-based TRON wallet automation tool that monitors and automatically sweeps TRX and TRC20 tokens to a destination wallet.

## Features
- **Ultra-fast response** (check intervals as low as 1 second)
- **TRX sweeping** - automatically transfer TRX to your secure wallet
- **TRC20 token support** - monitor and sweep multiple tokens
- **Web interface** for configuration and monitoring
- **Transaction logs** with detailed history
- **Customizable thresholds** for minimum transfer amounts
- **TRON API key support** for higher rate limits

## Setup Instructions

### Requirements
```
flask
flask-sqlalchemy
psycopg2-binary
tronpy
gunicorn
email-validator
```

### Installation
1. Clone this repository
2. Install the required dependencies:
   ```
   pip install flask flask-sqlalchemy psycopg2-binary tronpy gunicorn email-validator
   ```

3. Set up your database:
   - Create a PostgreSQL database
   - Set the DATABASE_URL environment variable

4. Run the application:
   ```
   python main.py
   ```

5. Access the web interface at http://localhost:5000

## Configuration
1. Navigate to the Configuration page
2. Enter your source wallet private key and address
3. Enter your destination wallet address
4. Configure check interval (1-60 seconds)
5. Enable TRX sweeping and/or TRC20 token sweeping
6. Add TRON API keys for higher rate limits (optional)
7. Save configuration and start the bot

## Security Notes
- The source wallet private key is stored in the database
- The destination wallet is for receiving funds only (no private key needed)
- Consider using a dedicated source wallet with minimal funds
- Run the bot on a secure server with limited access