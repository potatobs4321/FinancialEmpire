from .CommonDefine import OrderStatus, OrderSide
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class Order:
    order_id: int
    trader_id: str
    symbol: str
    side: OrderSide
    price: int  # 价格使用整数，避免浮点精度问题
    quantity: int
    filled_quantity: int = 0
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def remaining_quantity(self) -> int:
        return self.quantity - self.filled_quantity

    def is_active(self) -> bool:
        """订单是否仍然活跃（可以被撮合或撤销）"""
        return self.status in [OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED] and self.remaining_quantity > 0
