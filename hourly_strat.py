"""
This is my implementation of a 1-hour daytrading strategy.
The primary idea is to buy on the break of an inside candle
on tickers that are up on the day.

The Trading Protocol is as follows:
- The last fully formed 1hr bar must be an inside candle
    to it's predecessor
- The last fully formed 1hr bar must be green
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
import numpy
import pandas as pd
import talib
import webbrowser
import xml.etree.ElementTree as ET

from ib_insync import *

# Instantiate IB class and establish connection
ib = IB()
ib.connect('127.0.0.1', 7497, 2)


def main():

    # TODO: Really need to adjust the scanners better

    # TODO: Need to calculate risk/reward based on the profit taking currently implemented

    # Establish the time of day
    time_of_day = time.localtime()  # * NOTE: this is set to local time here in Vietnam

    # Initialize hour variable to help track time of day
    hour = 22

    # Initialize minimum volume requirement for scanner
    # * Adjust as needed
    volume = 500000

    while True:

        # Update all stop losses every hour
        if hour != time_of_day.tm_hour:
            if len(ib.positions()) > 0:
                ib.sleep(10)
                try:
                    adjust_all_stop_losses()
                except AttributeError:
                    pass

        # Close all positions at the end of the day
        # * NOTE: this will not work when the market closes early
        if time_of_day.tm_hour == 3 and time_of_day.tm_min >= 55:
            while True:
                close_all_positions()
                ib.sleep(10)
                if len(ib.positions()) == 0:
                    print(
                        f"Your total commissions for today are {commissions_paid()}")
                    ib.disconnect()
                    sys.exit("You have been disconnected")

        # Loop thru each ticker in the scanner results and add to watchlist
        # * This loop should only run once per hour hence the hour updated variable
        if hour != time_of_day.tm_hour:

            # Initialize empty watchlist variable
            watchlist = []

            # Store scanner results as a variable so list doesn't change while iterating
            scan_results = scanner(volume)

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

        # Build a ticker list with open trades
        tickers_with_open_trades = open_trades_ticker_set()

        # Loop thru watchlist and check for any orders to be placed
        for ticker in watchlist:

            # Create a contract
            contract = Stock(ticker, "SMART", "USD")

            # Create a dataframe of 1 hour bars
            df = build_dataframe(contract)

            # Check that order hasn't already been placed
            if ticker not in tickers_with_open_trades:

                # Place order when new hourly high is made
                if df.high.iloc[-1] >= df.high.iloc[-2]:
                    limit_price = round((df.high.iloc[-2] + 0.05), 2)
                    stop_loss = round((df.low.iloc[-2] - 0.01), 2)
                    risk_per_share = round((limit_price - stop_loss), 2)
                    quantity = share_size(risk_per_share)

                    # Profit levels based on risk per share
                    take_profit_1 = round(
                        (df.high.iloc[-2] + risk_per_share), 2)
                    take_profit_2 = round(
                        (df.high.iloc[-2] + risk_per_share * 2), 2)
                    take_profit_3 = round(
                        (df.high.iloc[-2] + risk_per_share * 4), 2)

                    # Spread orders out to vary profit taking prices
                    place_order(contract, "BUY", round(quantity/3),
                                limit_price, take_profit_1, stop_loss)
                    place_order(contract, "BUY", round(quantity/3),
                                limit_price, take_profit_2, stop_loss)
                    place_order(contract, "BUY", round(quantity/3),
                                limit_price, take_profit_3, stop_loss)

                    # Confirm order placement with print statement
                    print(f"An order has been placed for {ticker}. See TWS for details")

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
    """ Will return True if strategic criteria is met """

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
        whatToShow="MIDPOINT",
        useRTH=True,
        formatDate=1,
        keepUpToDate=True)

    return bars


def scanner(volume):
    """ 
    Returns a list of tickers to be used for potential trades 
    Pass on a volume argument.  Ideally, you
    want to screen for higher volume as the day progresses.  
    There are two scan subscriptions being made because IB only returns
    a maximum of 50 tickers per subscription.  Subs are divided by stock price.
    """
    # * Experiment with NASDAQ.SCM, volume, prices
    # * Try two subs with NASDAQ and NYSE

    # Create a ScannerSubscription to submit to the reqScannerData method
    sub_1 = ScannerSubscription(
        instrument="STK",
        locationCode="STK.NASDAQ.SCM",  # * Need to find a way to filter out AMEX stocks
        scanCode="TOP_PERC_GAIN")

    # sub_2 = ScannerSubscription(
    #    instrument="STK",
    #    locationCode="STK.NYSE",  # * Need to find a way to filter out AMEX stocks
    #    scanCode="TOP_OPEN_PERC_GAIN")

    # Set scanner criteria with the appropriate tag values
    tag_values_1 = [
        # * Still want to find a real ATR type of tag
        TagValue("changePercAbove", 2),
        TagValue("priceBelow", 40),
        TagValue("priceAbove", 0.20),
        TagValue("volumeAbove", volume),
        TagValue("priceRangeAbove", "0.1")]

    tag_values_2 = [
        TagValue("changePercAbove", "1"),
        TagValue("priceBelow", 15),
        TagValue("priceAbove", 0.5),
        TagValue("volumeAbove", volume),
        TagValue("priceRangeAbove", "1")]

    # The tag_values are given as 3rd argument; the 2nd argument must always be an empty list
    # (IB has not documented the 2nd argument and it's not clear what it does)
    scan_data_1 = ib.reqScannerData(sub_1, [], tag_values_1)
    #scan_data_2 = ib.reqScannerData(sub_2, [], tag_values_1)

    # Add tickers to a list and return that list
    symbols_1 = [sd.contractDetails.contract.symbol for sd in scan_data_1]
    #symbols_2 = [sd.contractDetails.contract.symbol for sd in scan_data_2]
    #symbols = symbols_1 + symbols_2
    print(len(symbols_1))
    # print(len(symbols_2))
    return symbols_1


def close_all_positions():
    """ Close all positions in account """

    # Cancel all existing orders first
    for order in ib.openOrders:
        ib.cancelOrder(order)

    # Market order out of all positions
    positions = ib.positions()
    for position in positions:
        contract = position.contract
        quantity = abs(position.position)
        order = MarketOrder(action="SELL", totalQuantity=quantity)
        ib.placeOrder(contract, order)
        ib.sleep(1)


def share_size(risk_per_share):
    """ 
    Function will determine the correct position sizing
    based on risk amount, account size and risk per share
    """
    account_size = 37000
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
            trade.order.auxPrice = df.low.iloc[-2]
            ib.placeOrder(contract, trade.order)


def open_trades_ticker_set():
    """ Returns a set of tickers with open trades """

    ticker_set = set()
    for trade in ib.openTrades():
        ticker_set.add(trade.contract.symbol)
    return ticker_set


def commissions_paid():
    """ Return the total cost of commissions in USD """
    commissions = sum(fill.commissionReport.commission for fill in ib.fills())
    return commissions


def scanner_parameters():
    """
    #! This function is not used in the actual trade execution.  
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
    #! This function is not used in the actual trade execution.  
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
