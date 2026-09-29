from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget


class OrderBookView(QWidget):
    """买卖盘深度。卖盘在上、买盘在下，最优价贴着中间的最新价。"""

    LEVELS = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 420)
        self._started = False
        self._symbol = ""
        self._latest_price = None
        self._ipo_price = None
        self._bids = []
        self._asks = []

    def set_book(self, started: bool, symbol: str, latest_price, ipo_price, bids, asks):
        self._started = started
        self._symbol = symbol
        self._latest_price = latest_price
        self._ipo_price = ipo_price
        self._bids = bids or []
        self._asks = asks or []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#121a22"))
        painter.setPen(QPen(QColor("#243140"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if not self._started:
            painter.setPen(QColor("#8b9bb0"))
            painter.setFont(QFont("Microsoft YaHei", 11))
            painter.drawText(self.rect(), Qt.AlignCenter, "点击「开始」后，这里会逐笔刷新摆盘")
            painter.end()
            return

        self._paint_book(painter)
        painter.end()

    def _paint_book(self, painter: QPainter):
        width = self.width()
        height = self.height()
        painter.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        painter.setPen(QColor("#e7eef8"))
        painter.drawText(QRectF(16, 10, width * 0.45, 24), Qt.AlignVCenter | Qt.AlignLeft, f"{self._symbol} 摆盘")

        legend_font = QFont("Microsoft YaHei", 9)
        painter.setFont(legend_font)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f6465d"))
        painter.drawRoundedRect(QRectF(width - 168, 16, 10, 10), 2, 2)
        painter.setBrush(QColor("#16c784"))
        painter.drawRoundedRect(QRectF(width - 78, 16, 10, 10), 2, 2)
        painter.setPen(QColor("#9aabbd"))
        painter.drawText(QRectF(width - 154, 10, 70, 22), Qt.AlignVCenter | Qt.AlignLeft, "买盘")
        painter.drawText(QRectF(width - 64, 10, 52, 22), Qt.AlignVCenter | Qt.AlignLeft, "卖盘")

        ask_rows = [None] * self.LEVELS
        for index, level in enumerate(self._asks[:self.LEVELS]):
            ask_rows[self.LEVELS - 1 - index] = level
        bid_rows = [None] * self.LEVELS
        for index, level in enumerate(self._bids[:self.LEVELS]):
            bid_rows[index] = level

        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.setPen(QColor("#7f90a3"))
        painter.drawText(QRectF(16, 34, 72, 16), Qt.AlignRight | Qt.AlignVCenter, "价格")
        painter.drawText(QRectF(88, 34, 78, 16), Qt.AlignRight | Qt.AlignVCenter, "数量")

        header_h = 56
        footer = 10
        mid_h = 46
        levels_h = height - header_h - footer - mid_h
        row_h = levels_h / (self.LEVELS * 2)

        quantities = [level[1] for level in ask_rows + bid_rows if level]
        max_qty = max(quantities) if quantities else 1

        top = header_h
        for level in ask_rows:
            self._paint_level(painter, level, top, row_h, max_qty, "ask")
            top += row_h
        self._paint_mid(painter, top, mid_h)
        top += mid_h
        for level in bid_rows:
            self._paint_level(painter, level, top, row_h, max_qty, "bid")
            top += row_h

    def _paint_level(self, painter: QPainter, level, top: float, row_h: float, max_qty: int, side: str):
        width = self.width()
        row = QRectF(8, top, width - 16, row_h)
        tint = QColor("#10241c") if side == "ask" else QColor("#241418")
        painter.fillRect(row, tint)

        price_rect = QRectF(row.left() + 8, row.top(), 72, row.height())
        qty_rect = QRectF(price_rect.right(), row.top(), 78, row.height())
        bar_rect = QRectF(qty_rect.right() + 8, row.top() + 5, row.right() - qty_rect.right() - 16, row.height() - 10)

        if bar_rect.width() > 0 and bar_rect.height() > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#1c2733"))
            painter.drawRoundedRect(bar_rect, 3, 3)

        if level is None:
            painter.setPen(QColor("#4d5d6e"))
            painter.setFont(QFont("Microsoft YaHei", 9))
            painter.drawText(price_rect, Qt.AlignVCenter | Qt.AlignRight, "—")
            return

        price, qty = level[0], level[1]
        color = QColor("#16c784") if side == "ask" else QColor("#f6465d")
        if bar_rect.width() > 0 and bar_rect.height() > 0 and max_qty > 0:
            bar_w = max(2.0, bar_rect.width() * qty / max_qty)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(bar_rect.left(), bar_rect.top(), bar_w, bar_rect.height()), 3, 3)

        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(color)
        painter.drawText(price_rect, Qt.AlignVCenter | Qt.AlignRight, str(price))
        painter.setPen(QColor("#d5deea"))
        painter.drawText(qty_rect, Qt.AlignVCenter | Qt.AlignRight, f"{qty:,}")

    def _paint_mid(self, painter: QPainter, top: float, mid_h: float):
        row = QRectF(8, top, self.width() - 16, mid_h)
        painter.fillRect(row, QColor("#1b2836"))

        latest = self._latest_price
        ipo = self._ipo_price
        if latest is None:
            price_text = "—"
            delta_text = ""
            color = QColor("#e7eef8")
        else:
            price_text = str(latest)
            delta = latest - ipo if ipo is not None else 0
            if delta > 0:
                color = QColor("#f6465d")
                delta_text = f"较发行 +{delta}"
            elif delta < 0:
                color = QColor("#16c784")
                delta_text = f"较发行 {delta}"
            else:
                color = QColor("#e7eef8")
                delta_text = "较发行 0"

        best_ask = self._asks[0][0] if self._asks else None
        best_bid = self._bids[0][0] if self._bids else None
        spread_text = f"价差 {best_ask - best_bid}" if best_ask is not None and best_bid is not None else "价差 —"

        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QColor("#9aabbd"))
        painter.drawText(QRectF(row.left() + 12, row.top(), 64, row.height()), Qt.AlignVCenter | Qt.AlignLeft, "最新价")
        painter.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        painter.setPen(color)
        painter.drawText(QRectF(row.left() + 76, row.top(), 88, row.height()), Qt.AlignVCenter | Qt.AlignLeft, price_text)
        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QColor("#9aabbd"))
        painter.drawText(
            QRectF(row.left() + 168, row.top(), row.width() - 180, row.height()),
            Qt.AlignVCenter | Qt.AlignRight,
            f"{spread_text}    {delta_text}",
        )
