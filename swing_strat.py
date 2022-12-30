""" 
Working on a strategy for swing trading.
The code here will work on defining a scanner
to filter out stocks that would qualify for a swing.
This would include inside candles with big volume spikes
on small cap stocks under $10 with a certain volatility.

The strategy can accomodate for both the daily and weekly.

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

from ib_insync import *
import sys


# Instantiate IB class and establish connection
ib = IB()
ib.connect('127.0.0.1', 7497, 1)  #* Change port id when on live account to 7496
if ib.isConnected():
    print("Connection established")
else:
    print("Failed to connect")


def main():

    # Read in scan results from CSV file
    print("Reading in scan results")
    filename = "scanresults.csv"
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
            if check_strategy_2(df):
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
        durationStr="5 D",          # Change to "5 W" for the weekly, "5 D" for daily
        barSizeSetting="1 day",     # Change to "1 week" for weekly, "1 day" for the daily
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
    if df.close.iloc[-2] > df.open.iloc[-2]:

        # Current bar must be an inside bar                                                   
        if df.low.iloc[-1] >= df.low.iloc[-2] and df.high.iloc[-1] <= df.high.iloc[-2]:
            return True
        elif df.close.iloc[-3] > df.open.iloc[-3] and df.low.iloc[-1] >= df.low.iloc[-2] and df.high.iloc[-1] <= df.high.iloc[-2]:
            return True

            # That inside bar must be green
            #if df.close.iloc[-2] >= df.open.iloc[-2]:
            return True

    return False


def check_strategy_2(df):
    """ Function checks for the second setup """

    # First and second bars to be checked both must be red
    #if df.close.iloc[-3] < df.open.iloc[-3] and df.close.iloc[-2] < df.open.iloc[-2]:

        # Prior bar must be an inside bar                                                   
    if df.low.iloc[-1] > df.low.iloc[-2] and df.high.iloc[-1] < df.high.iloc[-2]:

            # Bar must be green
            if df.close.iloc[-1] > df.open.iloc[-1]:
                return True
    
    return False


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
