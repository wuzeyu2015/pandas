import datetime

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


def GetStockDatApi(code, start, end, frequency):
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
    网格交易策略 - 移动基准价版本
    
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
        ('trade_shares', None),        # 【每格股数】每次买入/卖出的固定份额
        ('position_max', None),        # 【仓位上限】最大持仓限制（股数）
        ('position_min', None),        # 【仓位下限】最小持仓限制（股数）
    )
    
    def __init__(self):
        """初始化策略参数和状态变量"""
        # 验证必需参数
        self._validate_params()
        
        # 数据引用
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        
        # 订单管理
        self.order = None
        
        # 网格核心状态
        self.base_price = None
        
        # 统计信息
        self.buys = 0
        self.sells = 0
        self.first_day_open = None
        self.last_day_close = None

        
        # 交易历史（用于绘图）
        self.trade_history = []
    def _validate_params(self):
        """验证策略参数完整性"""
        if self.params.grid_size is None:
            raise ValueError("必须指定 grid_size 参数（格子大小）")
        if self.params.trade_shares is None:
            raise ValueError("必须指定 trade_shares 参数（每格交易股数）")
        if self.params.position_max is None:
            raise ValueError("必须指定 position_max 参数（最大持仓）")
        if self.params.position_min is None:
            raise ValueError("必须指定 position_min 参数（最小持仓）")
    
    def log(self, txt, dt=None, doprint=False):
        """日志输出函数"""
        if doprint:
            dt = dt or self.datas[0].datetime.datetime(0)
            print('%s, %s' % (dt.strftime('%Y-%m-%d %H:%M'), txt))

    def notify_order(self, order):
        """订单状态通知（静默处理，仅计数）"""
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.buys += 1
                self.log(
                    f'✅ 买入成交 | 价格: {order.executed.price:.3f} | '
                    f'数量: {order.executed.size} | '
                    f'金额: {order.executed.value:.2f}',
                    doprint=True)
            else:
                self.sells += 1
                self.log(
                    f'✅ 卖出成交 | 价格: {order.executed.price:.3f} | '
                    f'数量: {order.executed.size} | '
                    f'金额: {order.executed.value:.2f}',
                    doprint=True
                    )
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('❌ 订单取消/保证金不足/拒绝', doprint=True)
        
        self.order = None

    # def notify_trade(self, trade):
    #     """交易完成通知"""
    #     if not trade.isclosed:
    #         return
    #     self.log(f'💰 交易利润: 毛利润 {trade.pnl:.2f}, 净利润 {trade.pnlcomm:.2f}', doprint=True)

    
    def next(self):
        """
        每个Bar执行（标准模式）
        
        职责：
        - 初始化基准价（首个Bar）
        - 检测交易信号并提交订单
        - 盘尾更新基准价
        - 记录每日基准价历史
        """
        # 1. 初始化基准价（仅在第一个bar执行）
        self._initialize_base_price()
        
        # 2. 检查是否有未完成订单
        if self.order:
            return
        
        # 3. 执行网格交易逻辑（使用收盘价决策）
        self._execute_grid_trading(is_open_session=False)
        
        # 4. 盘尾更新基准价
        self._update_base_price_at_end_of_day()
    
    def _initialize_base_price(self):
        """
        初始化基准价（仅在第一个bar执行）
        
        Returns:
            bool: True表示已初始化，False表示无需初始化
        """
        if self.base_price is not None:
            # 已经初始化过了，跳过
            return False
        
        current_dt = self.datas[0].datetime.datetime(0)
        open_price = self.dataopen[0]
        # 🔍 调试日志：显示当前是哪个时间点
        self.log(f'🔍 [DEBUG] 初始化基准价 - 时间: {current_dt}, 开盘价: {open_price:.3f}', doprint=True)
        
        self.base_price = open_price
        
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

        return True
    
    def _update_base_price_at_end_of_day(self):
        """
        盘尾更新基准价为当日收盘价
        """
        # 如果基准价尚未初始化，跳过更新
        if self.base_price is None:
            return
        
        close = self.dataclose[0]
        # 检测是当天最后一个bar
        bar_end_time = bt.num2date(self.datas[0].datetime[0])
        market_close = datetime.time(15, 0)
        if bar_end_time.time() == market_close:
            self.log(f"{bar_end_time.date()} 当天最后一个 15min bar")
            old_base = self.base_price
            self.base_price = close
            self.log(f'📅 盘尾更新基准价: {old_base:.3f} -> {self.base_price:.3f}', doprint=True)

        
        
    
    def _execute_grid_trading(self, is_open_session=True):
        """
        执行网格交易逻辑（while循环处理跨格行情）
        
        Args:
            price: 决策价格（开盘价或收盘价）
            current_dt: 当前时间戳
            is_open_session: 是否为开盘时段
        """
        # 防御性检查：如果基准价未初始化，不执行交易
        if self.base_price is None:
            return
        price = self.dataclose[0]
        current_dt = self.datas[0].datetime.datetime(0)
        
        # ✅ 引入模拟持仓变量，跟踪当前Bar内的累计持仓变化
        simulated_position = self.position.size
        
        trades_executed = 0
        max_trades_per_bar = 100  # 防止死循环
        
        while trades_executed < max_trades_per_bar:
            # 计算触发价格
            buy_trigger = self.base_price - self.params.grid_size
            sell_trigger = self.base_price + self.params.grid_size
            
            # 检查买入条件
            if price <= buy_trigger:
                if self._execute_buy(price, buy_trigger, current_dt, trades_executed, simulated_position):
                    trades_executed += 1
                    # ✅ 更新模拟持仓
                    simulated_position += self.params.trade_shares
                else:
                    break
            
            # 检查卖出条件
            elif price >= sell_trigger:
                if self._execute_sell(price, sell_trigger, current_dt, trades_executed, simulated_position):
                    trades_executed += 1
                    # ✅ 更新模拟持仓
                    simulated_position -= self.params.trade_shares
                else:
                    break
            
            # 价格在格子内，退出循环
            else:
                break
        
        # 打印多次交易汇总
        if trades_executed > 1:
            session_type = "开盘" if is_open_session else "收盘"
            self.log(f'🔄 {session_type}共执行 {trades_executed} 次交易，基准价追平至 {self.base_price:.3f}', doprint=True)
    
    def _execute_buy(self, current_price, buy_trigger, current_dt, trade_index, simulated_position):
        """
        执行买入操作
        
        Args:
            simulated_position: 模拟持仓（当前Bar内累计后的持仓）
        
        Returns:
            bool: True表示成功执行，False表示无法执行
        """
        # ✅ 使用模拟持仓进行仓位检查
        current_position = simulated_position
        
        # 检查持仓上限
        if current_position >= self.params.position_max:
            if trade_index == 0:
                self.log(f'⚠️  持仓已达上限 ({current_position}股)，无法买入', doprint=True)
            return False
        
        # 检查资金充足性
        cash_needed = self.params.trade_shares * buy_trigger
        real_cash = self.broker.getcash()
        
        if cash_needed > real_cash:
            if trade_index == 0:
                self.log(f'⚠️  资金不足 (需要{cash_needed:.2f}元，可用{real_cash:.2f}元)', doprint=True)
            return False
        
        # 提交买入订单
        self.order = self.buy(size=self.params.trade_shares)
        
        # 更新基准价
        old_base = self.base_price
        self.base_price = buy_trigger
        self.log(f'📉 买入 #{trade_index+1}！触发价: {buy_trigger:.3f}, 更新基准价: {old_base:.3f} -> {self.base_price:.3f}', doprint=True)
        
        # 记录交易历史
        self.trade_history.append((current_dt, buy_trigger, 'BUY', self.base_price))
        
        return True
    
    def _execute_sell(self, current_price, sell_trigger, current_dt, trade_index, simulated_position):
        """
        执行卖出操作
        
        Args:
            simulated_position: 模拟持仓（当前Bar内累计后的持仓）
        
        Returns:
            bool: True表示成功执行，False表示无法执行
        """
        # ✅ 使用模拟持仓进行仓位检查
        current_position = simulated_position
        
        # 检查持仓充足性
        if current_position < self.params.trade_shares:
            self.log(f'⚠️  持仓不足 ({current_position}股 < {self.params.trade_shares}股)，无法卖出', doprint=True)
            return False
        
        # 检查最小持仓限制
        if current_position - self.params.trade_shares < self.params.position_min:
            self.log(f'⚠️  卖出后将低于最小持仓限制', doprint=True)
            return False
        
        # 提交卖出订单
        self.order = self.sell(size=self.params.trade_shares)
        
        # 更新基准价
        old_base = self.base_price
        self.base_price = sell_trigger
        self.log(f'📈 卖出 #{trade_index+1}！触发价: {sell_trigger:.3f}, 更新基准价: {old_base:.3f} -> {self.base_price:.3f}', doprint=True)
        
        # 记录交易历史
        self.trade_history.append((current_dt, sell_trigger, 'SELL', self.base_price))
        
        return True

    def stop(self):
        """回测结束时的统计汇总"""
        self.log('='*60, doprint=True)
        self.log('📊 网格策略回测结果', doprint=True)
        self.log('='*60, doprint=True)
        
        # 获取最终状态
        final_cash = self.broker.getcash()
        final_position = self.position.size
        final_value = self.broker.getvalue()
        final_close_price = self.dataclose[0]
        
        # 输出统计信息
        self.log(f'💰 最终账户余额: {final_cash:,.2f} 元', doprint=True)
        self.log(f'📊 最终持仓数量: {final_position} 股', doprint=True)
        self.log(f'📈 最终收盘价格: {final_close_price:.3f} 元', doprint=True)
        self.log(f'💵 总资产价值: {final_value:,.2f} 元', doprint=True)
        self.log(f'📈 买入次数: {self.buys}', doprint=True)
        self.log(f'📉 卖出次数: {self.sells}', doprint=True)
        self.log('='*60, doprint=True)


def run_backtest(
    strategy_class,
    code, 
    start, 
    end,
    frequency='1m',
    initial_cash=100000,
    commission=0.00005,
    initial_position=12000,        # ✅ 新增：初始持仓数量（股）
    initial_position_price=None, # ✅ 新增：初始持仓成本价（可选，默认使用首个Bar开盘价）
    **strategy_kwargs
):
    """
    通用回测引擎 - 支持任意策略
    
    Args:
        strategy_class: 策略类（如 GridStrategy, MovingAverageStrategy 等）
        code: 股票代码
        start: 开始日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        end: 结束日期（格式：'YYYYMMDD' 或 'YYYY-MM-DD'）
        frequency: 数据频率，默认'1m'（1分钟线）
        initial_cash: 初始资金，默认10万
        commission: 佣金费率，默认0.05%
        initial_position: 初始持仓数量（股），默认0
        initial_position_price: 初始持仓成本价，默认None（使用首个Bar开盘价）
        **strategy_kwargs: 策略参数（根据具体策略传入）
    
    Returns:
        results: 回测结果列表
        cerebro: Cerebro引擎实例
    
    Example:
        # 网格策略（无初始持仓）
        run_backtest(
            GridStrategy,
            '159952',
            '20251023',
            '20251119',
            grid_size=0.05,
            trade_shares=5000,
            position_max=150000,
            position_min=0
        )
        
        # 网格策略（已有10000股初始持仓）
        run_backtest(
            GridStrategy,
            '159952',
            '20251023',
            '20251119',
            initial_position=10000,
            initial_position_price=1.5,  # 成本价1.5元
            grid_size=0.05,
            trade_shares=5000,
            position_max=150000,
            position_min=0
        )
        
        # 双均线策略
        run_backtest(
            DualMAStrategy,
            '510300',
            '20240101',
            '20241231',
            fast_period=5,
            slow_period=20
        )
    """
    try:
        # 1. 获取数据
        print(f"\n{'='*70}")
        print(f"🚀 Backtrader 回测引擎")
        print(f"{'='*70}")
        print(f"📊 标的代码: {code}")
        print(f"📅 时间范围: {start} 至 {end}")
        print(f"⏱️  数据频率: {frequency}")
        print(f"💰 初始资金: {initial_cash:,.2f} 元")
        print(f"📈 佣金费率: {commission*100:.2f}%")
        print(f"🔧 策略类型: {strategy_class.__name__}")
        if strategy_kwargs:
            print(f"⚙️  策略参数: {strategy_kwargs}")
        print(f"{'='*70}\n")
        
        data = GetStockDatApi(code, start, end, frequency)
        if data.empty:
            print("⚠️  警告: 未获取到数据，无法进行回测")
            return None, None
        
        # 2. 创建Cerebro引擎
        cerebro = bt.Cerebro()
        
        # 3. 添加数据
        data_feed = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(data_feed)
        
        # 4. 添加策略（传入策略参数）
        cerebro.addstrategy(strategy_class, **strategy_kwargs)
        
        # 5. 设置初始资金和持仓
        if initial_position > 0:
            # ✅ 计算初始持仓需要的资金
            init_price = initial_position_price if initial_position_price is not None else data['open'].iloc[0]
            position_value = initial_position * init_price
            
            if position_value > initial_cash:
                print(f"⚠️  警告: 初始资金不足以购买 {initial_position} 股")
                print(f"   需要: {position_value:,.2f} 元, 可用: {initial_cash:,.2f} 元")
                return None, None
            
            # 扣除持仓占用的资金，设置剩余现金
            remaining_cash = initial_cash - position_value
            cerebro.broker.setcash(remaining_cash)
            
            # ✅ 通过直接操作 broker 建立初始持仓（更可靠的方式）
            # 创建一个买入订单对象
            order = bt.Order.Buy()
            order.size = initial_position
            order.price = init_price
            order.exectype = bt.Order.Limit
            
            # 提交订单到 broker
            cerebro.broker.submit_order(order)
            
            print(f'📊 初始持仓: {initial_position} 股 @ {init_price:.3f} 元 (价值 {position_value:,.2f} 元)')
            print(f'💰 剩余现金: {remaining_cash:,.2f} 元')
        else:
            # 无初始持仓，直接设置全部现金
            cerebro.broker.setcash(initial_cash)
        
        # 6. 设置佣金
        cerebro.broker.setcommission(commission=commission)
        
        # 7. 打印初始状态
        initial_value = cerebro.broker.getvalue()
        initial_cash_remaining = cerebro.broker.getcash()
        initial_position_size = cerebro.broker.getposition(data_feed).size if initial_position > 0 else 0
        
        print(f'💼 初始总资产: {initial_value:,.2f} 元')
        if initial_position > 0:
            print(f'📊 初始持仓: {initial_position_size} 股')
        print(f'💰 可用现金: {initial_cash_remaining:,.2f} 元\n')
        
        # 8. 运行回测
        print("⏳ 回测进行中...\n")
        results = cerebro.run()
        
        # 9. 打印最终结果
        final_value = cerebro.broker.getvalue()
        final_cash = cerebro.broker.getcash()
        profit = final_value - initial_cash
        profit_rate = (profit / initial_cash) * 100
        
        print(f"\n{'='*70}")
        print(f"✅ 回测完成")
        print(f"{'='*70}")
        print(f'💵 最终总资产: {final_value:,.2f} 元')
        print(f'💰 最终现金: {final_cash:,.2f} 元')
        print(f'📊 总收益: {profit:+,.2f} 元 ({profit_rate:+.2f}%)')
        print(f"{'='*70}\n")
        
        return results, cerebro
        
    except Exception as e:
        print(f"\n❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None


if __name__ == '__main__':
    # === 示例1：网格策略回测 ===
    print("\n" + "="*70)
    print("示例1：网格交易策略")
    print("="*70)
    
    run_backtest(
        strategy_class=GridStrategy,  # 传入策略类
        code='159952',
        start='20251023',
        end='20251223',
        frequency='1m',
        initial_cash=36000,
        
        # 网格策略专属参数
        grid_size=0.013,
        trade_shares=3000,
        position_max=18000,
        position_min=6000
    )
    
    # === 示例2：如何添加新策略 ===
    # 假设你有一个双均线策略：
    # class DualMAStrategy(bt.Strategy):
    #     params = (('fast_period', 5), ('slow_period', 20))
    #     def __init__(self):
    #         self.sma_fast = bt.indicators.SMA(period=self.params.fast_period)
    #         self.sma_slow = bt.indicators.SMA(period=self.params.slow_period)
    #     def next(self):
    #         if self.sma_fast[0] > self.sma_slow[0] and not self.position:
    #             self.buy()
    #         elif self.sma_fast[0] < self.sma_slow[0] and self.position:
    #             self.sell()
    
    # # 你可以这样调用：
    # run_backtest(
    #     strategy_class=DualMAStrategy,
    #     code='159952',
    #     start='20251023',
    #     end='20251119',
    #     fast_period=5,
    #     slow_period=20
    # )