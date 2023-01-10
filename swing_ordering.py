from ib_insync import *
import sys


# Instantiate IB class and establish connection
ib = IB()
# * Change port id when on live account to 7496, Paper account to 7497 
ib.connect('127.0.0.1', 7496, 1)
if ib.isConnected():
    print("Connection established")
else:
    print("Failed to connect")


def main():

    place_orders = True

    if not place_orders:
        adjust_stop_losses()
        print("Stop losses have been updated")

    tickers = []

    position_value = 0
    
    if place_orders:

        for ticker in tickers:

            # Create a contract
            contract = Stock(ticker, "SMART", "USD")
            ib.qualifyContracts(contract)
            df = build_dataframe(contract)

            # Set stop limit prices
            if df.open.iloc[-1] < 1:
                stop_limit = round((df.high.iloc[-1] + 0.005), 3)
            else:
                stop_limit = round((df.high.iloc[-1] + 0.01), 2)
            limit_price = round((df.high.iloc[-1] + 0.02), 2)

            # Set stop loss
            if df.open.iloc[-1] < 1:
                stop_loss = round((df.low.iloc[-1] - 0.005), 3)
            else:
                stop_loss = round((df.low.iloc[-1] - 0.01), 2)

            risk_per_share = round((limit_price - stop_loss), 2)
            take_profit_increment = risk_per_share
            take_profit_level = round(
                (df.high.iloc[-1] + take_profit_increment), 2)
            quantity = share_size(risk_per_share)

            place_order(
                contract,
                "BUY",
                quantity,
                limit_price,
                take_profit_level,
                take_profit_increment,
                stop_loss,
                stop_limit
            )
            print(f"Order for {ticker} has been placed")
            position_value += round(stop_limit * quantity)
            
        print(f"Total position value: ${position_value}")

def build_dataframe(contract):
    """ Returns a dataframe of weekly bars from a contract argument """

    # Request live updates for historical bars
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr= "5 D",          # Change to "5 W" for the weekly, "5 D" for daily
        barSizeSetting= "1 day",     # Change to "1 week" for weekly, "1 day" for the daily
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=True)

    # Build dataframe from bars data list
    df = util.df(bars)

    return df


def place_order(contract, action: str,
                quantity: int,
                limit_price: float,
                take_profit_limit_price: float,
                take_profit_increment: float,
                stop_loss_price: float,
                stop_limit: float):
    """ 
    This function handles all of the order placements into IB.
    It uses a bracket order to incorporate profit taking and 
    a stop loss.  

    The take_profit object includes scale attributes so that
    profit prices can vary depending on the level size.
    The scaleInitLevelSize is the first scaling out profit level of 
    the position.  The scaleSubsLevelSize is the next portion that
    the bracket order will sell at the next profit level. 
    The scalePriceIncrement is how much the profit level will
    increase up at each sell point.   

    NOTE: Make sure to always handle order transmission accurately.
    The transmit attribute for all orders should be set to False
    except for the last order, which is of course set to True.
    """
    # Get an order ID to assign to the parent order
    parent_order_id = ib.client.getReqId()

    # Parent Stop Limit order
    parent = Order()
    parent.orderId = parent_order_id
    parent.action = action
    parent.orderType = "STP LMT"
    parent.totalQuantity = quantity
    parent.lmtPrice = limit_price
    parent.auxPrice = stop_limit
    parent.tif = "GTC"
    #parent.outsideRth = True
    parent.transmit = False

    # Profit taking order
    take_profit = Order()
    take_profit.orderId = parent.orderId + 1
    take_profit.action = "SELL" if action == "BUY" else "BUY"
    take_profit.orderType = "LMT"
    take_profit.totalQuantity = quantity
    take_profit.lmtPrice = take_profit_limit_price
    take_profit.scaleInitLevelSize = quantity // 3
    take_profit.scaleSubsLevelSize = quantity // 4
    take_profit.scalePriceIncrement = take_profit_increment
    take_profit.parentId = parent_order_id
    take_profit.tif = "GTC"
    take_profit.outsideRth = True
    take_profit.transmit = False

    # Stop loss order
    stop_loss = Order()
    stop_loss.orderId = parent.orderId + 2
    stop_loss.action = "SELL" if action == "BUY" else "BUY"
    stop_loss.orderType = "STP"
    stop_loss.auxPrice = stop_loss_price
    stop_loss.totalQuantity = quantity
    stop_loss.parentId = parent_order_id
    stop_loss.tif = "GTC"
    stop_loss.transmit = True

    bracket_order = [parent, take_profit, stop_loss]

    for order in bracket_order:
        ib.placeOrder(contract, order)


def adjust_stop_losses():                                               
    """ Function will update all hourly stop losses """                                                

    for trade in ib.openTrades():

        if trade.order.orderType == "STP":

            # Create new contract based on the symbol
            contract = Stock(trade.contract.symbol, "SMART", "USD")
            ib.qualifyContracts(contract)

            # Make sure the bars data is up to date
            df = build_dataframe(contract)

            # Replace previous stop order with new price
            try:
                if df.low.iloc[-2] < 1:
                    trade.order.auxPrice = round((df.low.iloc[-1] - 0.005), 3)
                else:
                    trade.order.auxPrice = round((df.low.iloc[-1] - 0.01), 2)
                ib.placeOrder(contract, trade.order)
            except AttributeError:
                print(f"*** WARNING: Stop loss not updated for: {trade.contract.symbol} ***")
                continue
            ib.sleep(0.5)


def share_size(risk_per_share):
    """ 
    Function will determine the correct position sizing
    based on risk amount, account size and risk per share
    """
    account_size = 600
    risk_percent = 0.01
    shares = round((account_size * risk_percent) / risk_per_share)
    return shares


if __name__ == '__main__':
    main()
