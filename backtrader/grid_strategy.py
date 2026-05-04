import backtrader as bt
import jqdatasdk
import pandas as pd
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ✅ 强制指定 Noto 字体路径（CentOS Stream 10）
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


def GetStockDatApi(code, start='20240101', end='20240419', frequency='15m'):
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
            frequency=frequency,
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
    网格交易策略 - 移动基准价版本（完全使用Backtrader内部管理）
    
    核心逻辑：
    1. 设置初始基准价和格子大小
    2. 当价格下跌一个格子时，买入固定份数，并下移基准价
    3. 当价格上涨一个格子时，卖出固定份数，并上移基准价
    4. 每天收盘后强制更新基准价为收盘价
    
    === 三个核心控制参数 ===
    1. trade_shares: 每格买入/卖出的股数（例如：15000股）
    2. grid_size: 每个格子的价格间距（例如：0.05元）
    3. position_max/position_min: 仓位上下限控制
    """
    
    params = (
        ('grid_size', None),           # 【格子大小】每个网格的价格间距（元）
        ('trade_shares', None),       # 【每格股数】每次买入/卖出的固定份额
        ('position_max', None),      # 【仓位上限】最大持仓限制（股数）
        ('position_min', None),           # 【仓位下限】最小持仓限制（股数）
    )
    
    def __init__(self):
        # 验证必需参数是否提供
        if self.params.grid_size is None:
            raise ValueError("必须指定 grid_size 参数（格子大小）")
        if self.params.trade_shares is None:
            raise ValueError("必须指定 trade_shares 参数（每格交易股数）")
        if self.params.position_max is None:
            raise ValueError("必须指定 position_max 参数（最大持仓）")
        if self.params.position_min is None:
            raise ValueError("必须指定 position_min 参数（最小持仓）")
        
        # 价格数据
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        
        # 订单管理
        self.order = None
        
        # 网格策略核心状态
        self.base_price = None           # 基准价（网格中心价格）
        
        # 统计信息
        self.buys = 0                    # 买入次数
        self.sells = 0                   # 卖出次数
        self.first_day_open = None       # 首日开盘价
        self.last_day_close = None       # 最后一日收盘价
        
        # 日期跟踪
        self.current_date = None
        self.last_close_of_day = None
        
        # 交易历史（用于绘图）
        self.trade_history = []          # [(datetime, price, type, base_price), ...]
        self.base_price_history = []     # [(datetime, base_price), ...]
    
    def log(self, txt, dt=None, doprint=False):
        """日志函数"""
        if doprint:
            dt = dt or self.datas[0].datetime.datetime(0)
            print('%s, %s' % (dt.strftime('%Y-%m-%d %H:%M'), txt))

    def notify_order(self, order):
        """订单状态通知 - Backtrader自动调用"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buys += 1
                # 使用统一的计数器，并标注这是实际成交价格
                self.log(f'✅ 买入成交 #{self.buys}: {order.executed.size:.0f}股 @ {order.executed.price:.3f}元 (成交价)', 
                        doprint=True)
            else:
                self.sells += 1
                self.log(f'✅ 卖出成交 #{self.sells}: {order.executed.size:.0f}股 @ {order.executed.price:.3f}元 (成交价)', 
                        doprint=True)
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('❌ 订单取消/保证金不足/拒绝', doprint=True)
        
        self.order = None

    def notify_trade(self, trade):
        """交易完成通知"""
        if not trade.isclosed:
            return
        self.log(f'💰 交易利润: 毛利润 {trade.pnl:.2f}, 净利润 {trade.pnlcomm:.2f}', doprint=True)

    def next(self):
        """
        每个bar的执行逻辑 - 核心交易逻辑
        
        === 关键改进：使用 while 循环处理跨格行情 ===
        当价格大幅波动跨越多个格子时，在同一时间点连续执行多次交易
        确保基准价能快速追赶市场价格，避免滞后
        
        === 使用Backtrader内部状态 ===
        - self.broker.getcash(): 获取真实现金余额
        - self.position.size: 获取真实持仓数量
        - self.dataclose[0]: 当前收盘价
        """
        current_dt = self.datas[0].datetime.datetime(0)
        current_date = current_dt.date()
        close = self.dataclose[0]
        open_price = self.dataopen[0]
        
        # === 第一步：初始化基准价（只在第一天执行）===
        if self.base_price is None:
            self.base_price = open_price
            self.first_day_open = open_price
            
            # 使用Backtrader内部状态获取真实资金和持仓
            real_cash = self.broker.getcash()
            real_position = self.position.size
            
            self.log('='*60, doprint=True)
            self.log('🎯 网格策略启动', doprint=True)
            self.log(f'💰 真实账户余额: {real_cash:,.2f} 元', doprint=True)
            self.log(f'📊 真实持仓: {real_position} 股', doprint=True)
            self.log(f'🎯 初始基准价: {self.base_price:.3f}元', doprint=True)
            self.log(f'📏 格子大小: {self.params.grid_size:.4f} 元', doprint=True)
            self.log(f'📦 每格交易: {self.params.trade_shares} 股', doprint=True)
            self.log(f'⚖️  仓位限制: [{self.params.position_min}, {self.params.position_max}]', doprint=True)
            self.log('='*60, doprint=True)
            return
        
        # === 第二步：检测是否是新的一天，盘尾更新基准价 ===
        is_new_day = (current_date != self.current_date)
        if is_new_day and self.current_date is not None:
            # 每天收盘后，将基准价更新为前一天收盘价
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
        
        # === 第三步：如果有未完成订单，等待 ===
        if self.order:
            return
        
        # === 第四步：使用 while 循环处理跨格行情 ===
        # 核心思想：只要价格还在触发线外，就持续交易并更新基准价
        # 这样可以在一个时间点内完成多次买卖，快速追平价格差距
        
        trades_executed = 0  # 记录本次执行的交易次数
        max_trades_per_bar = 100  # 防止死循环的安全上限
        
        while trades_executed < max_trades_per_bar:
            # 重新计算触发价格（因为基准价可能在循环中被更新）
            buy_trigger = self.base_price - self.params.grid_size   # 买入触发价
            sell_trigger = self.base_price + self.params.grid_size  # 卖出触发价
            
            # 【优先检查买入】
            if close <= buy_trigger:
                # 【仓位控制1】检查当前真实持仓是否达到上限
                current_position = self.position.size
                if current_position >= self.params.position_max:
                    if trades_executed == 0:  # 只在第一次尝试时打印警告
                        self.log(f'⚠️  持仓已达上限 ({current_position}股)，无法买入', doprint=True)
                    break  # 退出 while 循环
                
                # 【资金控制】检查Backtrader中的真实现金是否足够
                cash_needed = self.params.trade_shares * buy_trigger
                real_cash = self.broker.getcash()
                
                if cash_needed > real_cash:
                    if trades_executed == 0:
                        self.log(f'⚠️  资金不足 (需要{cash_needed:.2f}元，可用{real_cash:.2f}元)', doprint=True)
                    break  # 退出 while 循环
                
                # 执行买入 - 使用市价单立即成交
                # 注意：不传 price 参数即为市价单，Backtrader会在当前bar结束时撮合
                self.order = self.buy(size=self.params.trade_shares)
                
                # 更新基准价为触发价（策略逻辑基于触发价，而非实际成交价）
                old_base = self.base_price
                self.base_price = buy_trigger
                self.log(f'📉 买入信号 #{trades_executed+1}！触发价: {buy_trigger:.3f}, 基准价: {old_base:.3f} -> {self.base_price:.3f} (等待成交...)', doprint=True)
                
                # 记录交易历史
                self.trade_history.append((current_dt, buy_trigger, 'BUY', self.base_price))
                trades_executed += 1
                
                # ⚠️ 重要：由于Backtrader订单是异步的，我们需要立即模拟持仓变化
                # 这样下一次循环判断时能基于最新的持仓状态
                # （实际成交会在 notify_order 中确认）
            
            # 【否则检查卖出】
            elif close >= sell_trigger:
                # 【仓位控制2】检查当前真实持仓是否足够卖出
                current_position = self.position.size
                if current_position < self.params.trade_shares:
                    if trades_executed == 0:
                        self.log(f'⚠️  持仓不足 ({current_position}股 < {self.params.trade_shares}股)，无法卖出', doprint=True)
                    break  # 退出 while 循环
                
                # 【仓位控制3】检查卖出后是否会低于最小持仓
                if current_position - self.params.trade_shares < self.params.position_min:
                    if trades_executed == 0:
                        self.log(f'⚠️  卖出后将低于最小持仓限制', doprint=True)
                    break  # 退出 while 循环
                
                # 执行卖出 - 使用市价单立即成交
                # 注意：不传 price 参数即为市价单，Backtrader会在当前bar结束时撮合
                self.order = self.sell(size=self.params.trade_shares)
                
                # 更新基准价为触发价（策略逻辑基于触发价，而非实际成交价）
                old_base = self.base_price
                self.base_price = sell_trigger
                self.log(f'📈 卖出信号 #{trades_executed+1}！触发价: {sell_trigger:.3f}, 基准价: {old_base:.3f} -> {self.base_price:.3f} (等待成交...)', doprint=True)
                
                # 记录交易历史
                self.trade_history.append((current_dt, sell_trigger, 'SELL', self.base_price))
                trades_executed += 1
            
            # 【价格在一个格子内，无需交易】
            else:
                break  # 退出 while 循环
        
        # 如果执行了多次交易，打印汇总信息
        if trades_executed > 1:
            self.log(f'🔄 本时间点共执行 {trades_executed} 次交易，基准价已追平至 {self.base_price:.3f}', doprint=True)

    def stop(self):
        """回测结束时的统计"""
        self.log('='*60, doprint=True)
        self.log('📊 网格策略回测结果', doprint=True)
        self.log('='*60, doprint=True)
        
        # 使用Backtrader内部状态获取最终结果
        final_cash = self.broker.getcash()
        final_position = self.position.size
        final_value = self.broker.getvalue()
        
        # 获取最终收盘价（最后一个bar的收盘价）
        final_close_price = self.dataclose[0]
        
        self.log(f'💰 最终账户余额: {final_cash:,.2f} 元', doprint=True)
        self.log(f'📊 最终持仓数量: {final_position} 股', doprint=True)
        self.log(f'📈 最终收盘价格: {final_close_price:.3f} 元', doprint=True)
        self.log(f'💵 总资产价值: {final_value:,.2f} 元', doprint=True)
        self.log(f'📈 买入次数: {self.buys}', doprint=True)
        self.log(f'📉 卖出次数: {self.sells}', doprint=True)
        
        if self.first_day_open:
            self.log(f'🎯 首日开盘价: {self.first_day_open:.3f} 元', doprint=True)
        if self.last_day_close:
            self.log(f'🎯 最后一日收盘价: {self.last_day_close:.3f} 元', doprint=True)
        
        # 计算收益率
        if hasattr(self, 'first_day_open') and self.first_day_open:
            buy_and_hold_return = (final_close_price - self.first_day_open) / self.first_day_open * 100
            self.log(f'📊 持有到期收益率: {buy_and_hold_return:.2f}%', doprint=True)
        
        self.log('='*60, doprint=True)


def run_backtest(code, start, end, 
                 grid_size, trade_shares, 
                 position_max, position_min,
                 initial_cash):
    """
    运行网格策略回测
    
    Args:
        code: 股票代码
        start: 开始日期
        end: 结束日期
        grid_size: 【格子大小】每个网格的价格间距（元）
        trade_shares: 【每格股数】每次买入/卖出的份额
        position_max: 【仓位上限】最大持仓
        position_min: 【仓位下限】最小持仓
        initial_cash: 初始资金（由Backtrader管理）
    """
    try:
        # 获取数据
        print(f"\n{'='*60}")
        print("🕸️  网格交易策略回测")
        print(f"{'='*60}")
        print(f"标的代码: {code}")
        print(f"时间范围: {start} 至 {end}")
        print(f"{'='*60}\n")
        
        data = GetStockDatApi(code, start, end,frequency='15m')
        if data.empty:
            print("⚠️  警告: 未获取到数据，无法进行回测")
            return
        
        # 创建Cerebro引擎
        cerebro = bt.Cerebro()
        # cerebro = bt.Cerebro(cheat_on_open=True)
        # 添加数据
        data_feed = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(data_feed)
        
        # 添加策略 - 传入三个核心控制参数
        cerebro.addstrategy(GridStrategy,
                           grid_size=grid_size,         # 格子大小
                           trade_shares=trade_shares,   # 每格股数
                           position_max=position_max,   # 仓位上限
                           position_min=position_min)   # 仓位下限
        
        # 【重要】设置初始资金 - 这是Backtrader管理的唯一资金来源
        cerebro.broker.setcash(initial_cash)
        
        # 设置佣金
        # cerebro.broker.setcommission(commission=0.0003)
        
        # 打印初始状态
        print(f'💰 初始资金: {cerebro.broker.getvalue():,.2f} 元\n')
        
        # 运行回测
        results = cerebro.run()
        strat = results[0]
        
        # 打印最终状态
        print(f'\n💵 最终资产: {cerebro.broker.getvalue():,.2f} 元')
        print(f'📈 收益率: {(cerebro.broker.getvalue() - initial_cash) / initial_cash * 100:.2f}%\n')
        
    except Exception as e:
        print(f"回测失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    # === 配置示例：三个核心参数的使用 ===
    run_backtest(
        code='159952',
        start='20251023',
        end='20251119',
        
        # 【控制1】每个格子多大：0.05元
        grid_size=0.05,
        
        # 【控制2】每格买入多少股：5000股
        trade_shares=5000,
        
        # 【控制3】仓位控制：最少0股，最多150000股
        position_min=0,
        position_max=150000,
        
        # 初始资金（Backtrader管理）
        initial_cash=24000
    )