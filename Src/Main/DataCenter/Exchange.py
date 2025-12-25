from Src.Main.DataCenter.Trader import Trader
from Src.Main.DataCenter.OrderBook import OrderBook
from Src.Main.DataCenter.Trade import Trade
from Src.Main.DataCenter.Order import Order
from typing import Dict, List, Optional
from Src.Main.Core.Logger import Logger, LogLevel
from Src.Main.DataCenter.CommonDefine import OrderStatus, OrderSide
import random
from collections import defaultdict


class Exchange:
    def __init__(self):
        self.traders: Dict[str, Trader] = {}
        self.order_books: Dict[str, OrderBook] = {}  # {symbol: OrderBook}
        self.latest_prices: Dict[str, int] = {}  # 最新成交价（整数）
        self.trades: List[Trade] = []
        self.all_orders: Dict[int, Order] = {}  # 所有订单 {order_id: order}
        self.next_order_id = 1
        self.next_trade_id = 1
        # IPO相关
        self.ipo_stocks: Dict[str, int] = {}  # Exchange持有的股票数量 {symbol: quantity}
        self.ipo_prices: Dict[str, int] = {}  # IPO价格（整数） {symbol: price}
        self.ipo_completed: Dict[str, bool] = {}  # IPO是否完成 {symbol: bool}
        self.ipo_applications: Dict[str, dict] = {}  # IPO申购记录 {symbol: {trader_id: {quantity, frozen_cash}}}

    def register_trader(self, trader_id: str, initial_cash: int) -> Trader:
        """注册交易者"""
        trader = Trader(trader_id, initial_cash, self)
        self.traders[trader_id] = trader
        return trader

    def set_initial_price(self, symbol: str, price: int):
        """设置股票初始价格"""
        self.latest_prices[symbol] = price

    def setup_ipo(self, symbol: str, price: int, total_shares: int):
        """设置股票IPO

        Args:
            symbol: 股票代码
            price: IPO价格（整数）
            total_shares: 发行总股数
        """
        self.ipo_stocks[symbol] = total_shares
        self.ipo_prices[symbol] = price
        self.ipo_completed[symbol] = False
        self.latest_prices[symbol] = price
        Logger.write_log(LogLevel.INFO, f"[IPO] {symbol} 发行 {total_shares} 股，IPO价格 {price}")

    def get_ipo_remaining(self, symbol: str) -> int:
        """获取IPO剩余股数"""
        return self.ipo_stocks.get(symbol, 0)

    def is_ipo_completed(self, symbol: str) -> bool:
        """检查IPO是否完成"""
        return self.ipo_completed.get(symbol, True)

    def get_latest_price(self, symbol: str) -> Optional[int]:
        """获取股票最新报价"""
        return self.latest_prices.get(symbol)

    def _get_order_book(self, symbol: str) -> OrderBook:
        """获取或创建订单簿"""
        if symbol not in self.order_books:
            self.order_books[symbol] = OrderBook(symbol)
        return self.order_books[symbol]

    def _validate_order(self, trader: Trader, side: OrderSide, symbol: str,
                        price: int, quantity: int):
        """验证订单有效性"""
        if side == OrderSide.BUY:
            # 检查是否有足够的现金
            required_cash = price * quantity
            if trader.cash < required_cash:
                return False, f"资金不足: 需要 {required_cash}, 可用 {trader.cash}"
        else:  # SELL
            # 检查是否有足够的持仓（不允许做空）
            available = trader.get_position(symbol)
            if available < quantity:
                return False, f"持仓不足: 需要 {quantity}, 可用 {available}"
        return True, "OK"

    def apply_ipo(self, trader_id: str, symbol: str, quantity: int) -> bool:
        """申购IPO股票

        Args:
            trader_id: 交易者ID
            symbol: 股票代码
            quantity: 申购数量

        Returns:
            是否申购成功
        """
        if symbol not in self.ipo_applications:
            self.ipo_applications[symbol] = {}

        trader = self.traders.get(trader_id)
        if not trader:
            return False

        ipo_price = self.ipo_prices.get(symbol, 0)
        if ipo_price <= 0:
            return False

        # 检查资金是否足够
        required_cash = ipo_price * quantity
        if trader.cash < required_cash:
            quantity = trader.cash // ipo_price
            if quantity <= 0:
                return False
            required_cash = ipo_price * quantity

        # 冻结申购资金
        trader.cash -= required_cash

        # 记录申购
        self.ipo_applications[symbol][trader_id] = {
            'quantity': quantity,
            'frozen_cash': required_cash
        }

        # Logger.write_log(LogLevel.INFO, f"[IPO申购] {trader_id} 申购 {symbol} {quantity}股，冻结资金 {required_cash}")
        return True

    def allocate_ipo(self, symbol: str) -> dict:
        """IPO摇号分配

        算法：
        1. 将申购信息打乱顺序
        2. 依次遍历每个申购者
        3. 从 [0, 申购数量] 中随机选取一个数作为中签数量
        4. 如果中签数量超过剩余股数，则只分配剩余股数并结束
        5. 后续申购者将无法中签

        Returns:
            分配结果 {trader_id: allocated_quantity}
        """
        if symbol not in self.ipo_applications:
            return {}

        applications = self.ipo_applications[symbol]
        total_shares = self.ipo_stocks.get(symbol, 0)
        ipo_price = self.ipo_prices.get(symbol, 0)

        if total_shares <= 0 or not applications:
            return {}

        # 计算总申购数量
        total_applied = sum(app['quantity'] for app in applications.values())
        application_multiples = total_applied / total_shares

        Logger.write_log(LogLevel.INFO, f"\n[IPO摇号] {symbol} 开始分配")
        Logger.write_log(LogLevel.INFO, f"  总发行股数: {total_shares}")
        Logger.write_log(LogLevel.INFO, f"  申购人数: {len(applications)}")
        Logger.write_log(LogLevel.INFO, f"  总申购数量: {total_applied}")
        Logger.write_log(LogLevel.INFO, f"  认购倍数: {application_multiples:.2f}x")

        allocation_result = {}
        remaining_shares = total_shares

        if total_applied <= total_shares:
            # 申购不足，全部中签
            Logger.write_log(LogLevel.INFO, f"  申购不足，全部中签")
            for trader_id, app in applications.items():
                allocation_result[trader_id] = app['quantity']
                remaining_shares -= app['quantity']
        else:
            # 超额申购，使用随机抽签算法
            Logger.write_log(LogLevel.INFO, f"  超额申购，进行摇号分配...")

            # 将申购信息转为列表并打乱顺序
            app_list = list(applications.items())
            random.shuffle(app_list)

            # 初始化分配结果
            for trader_id in applications:
                allocation_result[trader_id] = 0

            # 第一轮：依次遍历每个申购者进行随机分配
            for trader_id, app in app_list:
                if remaining_shares <= 0:
                    break

                # 从 [1, upper_qty] 中随机选取中签数量
                applied_qty = app['quantity']
                upper_qty = max(2, int(round(4.0 * applied_qty / application_multiples)))
                allocated = random.randint(1, upper_qty)

                # 不能超过申购数量
                allocated = min(allocated, applied_qty)
                # 不能超过剩余股数
                allocated = min(allocated, remaining_shares)

                allocation_result[trader_id] = allocated
                remaining_shares -= allocated

            # 第二轮：如果还有剩余股票，继续分配给还有申购额度的人
            if remaining_shares > 0:
                Logger.write_log(LogLevel.INFO, f"  第一轮分配后剩余 {remaining_shares} 股，进行补充分配...")

                # 多轮补充分配，直到分完或无法继续分配
                max_rounds = 10  # 防止无限循环
                for round_num in range(max_rounds):
                    if remaining_shares <= 0:
                        break

                    # 找出还有申购额度的人
                    eligible = []
                    for trader_id, app in applications.items():
                        applied_qty = app['quantity']
                        already_got = allocation_result.get(trader_id, 0)
                        remaining_quota = applied_qty - already_got
                        if remaining_quota > 0:
                            eligible.append((trader_id, remaining_quota))

                    if not eligible:
                        break

                    # 打乱顺序后继续分配
                    random.shuffle(eligible)

                    distributed_this_round = 0
                    for trader_id, remaining_quota in eligible:
                        if remaining_shares <= 0:
                            break

                        # 每人分配 1 到 min(剩余额度, 剩余股数) 之间的随机数
                        max_alloc = min(remaining_quota, remaining_shares)
                        additional = random.randint(1, max(1, max_alloc))
                        additional = min(additional, remaining_shares)

                        allocation_result[trader_id] += additional
                        remaining_shares -= additional
                        distributed_this_round += additional

                    if distributed_this_round == 0:
                        break

        # 处理分配结果
        winners = 0
        for trader_id, allocated in allocation_result.items():
            trader = self.traders[trader_id]
            app = applications[trader_id]

            if allocated > 0:
                winners += 1
                # 分配股票
                trader.positions[symbol] += allocated
                # 退还多冻结的资金
                refund = app['frozen_cash'] - (allocated * ipo_price)
                trader.cash += refund

                # 记录成交
                if allocated > 0:
                    order = Order(
                        order_id=self.next_order_id,
                        trader_id=trader_id,
                        symbol=symbol,
                        side=OrderSide.BUY,
                        price=ipo_price,
                        quantity=allocated,
                        filled_quantity=allocated,
                        status=OrderStatus.FILLED
                    )
                    self.all_orders[order.order_id] = order
                    self.next_order_id += 1

                    trade = Trade(
                        trade_id=self.next_trade_id,
                        symbol=symbol,
                        price=ipo_price,
                        quantity=allocated,
                        buyer_id=trader_id,
                        seller_id="EXCHANGE_IPO",
                        buy_order_id=order.order_id,
                        sell_order_id=0
                    )
                    self.trades.append(trade)
                    self.next_trade_id += 1
            else:
                # 未中签，退还全部冻结资金
                trader.cash += app['frozen_cash']

        # 更新IPO状态
        self.ipo_stocks[symbol] = remaining_shares
        if remaining_shares <= 0:
            self.ipo_completed[symbol] = True

        # 统计结果
        total_allocated = sum(allocation_result.values())
        Logger.write_log(LogLevel.INFO, f"\n[IPO分配结果]")
        Logger.write_log(LogLevel.INFO, f"  中签人数: {winners}/{len(applications)} ({winners / len(applications) * 100:.1f}%)")
        Logger.write_log(LogLevel.INFO, f"  分配股数: {total_allocated}/{total_shares}")
        Logger.write_log(LogLevel.INFO, f"  剩余股数: {remaining_shares}")

        # 清理申购记录
        del self.ipo_applications[symbol]

        return allocation_result

    def _buy_from_ipo(self, trader: Trader, symbol: str, price: int, quantity: int) -> Optional[Order]:
        """从IPO购买股票（已废弃，保留兼容性）"""
        # 新的IPO流程使用 apply_ipo 和 allocate_ipo
        return None

    def cancel_order(self, order_id: int) -> bool:
        """撤销订单"""
        order = self.all_orders.get(order_id)
        if not order or not order.is_active():
            return False

        trader = self.traders.get(order.trader_id)
        if not trader:
            return False

        # 退还冻结的资金或持仓
        remaining = order.remaining_quantity
        if order.side == OrderSide.BUY:
            trader.cash += order.price * remaining
        else:
            trader.positions[order.symbol] += remaining

        order.status = OrderStatus.CANCELLED
        Logger.write_log(LogLevel.INFO, f"[撤单] 订单 {order_id}: {order.trader_id} {order.side.value} {order.symbol} {remaining}@{order.price}")

        return True

    def submit_order(self, trader_id: str, symbol: str, side: OrderSide,
                     price: int, quantity: int) -> Order:
        """提交订单"""
        trader = self.traders.get(trader_id)
        if not trader:
            raise ValueError(f"未知的交易者: {trader_id}")

        # 如果是买单且IPO未完成，优先从IPO购买
        if side == OrderSide.BUY and not self.is_ipo_completed(symbol):
            ipo_order = self._buy_from_ipo(trader, symbol, price, quantity)
            if ipo_order:
                return ipo_order
            # 如果IPO买不了（比如没库存了），继续走正常流程

        # 如果是卖单但IPO未完成，拒绝（二级市场还没开放）
        if side == OrderSide.SELL and not self.is_ipo_completed(symbol):
            order = Order(
                order_id=self.next_order_id,
                trader_id=trader_id,
                symbol=symbol,
                side=side,
                price=price,
                quantity=quantity,
                status=OrderStatus.REJECTED
            )
            self.all_orders[order.order_id] = order
            self.next_order_id += 1
            Logger.write_log(LogLevel.INFO, f"[拒绝] 订单 {order.order_id}: IPO未完成，暂不能卖出")
            return order

        # 创建订单
        order = Order(
            order_id=self.next_order_id,
            trader_id=trader_id,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity
        )
        self.all_orders[order.order_id] = order
        self.next_order_id += 1

        # 验证订单
        valid, message = self._validate_order(trader, side, symbol, price, quantity)
        if not valid:
            order.status = OrderStatus.REJECTED
            Logger.write_log(LogLevel.INFO, f"[拒绝] 订单 {order.order_id}: {message}")
            return order

        # 冻结资金或持仓
        if side == OrderSide.BUY:
            trader.cash -= price * quantity
        else:
            trader.positions[symbol] -= quantity

        Logger.write_log(LogLevel.INFO, f"[接受] 订单 {order.order_id}: {trader_id} {side.value} {symbol} {quantity}@{price}")

        # 添加到订单簿
        order_book = self._get_order_book(symbol)
        if side == OrderSide.BUY:
            order_book.add_buy_order(order)
        else:
            order_book.add_sell_order(order)

        # 尝试撮合
        self._match_orders(symbol)

        # 处理未成交的订单（退还资金/持仓）- 只对部分成交的订单处理
        if order.status == OrderStatus.PARTIALLY_FILLED:
            # 部分成交，已经在_match_orders中处理了资金/持仓
            pass

        # 打印摆盘数据
        # self.print_order_book(symbol, 99)

        return order

    def _match_orders(self, symbol: str):
        """撮合订单

        撮合规则：
        - 买价 >= 卖价时可以成交
        - 成交价格以摆盘上先挂的订单价格为准（被动方价格）
        - 同价格的订单按提交时间先后顺序撮合（FIFO，order_id小的优先）
        """
        order_book = self._get_order_book(symbol)

        while True:
            best_buy = order_book.get_best_buy()
            best_sell = order_book.get_best_sell()

            if not best_buy or not best_sell:
                break

            # 检查价格是否匹配（买价 >= 卖价）
            if best_buy.price < best_sell.price:
                break

            # 撮合成交
            trade_quantity = min(best_buy.remaining_quantity, best_sell.remaining_quantity)

            # 成交价格以先挂单的订单价格为准（被动方价格）
            # order_id 小的订单是先提交的（被动方）
            if best_buy.order_id < best_sell.order_id:
                # 买单先挂，用买单价格成交
                trade_price = best_buy.price
            else:
                # 卖单先挂，用卖单价格成交
                trade_price = best_sell.price

            # 更新订单
            best_buy.filled_quantity += trade_quantity
            best_sell.filled_quantity += trade_quantity

            if best_buy.remaining_quantity == 0:
                best_buy.status = OrderStatus.FILLED
                # 清除trader的挂单记录
                buyer = self.traders[best_buy.trader_id]
                if buyer.pending_orders.get(symbol) == best_buy:
                    del buyer.pending_orders[symbol]
            else:
                best_buy.status = OrderStatus.PARTIALLY_FILLED

            if best_sell.remaining_quantity == 0:
                best_sell.status = OrderStatus.FILLED
                # 清除trader的挂单记录
                seller = self.traders[best_sell.trader_id]
                if seller.pending_orders.get(symbol) == best_sell:
                    del seller.pending_orders[symbol]
            else:
                best_sell.status = OrderStatus.PARTIALLY_FILLED

            # 更新交易者账户
            buyer = self.traders[best_buy.trader_id]
            seller = self.traders[best_sell.trader_id]

            # 买方：获得股票，退还多冻结的资金（如果买单价格高于成交价）
            buyer.positions[symbol] += trade_quantity
            price_diff = best_buy.price - trade_price
            buyer.cash += price_diff * trade_quantity

            # 卖方：获得现金
            seller.cash += trade_price * trade_quantity

            # 记录成交
            trade = Trade(
                trade_id=self.next_trade_id,
                symbol=symbol,
                price=trade_price,
                quantity=trade_quantity,
                buyer_id=best_buy.trader_id,
                seller_id=best_sell.trader_id,
                buy_order_id=best_buy.order_id,
                sell_order_id=best_sell.order_id
            )
            self.trades.append(trade)
            self.next_trade_id += 1

            # 更新最新价格
            self.latest_prices[symbol] = trade_price

            Logger.write_log(LogLevel.INFO, f"[成交] 交易 {trade.trade_id}: {symbol} {trade_quantity}@{trade_price} "
                f"(买方:{trade.buyer_id} #{best_buy.order_id}, 卖方:{trade.seller_id} #{best_sell.order_id})")

    def print_order_book(self, symbol: str, depth: int = 5):
        """打印订单簿（摆盘数据）"""
        order_book = self._get_order_book(symbol)
        snapshot = order_book.get_order_book_snapshot(depth)

        latest_price = self.latest_prices.get(symbol, 0)

        Logger.write_log(LogLevel.INFO, f"\n{'=' * 50}")
        Logger.write_log(LogLevel.INFO, f"  {symbol} 摆盘 (最新价: {latest_price})")
        Logger.write_log(LogLevel.INFO, f"{'=' * 50}")
        Logger.write_log(LogLevel.INFO, f"  {'卖盘':<10} {'价格':^10} {'买盘':>10} {'订单队列'}")
        Logger.write_log(LogLevel.INFO, f"  {'-' * 46}")

        asks = snapshot['asks']  # [(price, total_qty, [(order_id, qty), ...]), ...]
        bids = snapshot['bids']

        # 卖盘倒序显示（价格低的在下面，靠近中间）
        for price, total_qty, orders in reversed(asks):
            order_info = ','.join([f"#{oid}:{q}" for oid, q in orders[:3]])
            if len(orders) > 3:
                order_info += "..."
            Logger.write_log(LogLevel.INFO, f"  {total_qty:<10} {price:^10} {'':<10} [{order_info}]")

        if not asks:
            Logger.write_log(LogLevel.INFO, f"  {'--':<10} {'--':^10} {'':<10}")

        Logger.write_log(LogLevel.INFO, f"  {'-' * 46}")

        # 买盘正序显示（价格高的在上面，靠近中间）
        for price, total_qty, orders in bids:
            order_info = ','.join([f"#{oid}:{q}" for oid, q in orders[:3]])
            if len(orders) > 3:
                order_info += "..."
            Logger.write_log(LogLevel.INFO, f"  {'':<10} {price:^10} {total_qty:>10} [{order_info}]")

        if not bids:
            Logger.write_log(LogLevel.INFO, f"  {'':<10} {'--':^10} {'--':>10}")

        Logger.write_log(LogLevel.INFO, f"{'=' * 50}\n")

    def print_status(self):
        """打印交易所状态"""
        Logger.write_log(LogLevel.INFO, "\n" + "=" * 50)
        Logger.write_log(LogLevel.INFO, "交易所状态")
        Logger.write_log(LogLevel.INFO, "=" * 50)
        Logger.write_log(LogLevel.INFO, "\nIPO状态:")
        for symbol in self.ipo_stocks:
            remaining = self.ipo_stocks[symbol]
            completed = "已完成" if self.ipo_completed[symbol] else "进行中"
            Logger.write_log(LogLevel.INFO, f"  {symbol}: 剩余 {remaining} 股 ({completed})")
        Logger.write_log(LogLevel.INFO, "\n最新报价:")
        for symbol, price in self.latest_prices.items():
            Logger.write_log(LogLevel.INFO, f"  {symbol}: {price}")
        Logger.write_log(LogLevel.INFO, "\n交易者账户:")
        for trader in self.traders.values():
            Logger.write_log(LogLevel.INFO, f"  {trader}")
        Logger.write_log(LogLevel.INFO, "=" * 50 + "\n")

    def print_summary(self):
        """打印简要状态"""
        total_cash = sum(t.cash for t in self.traders.values())
        total_positions = defaultdict(int)
        for t in self.traders.values():
            for symbol, qty in t.positions.items():
                total_positions[symbol] += qty

        Logger.write_log(LogLevel.INFO, f"\n[汇总] 总现金: {total_cash}, 总持仓: {dict(total_positions)}, "
            f"成交数: {len(self.trades)}, 最新价: {self.latest_prices}")




if __name__ == '__main__':
    pass