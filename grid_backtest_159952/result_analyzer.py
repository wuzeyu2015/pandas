#!/usr/bin/env python3
"""
回测结果分析器
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from matplotlib import rcParams
from typing import Dict
import logging

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
rcParams.update({'figure.autolayout': True})

logger = logging.getLogger(__name__)

class ResultAnalyzer:
    """结果分析器"""
    
    def __init__(self, backtest_engine):
        self.engine = backtest_engine
        self.results = backtest_engine.get_results()
    
    def print_summary(self):
        """打印回测摘要"""
        if not self.results:
            logger.error("无回测结果")
            return
        
        summary = self.results['summary']
        trades = self.results['trades']
        position = self.results['position']
        
        print("\n" + "="*60)
        print("ETF网格交易回测结果摘要")
        print("="*60)
        
        print(f"\n📈 收益表现:")
        print(f"   初始资金: {summary['initial_cash']:,.2f} 元")
        print(f"   最终资产: {summary['final_value']:,.2f} 元")
        print(f"   总收益率: {summary['total_return']:+.2%}")
        print(f"   年化收益: {summary['annual_return']:+.2%}")
        print(f"   最大回撤: {summary['max_drawdown']:+.2%}")
        print(f"   夏普比率: {summary['sharpe_ratio']:.3f}")
        
        print(f"\n📊 交易统计:")
        print(f"   总交易次数: {trades['total_trades']} 次")
        print(f"   买入次数: {trades['buy_trades']} 次")
        print(f"   卖出次数: {trades['sell_trades']} 次")
        print(f"   交易胜率: {trades['win_rate']:.2%}")
        
        print(f"\n💼 最终持仓:")
        print(f"   现金余额: {position['final_cash']:,.2f} 元")
        print(f"   持有股数: {position['final_shares']} 股")
        print(f"   持仓市值: {position['final_position_value']:,.2f} 元")
        
        print(f"\n⏱️ 回测周期:")
        print(f"   总天数: {int(summary['total_days'])} 天")
        
        print("\n" + "="*60)
    
    def plot_results(self, save_path=None):
        """绘制回测结果图表"""
        if not self.engine.daily_records:
            logger.error("无回测数据")
            return
        
        daily_df = self.engine.get_daily_dataframe()
        trade_df = self.engine.get_trade_dataframe()
        
        fig, axes = plt.subplots(3, 1, figsize=(12, 10))
        
        # 1. 价格和网格交易图
        ax1 = axes[0]
        ax1.plot(daily_df['date'], daily_df['price'], label='ETF价格', linewidth=1, alpha=0.7)
        
        # 绘制交易点
        if not trade_df.empty:
            buy_trades = trade_df[trade_df['trade_type'] == 'buy']
            sell_trades = trade_df[trade_df['trade_type'] == 'sell']
            
            ax1.scatter(buy_trades['date'], buy_trades['price'], 
                       color='red', s=30, label='买入', marker='^', alpha=0.7)
            ax1.scatter(sell_trades['date'], sell_trades['price'], 
                       color='green', s=30, label='卖出', marker='v', alpha=0.7)
        
        ax1.set_title('ETF价格走势与交易信号')
        ax1.set_ylabel('价格 (元)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. 资产变化图
        ax2 = axes[1]
        ax2.plot(daily_df['date'], daily_df['total_value'], 
                label='总资产', color='blue', linewidth=2)
        ax2.plot(daily_df['date'], daily_df['position_value'], 
                label='持仓市值', color='orange', linewidth=1, alpha=0.7)
        ax2.plot(daily_df['date'], daily_df['cash'], 
                label='现金', color='green', linewidth=1, alpha=0.7)
        
        ax2.set_title('资产变化曲线')
        ax2.set_ylabel('金额 (元)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. 累计收益率图
        ax3 = axes[2]
        ax3.plot(daily_df['date'], daily_df['cumulative_return'], 
                label='累计收益率', color='red', linewidth=2)
        ax3.axhline(y=0, color='gray', linestyle='-', linewidth=0.5, alpha=0.5)
        
        # 填充回撤区域
        peak = daily_df['total_value'].expanding().max()
        drawdown = (daily_df['total_value'] - peak) / peak
        ax3.fill_between(daily_df['date'], drawdown, 0, 
                        alpha=0.3, color='red', label='回撤')
        
        ax3.set_title('累计收益率与回撤')
        ax3.set_xlabel('日期')
        ax3.set_ylabel('收益率')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 格式化y轴为百分比
        from matplotlib.ticker import PercentFormatter
        ax3.yaxis.set_major_formatter(PercentFormatter(1.0))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"图表已保存到: {save_path}")
        
        plt.show()
    
    def export_results(self, export_dir="results"):
        """导出结果到CSV"""
        import os
        os.makedirs(export_dir, exist_ok=True)
        
        # 导出交易记录
        trade_df = self.engine.get_trade_dataframe()
        if not trade_df.empty:
            trade_file = f"{export_dir}/trade_records.csv"
            trade_df.to_csv(trade_file, index=False, encoding='utf-8-sig')
            logger.info(f"交易记录已导出到: {trade_file}")
        
        # 导出每日记录
        daily_df = self.engine.get_daily_dataframe()
        if not daily_df.empty:
            daily_file = f"{export_dir}/daily_records.csv"
            daily_df.to_csv(daily_file, index=False, encoding='utf-8-sig')
            logger.info(f"每日记录已导出到: {daily_file}")
        
        # 导出摘要
        if self.results:
            import json
            summary_file = f"{export_dir}/summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"回测摘要已导出到: {summary_file}")