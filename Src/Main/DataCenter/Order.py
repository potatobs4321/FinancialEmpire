from CommonDefine import OrderStatus

class COrder():
    def __init__(self, stock_id, price, qty):
        self.stock_id = stock_id
        self.price = price
        self.qty = qty
        # the status of a new order is always submitted
        self.status = OrderStatus.SUBMITTED
        self.filled_qty = 0
        self.filled_price = 0

    def is_opened(self):
        return self.status == OrderStatus.FILLED_ALL or \
               self.status == OrderStatus.FILLED_PART

    def is_finished(self):
        return self.status == OrderStatus.CANCELED or\
            self.status == OrderStatus.CLOSED
