from PyQt5.QtCore import QObject
from Account import *
from ..Core.Logger import *

TRADER_ID_START = 10000

class CExchange(QObject):
    trader_accounts = {}
    pending_orders = {}


    @staticmethod
    def create_trader_id():
        global TRADER_ID_START
        TRADER_ID_START += 1
        return TRADER_ID_START


    @classmethod
    def open_account(cls, deposit):
        trader_id = cls.create_trader_id()
        cls.trader_accounts[trader_id] = CAccount(deposit)
        return trader_id


    @classmethod
    def place_order(cls, trader_id, stock_id, price, qty):
        if trader_id not in cls.trader_accounts:
            Logger.write_log(LogLevel.ERROR, "cannot find trader {}".format(trader_id))
            return 0
        if price <= 0:
            Logger.write_log(LogLevel.ERROR, "price must be positive")
            return 0
        if qty == 0:
            Logger.write_log(LogLevel.ERROR, "qty cannot be zero")
            return 0
        trader_account = cls.trader_accounts[trader_id]
        amount = price * qty
        if qty > 0:
            if trader_account.cash < amount:
                Logger.write_log(LogLevel.WARNING, "cash {} < amount {}".format(trader_account.cash, amount))
                return 0
        else:
            trader_orders = trader_account.get_holding_order()
            for order in trader_orders:
                if order.is_opened():
                    pass




if __name__ == '__main__':
    pass