from .Order import Order
from typing import Dict, List, Optional
from collections import defaultdict
import random
from ..Core.Logger import Logger, LogLevel
from .CommonDefine import OrderStatus, OrderSide


class Trader:
    def __init__(self, trader_id: str, cash: int, exchange: 'Exchange'):
        self.trader_id = trader_id
        self.cash = cash  # 现金余额（整数）
        self.positions: Dict[str, int] = defaultdict(int)  # 持仓 {symbol: quantity}
        self.exchange = exchange
        self.orders: List[Order] = []
        self.expected_prices: Dict[str, int] = {}  # 对各股票价格的预期 {symbol: expected_price}
        self.expected_price_update_round: Dict[str, int] = {}  # 预期价格上次更新的轮次 {symbol: round}
        self.expected_price_interval: Dict[str, int] = {}  # 预期价格更新间隔 {symbol: interval}
        self.pending_orders: Dict[str, Order] = {}  # 当前挂单 {symbol: order}

    def get_position(self, symbol: str) -> int:
        """获取某只股票的持仓数量"""
        return self.positions.get(symbol, 0)

    def get_latest_price(self, symbol: str) -> Optional[int]:
        """获取股票最新报价"""
        return self.exchange.get_latest_price(symbol)

    def get_expected_price(self, symbol: str) -> int:
        """获取对某只股票价格的预期（已缓存的值）"""
        return self.expected_prices.get(symbol, 0)

    def update_expected_price(self, symbol: str, current_round: int) -> tuple:
        """更新对某只股票价格的预期（每隔3-5轮更新一次）

        Args:
            symbol: 股票代码
            current_round: 当前轮次

        Returns:
            (更新后的预期价格, 是否发生了变更)
        """
        last_update = self.expected_price_update_round.get(symbol, -999)
        interval = self.expected_price_interval.get(symbol, 0)
        old_expected = self.expected_prices.get(symbol, 0)

        # 检查是否需要更新预期价格
        if current_round - last_update >= interval:
            latest_price = self.get_latest_price(symbol)
            if latest_price is None or latest_price <= 0:
                return (old_expected, False)

            # 预期价格在最新价的 ±10% 范围内随机波动
            fluctuation = random.uniform(-0.10, 0.10)
            expected = int((latest_price * (1 + fluctuation)))
            # 确保预期价格至少为1
            expected = max(1, expected)
            Logger.write_log(LogLevel.INFO, f"[TRADER] {symbol} 当前价格： {latest_price} ，预期价格 {expected}")

            # 保存预期价格和更新信息
            self.expected_prices[symbol] = expected
            self.expected_price_update_round[symbol] = current_round
            self.expected_price_interval[symbol] = random.randint(1, 5)  # 下次更新间隔3-5轮

            return (expected, expected != old_expected)

        return (old_expected, False)

    def get_active_pending_order(self, symbol: str) -> Optional[Order]:
        """获取某只股票的活跃挂单"""
        order = self.pending_orders.get(symbol)
        if order and order.is_active():
            return order
        return None

    def make_trading_decision(self, symbol: str, current_round: int):
        """根据预期价格做出交易决策

        Args:
            symbol: 股票代码
            current_round: 当前轮次

        交易逻辑：
        - 只在预期价格变更时才进行交易操作
        - 无持仓时：
            - 看涨（预期 > 最新价）：以最新价下买单（急于买入）
            - 看跌（预期 < 最新价）：以预期价挂低点买单（等待低价买入）
        - 有持仓时：
            - 看跌（预期 < 最新价）：以最新价下卖单（急于卖出）
            - 看涨（预期 > 最新价）：以预期价挂高点卖单（等待高价卖出）
        """
        latest_price = self.get_latest_price(symbol)
        if latest_price is None or latest_price <= 0:
            return

        # 更新预期价格（每隔1-5轮更新一次）
        expected_price, price_changed = self.update_expected_price(symbol, current_round)
        if expected_price <= 0:
            return

        # 只有预期价格变更时才做交易决策
        if not price_changed:
            return

        position = self.get_position(symbol)
        pending_order = self.get_active_pending_order(symbol)

        # 确定交易方向、价格和数量
        target_side = None
        order_price = 0
        target_quantity = 0

        if position == 0:
            # 没有持仓，准备买入
            if expected_price > latest_price:
                # 看涨：以预期价下买单（愿意出高价买入）
                target_side = OrderSide.BUY
                order_price = expected_price
                Logger.write_log(LogLevel.INFO, f"[决策] {self.trader_id} 看涨，愿出高价 {order_price} 买入")
            else:
                # 看跌：以预期价挂低点买单（等待低价机会）
                target_side = OrderSide.BUY
                order_price = expected_price
                Logger.write_log(LogLevel.INFO, f"[决策] {self.trader_id} 看跌，挂低价 {order_price} 买单等待")

            # 计算可买数量（需要考虑已冻结的资金）
            available_cash = self.cash
            if pending_order and pending_order.side == OrderSide.BUY:
                available_cash += pending_order.price * pending_order.remaining_quantity
            max_quantity = available_cash // order_price
            if max_quantity <= 0:
                return
            target_quantity = max_quantity
        else:
            # 有持仓，准备卖出
            if expected_price < latest_price:
                # 看跌：以预期价下卖单（愿意低价卖出）
                target_side = OrderSide.SELL
                order_price = expected_price
                Logger.write_log(LogLevel.INFO, f"[决策] {self.trader_id} 看跌，愿低价 {order_price} 卖出")
            else:
                # 看涨：以预期价挂高点卖单（等待高价机会）
                target_side = OrderSide.SELL
                order_price = expected_price
                Logger.write_log(LogLevel.INFO, f"[决策] {self.trader_id} 看涨，挂高价 {order_price} 卖单等待")

            # 计算可卖数量（需要考虑已冻结的持仓）
            available_position = position
            if pending_order and pending_order.side == OrderSide.SELL:
                available_position += pending_order.remaining_quantity
            if available_position <= 0:
                return
            target_quantity = available_position

        # 检查是否需要调整挂单
        if pending_order:
            if pending_order.side == target_side and pending_order.price == order_price:
                # 挂单价格一致，不需要操作
                return
            else:
                # 挂单价格不一致或方向不对，撤单
                self.cancel_order(symbol)

        # 下新单
        if target_side == OrderSide.BUY:
            self.buy(symbol, order_price, target_quantity)
        else:
            self.sell(symbol, order_price, target_quantity)

    def cancel_order(self, symbol: str) -> bool:
        """撤销某只股票的挂单"""
        order = self.pending_orders.get(symbol)
        if order and order.is_active():
            result = self.exchange.cancel_order(order.order_id)
            if result:
                del self.pending_orders[symbol]
            return result
        return False

    def buy(self, symbol: str, price: int, quantity: int) -> Order:
        """下买单"""
        order = self.exchange.submit_order(
            trader_id=self.trader_id,
            symbol=symbol,
            side=OrderSide.BUY,
            price=price,
            quantity=quantity
        )
        self.orders.append(order)
        # 如果订单被接受且有剩余数量，记录为挂单
        if order.is_active():
            self.pending_orders[symbol] = order
        elif symbol in self.pending_orders:
            del self.pending_orders[symbol]
        return order

    def sell(self, symbol: str, price: int, quantity: int) -> Order:
        """下卖单"""
        order = self.exchange.submit_order(
            trader_id=self.trader_id,
            symbol=symbol,
            side=OrderSide.SELL,
            price=price,
            quantity=quantity
        )
        self.orders.append(order)
        # 如果订单被接受且有剩余数量，记录为挂单
        if order.is_active():
            self.pending_orders[symbol] = order
        elif symbol in self.pending_orders:
            del self.pending_orders[symbol]
        return order

    def __repr__(self):
        return f"Trader({self.trader_id}, cash={self.cash}, positions={dict(self.positions)})"