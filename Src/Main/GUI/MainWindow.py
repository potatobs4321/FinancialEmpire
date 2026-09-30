from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from Src.Main.Core.ConfigManager import ConfigManager
from Src.Main.Core.Logger import Logger
from Src.Main.GUI.ExpectationView import ExpectationView
from Src.Main.GUI.MarketSimulation import MarketSimulation
from Src.Main.GUI.OrderBookView import OrderBookView
from Src.Main.GUI.PriceChartView import PriceChartView


class MainWindow(QMainWindow):
    """交易模拟播放窗口：左侧实时摆盘，右上价格曲线，右下全市场预期分布。"""

    FRAME_MS = 80
    # 拖拽窗口或分割条时会连续触发事件，攒到用户手停下来再落盘一次
    LAYOUT_SAVE_DELAY_MS = 500
    # 显示后等一会儿再开始记录尺寸，留时间给窗口管理器完成裁剪
    CONFIG_READY_DELAY_MS = 300

    # 参数输入框的合法区间。交易者数量上限刻意收紧：盘口快照重建与
    # price_points 每帧全量拷贝尚未优化，人数过大会把界面拖死。
    PARAM_LIMITS = {
        "traders": (1, 2000),
        "rounds": (1, 10000),
        "ipo_price": (1, 1000000),
        "ipo_shares": (1, 100000000),
    }

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.setWindowTitle("FinancialEmpire 交易模拟")

        # 先建好写盘防抖与就绪标志，再还原尺寸：
        # resize() 可能同步触发 resizeEvent，属性必须已经存在。
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(self.LAYOUT_SAVE_DELAY_MS)
        self._layout_save_timer.timeout.connect(self._save_layout)
        # 启动阶段一律不写盘，否则屏幕装不下时被裁剪的尺寸会被当成用户偏好存下来
        self._config_ready = False

        self._restore_window_size()

        # 上次生效的参数，输入非法时回退到这里
        self._applied = {
            "traders": MarketSimulation.NUM_TRADERS,
            "rounds": MarketSimulation.MAX_ROUNDS,
            "ipo_price": MarketSimulation.IPO_PRICE,
            "ipo_shares": None,
        }
        self.sim = MarketSimulation()

        self.timer = QTimer(self)
        self.timer.setInterval(self.FRAME_MS)
        self.timer.timeout.connect(self._on_tick)

        self._build_ui()
        self._refresh()

    def _restore_window_size(self):
        """按配置文件还原窗口尺寸，并裁剪到当前屏幕的可用区域内。

        裁剪是必要的：在 4K 屏上把窗口拉到 3000×2000 之后换到笔记本，
        直接还原会得到一个比屏幕还大的窗口。

        下限刻意不在这里管：Qt 会按布局的最小尺寸（minimumSizeHint，当前 868×574）
        自行顶回。自己再设一个下限反而会和布局最小值打架——用户把窗口缩到
        布局允许的最小尺寸后关闭，下次启动会被抬得比离开时更大。
        """
        width = self.config.get("window", "width")
        height = self.config.get("window", "height")
        width = int(width) if isinstance(width, int) else self.config.DEFAULTS["window"]["width"]
        height = int(height) if isinstance(height, int) else self.config.DEFAULTS["window"]["height"]

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, available.width())
            height = min(height, available.height())
        self.resize(width, height)

    def _save_layout(self):
        """把窗口尺寸与三个面板的尺寸一起落盘（一次写盘覆盖全部布局状态）。"""
        self.config.set("window", "width", int(self.width()))
        self.config.set("window", "height", int(self.height()))
        self.config.set("layout", "main_splitter", [int(size) for size in self.main_splitter.sizes()])
        self.config.set("layout", "right_splitter", [int(size) for size in self.right_splitter.sizes()])
        self.config.save()

    def _flush_layout(self):
        """把待写入的布局立刻落盘。

        只在确实有未落盘的改动时才写：若无论是否有改动都写，
        上面被裁剪过的启动尺寸会在退出时覆盖掉用户的真实偏好。
        """
        if self._layout_save_timer.isActive():
            self._layout_save_timer.stop()
            self._save_layout()

    def _on_splitter_moved(self, position: int, index: int):
        if self._config_ready:
            self._layout_save_timer.start()

    def _apply_splitter_sizes(self, splitter: QSplitter, key: str):
        """把记录的分割条尺寸套回分割器。

        尺寸个数与分割器里的面板数对不上就放弃（例如配置来自改动过布局的旧版本），
        让 stretchFactor 决定初始比例。
        """
        sizes = self.config.get("layout", key)
        if not isinstance(sizes, list) or len(sizes) != splitter.count():
            return
        splitter.setSizes([int(size) for size in sizes])

    def _restore_splitters(self):
        """还原摆盘 / 价格走势 / 预期分布三块面板的尺寸。

        必须在布局生效之后调用：分割器还没有真实大小时 setSizes 会被直接丢弃，
        所以由 showEvent 推迟到下一轮事件循环执行。
        """
        self._apply_splitter_sizes(self.main_splitter, "main_splitter")
        self._apply_splitter_sizes(self.right_splitter, "right_splitter")

    def _mark_config_ready(self):
        self._config_ready = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._config_ready:
            self._layout_save_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        # 只在首次显示时还原：_config_ready 置位后再 show 不该冲掉用户当前的分割位置
        if not self._config_ready:
            QTimer.singleShot(0, self._restore_splitters)
            QTimer.singleShot(self.CONFIG_READY_DELAY_MS, self._mark_config_ready)

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

        self._param_widgets = []
        params = QHBoxLayout()
        params.setSpacing(8)
        self.edit_traders = self._add_param(params, "交易者数量", MarketSimulation.NUM_TRADERS,
                                            "模拟中的自动交易者个数（1–2000）")
        self.edit_rounds = self._add_param(params, "总轮次", MarketSimulation.MAX_ROUNDS,
                                           "模拟推进的总轮次")
        self.edit_price = self._add_param(params, "发行价", MarketSimulation.IPO_PRICE,
                                          "IPO 发行价（整数）")
        self.edit_shares = self._add_param(params, "发行数量", "",
                                           "留空 = 按人均 500 股随交易者数量自动缩放")
        self.edit_shares.setPlaceholderText("自动")
        params.addSpacing(6)
        self.lbl_hint = QLabel()
        self.lbl_hint.setObjectName("hintLabel")
        params.addWidget(self.lbl_hint)
        params.addStretch(1)

        stats = QHBoxLayout()
        stats.setSpacing(18)
        self.lbl_round = QLabel()
        self.lbl_price = QLabel()
        self.lbl_price.setObjectName("priceLabel")
        self.lbl_trades = QLabel()
        self.lbl_last = QLabel()
        self.lbl_expect = QLabel()
        self.lbl_expect.setObjectName("expectLabel")
        for label in (self.lbl_round, self.lbl_price, self.lbl_trades, self.lbl_last, self.lbl_expect):
            stats.addWidget(label)
        stats.addStretch(1)

        self.order_book = OrderBookView()
        self.price_chart = PriceChartView()
        self.expectation = ExpectationView()

        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.addWidget(self.price_chart)
        self.right_splitter.addWidget(self.expectation)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.order_book)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 6)
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        for splitter in (self.main_splitter, self.right_splitter):
            splitter.splitterMoved.connect(self._on_splitter_moved)

        root.addLayout(controls)
        root.addLayout(params)
        root.addLayout(stats)
        root.addWidget(self.main_splitter, 1)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #0e141b;
                color: #d7dee8;
                font-family: "Microsoft YaHei";
                font-size: 13px;
            }
            QLabel#priceLabel { font-size: 18px; font-weight: 600; }
            QLabel#statusLabel { color: #8b9bb0; }
            QLabel#expectLabel { color: #b4d6ff; }
            QLabel#hintLabel { color: #66788a; }
            QLineEdit {
                background: #17202a;
                border: 1px solid #314154;
                border-radius: 4px;
                padding: 4px 6px;
                color: #e8eef6;
            }
            QLineEdit:focus { border-color: #5b8cff; }
            QLineEdit:disabled {
                background: #101720;
                border-color: #232f3d;
                color: #55636f;
            }
            QLabel:disabled { color: #55636f; }
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

    def _add_param(self, layout, label: str, value, tooltip: str) -> QLineEdit:
        caption = QLabel(label)
        layout.addWidget(caption)
        edit = QLineEdit(str(value))
        edit.setFixedWidth(84)
        edit.setAlignment(Qt.AlignRight)
        edit.setValidator(QIntValidator(1, 1000000000, self))
        edit.setToolTip(tooltip)
        layout.addWidget(edit)
        # 连标签一起登记，锁定参数时整组置灰，避免"字亮框灰"的割裂感
        self._param_widgets.extend((caption, edit))
        return edit

    def _set_params_enabled(self, enabled: bool):
        """锁定/解锁参数输入区。判据统一是 phase == "idle"：
        开始后进入 trading、跑完停在 done 都保持锁定，只有重置回到 idle 才解锁。
        """
        for widget in self._param_widgets:
            widget.setEnabled(enabled)
        self.lbl_hint.setText("改完点「重置」生效" if enabled else "参数已锁定，点「重置」后可修改")

    def _read_params(self) -> dict:
        """读取参数输入框：非法输入回退到上次生效值，越界值夹到区间内后写回。"""
        params = {}
        for key, edit, allow_empty in (
            ("traders", self.edit_traders, False),
            ("rounds", self.edit_rounds, False),
            ("ipo_price", self.edit_price, False),
            ("ipo_shares", self.edit_shares, True),
        ):
            text = edit.text().strip()
            if allow_empty and text == "":
                params[key] = None
                continue
            low, high = self.PARAM_LIMITS[key]
            fallback = self._applied.get(key)
            try:
                value = int(text)
            except ValueError:
                value = fallback if fallback is not None else low
            value = max(low, min(high, value))
            edit.setText(str(value))
            params[key] = value
        self._applied.update(params)
        return params

    def _create_simulation(self) -> MarketSimulation:
        """按当前输入框重建模拟。改动参数只有走到这里才会真正生效。"""
        params = self._read_params()
        return MarketSimulation(
            num_traders=params["traders"],
            max_rounds=params["rounds"],
            ipo_price=params["ipo_price"],
            ipo_shares=params["ipo_shares"],
        )

    def _on_speed(self, value: int):
        self.lbl_speed.setText(f"速度 {value}x")

    def _on_start(self):
        if self.sim.phase == "idle":
            # 从空闲态开始才算"应用参数"，暂停后继续不会重建模拟
            self.sim = self._create_simulation()
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
        self.sim = self._create_simulation()
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
            self.lbl_expect.setText("预期中位数 —")
            self.lbl_status.setText("就绪")
            self._push_expectation(snap, started=False)
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

        self._push_expectation(snap, started=True)
        median = snap["expected_median"]
        if median is None:
            self.lbl_expect.setText("预期中位数 —")
        else:
            delta = median - (snap["latest_price"] or 0)
            self.lbl_expect.setText(f"预期中位数 {median:.0f}（{delta:+.0f}）")

        if snap["phase"] == "done":
            self.lbl_status.setText("模拟结束")
        elif self.timer.isActive():
            self.lbl_status.setText("播放中")
        else:
            self.lbl_status.setText("已暂停")
        self._sync_buttons()

    def _push_expectation(self, snap: dict, started: bool):
        """把预期分布数据推给视图；数据已在模型中按固定价格桶聚合。"""
        self.expectation.set_data(
            started=started,
            heat=snap["expected_heat"],
            heat_max=snap["expected_heat_max"],
            band=snap["expected_band"],
            points=snap["price_points"],
            ipo_price=snap["ipo_price"],
            max_round=snap["max_rounds"],
            low=snap["expected_low"],
            high=snap["expected_high"],
            median=snap["expected_median"],
            spread=snap["expected_spread"],
        )

    def _sync_buttons(self):
        running = self.timer.isActive()
        phase = self.sim.phase
        self.btn_start.setEnabled(phase != "done" and not running)
        self.btn_start.setText("继续" if phase == "trading" and not running else "开始")
        self.btn_pause.setEnabled(running)
        self.btn_reset.setEnabled(True)
        self._set_params_enabled(phase == "idle")

    def closeEvent(self, event):
        self.timer.stop()
        self._flush_layout()
        Logger.flush(force=True)
        super().closeEvent(event)
