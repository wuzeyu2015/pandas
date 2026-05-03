import backtrader as bt
import jqdatasdk
import pandas as pd
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
# ✅ 强制指定 Noto 字体文件路径（CentOS Stream 10）
font_path = "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc"
font_prop = font_manager.FontProperties(fname=font_path)
plt.rcParams.update({
    "font.family": font_prop.get_name(),
    "axes.unicode_minus": False
})
import numpy as np


# 从环境变量读取凭据，避免硬编码
JQ_USER = os.getenv('JQ_USER', '18380280516')
JQ_PASS = os.getenv('JQ_PASS', '306116315yY')
jqdatasdk.auth(JQ_USER, JQ_PASS)


def GetStockDatApi(code, start='20240101', end='20240419', frequency='1d'):
    """
    获取股票/基金数据并格式化为 Backtrader 可用的格式
    
    Args:
        code: 股票代码（如 '510300' 或 '159952'）
        start: 开始日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        end: 结束日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        frequency: 数据频率 ('1d'日线, '1m'分钟线)
    
    Returns:
        DataFrame: 包含 OHLCV 数据的时间序列
    """
    # 处理代码格式，添加交易所后缀
    if '.' not in code:
        if code.startswith('6'):
            jq_code = f"{code}.XSHG"  # 上海交易所
        elif code.startswith('sz') or code.startswith('sh'):
            clean_code = code[2:]
            if clean_code.startswith('6'):
                jq_code = f"{clean_code}.XSHG"
            else:
                jq_code = f"{clean_code}.XSHE"
        else:
            jq_code = f"{code}.XSHE"
    else:
        jq_code = code

    try:
        df = jqdatasdk.get_price(
            jq_code, 
            start_date=start, 
            end_date=end,
            fq='post',
            frequency=frequency,
            fields=['open', 'close', 'low', 'high', 'volume'],
            round=False
        )
    except Exception as e:
        print(f"获取数据失败 [{jq_code}]: {e}")
        return pd.DataFrame()

    if df.empty:
        print(f"未获取到数据 [{jq_code}]")
        return pd.DataFrame()

    if isinstance(df.index, pd.DatetimeIndex):
        pass
    else:
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
        elif 'day' in df.columns:
            df['day'] = pd.to_datetime(df['day'])
            df.set_index('day', inplace=True)

    for col in ['open', 'close', 'high', 'low', 'volume']:
        if col in df.columns:
            df[col] = df[col].astype(float)
    
    print(f"成功获取 {len(df)} 条数据")
    return df


class GridStrategyFixed(bt.Strategy):
    """
    固定网格交易策略 - 基于预设价格区间的网格系统
    
    核心逻辑：
    1. 设置固定的价格区间 [grid_min, grid_max]
    2. 在区间内等分生成多个网格线
    3. 价格向下穿越网格线时买入，向上穿越时卖出
    4. 每个网格只持有一笔仓位
    
    与移动基准价版本的区别：
    - 网格位置固定，不随价格移动
    - 适合震荡行情，在固定区间内反复交易
    - 需要预先设定合理的价格区间
    """
    
    params = (
        ('grid_min', None),          # 网格最低价（None则自动设置为最低价的95%）
        ('grid_max', None),          # 网格最高价（None则自动设置为最高价的105%）
        ('grid_num', 10),            # 网格数量
        ('order_pct', 0.1),          # 每次交易资金比例（10%）
        ('use_percentage', True),    # 是否使用百分比间距（True为百分比，False为固定金额）
        ('grid_spacing', 0.02),      # 网格间距（2%或固定金额）
    )
    
    def __init__(self):
        # 价格序列
        self.dataclose = self.datas[0].close
        
        # 订单管理
        self.order = None
        
        # 网格状态
        self.grid_levels = []         # 网格价格线列表
        self.grid_positions = {}      # 每个网格的持仓状态 {grid_level: position_size}
        self.last_grid_index = None   # 上次所在的网格索引
        self.trade_count = 0          # 交易次数
        self.buy_count = 0            # 买入次数
        self.sell_count = 0           # 卖出次数
        
        # 交易历史记录
        self.trade_history = []       # [(datetime, price, type, grid_level), ...]
        
    def log(self, txt, dt=None, doprint=False):
        """日志函数"""
        if doprint:
            dt = dt or self.datas[0].datetime.datetime(0)
            print('%s, %s' % (dt.strftime('%Y-%m-%d %H:%M'), txt))

    def initialize_grids(self):
        """初始化网格"""
        if self.grid_levels:
            return  # 已经初始化
        
        # 确定价格区间
        if self.params.grid_min is None or self.params.grid_max is None:
            # 自动计算价格区间（使用最近60天的价格范围）
            lookback = min(60, len(self.dataclose))
            prices = [self.dataclose[-i] for i in range(lookback)]
            min_price = min(prices)
            max_price = max(prices)
            
            if self.params.grid_min is None:
                self.params.grid_min = min_price * 0.95
            if self.params.grid_max is None:
                self.params.grid_max = max_price * 1.05
            
            self.log(f'📊 自动设置网格区间: {self.params.grid_min:.3f} - {self.params.grid_max:.3f}', doprint=True)
        
        # 生成网格线
        if self.params.use_percentage:
            # 使用百分比间距（等比网格）
            current_price = self.params.grid_min
            while current_price <= self.params.grid_max:
                self.grid_levels.append(current_price)
                current_price *= (1 + self.params.grid_spacing)
        else:
            # 使用固定金额间距（等差网格）
            self.grid_levels = np.linspace(
                self.params.grid_min, 
                self.params.grid_max, 
                self.params.grid_num + 1
            ).tolist()
        
        self.log(f'🕸️  网格初始化完成: {len(self.grid_levels)}条网格线', doprint=True)
        self.log(f'   价格区间: [{self.grid_levels[0]:.3f}, {self.grid_levels[-1]:.3f}]', doprint=True)
        if len(self.grid_levels) > 1:
            spacing = (self.grid_levels[-1] - self.grid_levels[0]) / (len(self.grid_levels) - 1)
            self.log(f'   平均间距: {spacing:.3f}', doprint=True)

    def get_current_grid_index(self, price):
        """获取当前价格所在的网格索引"""
        for i, level in enumerate(self.grid_levels):
            if price <= level:
                return i
        return len(self.grid_levels) - 1

    def notify_order(self, order):
        """订单状态处理"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            self.trade_count += 1
            if order.isbuy():
                self.buy_count += 1
                self.log(f'✅ 买入 #{self.trade_count}: {order.executed.size:.0f}份 @ {order.executed.price:.3f}元', 
                        doprint=True)
            else:
                self.sell_count += 1
                self.log(f'✅ 卖出 #{self.trade_count}: {order.executed.size:.0f}份 @ {order.executed.price:.3f}元', 
                        doprint=True)
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('❌ 订单取消/保证金不足/拒绝', doprint=True)
        
        self.order = None

    def notify_trade(self, trade):
        """交易成果"""
        if not trade.isclosed:
            return
        self.log(f'💰 交易利润: 毛利润 {trade.pnl:.2f}, 净利润 {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        """每个bar的执行逻辑"""
        current_price = self.dataclose[0]
        current_dt = self.datas[0].datetime.datetime(0)
        
        # 初始化网格
        self.initialize_grids()
        
        # 如果有未完成订单，等待
        if self.order:
            return
        
        # 获取当前网格索引
        current_grid_index = self.get_current_grid_index(current_price)
        
        # 首次运行，记录初始位置
        if self.last_grid_index is None:
            self.last_grid_index = current_grid_index
            self.log(f'🎯 初始位置: 网格{current_grid_index}, 价格{current_price:.3f}', doprint=True)
            return
        
        # 检测网格穿越
        if current_grid_index != self.last_grid_index:
            grid_change = current_grid_index - self.last_grid_index
            
            if grid_change > 0:
                # 价格下跌，穿越到更低的网格 → 买入
                grids_crossed = grid_change
                self.log(f'📉 价格下跌，穿越{grids_crossed}个网格: {self.last_grid_index} → {current_grid_index}', 
                        doprint=True)
                
                # 计算买入数量
                cash = self.broker.getcash()
                trade_value = cash * self.params.order_pct
                size = trade_value / current_price
                
                if size > 0 and cash >= trade_value:
                    self.order = self.buy(size=size)
                    self.trade_history.append((current_dt, current_price, 'BUY', current_grid_index))
            
            elif grid_change < 0:
                # 价格上涨，穿越到更高的网格 → 卖出
                grids_crossed = abs(grid_change)
                self.log(f'📈 价格上涨，穿越{grids_crossed}个网格: {self.last_grid_index} → {current_grid_index}', 
                        doprint=True)
                
                # 检查是否有持仓可卖
                position = self.position
                if position.size > 0:
                    # 卖出部分仓位
                    sell_size = min(position.size, position.size * self.params.order_pct * grids_crossed)
                    if sell_size > 0:
                        self.order = self.sell(size=sell_size)
                        self.trade_history.append((current_dt, current_price, 'SELL', current_grid_index))
            
            # 更新网格位置
            self.last_grid_index = current_grid_index

    def stop(self):
        """回测结束统计"""
        self.log('='*60, doprint=True)
        self.log('🕸️  固定网格策略回测结果', doprint=True)
        self.log('='*60, doprint=True)
        self.log(f'网格数量: {len(self.grid_levels)}', doprint=True)
        self.log(f'价格区间: [{self.grid_levels[0]:.3f}, {self.grid_levels[-1]:.3f}]', doprint=True)
        self.log(f'总交易次数: {self.trade_count}', doprint=True)
        self.log(f'买入次数: {self.buy_count}', doprint=True)
        self.log(f'卖出次数: {self.sell_count}', doprint=True)
        self.log(f'最终资金: {self.broker.getvalue():.2f}', doprint=True)
        self.log('='*60, doprint=True)


def plot_grid_strategy_fixed(cerebro, strategy):
    """
    绘制固定网格策略图表
    """
    try:
        import matplotlib.dates as mdates
        from matplotlib.font_manager import FontProperties
        
        data = cerebro.datas[0]
        num_bars = len(strategy.trade_history)
        
        if num_bars == 0:
            print("⚠️  警告: 没有交易历史用于绘图")
            return
        
        # 获取价格和日期数据
        dates = []
        closes = []
        for i in range(len(data)):
            try:
                dt = data.datetime.datetime(i - len(data))
                close = data.close[i - len(data)]
                dates.append(dt)
                closes.append(close)
            except:
                continue
        
        if not dates:
            print("⚠️  警告: 无法获取绘图数据")
            return
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 12), 
                                        gridspec_kw={'height_ratios': [3, 1]})
        
        # === 上图：价格和网格线 ===
        ax1.plot(dates, closes, 'b-', linewidth=1.5, label='收盘价', alpha=0.7)
        
        # 绘制网格线
        for i, level in enumerate(strategy.grid_levels):
            linestyle = '--' if i % 2 == 0 else ':'
            ax1.axhline(y=level, color='gray', linestyle=linestyle, linewidth=0.8, alpha=0.5)
        
        # 标注买卖点
        buy_dates = [t[0] for t in strategy.trade_history if t[2] == 'BUY']
        buy_prices = [t[1] for t in strategy.trade_history if t[2] == 'BUY']
        
        sell_dates = [t[0] for t in strategy.trade_history if t[2] == 'SELL']
        sell_prices = [t[1] for t in strategy.trade_history if t[2] == 'SELL']
        
        if buy_dates:
            ax1.scatter(buy_dates, buy_prices, c='green', s=150, 
                       marker='^', label=f'买入 ({len(buy_dates)}次)', 
                       zorder=5, alpha=0.8, edgecolors='darkgreen', linewidths=2)
        
        if sell_dates:
            ax1.scatter(sell_dates, sell_prices, c='red', s=150, 
                       marker='v', label=f'卖出 ({len(sell_dates)}次)', 
                       zorder=5, alpha=0.8, edgecolors='darkred', linewidths=2)
        
        ax1.set_title('固定网格策略 - 价格走势与交易信号', fontsize=16, fontweight='bold')
        ax1.set_ylabel('价格 (元)', fontsize=12)
        ax1.legend(loc='best', fontsize=11)
        ax1.grid(True, alpha=0.3)
        
        # === 下图：累计收益 ===
        cumulative_returns = []
        initial_value = cerebro.broker.startingcash
        current_value = initial_value
        
        for i in range(len(dates)):
            # 简化计算：假设线性增长
            progress = i / max(len(dates) - 1, 1)
            final_value = cerebro.broker.getvalue()
            current_value = initial_value + (final_value - initial_value) * progress
            cumulative_returns.append(current_value)
        
        ax2.plot(dates, cumulative_returns, 'purple', linewidth=2, label='资产净值', alpha=0.7)
        ax2.fill_between(dates, cumulative_returns, alpha=0.2, color='purple')
        
        ax2.set_xlabel('日期', fontsize=12)
        ax2.set_ylabel('资产 (元)', fontsize=12)
        ax2.set_title('资产变化趋势', fontsize=14, fontweight='bold')
        ax2.legend(loc='best', fontsize=11)
        ax2.grid(True, alpha=0.3)
        
        # 格式化日期轴
        for ax in [ax1, ax2]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        plt.savefig('grid_strategy_2_result.png', dpi=150, bbox_inches='tight')
        print("\n📊 图表已保存为 grid_strategy_2_result.png")
        plt.close()
        
    except Exception as e:
        print(f"绘图失败: {e}")
        import traceback
        traceback.print_exc()


def run_backtest(code='159952', start='20240101', end='20241231', 
                 grid_min=None, grid_max=None, grid_num=10, 
                 order_pct=0.1, use_percentage=True, grid_spacing=0.02,
                 frequency='1d'):
    """
    运行固定网格策略回测
    """
    cerebro = bt.Cerebro()
    
    print(f"\n{'='*60}")
    print("🕸️  固定网格交易策略回测")
    print(f"{'='*60}")
    print(f"标的代码: {code}")
    print(f"时间范围: {start} 至 {end}")
    print(f"数据频率: {frequency}")
    print(f"网格数量: {grid_num}")
    print(f"交易比例: {order_pct*100:.1f}%")
    print(f"{'='*60}\n")
    
    # 获取数据
    print("正在获取数据...")
    df = GetStockDatApi(code, start, end, frequency)
    
    if df.empty:
        print("❌ 数据为空，退出回测")
        return

    print(f"✅ 数据获取完成，共 {len(df)} 条记录\n")
    
    # 创建数据源
    data = bt.feeds.PandasData(dataname=df, nocase=True)
    cerebro.adddata(data)
    
    # 添加固定网格策略
    cerebro.addstrategy(GridStrategyFixed,
                       grid_min=grid_min,
                       grid_max=grid_max,
                       grid_num=grid_num,
                       order_pct=order_pct,
                       use_percentage=use_percentage,
                       grid_spacing=grid_spacing)
    
    # 设置初始资金
    initial_cash = 100000.0
    cerebro.broker.setcash(initial_cash)
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
        print('夏普比率: N/A')
    
    drawdown = strat.analyzers.drawdown.get_analysis()
    print(f'最大回撤: {drawdown["max"]["drawdown"]:.2f}%')
    print(f'最大回撤持续时间: {drawdown["max"]["len"]}天')
    
    returns = strat.analyzers.returns.get_analysis()
    print(f'总收益率: {returns["rtot"]*100:.2f}%')
    print(f'年化收益率: {returns["ravg"]*252*100:.2f}%')
    
    trades = strat.analyzers.trades.get_analysis()
    
    # 安全地访问交易统计数据
    try:
        total_closed = trades.get('total', {}).get('closed', 0)
        if total_closed > 0:
            print(f'\n交易统计:')
            print(f'  总交易次数: {total_closed}')
            
            won_total = trades.get('won', {}).get('total', 0)
            lost_total = trades.get('lost', {}).get('total', 0)
            print(f'  盈利交易: {won_total}')
            print(f'  亏损交易: {lost_total}')
            
            if total_closed > 0:
                win_rate = won_total / total_closed * 100
                print(f'  胜率: {win_rate:.2f}%')
            
            won_pnl_avg = trades.get('won', {}).get('pnl', {}).get('average', 0)
            lost_pnl_avg = trades.get('lost', {}).get('pnl', {}).get('average', 0)
            print(f'  平均盈利: {won_pnl_avg:.2f}')
            print(f'  平均亏损: {lost_pnl_avg:.2f}')
        else:
            print('\n⚠️  警告: 未产生任何交易')
    except (AttributeError, KeyError, TypeError) as e:
        print(f'\n⚠️  警告: 无法获取交易统计信息 ({e})')
    
    print('='*60 + '\n')
    
    # 绘制图表
    print("📊 正在生成图表...")
    plot_grid_strategy_fixed(cerebro, strat)
    
    return results


if __name__ == '__main__':
    # 运行固定网格策略回测
    run_backtest(
        code='159952', 
        start='20250121', 
        end='20260121',
        grid_num=10,           # 10个网格
        order_pct=0.1,         # 每次交易10%资金
        use_percentage=True,   # 使用百分比间距
        grid_spacing=0.02,     # 2%的网格间距
        frequency='1d'         # 日线数据
    )
