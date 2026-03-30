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
                 capital: float = 24000.0,
                 position: int = 0,
                 position_price: float = 0,
                 position_max: int = 10000,
                 position_min: int = 2000,
                 grid_size: float = 0.013,
                 trade_shares: int = 2000,
                 max_drawdown_stop_loss: float = 0.15):
        """
        初始化网格回测引擎

        Args:
            fund_code: 基金代码
            capital: 初始资金
            position: 初始持仓
            position_price: 持仓金额
            position_average_price: 持仓均价 
            grid_size: 格子大小（价格尺度）
            trade_shares: 每次交易的份数
            base_price: 基准价
            max_drawdown_stop_loss: 最大回撤止损线
        """
        self.fund_code = fund_code
        self.capital = capital
        self.position = position
        self.position_max = position_max
        self.position_min = position_min
        self.position_price = position_price
        self.position_average_price = 0
        self.grid_size = grid_size
        self.trade_shares = trade_shares
        self.max_drawdown_stop_loss = max_drawdown_stop_loss

        # 交易记录
        self.trade_records: List[Dict] = []
        self.equity_curve = []

        # 当前状态
        self.max_drawdown = 0
        self.peak_capital = capital
    def run_backtest(self, df: pd.DataFrame) -> Dict:
        """
        运行网格回测

        Args:
            df: 包含日期和净值的数据框

        Returns:
            回测结果字典
        """
        print(f"\n{'='*60}")
        print(f"开始回测:  ({self.fund_code})")
        print(f"初始资金: {self.capital:,.2f} 元")
        print(f"格子大小: {self.grid_size:.4f} 元 ")
        print(f"交易份数: {self.trade_shares} 份")
        print(f"回测周期: {df['date'].iloc[240]} 至 {df['date'].iloc[-1]}")
        print(f"交易份数: {self.trade_shares} 份")    
        print(f"{'='*60}\n")
  
        # 初始化基准价为回测前一日的收盘价
        self.base_price = df.iloc[239]['close']
        print(f"初始基准价: {self.base_price}")   
        # 初始化状态
        self.capital = self.capital
        self.position = 0
        self.max_drawdown = 0
        self.peak_capital = self.capital
        self.equity_curve = []

        # 遍历每一分钟（从第二日开始）
        for idx in range(240, len(df)):
            row = df.iloc[idx]
            date = row['date']
            close = row['close']

            # 记录当前资金
            current_equity = self.capital + self.position * close
            self.equity_curve.append({
                'date': date,
                'capital': self.capital,
                'position': self.position,
                'close': close,
                'total_equity': current_equity,
                'base_price': self.base_price
            })



            # 每分钟进行交易检查
            self._check_trading_condition(date, close)

            # # 每天收盘价强制更新基准价
            # if (idx + 1) % 240 == 0:
            #     self.base_price = close
            #     print(f"盘尾更新基准价: {self.base_price}----------------------------------------")   
                

        # 转换为DataFrame
        equity_df = pd.DataFrame(self.equity_curve)

        # 计算最终收益
        final_equity = equity_df.iloc[-1]['total_equity']

        # 计算策略信息
        strategy_info = {
            'fund_code': self.fund_code,
            'capital': self.capital,
            'final_capital': final_equity,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown * 100,
            'total_trades': len(self.trade_records),
            'grid_size': self.grid_size,
            'grid_size_pct': self.grid_size,
            'trade_shares': self.trade_shares
        }

        # 添加交易记录
        trades_df = pd.DataFrame(self.trade_records)

        # 创建结果
        results = {
            'summary': strategy_info,
            'trades': trades_df,
            'equity_curve': equity_df,
            'fund_data': df
        }

        print(f"\n{'='*60}")
        print("回测结果摘要")
        print(f"{'='*60}")
        print(f"最终资金: {final_equity:,.2f} 元")
        print(f"最大回撤: {self.max_drawdown*100:.2f}%")
        print(f"总交易次数: {len(self.trade_records)}")
        print(f"{'='*60}\n")

        return results

    def _check_trading_condition(self, date, close: float):
        """
        检查交易条件并执行交易

        逻辑：
        - 超过基准价+格子 -> 卖出一份
        - 低于基准价-格子 -> 买入一个ETF的份数

        Args:
            date: 当前日期
            close: 当前净值/价格
        """
        # 卖出触发线：基准价 + 格子
        sell_price = self.base_price + self.grid_size

        # 买入触发线：基准价 - 格子
        buy_price = self.base_price - self.grid_size

        # 卖出条件：价格达到卖出触发线
        if close >= sell_price:
            self._sell(date, close)
            return

        # 买入条件：价格低于买入触发线且有足够资金
        if close <= buy_price:
            self._buy(date, close)

    def _buy(self, date, price: float):
        """
        买入操作

        Args:
            date: 日期
            price: 成交价格
        """
        # 交易金额 = 份数 * 价格
        trade_amount = self.trade_shares * price

        # 检查资金是否足够
        if trade_amount > self.capital:
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 资金不足，无法买入 {self.trade_shares} 份 @ {price:.4f}元")
            return
        # 检查持仓是否超过限制
        if self.position >= self.position_max:
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 持仓超过限制，无法买入 {self.trade_shares} 份 @ {price:.4f}元")
            return 
        # 执行买入
        self.capital -= trade_amount
        self.position_price += trade_amount
        self.position += self.trade_shares

        # 更新持仓成本
        self.position_average_price =  self.position_price / self.position

        # 更新基准价
        self.base_price = price
        print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 买入 {self.trade_shares} 份 @ {price}元")
        print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 买入更新基准价: {self.base_price}")   
        # 记录交易
        self._record_trade(
            date=date,
            trade_type='buy',
            price=price,
            quantity=self.trade_shares,
            amount=trade_amount,
        )


    def _sell(self, date, price: float):
        """
        卖出操作

        Args:
            date: 日期
            price: 卖出价格
        """
        if self.position < self.trade_shares:
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 持仓不够，无法卖出  {self.trade_shares} 份 @ {price:.4f}元")
            return
        # 检查持仓是否低于限制
        if self.position <= self.position_min:
            print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 持仓低于限制，无法卖出 {self.trade_shares} 份 @ {price:.4f}元")
            return 
        # 交易金额 = 份数 * 价格
        trade_amount = self.trade_shares * price

        # 执行卖出
        self.capital += trade_amount
        self.position -= self.trade_shares
        self.position_price -= trade_amount
        # 记录交易
        self._record_trade(
            date=date,
            trade_type='sell',
            price=price,
            quantity=self.position,
            amount=trade_amount
        )

        self.base_price = price
        print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 卖出 {self.trade_shares} 份 @ {price}元")
        print(f"[{date.strftime('%Y-%m-%d %H:%M')}] 卖出更新基准价: {self.base_price}")   

    def _record_trade(self, date, trade_type: str, price: float, quantity: int,
                     amount: float):
        """
        记录交易

        Args:
            date: 日期
            trade_type: 交易类型 (buy/sell)
            price: 价格
            quantity: 数量
            amount: 金额
        """
        self.trade_records.append({
            'date': date.strftime('%Y-%m-%d %H:%M:%S'),
            'trade_type': trade_type,
            'price': price,
            'quantity': quantity,
            'amount': amount
        })


