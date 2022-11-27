"""
This is my implementation of a 1-hour daytrading strategy.
The primary idea is to buy on the break of an inside candle
on tickers that are up on the day.

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

    # Establish the time of day
    time_of_day = time.localtime()  # * NOTE: this is set to local time here in Vietnam

    # Trading cannot start until after the first 1.5 hours of the day
    if time_of_day.tm_hour >= 12:   #! Change this back to 23

        #! TODO: Fix this issue 
        # Update all stop losses every hour
        if time_of_day.tm_min == 0:
            ib.sleep(10)
            adjust_all_stop_losses()

        # Close all positions at the end of the day
        if time_of_day.tm_hour == 3 and time_of_day.tm_min > 55:  # * NOTE: this will not work when the market closes early
            while True:
                close_all_positions()
                ib.sleep(10)
                if len(ib.positions()) == 0:
                    print(commissions_paid())
                    ib.disconnect()
                    sys.exit("You have been disconnected")

        # Initialize minimum volume requirement for scanner
        volume = 750000 #! Adjust as needed

        # Store scanner results as a variable so list doesn't change while iterating
        scan_results = scanner(volume)

        # Initialize empty watchlist variable
        watchlist = []
        
        # Loop thru each ticker in the scanner results and add to watchlist
        for ticker in scan_results:

            # Create a contract
            contract = Stock(ticker, "SMART", "USD")

            # Create a dataframe of 1 hour bars
            df = build_dataframe(contract)

            # Append ticker to watchlist if requirements met
            try:
                if check_strategy(df):
                    watchlist.append(ticker)
            except AttributeError:
                continue

        # Loop thru watchlist and check for any orders to be placed
        for ticker in watchlist:

            # Create a contract
            contract = Stock(ticker, "SMART", "USD")

            # Create a dataframe of 1 hour bars
            df = build_dataframe(contract)

            # Place order when new hourly high is made
            if df.high.iloc[-1] >= df.high.iloc[-2]:
                limit_price = round((df.high.iloc[-2] + 0.05), 2)
                stop_loss = round((df.low.iloc[-2] - 0.01), 2)
                risk_per_share = round((limit_price - stop_loss), 2)
                quantity = share_size(risk_per_share)

                # Profit levels based on risk per share
                take_profit_1 = round((df.high.iloc[-2] + risk_per_share), 2)
                take_profit_2 = round((df.high.iloc[-2] + risk_per_share * 2), 2)
                take_profit_3 = round((df.high.iloc[-2] + risk_per_share * 4), 2)

                # Spread orders out to vary profit taking prices
                place_order(contract, "BUY", round(quantity/3), limit_price, take_profit_1, stop_loss)
                place_order(contract, "BUY", round(quantity/3), limit_price, take_profit_2, stop_loss)
                place_order(contract, "BUY", round(quantity/3), limit_price, take_profit_3, stop_loss)

                # Confirm order placement with print statement
                print(f"An order has been placed for {ticker}. See TWS for details")
        
        # Sleep interval to allow for updates
        ib.sleep(10)

    else:
        ib.disconnect
        sys.exit("Too early to trade")

    # Sleep interval
    ib.sleep(2)

    # Run infinitely
    #ib.run()
    ib.disconnect()
    print("You have been disconnected")


def build_dataframe(contract):
    """ Returns a dataframe of 1 hour bars from a contract argument """

    # Use qualify contracts function to automatically fill in additional info
    ib.qualifyContracts(contract)

    # Request live updates for historical bars
    bars = get_data(contract)

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
        else:
            return False
    else:
        return False


def on_bar_update(bars: BarDataList, has_new_bar: bool):
    """ Callback function to update on every new bar """


def place_order(contract, direction, qty, lp, tp, sl):
    """ Place bracket order with IB """

    bracket_order = ib.bracketOrder(direction, qty, lp, tp, sl)
    for ord in bracket_order:
        ib.placeOrder(contract, ord)


def get_data(contract):
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

    # Create a ScannerSubscription to submit to the reqScannerData method
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",    #* Need to find a way to filter out AMEX stocks
        scanCode="TOP_OPEN_PERC_GAIN")  

    # Set scanner criteria with the appropriate tag values
    tag_values_1 = [
        TagValue("changePercAbove", "2"),   #* Still want to find a real ATR type of tag
        TagValue("priceBelow", 40),
        TagValue("priceAbove", 15),
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
    scan_data_1 = ib.reqScannerData(sub, [], tag_values_1)
    scan_data_2 = ib.reqScannerData(sub, [], tag_values_2)

    # Add tickers to a list and return that list
    symbols_1 = [sd.contractDetails.contract.symbol for sd in scan_data_1]
    symbols_2 = [sd.contractDetails.contract.symbol for sd in scan_data_2]
    symbols = symbols_1 + symbols_2
    print(len(symbols))
    return symbols


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
            bars = get_data(contract)
            bars.updateEvent += on_bar_update
            df = util.df(get_data(contract))

            # Replace previous stop order with new price
            trade.order.auxPrice = df.low.iloc[-2]
            ib.placeOrder(contract, trade.order)


def commissions_paid():
    """ Return the total cost of commissions in USD """
    commissions = sum(fill.commissionReport.commission for fill in ib.fills())
    return commissions


def positions():
    """ Returns a list of all positions in the account"""
    return ib.positions()


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
    print(len(tags), "Tags:")
    print(tags)


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
