
import backtrader as bt
import jqdatasdk
import pandas as pd
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 配置中文字体支持 - 使用系统已安装的 Noto Sans CJK 字体
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'SimHei', 'DejaVu Sans']
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
        # 获取日线数据（改为 '1d' 以匹配双均线策略的常规用法）
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
    # JQData 返回的 DataFrame 索引通常是 DatetimeIndex
    if isinstance(df.index, pd.DatetimeIndex):
        # 已经是时间索引，无需处理
        pass
    else:
        # 如果时间在列中（可能是 'time' 或 'day'）
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

class dua_ma_strategy(bt.Strategy):
    # 全局设定交易策略的参数
    params=(
            ('ma_short', 5),   # 短期均线：5日
            ('ma_long', 20),   # 长期均线：20日
           )
    
    def __init__(self):
        # 指定价格序列
        self.dataclose = self.datas[0].close
        # 初始化交易指令、买卖价格和手续费
        self.order = None
        self.buyprice = None
        self.buycomm = None

        # 添加移动均线指标
        # 短期移动平均线（日线数据下为30日均线）
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_short)
        # 长期移动平均线（日线数据下为60日均线）
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=self.params.ma_long)

    def log(self, txt, dt=None, doprint=False):
        # 日志函数，用于统一输出日志格式
        if doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def notify_order(self, order):
        """
        订单状态处理
        Arguments:
            order {object} -- 订单状态
        """
        if order.status in [order.Submitted, order.Accepted]:
            # 如订单已被处理，则不用做任何事情
            return
        
        # 检查订单是否完成
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
                self.log(f'买入: 价格 {order.executed.price:.2f}, 成本 {order.executed.value:.2f}, 手续费 {order.executed.comm:.2f}', doprint=True)
            else:
                self.log(f'卖出: 价格 {order.executed.price:.2f}, 成本 {order.executed.value:.2f}, 手续费 {order.executed.comm:.2f}', doprint=True)
            self.bar_executed = len(self)
        
        # 订单因为缺少资金之类的原因被拒绝执行
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('订单取消/保证金不足/拒绝', doprint=True)
        
        # 订单状态处理完成，设为空
        self.order = None

    # 记录交易收益情况
    def notify_trade(self, trade):
        """
        交易成果
        Arguments:
            trade {object} -- 交易状态
        """
        if not trade.isclosed:
            return
        # 显示交易的毛利率和净利润
        self.log(f'交易利润: 毛利润 {trade.pnl:.2f}, 净利润 {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        # 记录收盘价
        # self.log('Close, %.2f' % self.dataclose[0])
        
        if self.order:  # 是否有指令等待执行
            return
        
        # 是否持仓
        if not self.position:  # 没有持仓
            # 执行买入条件判断：短期均线上穿长期均线（金叉）
            if self.sma_short[0] > self.sma_long[0] and self.sma_short[-1] <= self.sma_long[-1]:
                self.order = self.buy()  # 执行买入
                self.log(f'买入信号, 收盘价: {self.dataclose[0]:.2f}', doprint=True)
        else:
            # 执行卖出条件判断：短期均线下穿长期均线（死叉）
            if self.sma_short[0] < self.sma_long[0] and self.sma_short[-1] >= self.sma_long[-1]:
                self.order = self.sell()  # 执行卖出
                self.log(f'卖出信号, 收盘价: {self.dataclose[0]:.2f}', doprint=True)

    # 回测结束后输出
    def stop(self):
        self.log(f'双均线策略 (短期={self.params.ma_short}, 长期={self.params.ma_long}) 最终资金: {self.broker.getvalue():.2f}', doprint=True)


def run_backtest(code='159952', start='20240419', end='20250419'):
    cerebro = bt.Cerebro()
    
    print(f"正在获取 {code} 的数据...")
    df = GetStockDatApi(code, start, end)
    
    if df.empty:
        print("数据为空，退出回测")
        return

    print(f"数据获取完成，共 {len(df)} 条记录")
    
    # 创建数据源
    # nocase=True 允许列名大小写不敏感
    data = bt.feeds.PandasData(dataname=df, nocase=True)
    
    cerebro.adddata(data)
    cerebro.addstrategy(dua_ma_strategy)
    
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.001)
    
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    print('=' * 50)
    print(f'初始资金: {cerebro.broker.getvalue():.2f}')
    results = cerebro.run()
    print(f'最终资金: {cerebro.broker.getvalue():.2f}')
    print('=' * 50)
    
    strat = results[0]
    print('\n--- 分析结果 ---')
    print('Sharpe Ratio:', strat.analyzers.sharpe.get_analysis())
    
    drawdown = strat.analyzers.drawdown.get_analysis()
    print('最大回撤: %.2f%%' % drawdown['max']['drawdown'])
    
    returns = strat.analyzers.returns.get_analysis()
    print('总收益率: %.2f%%' % (returns['rtot'] * 100))
    print('年化收益率: %.2f%%' % (returns['ravg'] * 252 * 100)) # 假设一年252个交易日
    
    # 保存图表而不是显示，因为使用了 Agg 后端
    try:
        import matplotlib.dates as mdates
        
        # 调整绘图参数以解决紧凑问题并显示日期
        cerebro.plot(
            dpi=600,
            numfigs=2,
            iplot=False, 
            figsize=(200, 9),  # 增大图形尺寸 (宽, 高)
            style='line', # K线图风格
            barup='red', bardown='green', # A股风格：红涨绿跌
            volup='red', voldown='green',
            subplot_params={
                'top': 0.95,    # 顶部边距
                'bottom': 0.15, # 底部边距（留更多空间给日期标签）
                'left': 0.08,   # 左边距
                'right': 0.95,  # 右边距
                'hspace': 0.5,  # 子图垂直间距
            },
            # 关键：配置日期轴格式化器
            xstart=None, xend=None,
            formatter=mdates.DateFormatter('%Y-%m-%d'),
            xtickrotation=45, # 旋转日期标签以防重叠
        )
        
        # 获取当前 figure 对象并进一步调整
        fig = plt.gcf()
        ax = fig.axes[0] # 获取主坐标轴
        
        # 确保日期标签显示清晰
        for label in ax.get_xticklabels():
            label.set_ha('right')
            label.set_fontsize(8)
            
        plt.savefig('dua_ma_strategy.png', dpi=150, bbox_inches='tight')
        print("\n图表已保存为 dua_ma_strategy.png")
    except Exception as e:
        print(f"绘图失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # 使用配置文件中的基金代码，注意：根据JQData权限调整日期范围
    run_backtest(code='159952', start='20240121', end='20260121')
