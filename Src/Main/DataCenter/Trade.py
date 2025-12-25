from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class Trade:
    trade_id: int
    symbol: str
    price: int  # 价格使用整数
    quantity: int
    buyer_id: str
    seller_id: str
    buy_order_id: int
    sell_order_id: int
    timestamp: datetime = field(default_factory=datetime.now)
