from typing import Tuple

import numpy as np
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget


class ExpectationView(QWidget):
    """全市场预期分布：横轴轮次、纵轴价格、亮度表示该价位上的预期人数。

    数据在模型中已按固定价格桶聚合，因此渲染成本只与桶数有关、与交易者数量无关：
    交易者很少时图形自然退化为散点，数量变大后过渡为密度云。
    叠加的 p10-p90 分位带与中位数线给出共识价位与分歧程度。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 220)
        self._started = False
        self._heat = None
        self._heat_max = 1
        self._band = []
        self._points = []
        self._ipo_price = None
        self._max_round = 100
        self._low = 0.0
        self._high = 1.0
        self._median = None
        self._spread = None
        self._image = None
        self._image_buffer = None
        self._lut = self._build_lut()

    @staticmethod
    def _build_lut() -> np.ndarray:
        """密度到颜色的查找表：深色底 → 蓝 → 亮蓝，贴合现有暗色主题。"""
        stops = np.array([0.0, 0.35, 0.7, 1.0], dtype=np.float64)
        colors = np.array([
            [18, 26, 34],
            [30, 62, 120],
            [70, 120, 220],
            [180, 214, 255],
        ], dtype=np.float64)
        xs = np.linspace(0.0, 1.0, 256)
        channels = [np.interp(xs, stops, colors[:, c]) for c in range(3)]
        return np.stack(channels, axis=1).astype(np.uint8)

    def set_data(self, started: bool, heat, heat_max: int, band, points,
                 ipo_price, max_round: int, low: float, high: float,
                 median, spread):
        self._started = started
        self._heat = heat
        self._heat_max = max(1, int(heat_max or 1))
        self._band = band or []
        self._points = points or []
        self._ipo_price = ipo_price
        self._max_round = max(1, int(max_round or 1))
        self._low = float(low)
        self._high = float(high)
        self._median = median
        self._spread = spread
        self._image = None  # 数据已变化，图像缓存作废
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
            painter.drawText(self.rect(), Qt.AlignCenter, "点击「开始」后，这里会画出所有交易者的预期分布")
            painter.end()
            return

        self._paint_chart(painter)
        painter.end()

    def _paint_chart(self, painter: QPainter):
        width = self.width()
        height = self.height()
        painter.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        painter.setPen(QColor("#e7eef8"))
        painter.drawText(QRectF(16, 10, 200, 24), Qt.AlignVCenter | Qt.AlignLeft, "预期分布")

        if self._median is not None:
            summary = f"预期中位数 {self._median:.0f}"
            if self._spread is not None:
                summary += f" · 分歧 {self._spread:.0f}"
            painter.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            painter.setPen(QColor("#b4d6ff"))
            painter.drawText(QRectF(width - 300, 10, 284, 24), Qt.AlignVCenter | Qt.AlignRight, summary)

        left, top, right, bottom = 58, 46, 18, 36
        plot = QRectF(left, top, width - left - right, height - top - bottom)
        if plot.width() <= 0 or plot.height() <= 0:
            return

        y_min, y_max = self._value_range()
        x_max = float(self._max_round)

        def map_x(x: float) -> float:
            return plot.left() + (x / x_max) * plot.width()

        def map_y(y: float) -> float:
            return plot.bottom() - (y - y_min) / (y_max - y_min) * plot.height()

        painter.setFont(QFont("Microsoft YaHei", 8))
        for value in self._y_ticks(y_min, y_max):
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
        painter.drawText(QRectF(plot.left(), height - 18, plot.width(), 16), Qt.AlignHCenter | Qt.AlignVCenter, "交易轮次")

        self._paint_heat(painter, plot, map_x, y_min, y_max)
        self._paint_overlays(painter, plot, map_x, map_y)

    def _paint_heat(self, painter: QPainter, plot: QRectF, map_x, y_min: float, y_max: float):
        self._ensure_image()
        if self._image is None:
            return
        span = self._high - self._low
        if span <= 0:
            return

        # 把固定分桶的图像裁到当前显示的价格区间，保证与叠加线共用一个 y 映射
        frac_top = min(1.0, max(0.0, (y_max - self._low) / span))
        frac_bottom = min(1.0, max(0.0, (y_min - self._low) / span))
        image_height = self._image.height()
        source = QRectF(
            0.0,
            (1.0 - frac_top) * image_height,
            float(self._image.width()),
            max(1.0, (frac_top - frac_bottom) * image_height),
        )

        # 每列代表一个轮次，列中心对齐轮次刻度（第 r 轮落在 x = r 上）
        target_left = map_x(-0.5)
        target_width = (self._image.width() / float(self._max_round)) * plot.width()

        painter.setClipRect(plot)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(QRectF(target_left, plot.top(), target_width, plot.height()), self._image, source)
        painter.setClipping(False)

    def _paint_overlays(self, painter: QPainter, plot: QRectF, map_x, map_y):
        painter.setClipRect(plot)

        if self._ipo_price is not None:
            ipo_y = map_y(self._ipo_price)
            if plot.top() <= ipo_y <= plot.bottom():
                painter.setPen(QPen(QColor("#f0b90b"), 1, Qt.DashLine))
                painter.drawLine(QPointF(plot.left(), ipo_y), QPointF(plot.right(), ipo_y))

        if len(self._band) >= 2:
            upper = [QPointF(map_x(round_num - 0.5), map_y(p90)) for round_num, _, _, p90 in self._band]
            lower = [QPointF(map_x(round_num - 0.5), map_y(p10)) for round_num, p10, _, _ in reversed(self._band)]
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(91, 140, 255, 48))
            painter.drawPolygon(QPolygonF(upper + lower))

            painter.setPen(QPen(QColor("#b4d6ff"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF([QPointF(map_x(r - 0.5), map_y(median)) for r, _, median, _ in self._band]))

        if len(self._points) >= 2:
            painter.setPen(QPen(QColor(160, 175, 195, 150), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolyline(QPolygonF([QPointF(map_x(x), map_y(y)) for x, y in self._points]))
        painter.setClipping(False)

        if self._band:
            last_round = self._band[-1][0]
            play_x = map_x(last_round - 0.5)
            painter.setPen(QPen(QColor(255, 255, 255, 36), 1, Qt.DashLine))
            painter.drawLine(QPointF(play_x, plot.top()), QPointF(play_x, plot.bottom()))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#b4d6ff"))
            painter.drawEllipse(QPointF(play_x, map_y(self._band[-1][2])), 3.5, 3.5)

    def _value_range(self) -> Tuple[float, float]:
        values = [float(price) for _, price in self._points]
        for _, p10, _, p90 in self._band:
            values.append(p10)
            values.append(p90)
        if self._ipo_price is not None:
            values.append(float(self._ipo_price))
        if self._median is not None:
            values.append(float(self._median))
        if not values:
            return 0.0, 1.0

        y_min, y_max = min(values), max(values)
        if y_max == y_min:
            return y_min - 10.0, y_max + 10.0
        margin = (y_max - y_min) * 0.12
        return y_min - margin, y_max + margin

    def _ensure_image(self):
        if self._image is not None:
            return
        heat = self._heat
        if heat is None:
            return
        heat = np.asarray(heat, dtype=np.float32)
        if heat.ndim != 2 or heat.size == 0:
            return

        # 平方根压缩动态范围，避免少数高密度桶把其余部分压成全黑
        norm = np.sqrt(np.clip(heat / float(self._heat_max), 0.0, 1.0))
        indices = np.clip((norm * 255.0).astype(np.int32), 0, 255)
        rgb = self._lut[indices]                 # (轮次, 价格桶, 3)
        rgb = np.transpose(rgb, (1, 0, 2))       # (价格桶, 轮次, 3)
        rgb = np.ascontiguousarray(rgb[::-1])    # 价格高的桶放在图像上方

        height, width = rgb.shape[0], rgb.shape[1]
        stride = ((width * 3 + 3) // 4) * 4      # QImage 要求扫描行 4 字节对齐
        if stride != width * 3:
            padded = np.zeros((height, stride), dtype=np.uint8)
            padded[:, : width * 3] = rgb.reshape(height, width * 3)
            buffer = padded.tobytes()
        else:
            buffer = rgb.tobytes()

        self._image_buffer = buffer              # QImage 不拷贝数据，必须持有引用
        self._image = QImage(buffer, width, height, stride, QImage.Format_RGB888)

    @staticmethod
    def _y_ticks(y_min: float, y_max: float):
        span = y_max - y_min
        if span <= 8:
            return list(range(int(np.floor(y_min)), int(np.ceil(y_max)) + 1))
        return [y_min + span * index / 4 for index in range(5)]
