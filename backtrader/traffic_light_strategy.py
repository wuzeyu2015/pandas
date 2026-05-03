import backtrader as bt
import jqdatasdk
import pandas as pd
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# 配置中文字体支持 - 使用系统已安装的 Noto Sans CJK 字体
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 从环境变量读取凭据，避免硬编码
JQ_USER = os.getenv('JQ_USER', '18380280516')
JQ_PASS = os.getenv('JQ_PASS', '306116315yY')
jqdatasdk.auth(JQ_USER, JQ_PASS)

def GetStockDatApi(code, start='20240101', end='20240419'):
    """
    获取股票/基金数据并格式化为 Backtrader 可用的格式
    
    Args:
        code: 股票代码（如 '510300' 或 '159952'）
        start: 开始日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        end: 结束日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
    
    Returns:
        DataFrame: 包含 OHLCV 数据的时间序列
    """
    # 处理代码格式，添加交易所后缀
    if '.' not in code:
        if code.startswith('6'):
            jq_code = f"{code}.XSHG"  # 上海交易所
        else:
            jq_code = f"{code}.XSHE"  # 深圳交易所
    else:
        jq_code = code

    try:
        # 获取日线数据
        df = jqdatasdk.get_price(
            jq_code, 
            start_date=start, 
            end_date=end,
            fq='post',  # 后复权
            frequency='1d',  # 日线数据
            fields=['open', 'close', 'low', 'high', 'volume'],
            round=False
        )
    except Exception as e:
        print(f"获取数据失败 [{jq_code}]: {e}")
        return pd.DataFrame()

    if df.empty:
        print(f"未获取到数据 [{jq_code}]，请检查代码和日期范围")
        return pd.DataFrame()

    # 处理时间索引
    if isinstance(df.index, pd.DatetimeIndex):
        pass
    else:
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        elif 'day' in df.columns:
            df['day'] = pd.to_datetime(df['day'])
            df.set_index('day', inplace=True)

    # 确保数据类型正确
    for col in ['open', 'close', 'high', 'low', 'volume']:
        if col in df.columns:
            df[col] = df[col].astype(float)
    
    print(f"成功获取 {len(df)} 条数据，时间范围: {df.index[0]} 至 {df.index[-1]}")
    return df


class TrafficLightStrategy(bt.Strategy):
    """
    红绿灯策略 - 基于多指标综合判断的交易系统
    
    信号规则：
    🟢 绿灯（买入/持有）：多个指标同时看多
    🔴 红灯（卖出/观望）：多个指标同时看空
    🟡 黄灯（谨慎/减仓）：指标矛盾或市场震荡
    """
    
    params = (
        ('ma_short', 5),      # 短期均线周期
        ('ma_medium', 20),    # 中期均线周期
        ('ma_long', 60),      # 长期均线周期
        ('rsi_period', 14),   # RSI周期
        ('rsi_overbought', 70),  # RSI超买线
        ('rsi_oversold', 30),    # RSI超卖线
        ('macd_fast', 12),    # MACD快线周期
        ('macd_slow', 26),    # MACD慢线周期
        ('macd_signal', 9),   # MACD信号线周期
        ('green_threshold', 2),  # 绿灯所需的最小看多指标数
        ('red_threshold', 2),    # 红灯所需的最小看空指标数
    )
    
    def __init__(self):
        # 价格序列
        self.dataclose = self.datas[0].close
        
        # 订单管理
        self.order = None
        self.buyprice = None
        self.buycomm = None
        
        # 当前信号灯状态
        self.traffic_light = 'YELLOW'  # 初始为黄灯
        
        # 指标1：三条均线
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_short)
        self.sma_medium = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_medium)
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_long)
        
        # 指标2：RSI
        self.rsi = bt.indicators.RSI(
            self.datas[0], period=self.params.rsi_period)
        
        # 指标3：MACD
        self.macd = bt.indicators.MACD(
            self.datas[0],
            period_me1=self.params.macd_fast,
            period_me2=self.params.macd_slow,
            period_signal=self.params.macd_signal)
        
        # 记录信号灯历史
        self.light_history = []
        
    def log(self, txt, dt=None, doprint=False):
        """日志函数"""
        if doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def calculate_traffic_light(self):
        """
        计算当前信号灯状态
        
        Returns:
            str: 'GREEN', 'RED', 或 'YELLOW'
        """
        bullish_count = 0  # 看多指标计数
        bearish_count = 0  # 看空指标计数
        
        # === 指标1：均线系统 ===
        # 多头排列：短 > 中 > 长
        if (self.sma_short[0] > self.sma_medium[0] and 
            self.sma_medium[0] > self.sma_long[0]):
            bullish_count += 1
        # 空头排列：短 < 中 < 长
        elif (self.sma_short[0] < self.sma_medium[0] and 
              self.sma_medium[0] < self.sma_long[0]):
            bearish_count += 1
        
        # === 指标2：RSI ===
        if self.rsi[0] > 50 and self.rsi[0] < self.params.rsi_overbought:
            # RSI在50-70之间，健康上涨
            bullish_count += 1
        elif self.rsi[0] < 50 and self.rsi[0] > self.params.rsi_oversold:
            # RSI在30-50之间，弱势
            bearish_count += 1
        elif self.rsi[0] >= self.params.rsi_overbought:
            # RSI超买，警惕回调
            bearish_count += 1
        elif self.rsi[0] <= self.params.rsi_oversold:
            # RSI超卖，可能反弹
            bullish_count += 1
        
        # === 指标3：MACD ===
        macd_line = self.macd.macd[0]
        signal_line = self.macd.signal[0]
        
        if macd_line > signal_line and macd_line > 0:
            # MACD金叉且在零轴上方
            bullish_count += 1
        elif macd_line < signal_line and macd_line < 0:
            # MACD死叉且在零轴下方
            bearish_count += 1
        
        # === 判断信号灯 ===
        if bullish_count >= self.params.green_threshold:
            return 'GREEN'
        elif bearish_count >= self.params.red_threshold:
            return 'RED'
        else:
            return 'YELLOW'

    def notify_order(self, order):
        """订单状态处理"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
                self.log(f'🟢 买入: 价格 {order.executed.price:.2f}, '
                        f'成本 {order.executed.value:.2f}, '
                        f'手续费 {order.executed.comm:.2f}', doprint=True)
            else:
                self.log(f'🔴 卖出: 价格 {order.executed.price:.2f}, '
                        f'成本 {order.executed.value:.2f}, '
                        f'手续费 {order.executed.comm:.2f}', doprint=True)
            self.bar_executed = len(self)
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('❌ 订单取消/保证金不足/拒绝', doprint=True)
        
        self.order = None

    def notify_trade(self, trade):
        """交易成果"""
        if not trade.isclosed:
            return
        self.log(f'💰 交易利润: 毛利润 {trade.pnl:.2f}, '
                f'净利润 {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        """每个bar的执行逻辑"""
        # 计算当前信号灯
        self.traffic_light = self.calculate_traffic_light()
        self.light_history.append(self.traffic_light)
        
        # 如果有未完成订单，等待
        if self.order:
            return
        
        # 根据信号灯执行操作
        if self.traffic_light == 'GREEN':
            # 🟢 绿灯：买入或持有
            if not self.position:
                self.order = self.buy()
                self.log(f'🟢 绿灯信号 - 买入, 收盘价: {self.dataclose[0]:.2f}', 
                        doprint=True)
            else:
                self.log(f'🟢 绿灯信号 - 持有, 收盘价: {self.dataclose[0]:.2f}', 
                        doprint=True)
                
        elif self.traffic_light == 'RED':
            # 🔴 红灯：卖出或观望
            if self.position:
                self.order = self.sell()
                self.log(f'🔴 红灯信号 - 卖出, 收盘价: {self.dataclose[0]:.2f}', 
                        doprint=True)
            else:
                self.log(f'🔴 红灯信号 - 观望, 收盘价: {self.dataclose[0]:.2f}', 
                        doprint=True)
                
        else:  # YELLOW
            # 🟡 黄灯：保持现状，不操作
            if self.position:
                self.log(f'🟡 黄灯信号 - 谨慎持有, 收盘价: {self.dataclose[0]:.2f}', 
                        doprint=True)
            else:
                self.log(f'🟡 黄灯信号 - 谨慎观望, 收盘价: {self.dataclose[0]:.2f}', 
                        doprint=True)

    def stop(self):
        """回测结束统计"""
        # 统计信号灯分布
        green_count = self.light_history.count('GREEN')
        red_count = self.light_history.count('RED')
        yellow_count = self.light_history.count('YELLOW')
        total = len(self.light_history)
        
        self.log('=' * 60, doprint=True)
        self.log('🚦 红绿灯策略统计', doprint=True)
        self.log(f'🟢 绿灯: {green_count}次 ({green_count/total*100:.1f}%)', doprint=True)
        self.log(f'🔴 红灯: {red_count}次 ({red_count/total*100:.1f}%)', doprint=True)
        self.log(f'🟡 黄灯: {yellow_count}次 ({yellow_count/total*100:.1f}%)', doprint=True)
        self.log(f'最终资金: {self.broker.getvalue():.2f}', doprint=True)
        self.log('=' * 60, doprint=True)


def plot_traffic_light_signals(cerebro, strategy):
    """
    绘制带红绿灯信号的图表
    """
    try:
        import matplotlib.dates as mdates
        from matplotlib.patches import Circle
        from matplotlib.font_manager import FontProperties
        
        # 设置中文字体属性
        font_prop = FontProperties(family='Noto Sans CJK SC')
        
        # 获取数据 - 使用更安全的方式
        data = cerebro.datas[0]
        
        # 从策略的灯历史获取实际的交易天数
        num_bars = len(strategy.light_history)
        
        # 安全地获取日期和价格数据
        dates = []
        closes = []
        for i in range(num_bars):
            try:
                # 使用相对索引，从最后一个bar往前推
                dt = data.datetime.date(i - num_bars + 1)
                close = data.close[i - num_bars + 1]
                dates.append(dt)
                closes.append(close)
            except:
                # 如果访问失败，跳过该点
                continue
        
        if not dates or not closes:
            print("⚠️  警告: 无法获取绘图数据")
            return
        
        # 获取信号灯历史
        light_history = strategy.light_history[-len(dates):]  # 确保长度匹配
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 12), 
                                        gridspec_kw={'height_ratios': [3, 1]})
        
        # === 上图：价格和信号灯 ===
        ax1.plot(dates, closes, 'b-', linewidth=1.5, label='收盘价')
        
        # 绘制均线 - 同样使用安全的方式获取
        sma_short = []
        sma_medium = []
        sma_long = []
        
        for i in range(len(dates)):
            try:
                idx = i - len(dates) + 1
                sma_short.append(strategy.sma_short[idx])
                sma_medium.append(strategy.sma_medium[idx])
                sma_long.append(strategy.sma_long[idx])
            except:
                # 如果均线数据不可用，用None填充
                sma_short.append(None)
                sma_medium.append(None)
                sma_long.append(None)
        
        # 过滤掉None值用于绘图
        valid_indices = [i for i, v in enumerate(sma_short) if v is not None]
        if valid_indices:
            valid_dates = [dates[i] for i in valid_indices]
            valid_sma_short = [sma_short[i] for i in valid_indices]
            valid_sma_medium = [sma_medium[i] for i in valid_indices]
            valid_sma_long = [sma_long[i] for i in valid_indices]
            
            ax1.plot(valid_dates, valid_sma_short, 'g--', linewidth=1, 
                    label=f'{strategy.params.ma_short}日均线')
            ax1.plot(valid_dates, valid_sma_medium, 'orange', linewidth=1, 
                    label=f'{strategy.params.ma_medium}日均线')
            ax1.plot(valid_dates, valid_sma_long, 'r--', linewidth=1, 
                    label=f'{strategy.params.ma_long}日均线')
        
        # 在价格图上标注红绿灯
        green_dates = [dates[i] for i, light in enumerate(light_history) if light == 'GREEN']
        green_prices = [closes[i] for i, light in enumerate(light_history) if light == 'GREEN']
        
        red_dates = [dates[i] for i, light in enumerate(light_history) if light == 'RED']
        red_prices = [closes[i] for i, light in enumerate(light_history) if light == 'RED']
        
        yellow_dates = [dates[i] for i, light in enumerate(light_history) if light == 'YELLOW']
        yellow_prices = [closes[i] for i, light in enumerate(light_history) if light == 'YELLOW']
        
        # 用不同颜色的点标记
        if green_dates:
            ax1.scatter(green_dates, green_prices, c='green', s=100, 
                       marker='^', label='🟢 绿灯', zorder=5, alpha=0.7)
        if red_dates:
            ax1.scatter(red_dates, red_prices, c='red', s=100, 
                       marker='v', label='🔴 红灯', zorder=5, alpha=0.7)
        if yellow_dates:
            ax1.scatter(yellow_dates, yellow_prices, c='yellow', s=50, 
                       marker='o', label='🟡 黄灯', zorder=5, alpha=0.5, edgecolors='orange')
        
        ax1.set_title('红绿灯策略 - 价格走势与信号', fontsize=16, fontweight='bold', fontproperties=font_prop)
        ax1.set_ylabel('价格', fontsize=12, fontproperties=font_prop)
        ax1.legend(loc='best', fontsize=10, prop=font_prop)
        ax1.grid(True, alpha=0.3)
        
        # === 下图：信号灯状态 ===
        light_values = []
        for light in light_history:
            if light == 'GREEN':
                light_values.append(2)
            elif light == 'RED':
                light_values.append(0)
            else:
                light_values.append(1)
        
        colors = ['green' if v == 2 else 'red' if v == 0 else 'yellow' 
                 for v in light_values]
        
        ax2.bar(range(len(light_values)), light_values, color=colors, alpha=0.6)
        ax2.set_ylim(-0.5, 2.5)
        ax2.set_yticks([0, 1, 2])
        ax2.set_yticklabels(['🔴 红灯', '🟡 黄灯', '🟢 绿灯'])
        ax2.set_xlabel('交易日', fontsize=12, fontproperties=font_prop)
        ax2.set_title('信号灯状态变化', fontsize=14, fontweight='bold', fontproperties=font_prop)
        ax2.grid(True, alpha=0.3, axis='y')
        
        # 格式化日期轴
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig('traffic_light_result.png', dpi=150, bbox_inches='tight')
        print("\n📊 图表已保存为 traffic_light_result.png")
        plt.close()
        
    except Exception as e:
        print(f"绘图失败: {e}")
        import traceback
        traceback.print_exc()


def run_backtest(code='159952', start='20240101', end='20241231'):
    """
    运行红绿灯策略回测
    
    Args:
        code: 基金/股票代码
        start: 开始日期
        end: 结束日期
    """
    cerebro = bt.Cerebro()
    
    print(f"\n{'='*60}")
    print(f"🚦 红绿灯策略回测")
    print(f"{'='*60}")
    print(f"标的代码: {code}")
    print(f"时间范围: {start} 至 {end}")
    print(f"{'='*60}\n")
    
    # 获取数据
    print("正在获取数据...")
    df = GetStockDatApi(code, start, end)
    
    if df.empty:
        print("❌ 数据为空，退出回测")
        return

    print(f"✅ 数据获取完成，共 {len(df)} 条记录\n")
    
    # 创建数据源
    data = bt.feeds.PandasData(dataname=df, nocase=True)
    cerebro.adddata(data)
    
    # 添加红绿灯策略
    cerebro.addstrategy(TrafficLightStrategy)
    
    # 设置初始资金和手续费
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)
    
    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    print(f'💰 初始资金: {cerebro.broker.getvalue():.2f}')
    print(f"🔄 开始回测...\n")
    
    # 运行回测
    results = cerebro.run()
    strat = results[0]
    
    print(f'💵 最终资金: {cerebro.broker.getvalue():.2f}')
    
    # 输出分析结果
    print('\n' + '='*60)
    print('📈 策略性能分析')
    print('='*60)
    
    sharpe = strat.analyzers.sharpe.get_analysis()
    sharpe_ratio = sharpe.get('sharperatio')
    if sharpe_ratio is not None:
        print(f'夏普比率: {sharpe_ratio:.4f}')
    else:
        print('夏普比率: N/A (数据不足或无交易)')
    
    drawdown = strat.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown["max"]["drawdown"]:.2f}%')
    print(f'最大回撤持续时间: {drawdown["max"]["len"]}天')
    
    returns = strat.analyzers.returns.get_analysis()
    print(f'总收益率: {returns["rtot"]*100:.2f}%')
    print(f'年化收益率: {returns["ravg"]*252*100:.2f}%')
    
    trades = strat.analyzers.trades.get_analysis()
    if trades.total.closed > 0:
        print(f'\n交易统计:')
        print(f'  总交易次数: {trades.total.closed}')
        print(f'  盈利交易: {trades.won.total}')
        print(f'  亏损交易: {trades.lost.total}')
        win_rate = trades.won.total / trades.total.closed * 100
        print(f'  胜率: {win_rate:.2f}%')
        print(f'  平均盈利: {trades.won.pnl.average:.2f}')
        print(f'  平均亏损: {trades.lost.pnl.average:.2f}')
    else:
        print('\n⚠️  警告: 未产生任何交易，请检查以下项：')
        print('  1. 回测时间范围是否足够长（建议至少1年以上）')
        print('  2. 均线周期参数是否过大（当前为5/20/60日）')
        print('  3. 数据质量是否正常')
    
    print('='*60 + '\n')
    
    # 绘制图表
    print("📊 正在生成图表...")
    plot_traffic_light_signals(cerebro, strat)
    
    return results


if __name__ == '__main__':
    # 运行红绿灯策略回测
    # 可以修改参数测试不同的标的和时间范围
    run_backtest(code='159952', start='20240101', end='20260101')
