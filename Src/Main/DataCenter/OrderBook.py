import heapq
from typing import Dict, List, Optional
from collections import defaultdict
from Src.Main.DataCenter.Order import Order


class OrderBook:
    """订单簿 - 管理某只股票的买卖订单"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        # 买单：价格高的优先（使用负数实现最大堆）
        # 使用 order_id 作为第二排序键，避免 Order 对象直接比较
        self.buy_orders: List[tuple] = []  # (-price, order_id, order)
        # 卖单：价格低的优先（最小堆）
        self.sell_orders: List[tuple] = []  # (price, order_id, order)

    def add_buy_order(self, order: Order):
        heapq.heappush(self.buy_orders, (-order.price, order.order_id, order))

    def add_sell_order(self, order: Order):
        heapq.heappush(self.sell_orders, (order.price, order.order_id, order))

    def get_best_buy(self) -> Optional[Order]:
        """获取最高买价订单"""
        while self.buy_orders:
            _, _, order = self.buy_orders[0]
            if order.is_active():
                return order
            heapq.heappop(self.buy_orders)
        return None

    def get_best_sell(self) -> Optional[Order]:
        """获取最低卖价订单"""
        while self.sell_orders:
            _, _, order = self.sell_orders[0]
            if order.is_active():
                return order
            heapq.heappop(self.sell_orders)
        return None

    def get_order_book_snapshot(self, depth: int = 5) -> dict:
        """获取订单簿快照（摆盘数据）

        Args:
            depth: 显示的档位数

        Returns:
            {'bids': [(price, quantity, [(order_id, qty), ...]), ...],
             'asks': [(price, quantity, [(order_id, qty), ...]), ...]}
        """
        # 汇总买单（按价格聚合，同时记录每个订单的信息用于FIFO显示）
        buy_prices: Dict[int, List[tuple]] = defaultdict(list)
        for _, order_id, order in self.buy_orders:
            if order.is_active():
                buy_prices[order.price].append((order_id, order.remaining_quantity))

        # 汇总卖单（按价格聚合）
        sell_prices: Dict[int, List[tuple]] = defaultdict(list)
        for _, order_id, order in self.sell_orders:
            if order.is_active():
                sell_prices[order.price].append((order_id, order.remaining_quantity))

        # 排序：买单价格从高到低，卖单价格从低到高
        # 每个价位内的订单按order_id排序（FIFO）
        bids = []
        for price in sorted(buy_prices.keys(), reverse=True)[:depth]:
            orders = sorted(buy_prices[price], key=lambda x: x[0])  # 按order_id排序
            total_qty = sum(qty for _, qty in orders)
            bids.append((price, total_qty, orders))

        asks = []
        for price in sorted(sell_prices.keys())[:depth]:
            orders = sorted(sell_prices[price], key=lambda x: x[0])  # 按order_id排序
            total_qty = sum(qty for _, qty in orders)
            asks.append((price, total_qty, orders))

        return {'bids': bids, 'asks': asks}