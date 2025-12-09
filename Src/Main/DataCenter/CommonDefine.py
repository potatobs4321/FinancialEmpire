from enum import Enum

class OrderStatus(Enum):
    SUBMITTED = 0
    FILLED_ALL = 1
    FILLED_PART = 2
    CANCELED = 2
    CLOSED = 3

