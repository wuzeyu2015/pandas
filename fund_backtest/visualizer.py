"""
结果分析和可视化模块
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict
import warnings

warnings.filterwarnings('ignore')
sns.set_style("darkgrid")


class BacktestVisualizer:
    """回测结果可视化"""

    def __init__(self, results: Dict):
        """
        初始化可视化器

        Args:
            results: 回测结果字典
        """
        self.results = results
        self.summary = results['summary']
        self.trades = results['trades']
        self.equity_curve = results['equity_curve']
        self.fund_data = results['fund_data']

        # 获取基准价（从 equity_curve 中获取）
        self.base_price = self.equity_curve['base_price'].iloc[0]

    def plot_equity_curve(self, figsize: tuple = (12, 6)):
        """
        绘制资金曲线

        Args:
            figsize: 图形大小
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)

        # 资金曲线
        ax1.plot(self.equity_curve['date'],
                self.equity_curve['total_equity'],
                linewidth=2, color='#2ecc71', label='总资产')
        ax1.plot(self.equity_curve['date'],
                self.equity_curve['capital'],
                linewidth=1.5, color='#3498db', alpha=0.7, label='现金')

        # 填充显示总资产
        ax1.fill_between(self.equity_curve['date'],
                        self.equity_curve['capital'],
                        self.equity_curve['total_equity'],
                        alpha=0.2, color='#2ecc71')

        # 添加网格线
        ax1.grid(True, alpha=0.3)

        # 设置标题和标签
        ax1.set_title(f'{self.summary["fund_code"]} ({self.summary["fund_code"]}) - 资金曲线',
                     fontsize=14, fontweight='bold')
        ax1.set_ylabel('金额 (元)', fontsize=12)
        ax1.legend(loc='upper left')

        # 添加关键点标注
        final_equity = self.equity_curve.iloc[-1]['total_equity']
        initial_equity = self.equity_curve.iloc[0]['total_equity']
        ax1.axhline(y=initial_equity, color='#95a5a6', linestyle='--',
                   linewidth=1, label='初始资金')
        ax1.text(self.equity_curve['date'].iloc[0], initial_equity,
                f"初始: {initial_equity:,.2f}",
                fontsize=10, verticalalignment='bottom')

        ax1.text(self.equity_curve['date'].iloc[-1], final_equity,
                f"最终: {final_equity:,.2f}",
                fontsize=10, verticalalignment='top')

        # 持仓变化
        ax2.plot(self.equity_curve['date'], self.equity_curve['position'],
                linewidth=2, color='#e74c3c', label='持仓数量')
        ax2.fill_between(self.equity_curve['date'], 0, self.equity_curve['position'],
                        alpha=0.3, color='#e74c3c')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylabel('持仓数量 (份)', fontsize=12)
        ax2.set_xlabel('日期', fontsize=12)
        ax2.legend(loc='upper left')

        plt.tight_layout()
        return fig

    def plot_nav_and_trades(self, figsize: tuple = (14, 6)):
        """
        绘制净值曲线和交易点

        Args:
            figsize: 图形大小
        """
        fig, ax = plt.subplots(figsize=figsize)

        # 净值曲线
        ax.plot(self.fund_data['date'], self.fund_data['nav'],
               linewidth=2, color='#3498db', label='净值')

        # 绘制基准线
        ax.axhline(y=self.base_price, color='#95a5a6', linestyle='--',
                  alpha=0.5, linewidth=1, label='基准价')

        # 绘制买卖触发线
        buy_trigger = self.base_price - self.summary['grid_size']
        sell_trigger = self.base_price + self.summary['grid_size']
        ax.axhline(y=buy_trigger, color='#2ecc71', linestyle=':', alpha=0.3, linewidth=1, label='买入线')
        ax.axhline(y=sell_trigger, color='#e74c3c', linestyle=':', alpha=0.3, linewidth=1, label='卖出线')

        # 标记买入点
        buys = self.trades[self.trades['trade_type'] == 'buy']
        if not buys.empty:
            ax.scatter(buys['date'], buys['price'], color='#2ecc71',
                      s=100, marker='^', label='买入', zorder=5)

        # 标记卖出点
        sells = self.trades[self.trades['trade_type'] == 'sell']
        if not sells.empty:
            ax.scatter(sells['date'], sells['price'], color='#e74c3c',
                      s=100, marker='v', label='卖出', zorder=5)

        # 设置标题和标签
        ax.set_title(f'{self.summary["fund_code"]} - 净值曲线与交易点',
                    fontsize=14, fontweight='bold')
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('净值', fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)

        # 添加参数标注
        ax.text(self.fund_data['date'].iloc[0], self.fund_data['nav'].min() * 0.98,
               f"格子: {self.summary['grid_size']:.4f}元\n份数: {self.summary['trade_shares']}",
               fontsize=10, color='#7f8c8d')

        plt.tight_layout()
        return fig

    def plot_trade_distribution(self, figsize: tuple = (10, 5)):
        """
        绘制交易分布

        Args:
            figsize: 图形大小
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

        # 交易类型分布
        trade_types = self.trades['trade_type'].value_counts()
        trade_types.plot(kind='pie', ax=ax1, autopct='%1.1f%%',
                        colors=['#2ecc71', '#e74c3c'])
        ax1.set_title('交易类型分布', fontweight='bold')
        ax1.axis('equal')

        # 交易金额分布
        trades_by_date = self.trades.groupby('date').agg({
            'amount': 'sum',
            'profit': 'sum'
        }).sort_index()

        ax2.plot(trades_by_date.index, trades_by_date['amount'],
                linewidth=2, color='#3498db')
        ax2.fill_between(trades_by_date.index, trades_by_date['amount'],
                        alpha=0.3, color='#3498db')
        ax2.set_title('每日交易金额', fontweight='bold')
        ax2.set_xlabel('日期', fontsize=10)
        ax2.set_ylabel('交易金额 (元)', fontsize=10)
        ax2.grid(True, alpha=0.3)

        # 显示盈亏分布
        buys = self.trades[self.trades['trade_type'] == 'buy']
        sells = self.trades[self.trades['trade_type'] == 'sell']

        ax2_twin = ax2.twinx()
        ax2_twin.plot(trades_by_date.index, trades_by_date['profit'],
                     linewidth=2, color='#e74c3c')
        ax2_twin.set_ylabel('累计盈亏 (元)', fontsize=10)

        plt.tight_layout()
        return fig

    def plot_max_drawdown(self, figsize: tuple = (12, 4)):
        """
        绘制回撤曲线

        Args:
            figsize: 图形大小
        """
        fig, ax = plt.subplots(figsize=figsize)

        # 计算回撤
        equity = self.equity_curve['total_equity'].values
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak

        # 绘制回撤
        ax.fill_between(self.equity_curve['date'], 0, drawdown * 100,
                       color='#e74c3c', alpha=0.3)
        ax.plot(self.equity_curve['date'], drawdown * 100,
               linewidth=2, color='#e74c3c')
        ax.axhline(y=0, color='#2ecc71', linestyle='--', linewidth=1)

        # 标记最大回撤点
        max_dd_idx = np.argmax(drawdown)
        max_dd_date = self.equity_curve['date'].iloc[max_dd_idx]
        max_dd_value = drawdown[max_dd_idx] * 100
        ax.annotate(f'最大回撤: {max_dd_value:.2f}%',
                   xy=(max_dd_date, max_dd_value),
                   xytext=(10, 10), textcoords='offset points',
                   fontsize=10, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7))

        # 设置标题和标签
        ax.set_title(f'{self.summary["fund_code"]} - 回撤曲线',
                    fontsize=14, fontweight='bold')
        ax.set_xlabel('日期', fontsize=12)
        ax.set_ylabel('回撤 (%)', fontsize=12)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return fig

    def print_trade_summary(self):
        """打印交易摘要"""
        if self.trades.empty:
            print("\n没有交易记录")
            return

        print("\n" + "="*60)
        print("交易摘要")
        print("="*60)

        # 总交易统计
        total_buys = len(self.trades[self.trades['trade_type'] == 'buy'])
        total_sells = len(self.trades[self.trades['trade_type'] == 'sell'])

        print(f"总买入次数: {total_buys}")
        print(f"总卖出次数: {total_sells}")
        print(f"净持仓变化: {total_sells - total_buys}")

        # 交易频率
        trades_by_date = self.trades.groupby('date').size()
        print(f"\n交易频率:")
        print(f"  最高日交易: {trades_by_date.max()} 次")
        print(f"  平均日交易: {trades_by_date.mean():.2f} 次")

        # 交易规模
        print(f"\n交易规模:")
        buy_amounts = self.trades[self.trades['trade_type'] == 'buy']['amount']
        sell_amounts = self.trades[self.trades['trade_type'] == 'sell']['amount']

        print(f"  买入金额: {buy_amounts.sum():,.2f} 元")
        print(f"  卖出金额: {sell_amounts.sum():,.2f} 元")

        # 首次和最后交易
        print(f"\n首次交易: {self.trades.iloc[0]['date']} "
              f"- {self.trades.iloc[0]['trade_type'].upper()} {self.trades.iloc[0]['quantity']}份 @ "
              f"{self.trades.iloc[0]['price']:.2f}元")
        print(f"最后交易: {self.trades.iloc[-1]['date']} "
              f"- {self.trades.iloc[-1]['trade_type'].upper()} {self.trades.iloc[-1]['quantity']}份 @ "
              f"{self.trades.iloc[-1]['price']:.2f}元")

        # 交易详情
        print("\n" + "-"*60)
        print("交易详情:")
        print("-"*60)

        # 按日期分组显示
        for date, group in self.trades.groupby('date'):
            if len(group) > 1:
                print(f"\n{date}:")
                for _, trade in group.iterrows():
                    type_symbol = '▲' if trade['trade_type'] == 'buy' else '▼'
                    print(f"  {type_symbol} {trade['trade_type'].upper()} "
                          f"{trade['quantity']}份 @ {trade['price']:.2f}元 "
                          f"(金额: {trade['amount']:.2f}元, "
                          f"费用: {trade['fee']:.2f}元, "
                          f"盈亏: {trade.get('profit', 0):.2f}元)")

        print("\n" + "="*60)

    def generate_summary_report(self) -> str:
        """
        生成摘要报告

        Returns:
            文本格式的摘要报告
        """
        summary = self.summary

        report = f"""
{'='*60}
{summary['fund_code']} ({summary['fund_code']}) 网格回测报告
{'='*60}

回测参数:
  初始资金: {summary['capital']:,.2f} 元
  回测周期: {self.fund_data['date'].iloc[0]} 至 {self.fund_data['date'].iloc[-1]}

回测结果:
  最终资产: {summary['final_capital']:,.2f} 元
  总收益率: {summary['total_return_pct']:.2f}%
  年化收益率: {summary['annual_return_pct']:.2f}%
  最大回撤: {summary['max_drawdown_pct']:.2f}%

交易统计:
  总交易次数: {summary['total_trades']}
  净持仓: {self.trades['trade_type'].value_counts().get('buy', 0) - self.trades['trade_type'].value_counts().get('sell', 0)}

网格设置:
  格子大小: {summary['grid_size']:.4f}元 ({summary['grid_size_pct']*100:.2f}%)
  交易份数: {summary['trade_shares']} 份

{'='*60}
"""

        return report

    def save_plots(self, output_dir: str = "output"):
        """
        保存所有图表

        Args:
            output_dir: 输出目录
        """
        import os
        os.makedirs(output_dir, exist_ok=True)

        print(f"\n保存图表到 {output_dir}/")

        # 资金曲线
        fig1 = self.plot_equity_curve()
        fig1.savefig(f"{output_dir}/equity_curve.png", dpi=300, bbox_inches='tight')
        plt.close(fig1)
        print("  - 资金曲线")

        # 净值曲线和交易
        fig2 = self.plot_nav_and_trades()
        fig2.savefig(f"{output_dir}/nav_and_trades.png", dpi=300, bbox_inches='tight')
        plt.close(fig2)
        print("  - 净值曲线与交易")

        # 交易分布
        fig3 = self.plot_trade_distribution()
        fig3.savefig(f"{output_dir}/trade_distribution.png", dpi=300, bbox_inches='tight')
        plt.close(fig3)
        print("  - 交易分布")

        # 回撤曲线
        fig4 = self.plot_max_drawdown()
        fig4.savefig(f"{output_dir}/max_drawdown.png", dpi=300, bbox_inches='tight')
        plt.close(fig4)
        print("  - 回撤曲线")
