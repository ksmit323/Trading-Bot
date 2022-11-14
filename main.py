import threading
import time

import backtesting
import matplotlib
import numpy
import pandas as pd
import talib

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import *


class IBapi (EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.data = []  # Initialize variable to store candle

    # def tickPrice(self, reqId, tickType, price, attrib):
    #    if price > 0:
    #        print("The current asking price is: ", price)

    # def historicalData(self, reqId, bar):
    #    print(f"Time: {bar.date} Close: {bar.close} Low: {bar.low}")
    #    self.data.append([bar.date, bar.close, bar.low])

    """ Code for inputting a trade """

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextorderId = orderId
        print("The next valid order Id is ", self.nextorderId)

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        print('orderStatus - orderid:', orderId, 'status:', status, 'filled',
              filled, 'remaining', remaining, 'lastFillPrice', lastFillPrice)

    def openOrder(self, orderId, contract, order, orderState):
        print('openOrder id:', orderId, contract.symbol, contract.secType, '@', contract.exchange,
              ':', order.action, order.orderType, order.totalQuantity, orderState.status)

    def execDetails(self, reqId, contract, execution):
        print('Order Executed: ', reqId, contract.symbol, contract.secType, contract.currency,
              execution.execId, execution.orderId, execution.shares, execution.lastLiquidity)


def run_loop():
    app.run()


app = IBapi()
app.connect('127.0.0.1', 7497, 1)

app.nextorderId = None

# Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

# Sleep interval to allow time for connection to server
time.sleep(1)


def stock_order(symbol):
    """ Function to create contract object """
    contract = Contract()
    contract.symbol = symbol
    contract.secType = 'STK'
    contract.exchange = 'SMART'
    contract.currency = 'USD'
    return contract


# Check if the API is connected via orderid
while True:
    if isinstance(app.nextorderId, int):
        print("Connected")
        break
    else:
        print("Waiting for a connection")
        time.sleep(1)

# Create order object
order = Order()
order.action = "BUY"
order.totalQuantity = 10
order.orderType = "LMT"
order.lmtPrice = "200"
order.orderId = app.nextorderId
app.nextorderId += 1
order.transmit = False  # Only the last order is True

# Create stop loss order object
stop_order = Order()
stop_order.action = "SELL"
stop_order.totalQuantity = order.totalQuantity
stop_order.orderType = "STP"
stop_order.auxPrice = 190
stop_order.orderId = app.nextorderId
app.nextorderId += 1
stop_order.parentId = order.orderId
order.transmit = False  # Only the last order is True

# Create take profit order object
take_profit = Order()
take_profit.action = "SELL"
take_profit.totalQuantity = order.totalQuantity
take_profit.orderType = "LMT"
take_profit.lmtPrice = 250
take_profit.orderId = app.nextorderId
app.nextorderId += 1
take_profit.parentId = order.orderId
order.transmit = True   # Only the last order is True

# Place orders
app.placeOrder(order.orderId, stock_order("AAPL"), order)
app.placeOrder(stop_order.orderId, stock_order("AAPL"), stop_order)
app.placeOrder(take_profit.orderId, stock_order("AAPL"), take_profit)
#app.nextorderId += 1


# Cancel order
#time.sleep(3)
#print("Canceling order")
#app.cancelOrder(app.nextorderId, "")
#time.sleep(3)


"""
# Request historical candles
# Set False to True for streaming data
app.reqHistoricalData(1, a_contract, "", "1 D",
                      "1 hour", "ASK", 1, 2, False, [])
time.sleep(5)

# Working with Pandas DataFrames
df = pd.DataFrame(
    app.data,
    columns=['DateTime', 'Close', 'Low']
)
df['DateTime'] = pd.to_datetime(df['DateTime'], unit='s')
df.to_csv("Hourly.csv")
print(df)
"""


"""
# Request Market Data
# app.reqMarketDataType(4) # Only required for delayed data
app.reqMktData(1, a_contract, "", False, False, [])
time.sleep(10)  # Sleep interval to allow time for imcoming data
"""

# Discconnect from server
app.disconnect()
