from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication, QWidget
import sys
from Src.Main.DataCenter.Exchange import Exchange
from Src.Main.Core.Logger import Logger, LogLevel
import math
import random
import numpy as np
import matplotlib.pyplot as plt

# 配置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']  # 中文字体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

def main():
    # app = QApplication(sys.argv)
    # window = QWidget()
    # window.setWindowTitle('最简单的 PyQt5 窗口')
    # window.setGeometry(100, 100, 400, 300)  # x, y, width, height
    # window.show()
    #
    # sys.exit(app.exec_())

    # 参数设置
    NUM_TRADERS = 20  # 交易者数量
    # 注：每个交易者的初始资金为10000~10000000之间的随机数（100的倍数）
    IPO_PRICE = 100  # IPO价格（整数）
    IPO_SHARES = 10000  # IPO总股数
    SYMBOL = "AAPL"  # 股票代码
    MAX_ROUNDS = 100  # 最大交易轮数

    Logger.write_log(LogLevel.INFO, "=" * 60)
    Logger.write_log(LogLevel.INFO, "股票交易模拟系统")
    Logger.write_log(LogLevel.INFO, "=" * 60)

    # 创建交易所
    exchange = Exchange()

    # 设置IPO
    exchange.setup_ipo(SYMBOL, IPO_PRICE, IPO_SHARES)

    # 自动生成n个交易者，每个交易者的初始资金使用左偏正态分布
    # 使用对数正态分布实现：大多数人资金较少，少数人资金很多
    traders = []
    MIN_CASH = 10000
    MAX_CASH = 10000000
    TARGET_MEAN = 100000  # 目标均值

    # 对数正态分布参数计算
    # 对于对数正态分布，如果 X ~ LogNormal(mu, sigma)，则 E[X] = exp(mu + sigma^2/2)
    # 我们设定 sigma = 1.0（方差参数），可以控制分布的偏斜程度
    # sigma 越大，分布越偏斜（右尾越长）
    SIGMA = 1.0  # 对数空间的标准差，控制偏斜程度
    # 根据目标均值计算 mu: mu = ln(TARGET_MEAN) - sigma^2/2
    MU = math.log(TARGET_MEAN) - (SIGMA ** 2) / 2

    total_initial_cash = 0
    cash_list = []

    for i in range(NUM_TRADERS):
        # 生成对数正态分布的随机数
        while True:
            initial_cash = np.random.lognormal(mean=MU, sigma=SIGMA)
            initial_cash = int(round(initial_cash / 100) * 100)  # 取整为100的倍数
            # 限制在有效范围内
            if MIN_CASH <= initial_cash <= MAX_CASH:
                break

        trader = exchange.register_trader(f"Trader_{i:03d}", initial_cash=initial_cash)
        traders.append(trader)
        total_initial_cash += initial_cash
        cash_list.append(initial_cash)

    avg_cash = total_initial_cash // NUM_TRADERS
    median_cash = int(np.median(cash_list))
    Logger.write_log(LogLevel.INFO, f"\n已注册 {NUM_TRADERS} 个交易者")
    Logger.write_log(LogLevel.INFO, f"  初始资金范围: {MIN_CASH} ~ {MAX_CASH} (100的倍数)")
    Logger.write_log(LogLevel.INFO, f"  分布类型: 左偏正态分布 (对数正态)")
    Logger.write_log(LogLevel.INFO, f"  目标均值: {TARGET_MEAN}, 实际均值: {avg_cash}, 中位数: {median_cash}")
    Logger.write_log(LogLevel.INFO, f"  总初始资金: {total_initial_cash}")

    # ========== Phase 1: IPO阶段 ==========
    Logger.write_log(LogLevel.INFO, "\n" + "=" * 60)
    Logger.write_log(LogLevel.INFO, "Phase 1: IPO申购阶段")
    Logger.write_log(LogLevel.INFO, "=" * 60)

    # 第一步：所有交易者提交申购
    apply_count = 0
    for trader in traders:
        # 每个交易者用30%-80%资金申购
        buy_ratio = random.uniform(0.5, 0.8)
        buy_amount = int(round(trader.cash * buy_ratio))
        quantity = buy_amount // IPO_PRICE
        if quantity > 0:
            if exchange.apply_ipo(trader.trader_id, SYMBOL, quantity):
                apply_count += 1

    Logger.write_log(LogLevel.INFO, f"\n申购阶段结束，共 {apply_count}/{len(traders)} 人申购")

    # 第二步：摇号分配
    Logger.write_log(LogLevel.INFO, "\n" + "=" * 60)
    Logger.write_log(LogLevel.INFO, "Phase 1.5: IPO摇号分配")
    Logger.write_log(LogLevel.INFO, "=" * 60)

    allocation = exchange.allocate_ipo(SYMBOL)
    print(allocation)

    # 标记IPO完成（无论是否完全认购都进入二级市场）
    remaining_ipo = exchange.get_ipo_remaining(SYMBOL)
    exchange.ipo_completed[SYMBOL] = True

    if remaining_ipo > 0:
        Logger.write_log(LogLevel.INFO, f"\nIPO阶段结束，未完全认购，{remaining_ipo} 股被冻结（不进入流通）")
    else:
        Logger.write_log(LogLevel.INFO, f"\nIPO阶段结束，全部 {IPO_SHARES} 股已分配完毕")

    # 打印初始状态
    exchange.print_summary()

    # ========== Phase 2: 二级市场交易 ==========
    Logger.write_log(LogLevel.INFO, "\n" + "=" * 60)
    Logger.write_log(LogLevel.INFO, "Phase 2: 二级市场交易 - 交易者相互买卖")
    Logger.write_log(LogLevel.INFO, "=" * 60)

    # 记录价格历史
    price_history = []
    round_history = []

    round_num = 0
    while round_num < MAX_ROUNDS:
        # time.sleep(0.1)
        round_num += 1
        Logger.write_log(LogLevel.INFO, f"\n{'#' * 60}")
        Logger.write_log(LogLevel.INFO, f"# 第 {round_num} 轮交易")
        Logger.write_log(LogLevel.INFO, f"{'#' * 60}")

        # 随机打乱交易者顺序
        random.shuffle(traders)

        # 每个交易者根据预期价格做决策
        for trader in traders:
            trader.make_trading_decision(SYMBOL, round_num)

        # 打印简要状态
        exchange.print_summary()

        # 记录当前轮次的最新价格
        current_price = exchange.get_latest_price(SYMBOL)
        if current_price:
            price_history.append(current_price)
            round_history.append(round_num)

    Logger.write_log(LogLevel.INFO, "\n" + "=" * 60)
    Logger.write_log(LogLevel.INFO, "交易模拟结束")
    Logger.write_log(LogLevel.INFO, "=" * 60)

    # 最终摆盘
    # exchange.print_order_book(SYMBOL, depth=10)

    # 最终状态
    # exchange.print_status()

    # 统计信息
    Logger.write_log(LogLevel.INFO, "\n交易统计:")
    Logger.write_log(LogLevel.INFO, f"  总交易次数: {len(exchange.trades)}")
    if exchange.trades:
        prices = [t.price for t in exchange.trades]
        Logger.write_log(LogLevel.INFO, f"  价格范围: {min(prices)} - {max(prices)}")
        Logger.write_log(LogLevel.INFO, f"  最终价格: {exchange.get_latest_price(SYMBOL)}")

    # 绘制价格走势图
    if price_history:
        plt.figure(figsize=(12, 6))
        plt.plot(round_history, price_history, 'b-', linewidth=1, label=f'{SYMBOL} 价格')
        plt.axhline(y=IPO_PRICE, color='r', linestyle='--', linewidth=1, label=f'IPO价格 ({IPO_PRICE})')

        # 添加标注
        plt.xlabel('交易轮次', fontsize=12)
        plt.ylabel('价格', fontsize=12)
        plt.title(f'{SYMBOL} 股票价格走势图', fontsize=14)
        plt.legend(loc='best')
        plt.grid(True, alpha=0.3)

        # 设置y轴范围，留出一些边距
        min_price = min(price_history)
        max_price = max(price_history)
        margin = (max_price - min_price) * 0.1 if max_price != min_price else 10
        plt.ylim(min_price - margin, max_price + margin)

        # 显示起始价和结束价
        plt.annotate(f'起始: {price_history[0]}',
                     xy=(round_history[0], price_history[0]),
                     xytext=(round_history[0] + len(round_history) * 0.05, price_history[0]),
                     fontsize=10)
        plt.annotate(f'结束: {price_history[-1]}',
                     xy=(round_history[-1], price_history[-1]),
                     xytext=(round_history[-1] - len(round_history) * 0.15, price_history[-1]),
                     fontsize=10)

        plt.tight_layout()
        plt.show()

if __name__ == '__main__':
    main()
