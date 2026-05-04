"""
网格回测核心模块
实现移动基准价的网格交易策略回测
"""
import pandas as pd
from typing import Dict, List

class GridBacktest:
    """网格交易回测引擎 - 移动基准价版本"""

    def __init__(self,
                 fund_code: str,
                 available: float = 24000.0,
                 position: int = 0,
                 position_max: int = 150000,
                 position_min: int = 0,
                 grid_size: float = 0.050,
                 trade_shares: int = 5000):
        """
        初始化网格回测引擎

        Args:
            fund_code: 基金代码
            available: 账户余额
            position: 持仓
            average_position_cost: 持仓成本价
            grid_size: 格子大小（价格尺度）
            trade_shares: 每次交易的份数
            base_price: 基准价
        """
        self.fund_code = fund_code
        self.available = available
        self.min_available = available
        self.position = position
        self.max_positon = position
        self.position_max = position_max
        self.position_min = position_min
        self.average_position_cost = 0
        self.grid_size = grid_size
        self.trade_shares = trade_shares
        self.to_sell = True
        self.sells = 0
        self.buys = 0
        self.to_buy = True
        self.end_price = 0

    def _buy(self, date, close: float):
        if self.to_buy == False:
            return
        # 买入触发线：基准价 - 格子
        buy_price = self.base_price - self.grid_size
        
        while close <= buy_price:
            # 交易金额 = 份数 * 价格
            trade_amount = self.trade_shares * buy_price

            # 检查资金是否足够
            if trade_amount > self.available:
                print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 资金不足，无法买入 {self.trade_shares} 份 @ {buy_price:.3f}元")
                self.to_buy = False
                return
            # 检查持仓是否超过限制
            if self.position >= self.position_max:
                print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 持仓超过限制，无法买入 {self.trade_shares} 份 @ {buy_price:.3f}元")
                self.to_buy = False
                return
            
            self.to_sell = True
            
            # 执行买入
            self.available -= trade_amount
            self.position += self.trade_shares
            self.max_positon = max(self.max_positon, self.position)
            self.min_available = min(self.min_available, self.available)
            # 更新基准价
            self.base_price = buy_price
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 买入 {self.trade_shares} 份 @ {buy_price:.3f}元")
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 买入更新基准价: {self.base_price:.3f}")   
            
            self.buys += 1
            buy_price = self.base_price - self.grid_size


    def _sell(self, date, close: float):
        if self.to_sell == False:
            return
        # 卖出触发线：基准价 + 格子
        sell_price = self.base_price + self.grid_size

        while close >= sell_price:

            if self.position < self.trade_shares:
                print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 持仓不够，无法卖出  {self.trade_shares} 份 @ {sell_price:.3f}元")
                self.to_sell = False
                return
            # 检查持仓是否低于限制
            if self.position <= self.position_min:
                print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 持仓低于限制，无法卖出 {self.trade_shares} 份 @ {sell_price:.3f}元")
                self.to_sell = False
                return 
            # 交易金额 = 份数 * 价格
            trade_amount = self.trade_shares * sell_price
            self.to_buy = True
            
            # 执行卖出
            self.available += trade_amount
            self.position -= self.trade_shares

            self.base_price = sell_price
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 卖出 {self.trade_shares} 份 @ {sell_price:.3f}元")
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 卖出更新基准价: {self.base_price:.3f}")   
            self.sells += 1
            sell_price = self.base_price + self.grid_size

    def run_backtest(self, df: pd.DataFrame) -> Dict:

        # 以首日开盘价初始基准价
        self.first_day_open = df.iloc[0]['open']
        self.last_day_close = df.iloc[len(df)-1]['close']
        self.base_price = self.first_day_open
        self.total_input = self.available + self.position * self.base_price
        print(f"\n{'='*60}")
        print(f"开始回测:  ({self.fund_code})")
        print(f"初始账户余额: {self.available:,.2f} 元")
        print(f"初始持仓: {self.position} 份")
        print(f"总成本: {self.total_input:.3f} 元")
        print(f"初始基准价: {self.base_price:.3f}元")
        print(f"格子大小: {self.grid_size:.4f} 元 ")
        print(f"交易份数: {self.trade_shares} 份")
        print(f"回测周期: {df.index[0]} 至 {df.index[-1]}")
        print(f"{'='*60}\n")


        # 标记每天最后一分钟
        df['is_last_minute_of_day'] = (
            df.groupby(df.index.date)['close']
            .transform('last')
            .eq(df['close'])
        )
        # 遍历每一分钟行情
        for idx, row in df.iterrows():
            
            date = idx
            close = row['close']
            self.end_price = close

            self._sell(date, close)
            self._buy(date, close)
            # 更新持仓成本价
            self.average_position_cost = (self.total_input - self.available) / self.position
            # 每天收盘价强制更新基准价
            if row['is_last_minute_of_day']:
                self.base_price = close
                print(f"盘尾更新基准价: {self.base_price}----------------------------------------") 


        print(f"\n{'='*60}")
        print("回测结果摘要")
        print(f"{'='*60}")
        total_output = self.available + self.end_price*self.position
        print(f"买入次数: {self.buys}")
        print(f"卖出次数: {self.sells}")

        print(f"最大持仓量: {self.max_positon}")
        print(f"最大持仓成本: {self.total_input - self.min_available:,.2f} 元")
        print(f"余额: {self.available}")
        print(f"盘尾价格: {self.end_price}")
        print(f"盘尾持仓: {self.position}")
        print(f"最终资产: {total_output:,.2f} 元")
        print(f"持仓单股成本: {self.average_position_cost:,.2f} 元")
        print(f"网格累计收益: {total_output - self.total_input:,.2f} 元")
        print(f"收益率: {(total_output - self.total_input)/(self.total_input - self.min_available)*100:,.2f}%")
        print(f"收益率(不做T): {(self.last_day_close - self.first_day_open)/self.first_day_open*100:,.2f}%")
        print(f"{'='*60}\n")





