import threading
import time

import bt # another backtesting library; got the documentation bookmarked
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

    # First, establish the time of day to get the correct volume value
    time = time.localtime() #* Note that it is set to local time here in Vietnam
    if time.tm_hour < 23:
        volume = 100000 #if morning trading, the volume requirement is lower
    else:
        volume = 500000 #if afternoon trading, the volume requirement is higher
    
    # Close all positions at the end of the day
    if time.tm_hour == 3 and time.tm_sec > 55:
        close_all_positions()

    # Create a contract
    contract("TSLA")

    # Use qualify contracts function to automatically fill in additional info
    ib.qualifyContracts(contract)

    # Request live updates for historical bars
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="60 mins",
        whatToShow="MIDPOINT",
        useRTH=True,
        formatDate=1,
        keepUpToDate=True)

    # Tell ib_insync library to call the on_bar_update function when new data is received
    # Set callback function for bar data
    bars.updateEvent += on_bar_update

    # Sleep interval
    ib.sleep(10)

    # Run infinitely
    ib.run()


def contract(ticker: str):
    """ Create a contract with a ticker argument """
    contract = Stock(ticker, "SMART", "USD")
    return contract


def place_order(contract, direction, qty, lp, tp, sl):
    """ Place bracket order with IB """
    bracket_order = ib.bracketOrder(
        direction,
        qty,
        limit_price=lp,
        take_profit_price=tp,
        stop_loss_price=sl,
    )

    for ord in bracket_order:
        ib.placeOrder(contract, ord)
    
    print("An order has been placed. See TWS for details")

def on_bar_update(bars: BarDataList, has_new_bar: bool):
    """ 
    This function defines the entire trading protocol and
    when the Tradig Bot executres trades.
    The Trading Protocol is as follows:
    - The last fully formed 1hr bar must be an inside candle
      to it's predecessor
    - The last fully formed 1hr bar must be green
    - The current bar must make a new high over the inside bar for
      a trade to execute (the entry)
    """
    # Begin an execution sequence at the top of every hour
    if has_new_bar:
        # Sleep so dataframe has time to update to the last bar
        ib.sleep(10)
        # Build dataframe from bars data list
        df = util.df(bars)



        





def scanner(volume):
    """ 
    Returns a list of tickers to be used for potential trades 
    Pass on a volume argument so the results will vary as the
    trading day continues into the afternoon.  Ideally, you
    want to screen for higher volume as the day progresses.
    """

    # Create a ScannerSubscription to submit to the reqScannerData method
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN")
    
    # Set scanner criteria with the appropriate tag values
    tag_values = [
        TagValue("changePercAbove", "0"),
        TagValue("priceBelow", 40),
        TagValue("volumeAbove", volume)]
    
    # The tag_values are given as 3rd argument; the 2nd argument must always be an empty list
    # (IB has not documented the 2nd argument and it's not clear what it does)
    scan_data = ib.reqScannerData(sub, [], tag_values)

    # Add tickers to a list and return that list
    symbols = [sd.contractDetails.contract.symbol for sd in scan_data]

    return symbols


def close_all_positions():
    """ Close all positions in account """

    # Create a list of all positions
    positions = ib.positions()
    # Loop thru each position and close it
    for position in positions:
        contract = position.contract
        quantity = abs(position.position)
        order = MarketOrder(action="SELL", totalQuantity=quantity)
        ib.placeOrder(contract, order)  


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
    with open(path,"w") as f:
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
