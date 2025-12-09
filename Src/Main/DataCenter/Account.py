

class CAccount:
    def __init__(self, deposit):
        self.cash = deposit
        self.holding_orders = {}
        self.finished_orders = {}

    @property
    def cash(self):
        return self.cash

    def get_holding_order(self):
        return self.holding_orders

    def get_order(self, order_id):
        if order_id in self.holding_orders:
            return self.holding_orders[order_id]
        elif order_id in self.finished_orders:
            return self.finished_orders[order_id]
        return None



if __name__ == '__main__':
    pass