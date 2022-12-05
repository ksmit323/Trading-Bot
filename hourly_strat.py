"""
This is my implementation of a 1-hour daytrading strategy.
The primary idea is to buy on the break of an inside candle
on tickers that are up on the day.

The Trading Protocol is as follows:
- The last fully formed 1hr bar must be an inside candle
    to it's predecessor
- That inside candle must be green
- The current bar must make a new high over the inside bar for
    a trade to execute (the entry)
- On every new 1hr candle update the stop loss to the low of the previous candle

IMPORTANT NOTE: This strategy is not capable of executing any
trades within the first 1.5 hours of the trading day because
the strategy requires at least three bars of information
"""

import threading
import time
import sys

import bt  # another backtesting library; got the documentation bookmarked
import backtesting
import matplotlib
import numpy as np
import pandas as pd
import talib
import webbrowser
import xml.etree.ElementTree as ET

from ib_insync import *

# Instantiate IB class and establish connection
ib = IB()
ib.connect('127.0.0.1', 7497, 1)


def main():

    # TODO: Need to calculate risk/reward based on the profit taking currently implemented
    # TODO: Must reduce the trades by not buying three at a time anymore
    # TODO: Parse out trades into usable data

    #! The primary issue right now is the bot trades too much

    #! Would like to consider the Kelly Criterion for position sizing and having a new risk profile

    #? How about a no trading ticker list for shitty tickers like TOPS

    #? Have been considering only trading in the morning to avoid afternoon chop

    # Initialize hour variable to help track time of day
    hour = 20

    # Variable to track how many order have been placed per ticker in a trading day
    orders_placed = 0

    while True:

        # Establish the time of day
        # * NOTE: this is set to local time here in Vietnam
        time_of_day = time.localtime()  

        # Update orders every hour
        if hour != time_of_day.tm_hour:

            # Cancel unfilled buy orders
            for order in ib.openOrders():
                if order.action == "BUY":
                    ib.cancelOrder(order)
                    print("Unfilled order cancelled")

            # Update stop losses 
            if len(ib.positions()) > 0:
                ib.sleep(10)
                adjust_all_stop_losses()
                print("Stop orders have been updated")

        # Close all positions at the end of the day
        # * NOTE: this will not work when the market closes early
        if time_of_day.tm_hour == 3 and time_of_day.tm_min >= 55:
            while True:
                cancel_all_open_orders()
                print("Now closing all positions")
                close_all_positions()
                ib.sleep(20)
                if len(ib.positions()) == 0:
                    print("All positions have been closed")
                    print(f"Today's total commissions: ${commissions_paid()}")
                    print(f"Total Orders Placed: {orders_placed}")
                    ib.disconnect()
                    sys.exit("You have been disconnected")

        # Loop thru each ticker in the scanner results and add to watchlist
        # * This loop should only run once per hour hence the updated hour variable
        if hour != time_of_day.tm_hour:

            # Initialize empty watchlist variable
            watchlist = []

            # Store scanner results as a variable so list doesn't change while iterating
            print("Scanning for tickers")
            scan_results = scanner(time_of_day)

            print("Now adding tickers to watchlist")

            for ticker in scan_results:

                # Create a contract
                contract = Stock(ticker, "SMART", "USD")

                # Create a dataframe of 1 hour bars
                df = build_dataframe(contract)

                # Append ticker to watchlist if it passes the strategy check
                try:
                    if check_strategy(df):
                        watchlist.append(ticker)
                except AttributeError:
                    continue

                # Update hour variable to prevent loop from running again
                hour = time_of_day.tm_hour

            print(f"{len(watchlist)} tickers have been added to the watchlist")
            print(watchlist)

        # Build a ticker list with open trades
        tickers_with_open_trades = open_trades_ticker_set()

        print("Starting iteration over watchlist")

        # Loop thru watchlist and check for any orders to be placed
        for ticker in watchlist:

            # Check that order hasn't already been placed           #? May need to consider how to adjust this so more than one trade can be made on the same ticker
            if ticker not in tickers_with_open_trades:              #? Could be done with a dictionary with tm_hour as the key and a ticker list as the value]
                                                                  
                print(f"Checking ticker {ticker}")

                # Create a contract
                contract = Stock(ticker, "SMART", "USD")

                # Create a dataframe of 1 hour bars
                df = build_dataframe(contract)

                # Remove ticker from watchlist if it makes a new low from previous candle
                if df.low.iloc[-1] < df.low.iloc[-2]:
                    watchlist.remove(ticker)

                # Place order when new hourly high is made if a new low hasn't been made first
                if df.high.iloc[-1] > df.high.iloc[-2] and df.low.iloc[-1] >= df.low.iloc[-2]:

                    # Set the limit price. Higher stocks have higher limit ranges
                    if df.open.iloc[-1] < 1:
                        limit_price = round((df.high.iloc[-2] + 0.005), 3)          #? Not sure if this will screw up the order placement with 3 decimals
                    elif df.open.iloc[-1] < 10:
                        limit_price = round((df.high.iloc[-2] + 0.01), 2)
                    else:
                        limit_price = round((df.high.iloc[-2] + 0.02), 2)

                    # Set the stop loss.  Higher priced stocks have higher stopo ut ranges
                    if df.open.iloc[-1] < 10:
                        stop_loss = round((df.low.iloc[-2] - 0.01), 2)
                    else:
                        stop_loss = round((df.low.iloc[-2] - 0.02), 2)

                    # Set share size based on risk levels
                    risk_per_share = round((limit_price - stop_loss), 2)
                    quantity = round(share_size(risk_per_share))

                    # Profit levels based on risk per share
                    take_profit_1 = round(
                        (df.high.iloc[-2] + risk_per_share * 4), 2)
                    take_profit_2 = round(
                        (df.high.iloc[-2] + risk_per_share * 6), 2)

                    # Spread orders out to vary profit taking prices
                    place_order(contract, "BUY", quantity,                         #! Bandaid solution for placing a single order. Not good to not spread out profit taking
                                limit_price, take_profit_1, stop_loss)                     

                    # Confirm order placement with print statement
                    print(f"An order has been placed for {ticker}. See TWS for details")
                    orders_placed += 1

        print("Finished iterating over the watchlist")

        # Sleep interval to allow for updates
        ib.sleep(10)


def build_dataframe(contract):
    """ Returns a dataframe of 1 hour bars from a contract argument """

    # Use qualify contracts function to automatically fill in additional info
    ib.qualifyContracts(contract)

    # Request live updates for historical bars
    bars = get_hist_data(contract)

    # Tell ib_insync library to call the on_bar_update function when new data is received
    # Set callback function for bar data
    bars.updateEvent += on_bar_update

    # Build dataframe from bars data list
    df = util.df(bars)

    return df


def check_strategy(df):
    """ Will return True if strategic criteria is met """                               #? Could maybe add to the strategy with three lower wicks in a row and buy on the next candle
                                                                                        
    # Bar prior to inside bar must be green
    if df.close.iloc[-3] >= df.open.iloc[-3]:

        # Prior bar must be an inside bar                                                   
        if df.low.iloc[-2] >= df.low.iloc[-3] and df.high.iloc[-2] <= df.high.iloc[-3]:

            # That inside bar must be green
            if df.close.iloc[-2] >= df.open.iloc[-2]:
                return True

    return False


def on_bar_update(bars: BarDataList, has_new_bar: bool):
    """ Callback function to update on every new bar """


def place_order(contract, direction, qty, lp, tp, sl):
    """ Place bracket order with IB """

    bracket_order = ib.bracketOrder(direction, qty, lp, tp, sl)
    for ord in bracket_order:
        ib.placeOrder(contract, ord)


def get_hist_data(contract):
    """ Return historical data with live updates """

    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="1 hour",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=True)

    return bars


def scanner(time_of_day):
    """ 
    Returns a list of tickers to be used for potential trades 
    Pass on a volume argument.  Ideally, you
    want to screen for higher volume as the day progresses.  
    There are two scan subscriptions being made because IB only returns
    a maximum of 50 tickers per subscription.  Subs are divided by stock price.
    """

    # Initialize minimum volume requirement for scanner. Scale up volume over time.
    if time_of_day.tm_hour == 23:
        volume_higher_priced = 500_000
        volume_lower_priced = 500_000
    elif time_of_day.tm_hour == 0 or time_of_day.tm_hour == 1:
        volume_higher_priced = 600_000
        volume_lower_priced = 750_000
    else:
        volume_higher_priced = 750_000
        volume_lower_priced = 1e6

    # Create a ScannerSubscription to submit to the reqScannerData method
    # * Currently only trading on the NASDAQ to avoid AMEX and overtrading
    sub_1 = ScannerSubscription(
        instrument="STK",
        locationCode="STK.NASDAQ",
        scanCode="TOP_OPEN_PERC_GAIN")

    # sub_2 = ScannerSubscription(
    #    instrument="STK",
    #    locationCode="STK.NYSE",
    #    scanCode="TOP_OPEN_PERC_GAIN")

    # Set scanner criteria with the appropriate tag values
    tag_values_1 = [
        # * Still want to find a real ATR type of tag
        TagValue("changePercAbove", 3),
        TagValue("priceBelow", 20),                         
        TagValue("priceAbove", 13),
        TagValue("volumeAbove", volume_higher_priced),
        TagValue("priceRangeAbove", "0.9"),
        TagValue("volumeRateAbove", 0), 
        TagValue("marketCapBelow1e6", 2000)]

    tag_values_2 = [                                 
        TagValue("changePercAbove", "4"),
        TagValue("priceBelow", 13),
        TagValue("priceAbove", 8),
        TagValue("volumeAbove", volume_lower_priced),
        TagValue("priceRangeAbove", "0.7"),
        TagValue("volumeRateAbove", 0),
        TagValue("marketCapBelow1e6", 1000)]
    
    tag_values_3 = [                                 
        TagValue("changePercAbove", "4"),
        TagValue("priceBelow", 8),
        TagValue("priceAbove", 4),
        TagValue("volumeAbove", volume_lower_priced),
        TagValue("priceRangeAbove", "0.4"),
        TagValue("volumeRateAbove", 0),
        TagValue("marketCapBelow1e6", 600)]

    tag_values_4 = [                                 
        TagValue("changePercAbove", "5"),
        TagValue("priceBelow", 4),
        TagValue("priceAbove", 0.3),
        TagValue("volumeAbove", volume_lower_priced),
        TagValue("priceRangeAbove", "0.1"),
        TagValue("volumeRateAbove", 0),
        TagValue("marketCapBelow1e6", 400)]

    # The tag_values are given as 3rd argument; the 2nd argument must always be an empty list
    # (IB has not documented the 2nd argument and it's not clear what it does)
    scan_data_1 = ib.reqScannerData(sub_1, [], tag_values_1)
    scan_data_2 = ib.reqScannerData(sub_1, [], tag_values_2)
    scan_data_3 = ib.reqScannerData(sub_1, [], tag_values_3)
    scan_data_4 = ib.reqScannerData(sub_1, [], tag_values_4)

    # Add tickers to a list and return that list
    symbols_1 = [sd.contractDetails.contract.symbol for sd in scan_data_1]
    symbols_2 = [sd.contractDetails.contract.symbol for sd in scan_data_2]
    symbols_higher_priced = symbols_1 + symbols_2
    symbols_3 = [sd.contractDetails.contract.symbol for sd in scan_data_3]
    symbols_4 = [sd.contractDetails.contract.symbol for sd in scan_data_4]
    symbols_lower_priced = symbols_3 + symbols_4

    print(len(symbols_higher_priced), "tickers found for higher priced stocks")
    print(len(symbols_lower_priced), "tickers found for lower priced stocks")
    return symbols_higher_priced + symbols_lower_priced


def cancel_all_open_orders():
    """ This function cancels all open orders """

    while len(ib.openOrders()) > 0:
        for order in ib.openOrders():
            ib.cancelOrder(order)
        ib.sleep(1)
    print("All orders have been cancelled")


def close_all_positions():
    """ Close all positions in account """

    # Market order out of all positions
    positions = ib.positions()
    for position in positions:
        contract = Stock(position.contract.symbol, "SMART", "USD")
        ib.qualifyContracts(contract)
        quantity = abs(position.position)
        order = MarketOrder(action="SELL", totalQuantity=quantity)
        ib.placeOrder(contract, order)
        ib.sleep(1)


def share_size(risk_per_share):
    """ 
    Function will determine the correct position sizing
    based on risk amount, account size and risk per share
    """
    account_size = 2_000
    risk_percent = 0.005
    shares = round((account_size * risk_percent) / risk_per_share)
    return shares


def adjust_all_stop_losses():
    """ Function will update all stop losses """

    for trade in ib.openTrades():
        if trade.order.orderType == "STP":

            # Create new contract based on the symbol
            contract = Stock(trade.contract.symbol, "SMART", "USD")

            # Make sure the bars data is up to date
            bars = get_hist_data(contract)
            bars.updateEvent += on_bar_update
            df = util.df(get_hist_data(contract))

            # Replace previous stop order with new price
            try:
                trade.order.auxPrice = df.low.iloc[-2] - 0.01
                ib.placeOrder(contract, trade.order)
            except AttributeError:
                print(trade)
                continue

def open_trades_ticker_set():
    """ Returns a set of tickers with open trades """

    ticker_set = set()
    for trade in ib.openTrades():
        ticker_set.add(trade.contract.symbol)
    return ticker_set


def commissions_paid():
    """ Return the total cost of commissions in USD """
    commissions = sum(fill.commissionReport.commission for fill in ib.fills())      # ? I think this is calculating for more than one day
    return round(commissions)


def scanner_parameters():
    """
    #* This function is not used in the actual trade execution.  
    It is only to find what scanner parameters are available for use.
    The code is here for reference only.
    Run this function in a separate script to find a list of scanner parameters
    Libraries you may need: webbrowser, xml.etree.ElementTree
    Function will produce a huge list of over 1800 tags..   
    Will need additional code to make it more readable.
    """
    # Create xml document with scanner parameters
    xml = ib.reqScannerParameters()

    # View all scanner parameters in a web browser
    path = "scanner_parameters.xml"
    with open(path, "w") as f:
        f.write(xml)
    webbrowser.open(path)

    # Parse XML document
    tree = ET.fromstring(xml)

    # Find all tags available for filtering
    tags = [elem.text for elem in tree.findall(".//AbstractField/code")]
    sorted_tags = sorted(tags)
    tags_set = set(sorted_tags)
    df = pd.DataFrame(data={"col1": tags_set})
    df.to_csv("./file.csv", sep=',', index=False)


def scan_codes():
    """
    #* This function is not used in the actual trade execution.  
    Not used in the actual trade execution
    Print this function in a separate script
    to get all the different types of scan codes
    such as "top percent gainers", etc.
    """
    # Create xml document with scanner parameters
    xml = ib.reqScannerParameters()

    # Parse XML document
    tree = ET.fromstring(xml)

    # Print all scan codes
    scan_codes = [e.text for e in tree.findall(".//scanCode")]
    print(len(scan_codes), "Scan Codes:")
    print(scan_codes)


if __name__ == '__main__':
    main()
