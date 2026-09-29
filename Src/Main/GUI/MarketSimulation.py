import math
import random
from typing import List, Optional, Tuple

import numpy as np

from Src.Main.DataCenter.Exchange import Exchange
from Src.Main.DataCenter.Trader import Trader


class MarketSimulation:
    """把原来的一次性模拟拆成可逐笔推进的过程，供界面逐帧播放。"""

    NUM_TRADERS = 20
    IPO_PRICE = 100
    IPO_SHARES = 10000
    SYMBOL = "AAPL"
    MAX_ROUNDS = 100
    BOOK_DEPTH = 8

    def __init__(self):
        self.exchange: Optional[Exchange] = None
        self.traders: List[Trader] = []
        self.phase = "idle"  # idle | trading | done
        self.round_num = 0
        self.trader_index = 0
        self.price_points: List[Tuple[float, int]] = []

    def start(self):
        """生成交易者、完成 IPO，停在二级市场开盘前。"""
        self.exchange = Exchange()
        self.exchange.setup_ipo(self.SYMBOL, self.IPO_PRICE, self.IPO_SHARES)
        self.traders = self._create_traders()
        self._run_ipo()
        self.exchange.ipo_completed[self.SYMBOL] = True
        self.price_points = [(0.0, self.IPO_PRICE)]
        self.round_num = 1
        self.trader_index = 0
        random.shuffle(self.traders)
        self.phase = "trading"

    def step_visible(self) -> bool:
        """向前推进，直到摆盘或价格发生变化，或当前轮结束。

        预期价格没变的交易者不会下单，这些空步会被跳过，避免画面停在原地。
        """
        if self.phase != "trading":
            return False

        while self.phase == "trading":
            before = self._fingerprint()
            if not self._advance_one():
                return False
            end_of_round = self.trader_index >= len(self.traders)
            if before != self._fingerprint() or end_of_round:
                return True
        return False

    def snapshot(self) -> dict:
        if self.exchange is None:
            return {
                "symbol": self.SYMBOL,
                "round": 0,
                "max_rounds": self.MAX_ROUNDS,
                "trader_index": 0,
                "trader_count": self.NUM_TRADERS,
                "latest_price": None,
                "ipo_price": self.IPO_PRICE,
                "trade_count": 0,
                "last_trade": None,
                "bids": [],
                "asks": [],
                "price_points": [],
                "phase": self.phase,
                "started": False,
            }

        book = self.exchange.get_order_book_snapshot(self.SYMBOL, self.BOOK_DEPTH)
        secondary_count = 0
        last_trade = None
        for trade in self.exchange.trades:
            if trade.seller_id == "EXCHANGE_IPO":
                continue
            secondary_count += 1
            last_trade = trade

        return {
            "symbol": self.SYMBOL,
            "round": self.round_num,
            "max_rounds": self.MAX_ROUNDS,
            "trader_index": self.trader_index,
            "trader_count": len(self.traders),
            "latest_price": self.exchange.get_latest_price(self.SYMBOL),
            "ipo_price": self.IPO_PRICE,
            "trade_count": secondary_count,
            "last_trade": last_trade,
            "bids": book["bids"],
            "asks": book["asks"],
            "price_points": list(self.price_points),
            "phase": self.phase,
            "started": True,
        }

    def _create_traders(self) -> List[Trader]:
        min_cash = 10000
        max_cash = 10000000
        target_mean = 100000
        sigma = 1.0
        mu = math.log(target_mean) - (sigma ** 2) / 2

        traders = []
        for i in range(self.NUM_TRADERS):
            while True:
                initial_cash = np.random.lognormal(mean=mu, sigma=sigma)
                initial_cash = int(round(initial_cash / 100) * 100)
                if min_cash <= initial_cash <= max_cash:
                    break
            traders.append(self.exchange.register_trader(f"Trader_{i:03d}", initial_cash=initial_cash))
        return traders

    def _run_ipo(self):
        for trader in self.traders:
            buy_ratio = random.uniform(0.5, 0.8)
            buy_amount = int(round(trader.cash * buy_ratio))
            quantity = buy_amount // self.IPO_PRICE
            if quantity > 0:
                self.exchange.apply_ipo(trader.trader_id, self.SYMBOL, quantity)
        self.exchange.allocate_ipo(self.SYMBOL)

    def _advance_one(self) -> bool:
        if self.phase != "trading" or self.exchange is None:
            return False

        if self.trader_index >= len(self.traders):
            if self.round_num >= self.MAX_ROUNDS:
                self.phase = "done"
                return False
            self.round_num += 1
            random.shuffle(self.traders)
            self.trader_index = 0

        trader = self.traders[self.trader_index]
        trader.make_trading_decision(self.SYMBOL, self.round_num)
        self.trader_index += 1

        price = self.exchange.get_latest_price(self.SYMBOL) or self.IPO_PRICE
        progress = (self.round_num - 1) + self.trader_index / len(self.traders)
        self.price_points.append((progress, int(price)))

        if self.round_num >= self.MAX_ROUNDS and self.trader_index >= len(self.traders):
            self.phase = "done"
        return True

    def _fingerprint(self) -> tuple:
        price = self.exchange.get_latest_price(self.SYMBOL)
        book = self.exchange.get_order_book_snapshot(self.SYMBOL, self.BOOK_DEPTH)
        bids = tuple((price_level, qty, len(orders)) for price_level, qty, orders in book["bids"])
        asks = tuple((price_level, qty, len(orders)) for price_level, qty, orders in book["asks"])
        return price, bids, asks
