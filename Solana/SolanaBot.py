import tweepy
import requests
import sqlite3
import re
from schedule import every, repeat, run_pending
import time
from solana.publickey import PublicKey
from solana.system_program import TransferParams, transfer
from solana.transaction import Transaction
from solana.rpc.api import Client
from solana.keypair import Keypair
from solana.token import Token, ASSOCIATED_TOKEN_PROGRAM_ID, TOKEN_PROGRAM_ID
import random

# Authentication for X API
auth = tweepy.OAuthHandler("consumer_key", "consumer_secret")
auth.set_access_token("access_token", "access_token_secret")
api = tweepy.API(auth)

# Authentication for GMGN API
gmgn_api_key = "your_gmgn_api_key"
gmgn_headers = {'Authorization': f'Bearer {gmgn_api_key}'}

# Authentication for PumpFun API (if applicable)
pumpfun_api_key = "your_pumpfun_api_key"
pumpfun_headers = {'Authorization': f'Bearer {pumpfun_api_key}'}

# Solanasniffer does not require authentication for public token checks
solanasniffer_base_url = "https://solanasniffer.com/score/"

# Solana client setup
client = Client("https://api.mainnet-beta.solana.com")

# Database connection
conn = sqlite3.connect('memecoins.db')
c = conn.cursor()

# Create tables if they don't exist
c.execute('''CREATE TABLE IF NOT EXISTS tweets 
             (id TEXT PRIMARY KEY, user TEXT, content TEXT, timestamp DATETIME, contract_address TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS coins 
             (contract_address TEXT PRIMARY KEY, ticker TEXT, platform TEXT, market_cap REAL, volume REAL, price_change REAL, timestamp DATETIME, solanasniffer_score REAL)''')
conn.commit()

# List of KOLs
KOLs = ['KOLUsername1', 'KOLUsername2', 'KOLUsername3']  # Replace with real KOL usernames

# Functions for managing priority fees
def set_priority_fee(tx: Transaction, micro_lamports: int):
    """
    Adds priority fee instruction to the transaction.
    """
    from solana.compute_budget import ComputeBudgetInstruction
    tx.add(ComputeBudgetInstruction.request_compute_units(200000, micro_lamports))

def check_and_alert_solanasniffer_score(contract_address):
    url = f"{solanasniffer_base_url}{contract_address}"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Parse the response. This is highly dependent on how Solanasniffer formats their response.
            # Here we assume JSON format, but you might need to adjust based on the actual API response.
            score = response.json().get('score', None)  # Adjust based on actual API response format
            if score is not None and score < 80:
                print(f"ALERT: Contract {contract_address} has a Solanasniffer score of {score}, which is below 80.")
                # Here you would send an alert. This could be via email, another API, or even posting to X.
            return score
    except Exception as e:
        print(f"Error checking Solanasniffer score for {contract_address}: {e}")
    return None

@repeat(every(1).minutes)
def scan_tweets_and_update_db():
    for kol in KOLs:
        tweets = api.user_timeline(screen_name=kol, count=200, tweet_mode='extended')
        
        for tweet in tweets:
            # Extract contract addresses from tweets
            contract_addresses = re.findall(r'[1-9A-HJ-NP-Za-km-z]{32,44}', tweet.full_text)
            
            for address in contract_addresses:
                # Insert tweet data into database
                c.execute("INSERT OR IGNORE INTO tweets VALUES (?, ?, ?, ?, ?)", 
                          (tweet.id_str, tweet.user.screen_name, tweet.full_text, tweet.created_at, address))
                
                # Query GMGN (omitted for brevity since focus is on Solanasniffer)
                
                # Query Solanasniffer and update DB
                score = check_and_alert_solanasniffer_score(address)
                if score is not None:
                    # Update or insert into coins table
                    c.execute("INSERT OR REPLACE INTO coins VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                              (address, None, 'Solana', None, None, None, tweet.created_at, score))
    
    conn.commit()

# Buy Function
def buy_token(source_wallet: Keypair, token_mint: PublicKey, amount_sol: float, slippage: float):
    """
    Buy tokens with conditions of priority fees and slippage.
    """
    amount_lamports = int(amount_sol * 1e9)
    
    tx = Transaction()
    
    priority_fee = random.randint(5000, 10000)  # Example values, adjust based on network conditions
    set_priority_fee(tx, priority_fee)
    
    token = Token(client, token_mint, TOKEN_PROGRAM_ID, source_wallet)
    destination = token.create_associated_token_account(source_wallet.public_key)
    
    slippage_amount = amount_lamports * (1 - slippage)  # Since slippage is applied negatively for buy
    tx.add(transfer(TransferParams(from_pubkey=source_wallet.public_key, 
                                   to_pubkey=destination, 
                                   lamports=slippage_amount)))
    
    tx.sign(source_wallet)
    result = client.send_transaction(tx, source_wallet)
    return result

# Sell Function
def sell_token(source_wallet: Keypair, token_mint: PublicKey, token_account: PublicKey, amount_to_sell: float, slippage: float):
    """
    Sell tokens with conditions of priority fees and slippage.
    """
    token = Token(client, token_mint, TOKEN_PROGRAM_ID, source_wallet)
    
    tx = Transaction()
    
    priority_fee = random.randint(5000, 10000)  # Example values, adjust based on network conditions
    set_priority_fee(tx, priority_fee)
    
    amount_to_sell = int(amount_to_sell * 1e9)
    
    slippage_amount = amount_to_sell * (1 + slippage)  # Positive slippage for sell
    
    tx.add(token.transfer(source_wallet.public_key, token_account, slippage_amount).instruction)
    
    tx.sign(source_wallet)
    result = client.send_transaction(tx, source_wallet)
    return result

# Main logic to automate trading
def trade_logic(wallet: Keypair, token_mint: PublicKey, token_account: PublicKey):
    # Purchase range 0.01-0.05 SOL
    purchase_amount = random.uniform(0.01, 0.05)
    
    # Slippage range 15-25%
    slippage = random.uniform(0.15, 0.25)
    
    # Buy
    buy_result = buy_token(wallet, token_mint, purchase_amount, slippage)
    print(f"Bought tokens: {buy_result}")
    
    # Monitor price for 10x take-profit target
    # Here you'd need some mechanism to check token price, which might involve querying a DEX or an external price oracle
    current_price = 1  # Placeholder for actual price checking logic
    target_price = current_price * 10
    
    # Simplified monitoring - in reality, you'd use a loop or event system
    while True:
        # Check price (Pseudo code)
        if check_price(token_mint) >= target_price:
            break
    
    # Calculate sell amount considering 15% moonbag retention
    tokens_bought = purchase_amount * 10  # Assuming 10x increase for simplicity
    tokens_to_sell = tokens_bought * 0.85  # 85% to sell, 15% retained
    
    # Sell
    sell_result = sell_token(wallet, token_mint, token_account, tokens_to_sell, slippage)
    print(f"Sold tokens: {sell_result}")

# Debug: Placeholder for price checking
def check_price(token_mint: PublicKey):
    # This is a placeholder. You need to implement actual price checking logic.
    return 10  # Example return, should be replaced with real price data

# Main execution
if __name__ == "__main__":
    # Example wallet setup (never use this in production, generate a new keypair for each use)
    wallet = Keypair.from_secret_key(bytes([1]*64))  # Example keypair
    token_mint = PublicKey("TokenMintAddressHere")
    token_account = PublicKey("AssociatedTokenAccountAddressHere")

    # Start scanning tweets and updating database
    scan_tweets_and_update_db()
    
    # Example trade execution
    trade_logic(wallet, token_mint, token_account)

    # Keep the script running to check for new tweets or for trading opportunities
    while True:
        run_pending()
        time.sleep(1)

    # Close database connection when done
    conn.close()