import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np

from Src.Main.DataCenter.Exchange import Exchange
from Src.Main.DataCenter.Trader import Trader


class MarketSimulation:
    """把原来的一次性模拟拆成可逐笔推进的过程，供界面逐帧播放。

    预期价的收集刻意做成"每轮聚合"而不是"逐笔事件流"：每轮只落下一行分位数
    和一个固定分辨率的价格直方图，因此存储与渲染成本都不随交易者数量线性增长，
    交易者数量从几十调到几千都不需要改渲染代码。
    """

    NUM_TRADERS = 20
    IPO_PRICE = 100
    # 发行总股数。留空表示按人均股数随交易者数量自动缩放（见 _total_shares）：
    # 固定股数而只增加交易者数量，会让价格被资金淹没（实测 T=300 时收盘价约 3000）。
    IPO_SHARES: Optional[int] = None
    IPO_SHARES_PER_TRADER = 500
    SYMBOL = "AAPL"
    MAX_ROUNDS = 100
    BOOK_DEPTH = 8

    # 预期分布图的价格分桶范围（相对发行价）。分桶固定才能逐轮增量累加；
    # 范围外的极值会被夹到首尾桶，对整体形态没有影响。
    DENSITY_LOW_RATIO = 0.3
    DENSITY_HIGH_RATIO = 3.0
    DENSITY_BINS = 120

    def __init__(self, num_traders: Optional[int] = None, max_rounds: Optional[int] = None,
                 ipo_price: Optional[int] = None, ipo_shares: Optional[int] = None):
        self.num_traders = int(num_traders) if num_traders else self.NUM_TRADERS
        self.max_rounds = int(max_rounds) if max_rounds else self.MAX_ROUNDS
        if self.num_traders < 1:
            raise ValueError("num_traders 至少为 1")
        if self.max_rounds < 1:
            raise ValueError("max_rounds 至少为 1")

        # 覆盖类常量。必须赶在下面按发行价推算分桶范围之前完成，
        # 否则发行价改了、密度图的价格分桶范围还停留在旧值上。
        if ipo_price:
            self.IPO_PRICE = int(ipo_price)
        if ipo_shares:
            self.IPO_SHARES = int(ipo_shares)

        self.exchange: Optional[Exchange] = None
        self.traders: List[Trader] = []
        self.phase = "idle"  # idle | trading | done
        self.round_num = 0
        self.trader_index = 0
        self.price_points: List[Tuple[float, int]] = []

        # 预期价快照矩阵：行 = 轮次，列 = 交易者的固定编号（0 表示尚无预期）。
        # 注意交易者每轮会被打乱顺序，所以列必须按 trader_id 映射，不能用遍历下标。
        self.expected_matrix = np.zeros((self.max_rounds + 1, self.num_traders), dtype=np.int32)
        # 每轮预期价的分位数 (p10, 中位数, p90)，尚未结算的轮次保持 NaN
        self.expected_stats = np.full((self.max_rounds + 1, 3), np.nan, dtype=np.float64)
        # 每轮的预期价价格直方图：行 = 轮次，列 = 价格桶
        self._density = np.zeros((self.max_rounds + 1, self.DENSITY_BINS), dtype=np.int32)
        self._trader_slots: Dict[str, int] = {}
        self._density_low = float(self.IPO_PRICE) * self.DENSITY_LOW_RATIO
        self._density_high = float(self.IPO_PRICE) * self.DENSITY_HIGH_RATIO
        self._density_edges = np.linspace(self._density_low, self._density_high, self.DENSITY_BINS + 1)

    def start(self):
        """生成交易者、完成 IPO，停在二级市场开盘前。"""
        self.exchange = Exchange()
        self.exchange.setup_ipo(self.SYMBOL, self.IPO_PRICE, self._total_shares())
        self.traders = self._create_traders()
        self._run_ipo()
        # 配售结束即视为发行收官，二级市场开盘。
        # allocate_ipo 只在股票全部配出时才置位，这里显式补齐，
        # 该标记目前仅用于状态展示（Exchange.print_status）。
        self.exchange.ipo_completed[self.SYMBOL] = True
        self.price_points = [(0.0, self.IPO_PRICE)]
        self.expected_matrix[:] = 0
        self.expected_stats[:] = np.nan
        self._density[:] = 0
        self.round_num = 1
        self.trader_index = 0
        random.shuffle(self.traders)
        self.phase = "trading"

    def _total_shares(self) -> int:
        """发行总股数；默认按人均股数随交易者数量等比缩放。

        交易者总现金大致随人数线性增长，如果发行股数固定不变，
        "总现金 / 总股数" 会随人数一起抬升，价格水平被资金推高到失真区间
        （实测：股数固定 10000 时，T=20 收盘价约 80，T=300 约 3000）。
        按人均股数缩放可以让这个比值与人数无关。
        """
        if self.IPO_SHARES:
            return int(self.IPO_SHARES)
        return int(self.IPO_SHARES_PER_TRADER) * self.num_traders

    def step_visible(self) -> bool:
        """向前推进，直到摆盘或价格发生变化，或当前轮结束。

        预期价格没变的交易者不会下单，这些空步会被跳过，避免画面停在原地。
        注意预期价刻意不参与指纹比对：否则几乎每一步都会被视为"有变化"，
        播放会退化成每帧只走一个交易者。
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
                "max_rounds": self.max_rounds,
                "trader_index": 0,
                "trader_count": self.num_traders,
                "latest_price": None,
                "ipo_price": self.IPO_PRICE,
                "trade_count": 0,
                "last_trade": None,
                "bids": [],
                "asks": [],
                "price_points": [],
                "phase": self.phase,
                "started": False,
                "expected_heat": None,
                "expected_heat_max": 1,
                "expected_band": [],
                "expected_low": self._density_low,
                "expected_high": self._density_high,
                "expected_median": None,
                "expected_spread": None,
            }

        book = self.exchange.get_order_book_snapshot(self.SYMBOL, self.BOOK_DEPTH)
        secondary_count = 0
        last_trade = None
        for trade in self.exchange.trades:
            if trade.seller_id == "EXCHANGE_IPO":
                continue
            secondary_count += 1
            last_trade = trade

        # 当前轮尚未结算，这里实时刷新它的密度行，让画面在轮内也能平滑生长
        self._refresh_density(self.round_num)
        stats = self._round_stats(self.round_num)
        median = stats[1] if stats else None
        spread = (stats[2] - stats[0]) if stats else None

        return {
            "symbol": self.SYMBOL,
            "round": self.round_num,
            "max_rounds": self.max_rounds,
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
            "expected_heat": self._density,
            "expected_heat_max": int(self._density.max()),
            "expected_band": self._band_series(),
            "expected_low": self._density_low,
            "expected_high": self._density_high,
            "expected_median": median,
            "expected_spread": spread,
        }

    def _create_traders(self) -> List[Trader]:
        min_cash = 10000
        max_cash = 10000000
        target_mean = 100000
        sigma = 1.0
        mu = math.log(target_mean) - (sigma ** 2) / 2

        traders = []
        self._trader_slots.clear()
        for i in range(self.num_traders):
            while True:
                initial_cash = np.random.lognormal(mean=mu, sigma=sigma)
                initial_cash = int(round(initial_cash / 100) * 100)
                if min_cash <= initial_cash <= max_cash:
                    break
            trader = self.exchange.register_trader(f"Trader_{i:03d}", initial_cash=initial_cash)
            # 固定列号：交易者列表每轮都会被 shuffle，只有这个映射是稳定的
            self._trader_slots[trader.trader_id] = i
            traders.append(trader)
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
            self._finalize_round()
            if self.round_num >= self.max_rounds:
                self.phase = "done"
                return False
            self.round_num += 1
            random.shuffle(self.traders)
            self.trader_index = 0
            # 信念延续：新一轮从上一轮的预期快照出发，再随决策逐步覆盖
            self.expected_matrix[self.round_num] = self.expected_matrix[self.round_num - 1]

        trader = self.traders[self.trader_index]
        trader.make_trading_decision(self.SYMBOL, self.round_num)
        expected = trader.get_expected_price(self.SYMBOL)
        if expected > 0:
            slot = self._trader_slots.get(trader.trader_id)
            if slot is not None:
                self.expected_matrix[self.round_num][slot] = expected
        self.trader_index += 1

        price = self.exchange.get_latest_price(self.SYMBOL) or self.IPO_PRICE
        progress = (self.round_num - 1) + self.trader_index / len(self.traders)
        self.price_points.append((progress, int(price)))

        if self.round_num >= self.max_rounds and self.trader_index >= len(self.traders):
            self._finalize_round()
            self.phase = "done"
        return True

    def _finalize_round(self):
        """结算当前轮：固定该轮的分位数与密度行，此后不再变化。"""
        round_num = self.round_num
        if round_num < 1 or round_num > self.max_rounds:
            return
        self._refresh_density(round_num)
        stats = self._round_stats(round_num)
        if stats is not None:
            self.expected_stats[round_num] = stats

    def _refresh_density(self, round_num: int):
        """把某一轮的预期价重新装桶；只处理一行，成本 O(交易者数)。"""
        if round_num < 1 or round_num > self.max_rounds:
            return
        row = self.expected_matrix[round_num]
        values = row[row > 0]
        if values.size == 0:
            self._density[round_num] = 0
            return
        bins = np.searchsorted(self._density_edges, values, side="right") - 1
        np.clip(bins, 0, self.DENSITY_BINS - 1, out=bins)
        self._density[round_num] = np.bincount(bins, minlength=self.DENSITY_BINS)

    def _round_stats(self, round_num: int) -> Optional[Tuple[float, float, float]]:
        """某一轮预期价的 (p10, 中位数, p90)，无有效数据时返回 None。"""
        if round_num < 1 or round_num > self.max_rounds:
            return None
        row = self.expected_matrix[round_num]
        values = row[row > 0]
        if values.size == 0:
            return None
        p10, median, p90 = np.percentile(values, [10, 50, 90])
        return float(p10), float(median), float(p90)

    def _band_series(self) -> List[Tuple[int, float, float, float]]:
        """分位带数据：已结算轮次取缓存值，当前轮实时计算。"""
        band: List[Tuple[int, float, float, float]] = []
        for round_num in range(1, self.round_num):
            p10, median, p90 = self.expected_stats[round_num]
            if np.isnan(median):
                continue
            band.append((round_num, float(p10), float(median), float(p90)))
        live = self._round_stats(self.round_num)
        if live is not None:
            band.append((self.round_num, live[0], live[1], live[2]))
        return band

    def _fingerprint(self) -> tuple:
        price = self.exchange.get_latest_price(self.SYMBOL)
        book = self.exchange.get_order_book_snapshot(self.SYMBOL, self.BOOK_DEPTH)
        bids = tuple((price_level, qty, len(orders)) for price_level, qty, orders in book["bids"])
        asks = tuple((price_level, qty, len(orders)) for price_level, qty, orders in book["asks"])
        return price, bids, asks
