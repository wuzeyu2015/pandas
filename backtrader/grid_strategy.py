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
            # 如果已经有sz/sh前缀，去掉它
            clean_code = code[2:]
            if clean_code.startswith('6'):
                jq_code = f"{clean_code}.XSHG"
            else:
                jq_code = f"{clean_code}.XSHE"
        else:
            jq_code = f"{code}.XSHE"  # 深圳交易所
    else:
        jq_code = code

    try:
        # 获取数据
        df = jqdatasdk.get_price(
            jq_code, 
            start_date=start, 
            end_date=end,
            fq='post',  # 后复权
            frequency='15m',
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


class GridStrategy(bt.Strategy):
    """
    网格交易策略 - 移动基准价版本
    
    核心逻辑：
    1. 设置初始基准价和格子大小
    2. 当价格下跌一个格子时，买入固定份数，并下移基准价
    3. 当价格上涨一个格子时，卖出固定份数，并上移基准价
    4. 每天收盘后强制更新基准价为收盘价
    """
    
    params = (
        ('grid_size', 0.05),         # 格子大小（元）
        ('trade_shares', 15000),     # 每次交易的份数
        ('position_max', 150000),    # 最大持仓限制
        ('position_min', 0),         # 最小持仓限制
        ('initial_available', 24000), # 初始可用资金
        ('initial_position', 15000),  # 初始持仓
    )
    
    def __init__(self):
        # 价格序列
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        
        # 订单管理
        self.order = None
        
        # 网格策略状态变量
        self.base_price = None           # 基准价
        self.available = self.params.initial_available  # 可用资金
        self.position_count = self.params.initial_position  # 持仓数量
        self.max_position = self.position_count  # 记录最大持仓
        self.min_available = self.available  # 记录最小可用资金
        self.total_input = None          # 总投入成本
        self.buys = 0                    # 买入次数
        self.sells = 0                   # 卖出次数
        self.first_day_open = None       # 首日开盘价
        self.last_day_close = None       # 最后一日收盘价
        self.to_buy = True               # 是否允许买入
        self.to_sell = True              # 是否允许卖出
        
        # 记录每日收盘价用于盘尾更新
        self.current_date = None
        self.last_close_of_day = None
        
        # 记录交易历史用于绘图
        self.trade_history = []  # [(datetime, price, type, base_price), ...]
        self.base_price_history = []  # [(datetime, base_price), ...]
    
    def log(self, txt, dt=None, doprint=False):
        """日志函数"""
        if doprint:
            dt = dt or self.datas[0].datetime.datetime(0)
            print('%s, %s' % (dt.strftime('%Y-%m-%d %H:%M'), txt))

    def notify_order(self, order):
        """订单状态处理"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'✅ 买入成交: {order.executed.size}份 @ {order.executed.price:.3f}元', 
                        doprint=True)
                self.buys += 1
            else:
                self.log(f'✅ 卖出成交: {order.executed.size}份 @ {order.executed.price:.3f}元', 
                        doprint=True)
                self.sells += 1
        
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
        current_dt = self.datas[0].datetime.datetime(0)
        current_date = current_dt.date()
        close = self.dataclose[0]
        open_price = self.dataopen[0]
        
        # 初始化基准价（使用首日开盘价）
        if self.base_price is None:
            self.base_price = open_price
            self.first_day_open = open_price
            self.total_input = self.available + self.position_count * self.base_price
            
            self.log('='*60, doprint=True)
            self.log('🎯 网格策略启动', doprint=True)
            self.log(f'初始账户余额: {self.available:,.2f} 元', doprint=True)
            self.log(f'初始持仓: {self.position_count} 份', doprint=True)
            self.log(f'总成本: {self.total_input:.3f} 元', doprint=True)
            self.log(f'初始基准价: {self.base_price:.3f}元', doprint=True)
            self.log(f'格子大小: {self.params.grid_size:.4f} 元', doprint=True)
            self.log(f'交易份数: {self.params.trade_shares} 份', doprint=True)
            self.log('='*60, doprint=True)
            return
        
        # 检测是否是新的一天
        is_new_day = (current_date != self.current_date)
        if is_new_day and self.current_date is not None:
            # 盘尾更新基准价为前一天收盘价
            if self.last_close_of_day is not None:
                old_base = self.base_price
                self.base_price = self.last_close_of_day
                self.log(f'📅 盘尾更新基准价: {old_base:.3f} -> {self.base_price:.3f}', doprint=True)
                
                # 记录基准价变化
                self.base_price_history.append((current_dt - pd.Timedelta(days=1), self.last_close_of_day))
        
        self.current_date = current_date
        self.last_close_of_day = close
        
        # 每天记录基准价
        self.base_price_history.append((current_dt, self.base_price))
        
        # 如果有未完成订单，等待
        if self.order:
            return
        
        # === 网格交易逻辑 ===
        
        # 计算买入触发价：基准价 - 格子大小
        buy_trigger = self.base_price - self.params.grid_size
        
        # 计算卖出触发价：基准价 + 格子大小
        sell_trigger = self.base_price + self.params.grid_size
        
        # 检查是否触发买入
        if close <= buy_trigger and self.to_buy:
            # 检查资金和持仓限制
            trade_amount = self.params.trade_shares * buy_trigger
            
            if trade_amount > self.available:
                self.log(f'⚠️  资金不足，无法买入 @ {buy_trigger:.3f}元', doprint=True)
                self.to_buy = False
            elif self.position_count >= self.params.position_max:
                self.log(f'⚠️  持仓超过限制，无法买入 @ {buy_trigger:.3f}元', doprint=True)
                self.to_buy = False
            else:
                # 执行买入
                self.to_sell = True
                self.order = self.buy(size=self.params.trade_shares, price=buy_trigger)
                
                # 更新状态
                self.available -= trade_amount
                self.position_count += self.params.trade_shares
                self.max_position = max(self.max_position, self.position_count)
                self.min_available = min(self.min_available, self.available)
                
                # 更新基准价
                old_base = self.base_price
                self.base_price = buy_trigger
                self.log(f'📉 买入触发！更新基准价: {old_base:.3f} -> {self.base_price:.3f}', doprint=True)
                
                # 记录交易
                self.trade_history.append((current_dt, buy_trigger, 'BUY', self.base_price))
        
        # 检查是否触发卖出
        elif close >= sell_trigger and self.to_sell:
            # 检查持仓限制
            if self.position_count < self.params.trade_shares:
                self.log(f'⚠️  持仓不够，无法卖出 @ {sell_trigger:.3f}元', doprint=True)
                self.to_sell = False
            elif self.position_count <= self.params.position_min:
                self.log(f'⚠️  持仓低于限制，无法卖出 @ {sell_trigger:.3f}元', doprint=True)
                self.to_sell = False
            else:
                # 执行卖出
                self.to_buy = True
                self.order = self.sell(size=self.params.trade_shares, price=sell_trigger)
                
                # 计算交易金额
                trade_amount = self.params.trade_shares * sell_trigger
                
                # 更新状态
                self.available += trade_amount
                self.position_count -= self.params.trade_shares
                
                # 更新基准价
                old_base = self.base_price
                self.base_price = sell_trigger
                self.log(f'📈 卖出触发！更新基准价: {old_base:.3f} -> {self.base_price:.3f}', doprint=True)
                
                # 记录交易
                self.trade_history.append((current_dt, sell_trigger, 'SELL', self.base_price))


def plot_grid_strategy(cerebro, strategy):
    """
    绘制网格策略图表
    
    Args:
        cerebro: Cerebro引擎实例
        strategy: 策略实例
    """
    try:
        import matplotlib.dates as mdates
        
        # 获取数据
        data = cerebro.datas[0]
        
        # 安全地获取日期和价格数据
        num_bars = len(strategy.base_price_history)
        if num_bars == 0:
            print("⚠️  警告: 没有历史数据用于绘图")
            return
        
        dates = []
        closes = []
        base_prices = []
        
        for dt, base_price in strategy.base_price_history:
            try:
                # 找到对应的收盘价
                idx = None
                for i in range(len(data)):
                    bar_dt = data.datetime.datetime(i - len(data))
                    if bar_dt.date() == dt.date():
                        idx = i - len(data)
                        break
                
                if idx is not None:
                    dates.append(dt)
                    closes.append(data.close[idx])
                    base_prices.append(base_price)
            except:
                continue
        
        if not dates:
            print("⚠️  警告: 无法获取绘图数据")
            return
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(20, 12), 
                                        gridspec_kw={'height_ratios': [3, 1]})
        
        # === 上图：价格和基准价 ===
        ax1.plot(dates, closes, 'b-', linewidth=1.5, label='收盘价', alpha=0.7)
        ax1.plot(dates, base_prices, 'r--', linewidth=1.5, label='基准价', alpha=0.7)
        
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
        
        ax1.set_title('网格交易策略 - 价格走势与交易信号', fontsize=16, fontweight='bold')
        ax1.set_ylabel('价格 (元)', fontsize=12)
        ax1.legend(loc='best', fontsize=11)
        ax1.grid(True, alpha=0.3)
        
        # === 下图：持仓和资金变化 ===
        # 计算每个时间点的持仓价值
        position_values = []
        total_values = []
        
        initial_available = strategy.params.initial_available
        initial_position = strategy.params.initial_position
        
        for i, (dt, close) in enumerate(zip(dates, closes)):
            # 简化：假设线性变化（实际应该逐笔计算）
            progress = i / max(len(dates) - 1, 1)
            
            # 估算当前持仓和资金
            current_position = initial_position + (strategy.position_count - initial_position) * progress
            current_available = initial_available + (strategy.available - initial_available) * progress
            
            position_values.append(current_position * close)
            total_values.append(current_available + current_position * close)
        
        ax2.plot(dates, position_values, 'orange', linewidth=1.5, label='持仓价值', alpha=0.7)
        ax2.plot(dates, total_values, 'purple', linewidth=1.5, label='总资产', alpha=0.7)
        ax2.fill_between(dates, total_values, alpha=0.2, color='purple')
        
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
        plt.savefig('grid_strategy_result.png', dpi=150, bbox_inches='tight')
        print("\n📊 图表已保存为 grid_strategy_result.png")
        plt.close()
        
    except Exception as e:
        print(f"绘图失败: {e}")
        import traceback
        traceback.print_exc()


def run_backtest(code='159952', start='20250121', end='20260128', 
                 grid_size=0.05, trade_shares=15000, position_max=150000, position_min=0,
                 initial_available=24000, initial_position=15000):
    """
    运行网格策略回测
    
    Args:
        code: 股票代码（如 '510300' 或 '159952'）
        start: 开始日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        end: 结束日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        grid_size: 格子大小（元）
        trade_shares: 每次交易的份数
        position_max: 最大持仓限制
        position_min: 最小持仓限制
        initial_available: 初始可用资金
        initial_position: 初始持仓
    """
    try:
        # 获取数据
        data = GetStockDatApi(code, start, end)
        if data.empty:
            print("⚠️  警告: 未获取到数据，无法进行回测")
            return
        
        # 创建Cerebro引擎
        cerebro = bt.Cerebro()
        
        # 添加数据
        data = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(data)
        
        # 添加策略
        cerebro.addstrategy(GridStrategy, grid_size=grid_size, trade_shares=trade_shares,
                            position_max=position_max, position_min=position_min,
                            initial_available=initial_available, initial_position=initial_position)
        
        # 设置初始资金
        cerebro.broker.setcash(initial_available)
        
        # 设置佣金
        cerebro.broker.setcommission(commission=0.0003)
        
        # 打印初始状态
        print(f'初始账户余额: {cerebro.broker.getvalue():,.2f} 元')
        
        # 运行回测并获取策略实例
        results = cerebro.run()
        strat = results[0]
        
        # 打印最终状态
        final_value = cerebro.broker.getvalue()
        print(f'最终账户余额: {final_value:,.2f} 元')
        print(f'净盈亏: {final_value - initial_available:,.2f} 元')
        print('='*60)
        
        # 绘制图表
        print("📊 正在生成图表...")
        plot_grid_strategy(cerebro, strat)
        
    except Exception as e:
        print(f"回测失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    run_backtest(code='159952',
                 start='20251023',
                 end='20260128', 
                 grid_size=0.05,
                 trade_shares=5000,
                 position_max=150000,
                 position_min=0,
                 initial_available=24000,
                 initial_position=15000)
