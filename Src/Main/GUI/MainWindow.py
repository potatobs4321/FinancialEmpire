from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from Src.Main.Core.Logger import Logger
from Src.Main.GUI.MarketSimulation import MarketSimulation
from Src.Main.GUI.OrderBookView import OrderBookView
from Src.Main.GUI.PriceChartView import PriceChartView


class MainWindow(QMainWindow):
    """交易模拟播放窗口：左侧实时摆盘，右侧价格曲线。"""

    FRAME_MS = 80

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FinancialEmpire 交易模拟")
        self.resize(1180, 760)
        self.sim = MarketSimulation()

        self.timer = QTimer(self)
        self.timer.setInterval(self.FRAME_MS)
        self.timer.timeout.connect(self._on_tick)

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.btn_start = QPushButton("开始")
        self.btn_start.setObjectName("startButton")
        self.btn_pause = QPushButton("暂停")
        self.btn_reset = QPushButton("重置")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_start.setToolTip("开始播放，或从暂停处继续")
        self.btn_pause.setToolTip("停在当前这一笔")
        self.btn_reset.setToolTip("重新生成交易者，从头再跑一遍")

        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(1, 8)
        self.speed.setValue(1)
        self.speed.setFixedWidth(150)
        self.speed.setToolTip("每个刷新周期向前推进的变化次数")
        self.lbl_speed = QLabel("速度 1x")
        self.speed.valueChanged.connect(self._on_speed)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setObjectName("statusLabel")

        controls.addWidget(self.btn_start)
        controls.addWidget(self.btn_pause)
        controls.addWidget(self.btn_reset)
        controls.addSpacing(12)
        controls.addWidget(self.lbl_speed)
        controls.addWidget(self.speed)
        controls.addStretch(1)
        controls.addWidget(self.lbl_status)

        stats = QHBoxLayout()
        stats.setSpacing(18)
        self.lbl_round = QLabel()
        self.lbl_price = QLabel()
        self.lbl_price.setObjectName("priceLabel")
        self.lbl_trades = QLabel()
        self.lbl_last = QLabel()
        for label in (self.lbl_round, self.lbl_price, self.lbl_trades, self.lbl_last):
            stats.addWidget(label)
        stats.addStretch(1)

        self.order_book = OrderBookView()
        self.price_chart = PriceChartView()
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.order_book)
        splitter.addWidget(self.price_chart)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root.addLayout(controls)
        root.addLayout(stats)
        root.addWidget(splitter, 1)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #0e141b;
                color: #d7dee8;
                font-family: "Microsoft YaHei";
                font-size: 13px;
            }
            QLabel#priceLabel { font-size: 18px; font-weight: 600; }
            QLabel#statusLabel { color: #8b9bb0; }
            QPushButton {
                background: #1c2836;
                border: 1px solid #314154;
                border-radius: 4px;
                padding: 6px 16px;
                color: #e8eef6;
                min-height: 18px;
            }
            QPushButton:hover { background: #243447; }
            QPushButton:disabled { color: #66788a; background: #17202a; }
            QPushButton#startButton {
                background: #1f6f4a;
                border-color: #2f9d66;
            }
            QPushButton#startButton:hover { background: #27865a; }
            QPushButton#startButton:disabled { background: #17202a; border-color: #314154; }
            QSlider::groove:horizontal {
                height: 4px;
                background: #314154;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #5b8cff;
                width: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }
            QSplitter::handle { background: #0e141b; }
        """)
        self._sync_buttons()

    def _on_speed(self, value: int):
        self.lbl_speed.setText(f"速度 {value}x")

    def _on_start(self):
        if self.sim.phase == "idle":
            self.sim.start()
            self._refresh()
        if self.sim.phase == "done":
            self._sync_buttons()
            return
        self.timer.start()
        self._sync_buttons()

    def _on_pause(self):
        self.timer.stop()
        self._sync_buttons()

    def _on_reset(self):
        self.timer.stop()
        Logger.flush(force=True)
        self.sim = MarketSimulation()
        self._refresh()

    def _on_tick(self):
        steps = self.speed.value()
        for _ in range(steps):
            if not self.sim.step_visible():
                break
        self._refresh()
        if self.sim.phase == "done":
            self.timer.stop()
            Logger.flush(force=True)
            self._sync_buttons()

    def _refresh(self):
        snap = self.sim.snapshot()
        self.order_book.set_book(
            started=snap["started"],
            symbol=snap["symbol"],
            latest_price=snap["latest_price"],
            ipo_price=snap["ipo_price"],
            bids=snap["bids"],
            asks=snap["asks"],
        )
        self.price_chart.set_series(
            started=snap["started"],
            points=snap["price_points"],
            ipo_price=snap["ipo_price"],
            max_round=snap["max_rounds"],
        )

        if not snap["started"]:
            self.lbl_round.setText(f"轮次 — / {snap['max_rounds']}")
            self.lbl_price.setText("最新价 —")
            self.lbl_price.setStyleSheet("color: #d7dee8; font-size: 18px; font-weight: 600;")
            self.lbl_trades.setText("成交 0")
            self.lbl_last.setText("尚未开盘")
            self.lbl_status.setText("就绪")
            self._sync_buttons()
            return

        trader_count = snap["trader_count"] or 1
        self.lbl_round.setText(
            f"第 {snap['round']} / {snap['max_rounds']} 轮 · {snap['trader_index']}/{trader_count}"
        )
        price = snap["latest_price"]
        ipo = snap["ipo_price"]
        self.lbl_price.setText(f"最新价 {price}")
        if price is None or price == ipo:
            color = "#d7dee8"
        elif price > ipo:
            color = "#f6465d"
        else:
            color = "#16c784"
        self.lbl_price.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: 600;")
        self.lbl_trades.setText(f"成交 {snap['trade_count']}")
        last = snap["last_trade"]
        if last is None:
            self.lbl_last.setText("二级市场尚未成交")
        else:
            self.lbl_last.setText(f"最新成交 {last.quantity:,} 股 @ {last.price}")

        if snap["phase"] == "done":
            self.lbl_status.setText("模拟结束")
        elif self.timer.isActive():
            self.lbl_status.setText("播放中")
        else:
            self.lbl_status.setText("已暂停")
        self._sync_buttons()

    def _sync_buttons(self):
        running = self.timer.isActive()
        phase = self.sim.phase
        self.btn_start.setEnabled(phase != "done" and not running)
        self.btn_start.setText("继续" if phase == "trading" and not running else "开始")
        self.btn_pause.setEnabled(running)
        self.btn_reset.setEnabled(True)

    def closeEvent(self, event):
        self.timer.stop()
        Logger.flush(force=True)
        super().closeEvent(event)
