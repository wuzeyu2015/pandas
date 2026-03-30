#!/usr/bin/env python3
"""
网格交易回测引擎
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
import logging
import yaml
import json

logger = logging.getLogger(__name__)

@dataclass
class TradeRecord:
    """交易记录"""
    date: pd.Timestamp
    trade_type: str  # 'buy' or 'sell'
    price: float
    shares: int
    amount: float
    commission: float
    tax: float
    grid_level: int
    cash_after: float
    shares_after: int

@dataclass
class DailyRecord:
    """每日记录"""
    date: pd.Timestamp
    price: float
    cash: float
    shares: int
    position_value: float
    total_value: float
    daily_return: float
    cumulative_return: float

class GridBacktest:
    """网格回测引擎"""
    
    def __init__(self, config_file="config.yaml"):
        """初始化回测引擎"""
        self.load_config(config_file)
        self.reset()
        
    def load_config(self, config_file):
        """加载配置文件"""
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        logger.info(f"加载配置: {json.dumps(self.config, indent=2, ensure_ascii=False)}")
    
    def reset(self):
        """重置回测状态"""
        # 账户状态
        self.cash = self.config['initial_cash']  # 现金
        self.shares = 0  # 持有股数
        self.total_cost = 0.0  # 总成本
        
        # 交易记录
        self.trade_records: List[TradeRecord] = []
        self.daily_records: List[DailyRecord] = []
        
        # 网格状态
        self.grid_prices: List[float] = []  # 网格价格线
        self.grid_positions: Dict[int, int] = {}  # 网格持仓 {网格线索引: 持仓数量}
        
        # 绩效统计
        self.peak_value = self.config['initial_cash']  # 峰值资产
        self.max_drawdown = 0.0  # 最大回撤
        
    def calculate_grid_prices(self, base_price: float) -> List[float]:
        """计算网格价格线"""
        grid_prices = []
        grid_step = self.config['grid_step']
        grid_number = self.config['grid_number']
        
        # 中心价格（初始建仓价）
        grid_prices.append(base_price)
        
        # 向上网格（卖出线）
        for i in range(1, grid_number + 1):
            sell_price = base_price * (1 + grid_step * i)
            grid_prices.insert(0, sell_price)  # 插入到前面，保持降序
        
        # 向下网格（买入线）
        for i in range(1, grid_number + 1):
            buy_price = base_price * (1 - grid_step * i)
            grid_prices.append(buy_price)  # 追加到后面
        
        # 初始化网格持仓状态
        for i in range(len(grid_prices)):
            self.grid_positions[i] = 0
        
        logger.info(f"生成网格价格线，共{len(grid_prices)}条:")
        for i, price in enumerate(grid_prices):
            level_type = "卖" if i < grid_number else "中" if i == grid_number else "买"
            level_num = abs(i - grid_number)
            logger.info(f"  网格{i:2d} [{level_type}{level_num:2d}]: {price:.3f}")
        
        return grid_prices
    
    def calculate_commission(self, amount: float, is_buy: bool) -> tuple:
        """计算交易费用"""
        # 佣金
        commission = amount * self.config['commission_rate']
        commission = max(commission, self.config['min_commission'])
        
        # 印花税（仅卖出收取）
        tax = 0
        if not is_buy:
            tax = amount * self.config['stamp_tax_rate']
        
        return commission, tax
    
    def execute_trade(self, date: pd.Timestamp, price: float, 
                     grid_level: int, is_buy: bool) -> bool:
        """执行交易"""
        # 计算实际成交价（考虑滑点）
        if is_buy:
            trade_price = price * (1 + self.config['slippage'])
        else:
            trade_price = price * (1 - self.config['slippage'])
        
        # 交易数量
        shares = self.config['position_per_grid']
        amount = trade_price * shares
        
        # 检查交易条件
        if is_buy:
            # 买入条件：现金足够且该网格未持仓
            if amount + self.config['min_commission'] > self.cash:
                logger.debug(f"{date.date()} 买入失败: 现金不足 (需{amount:.2f}, 有{self.cash:.2f})")
                return False
            if self.grid_positions[grid_level] > 0:
                logger.debug(f"{date.date()} 买入失败: 网格{grid_level}已有持仓")
                return False
        else:
            # 卖出条件：有持仓且该网格有持仓
            if self.shares < shares:
                logger.debug(f"{date.date()} 卖出失败: 持仓不足 (需{shares}, 有{self.shares})")
                return False
            if self.grid_positions[grid_level] <= 0:
                logger.debug(f"{date.date()} 卖出失败: 网格{grid_level}无持仓")
                return False
        
        # 计算费用
        commission, tax = self.calculate_commission(amount, is_buy)
        total_cost = amount + commission + tax if is_buy else amount - commission - tax
        
        # 更新账户
        if is_buy:
            self.cash -= total_cost
            self.shares += shares
            self.total_cost += total_cost
            self.grid_positions[grid_level] = shares
        else:
            self.cash += total_cost
            self.shares -= shares
            self.total_cost -= (self.total_cost / self.shares * shares) if self.shares > 0 else 0
            self.grid_positions[grid_level] = 0
        
        # 记录交易
        trade = TradeRecord(
            date=date,
            trade_type='buy' if is_buy else 'sell',
            price=trade_price,
            shares=shares,
            amount=amount,
            commission=commission,
            tax=tax,
            grid_level=grid_level,
            cash_after=self.cash,
            shares_after=self.shares
        )
        self.trade_records.append(trade)
        
        logger.info(f"{date.date()} {'买入' if is_buy else '卖出'} 网格{grid_level}: "
                   f"{shares}股 @ {trade_price:.3f}, 总额{amount:.2f}, 费用{commission+tax:.2f}")
        
        return True
    
    def check_grid_signals(self, date: pd.Timestamp, price: float) -> List[tuple]:
        """检查网格信号"""
        signals = []
        
        for i, grid_price in enumerate(self.grid_prices):
            # 计算网格索引偏移
            center_idx = self.config['grid_number']
            
            if i < center_idx:  # 卖出网格
                if price >= grid_price and self.grid_positions[i] > 0:
                    signals.append((i, grid_price, False))  # 卖出信号
            elif i > center_idx:  # 买入网格
                if price <= grid_price and self.grid_positions[i] == 0:
                    signals.append((i, grid_price, True))  # 买入信号
        
        return signals
    
    def run(self, data: pd.DataFrame) -> Dict:
        """运行回测"""
        logger.info("开始回测...")
        
        # 筛选回测日期范围
        mask = (data['date'] >= self.config['start_date']) & (data['date'] <= self.config['end_date'])
        data = data[mask].copy()
        
        if len(data) == 0:
            logger.error("回测日期范围内无数据")
            return {}
        
        # 初始化网格
        if self.config['initial_price'] is not None:
            base_price = self.config['initial_price']
        else:
            base_price = data.iloc[0]['close']
        
        self.grid_prices = self.calculate_grid_prices(base_price)
        
        # 初始建仓（在第一个交易日买入中心网格）
        first_row = data.iloc[0]
        self.execute_trade(
            date=first_row['date'],
            price=first_row['close'],
            grid_level=self.config['grid_number'],  # 中心网格
            is_buy=True
        )
        
        # 逐日回测
        prev_total_value = self.config['initial_cash']
        
        for idx, row in data.iterrows():
            current_price = row['close']
            date = row['date']
            
            # 检查网格信号并交易
            signals = self.check_grid_signals(date, current_price)
            for grid_level, grid_price, is_buy in signals:
                self.execute_trade(date, current_price, grid_level, is_buy)
            
            # 计算当日资产
            position_value = self.shares * current_price
            total_value = self.cash + position_value
            
            # 计算收益
            if prev_total_value > 0:
                daily_return = (total_value - prev_total_value) / prev_total_value
            else:
                daily_return = 0
            
            # 更新峰值和最大回撤
            if total_value > self.peak_value:
                self.peak_value = total_value
            
            drawdown = (self.peak_value - total_value) / self.peak_value
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
            
            # 记录每日数据
            daily_record = DailyRecord(
                date=date,
                price=current_price,
                cash=self.cash,
                shares=self.shares,
                position_value=position_value,
                total_value=total_value,
                daily_return=daily_return,
                cumulative_return=(total_value - self.config['initial_cash']) / self.config['initial_cash']
            )
            self.daily_records.append(daily_record)
            
            prev_total_value = total_value
        
        # 生成回测结果
        results = self.get_results()
        logger.info("回测完成!")
        
        return results
    
    def get_results(self) -> Dict:
        """获取回测结果"""
        if not self.daily_records:
            return {}
        
        # 计算绩效指标
        initial_cash = self.config['initial_cash']
        final_total_value = self.daily_records[-1].total_value
        total_return = (final_total_value - initial_cash) / initial_cash
        
        # 计算年化收益率
        days = (self.daily_records[-1].date - self.daily_records[0].date).days
        years = days / 365.0
        if years > 0:
            annual_return = (1 + total_return) ** (1 / years) - 1
        else:
            annual_return = 0
        
        # 计算夏普比率（简化版，无风险利率设为0）
        daily_returns = [r.daily_return for r in self.daily_records if r.daily_return != 0]
        if daily_returns:
            avg_return = np.mean(daily_returns)
            std_return = np.std(daily_returns)
            if std_return > 0:
                sharpe_ratio = avg_return / std_return * np.sqrt(252)  # 年化夏普
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        # 交易统计
        buy_trades = [t for t in self.trade_records if t.trade_type == 'buy']
        sell_trades = [t for t in self.trade_records if t.trade_type == 'sell']
        
        # 计算胜率（卖出价格高于买入成本）
        winning_trades = 0
        for sell in sell_trades:
            # 找到对应的买入交易
            for buy in buy_trades:
                if buy.grid_level == sell.grid_level and buy.date < sell.date:
                    if sell.price > buy.price:
                        winning_trades += 1
                    break
        
        win_rate = winning_trades / len(sell_trades) if sell_trades else 0
        
        results = {
            'summary': {
                'initial_cash': initial_cash,
                'final_value': final_total_value,
                'total_return': total_return,
                'annual_return': annual_return,
                'total_days': days,
                'max_drawdown': self.max_drawdown,
                'sharpe_ratio': sharpe_ratio
            },
            'trades': {
                'total_trades': len(self.trade_records),
                'buy_trades': len(buy_trades),
                'sell_trades': len(sell_trades),
                'win_rate': win_rate
            },
            'position': {
                'final_cash': self.cash,
                'final_shares': self.shares,
                'final_position_value': self.daily_records[-1].position_value
            }
        }
        
        return results
    
    def get_trade_dataframe(self) -> pd.DataFrame:
        """获取交易记录DataFrame"""
        if not self.trade_records:
            return pd.DataFrame()
        
        records = []
        for trade in self.trade_records:
            records.append({
                'date': trade.date,
                'trade_type': trade.trade_type,
                'price': trade.price,
                'shares': trade.shares,
                'amount': trade.amount,
                'commission': trade.commission,
                'tax': trade.tax,
                'grid_level': trade.grid_level,
                'cash_after': trade.cash_after,
                'shares_after': trade.shares_after
            })
        
        return pd.DataFrame(records)
    
    def get_daily_dataframe(self) -> pd.DataFrame:
        """获取每日记录DataFrame"""
        if not self.daily_records:
            return pd.DataFrame()
        
        records = []
        for daily in self.daily_records:
            records.append({
                'date': daily.date,
                'price': daily.price,
                'cash': daily.cash,
                'shares': daily.shares,
                'position_value': daily.position_value,
                'total_value': daily.total_value,
                'daily_return': daily.daily_return,
                'cumulative_return': daily.cumulative_return
            })
        
        return pd.DataFrame(records)