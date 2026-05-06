import backtrader as bt
import pandas as pd
from datetime import datetime


class SimpleStrategy(bt.Strategy):
    """
    最简单的策略示例 - 展示 next() 和 next_open() 的执行顺序
    """
    
    def log(self, txt, dt=None):
        """日志输出"""
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f'{dt.strftime("%Y-%m-%d %H:%M")} - {txt}')
    
    def __init__(self):
        """初始化"""
        self.dataclose = self.datas[0].close
        self.dataopen = self.datas[0].open
        self.bar_count = 0
    
    def next_open(self):
        """
        在 cheat_on_open=True 模式下，这个方法会在 next() 之后调用
        使用当前Bar的开盘价进行交易决策
        """
        self.bar_count += 1
        current_time = self.datas[0].datetime.datetime(0)
        open_price = self.dataopen[0]
        
        self.log(f'🔓 [next_open] Bar #{self.bar_count} | 开盘价: {open_price:.2f}')
        
        # 简单示例：在第二个Bar买入
        if self.bar_count == 2 and not self.position:
            self.buy(size=100)
            self.log(f'✅ [next_open] 买入 100 股 @ {open_price:.2f}')
    
    def next(self):
        """
        每个Bar都会调用
        在 cheat_on_open=True 模式下，先于 next_open() 执行
        """
        current_time = self.datas[0].datetime.datetime(0)
        close_price = self.dataclose[0]
        open_price = self.dataopen[0]
        
        self.log(f'📊 [next] Bar #{self.bar_count} | 开盘: {open_price:.2f}, 收盘: {close_price:.2f}')
        
        # 打印当前持仓和现金
        if self.position:
            self.log(f'   💼 持仓: {self.position.size} 股')
        self.log(f'   💰 现金: {self.broker.getcash():.2f}')


def create_sample_data():
    """
    创建5天的模拟行情数据
    """
    # 创建5个交易日的日期（假设是日线数据）
    dates = pd.date_range(start='2024-01-02', periods=5, freq='D')
    
    # 创建模拟的OHLCV数据
    data = {
        'open': [100.0, 102.0, 101.5, 103.0, 104.5],
        'high': [102.5, 103.5, 103.0, 105.0, 106.0],
        'low': [99.5, 101.0, 100.5, 102.5, 103.5],
        'close': [102.0, 101.5, 103.0, 104.5, 105.5],
        'volume': [1000000, 1200000, 1100000, 1300000, 1400000]
    }
    
    # 创建DataFrame
    df = pd.DataFrame(data, index=dates)
    df.index.name = 'datetime'
    
    print("📋 创建的测试数据:")
    print(df)
    print("\n" + "="*70 + "\n")
    
    return df


def main():
    """主函数"""
    print("="*70)
    print("Backtrader 最简单用例 - next() vs next_open() 执行顺序演示")
    print("="*70 + "\n")
    
    # 1. 创建测试数据
    df = create_sample_data()
    
    # 2. 创建Cerebro引擎（启用cheat_on_open模式）
    cerebro = bt.Cerebro(cheat_on_open=True)
    
    # 3. 添加数据
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data_feed)
    
    # 4. 添加策略
    cerebro.addstrategy(SimpleStrategy)
    
    # 5. 设置初始资金
    initial_cash = 100000.0
    cerebro.broker.setcash(initial_cash)
    
    # 6. 打印初始状态
    print(f'💰 初始资金: {initial_cash:,.2f} 元')
    print(f'📊 数据条数: {len(df)} 条')
    print("\n" + "="*70)
    print("开始回测...\n")
    print("="*70 + "\n")
    
    # 7. 运行回测
    results = cerebro.run()
    
    # 8. 打印最终结果
    print("\n" + "="*70)
    print("回测结束")
    print("="*70)
    final_value = cerebro.broker.getvalue()
    final_cash = cerebro.broker.getcash()
    print(f'💵 最终资产: {final_value:,.2f} 元')
    print(f'💰 最终现金: {final_cash:,.2f} 元')
    print(f'📈 收益率: {(final_value - initial_cash) / initial_cash * 100:.2f}%')
    print("="*70)


if __name__ == '__main__':
    main()
