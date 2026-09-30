import math

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget


class PriceChartView(QWidget):
    """价格随交易轮次向右延伸，播放头标出当前进度。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 220)
        self._started = False
        self._points = []
        self._ipo_price = None
        self._max_round = 100

    def set_series(self, started: bool, points, ipo_price, max_round: int):
        self._started = started
        self._points = points or []
        self._ipo_price = ipo_price
        self._max_round = max(1, max_round)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#121a22"))
        painter.setPen(QPen(QColor("#243140"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if not self._started or not self._points:
            painter.setPen(QColor("#8b9bb0"))
            painter.setFont(QFont("Microsoft YaHei", 11))
            painter.drawText(self.rect(), Qt.AlignCenter, "点击「开始」后，这里会画出价格曲线")
            painter.end()
            return

        self._paint_chart(painter)
        painter.end()

    def _paint_chart(self, painter: QPainter):
        width = self.width()
        height = self.height()
        painter.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        painter.setPen(QColor("#e7eef8"))
        painter.drawText(QRectF(16, 10, 160, 24), Qt.AlignVCenter | Qt.AlignLeft, "价格走势")

        latest = self._points[-1][1]
        direction = 0
        previous = self._points[0][1]
        for _, price in self._points[1:]:
            if price != previous:
                direction = 1 if price > previous else -1
            previous = price
        if direction > 0:
            latest_color = QColor("#f6465d")
        elif direction < 0:
            latest_color = QColor("#16c784")
        else:
            latest_color = QColor("#e7eef8")
        painter.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        painter.setPen(latest_color)
        painter.drawText(QRectF(width - 180, 10, 164, 24), Qt.AlignVCenter | Qt.AlignRight, f"最新 {latest}")

        left, top, right, bottom = 58, 46, 18, 36
        plot = QRectF(left, top, width - left - right, height - top - bottom)
        if plot.width() <= 0 or plot.height() <= 0:
            return

        prices = [price for _, price in self._points]
        if self._ipo_price is not None:
            prices.append(self._ipo_price)
        y_min = min(prices)
        y_max = max(prices)
        if y_max == y_min:
            y_min -= 10
            y_max += 10
        else:
            margin = (y_max - y_min) * 0.12
            y_min -= margin
            y_max += margin
        x_max = float(self._max_round)

        def map_x(x: float) -> float:
            return plot.left() + (x / x_max) * plot.width()

        def map_y(y: float) -> float:
            return plot.bottom() - (y - y_min) / (y_max - y_min) * plot.height()

        painter.setFont(QFont("Microsoft YaHei", 8))
        ticks = self._y_ticks(y_min, y_max)
        for value in ticks:
            y = map_y(value)
            painter.setPen(QPen(QColor("#243140"), 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QColor("#7f90a3"))
            painter.drawText(QRectF(4, y - 8, left - 10, 16), Qt.AlignRight | Qt.AlignVCenter, str(int(round(value))))

        for index in range(5):
            x_value = x_max * index / 4
            x = map_x(x_value)
            painter.setPen(QColor("#7f90a3"))
            painter.drawText(QRectF(x - 24, plot.bottom() + 6, 48, 18), Qt.AlignHCenter | Qt.AlignTop, str(int(round(x_value))))

        painter.setPen(QColor("#7f90a3"))
        painter.drawText(QRectF(plot.left(), height - 18, plot.width(), 16), Qt.AlignHCenter | Qt.AlignVCenter, "交易轮次")

        if self._ipo_price is not None:
            ipo_y = map_y(self._ipo_price)
            ipo_pen = QPen(QColor("#f0b90b"), 1, Qt.DashLine)
            painter.setPen(ipo_pen)
            painter.drawLine(QPointF(plot.left(), ipo_y), QPointF(plot.right(), ipo_y))
            painter.setFont(QFont("Microsoft YaHei", 8))
            painter.drawText(QRectF(plot.right() - 72, ipo_y - 16, 70, 14), Qt.AlignRight | Qt.AlignVCenter, f"IPO {self._ipo_price}")

        play_x = map_x(self._points[-1][0])
        painter.setPen(QPen(QColor(255, 255, 255, 36), 1, Qt.DashLine))
        painter.drawLine(QPointF(play_x, plot.top()), QPointF(play_x, plot.bottom()))

        painter.setClipRect(plot)
        polygon = QPolygonF([QPointF(map_x(x), map_y(y)) for x, y in self._points])
        if len(self._points) >= 2:
            fill = QPolygonF(polygon)
            fill.append(QPointF(map_x(self._points[-1][0]), plot.bottom()))
            fill.append(QPointF(map_x(self._points[0][0]), plot.bottom()))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(91, 140, 255, 42))
            painter.drawPolygon(fill)

        line_pen = QPen(QColor("#5b8cff"), 2)
        line_pen.setCapStyle(Qt.RoundCap)
        line_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(line_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolyline(polygon)

        last_x, last_y = self._points[-1]
        painter.setPen(Qt.NoPen)
        painter.setBrush(latest_color)
        painter.drawEllipse(QPointF(map_x(last_x), map_y(last_y)), 4.0, 4.0)
        painter.setClipping(False)

    @staticmethod
    def _y_ticks(y_min: float, y_max: float):
        span = y_max - y_min
        if span <= 8:
            start = math.floor(y_min)
            end = math.ceil(y_max)
            return list(range(start, end + 1))
        return [y_min + span * index / 4 for index in range(5)]
