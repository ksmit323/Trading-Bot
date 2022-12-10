""" 
Working on a strategy for swing trading.
The code here will work on defining a scanner
to filter out stocks that would qualify for a swing.
This would include inside candles with big volume spikes
on small cap stocks under $10 with a certain volatility.

There will be both a screening for both daily and weekly candles (maybe monthly).

A list of tickers that may be helpful as examples to tune the scanner on:
- CABA, weekly
- NYMX, daily
- DAO, weekly
- EAR, weekly
- EH, weekly
- KOPN, daily
- LIZI, weekly
- NMTC, weekly
"""

import pandas as pd
import talib                                               
from ib_insync import *
import sys
import csv


# Instantiate IB class and establish connection
ib = IB()
ib.connect('127.0.0.1', 7497, 2)  #* Change port id when on live account to 7496
if ib.isConnected():
    print("Connection established")
else:
    print("Failed to connect")


def main():
    """ Starting out with building the weekly scanner.  Will consider daily after. """

    # Ensure correct usage
    if len(sys.argv) != 2:
        sys.exit("Usage: python swing_strat.py FILENAME")
    

    # Read in scan results from CSV file
    print("Reading in scan results")
    filename = sys.argv[1]
    scan_results = scanner(filename)
    print(f"{len(scan_results)} tickers found in scanner")

    # Initialize watchlist
    watchlist = []

    # Scan tickers to add to watchlist
    print("Now adding tickers to the watchlist")
    for ticker in scan_results:

        # Create a contract
        contract = Stock(ticker, "SMART", "USD")
        
        # Use qualify contracts function to automatically fill in additional info
        ib.qualifyContracts(contract)

        # Create a dataframe of weekly bars
        df = build_dataframe(contract)

        # Add ticker to watchlist if strategy function returns True
        try:
            if check_strategy(df):
                watchlist.append(ticker)
        except AttributeError:
            continue
        
    print(len(watchlist))
    print(watchlist)


def scanner(filename):
    """ Read in scan results from TOS CSV file """
    scan_results = []
    with open(filename, "r") as file:
        for ticker in file:
            ticker = ticker.strip('\n')
            scan_results.append(ticker)
    
    return scan_results


def build_dataframe(contract):
    """ Returns a dataframe of weekly bars from a contract argument """

    # Request live updates for historical bars
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="7 D",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=True)

    # Build dataframe from bars data list
    df = util.df(bars)

    return df


def check_strategy(df):
    """ Function checks if strategic criteria has been met """                               
                                                                                        
    # Bar prior to inside bar must be green
    if df.close.iloc[-2] >= df.open.iloc[-2]:

        # Current bar must be an inside bar                                                   
        if df.low.iloc[-1] >= df.low.iloc[-2] and df.high.iloc[-1] <= df.high.iloc[-2]:

            # That inside bar must be green
            #if df.close.iloc[-2] >= df.open.iloc[-2]:
            return True

    return False


def place_order():
    ...


def share_size(risk_per_share):
    """ 
    Function will determine the correct position sizing
    based on risk amount, account size and risk per share
    """
    account_size = 1700
    risk_percent = 0.02
    shares = round((account_size * risk_percent) / risk_per_share)
    return shares


if __name__ == '__main__':
    main()
