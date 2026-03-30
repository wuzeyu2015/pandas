"""
主程序入口
"""
import sys
import os
import argparse
from datetime import datetime
from grid_backtest import GridBacktest
from visualizer import BacktestVisualizer

import pandas as pd
import akshare as ak
from typing import Optional
import jqdatasdk

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
jqdatasdk.auth('18380280516', '306116315yY')



def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='基金网格回测系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用默认参数回测
  python main.py --fund-code 159952 --days 730

  # 使用自定义网格参数
  python main.py --fund-code 159952 --grid-count 30 --grid-spacing 0.01

  # 从配置文件加载
  python main.py --config config.yaml
        """
    )

    parser.add_argument('--fund-code', type=str, help='基金代码')
    parser.add_argument('--fund-name', type=str, help='基金名称')
    parser.add_argument('--days', type=int, help='回测天数（最近N天）')
    parser.add_argument('--grid-count', type=int, help='网格数量')
    parser.add_argument('--grid-spacing', type=float, help='网格间距（百分比）')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--output-dir', type=str, default='output', help='输出目录')
    parser.add_argument('--no-visualize', action='store_true', help='不生成可视化图表')

    args = parser.parse_args()

    # 确定回测参数
    fund_code = args.fund_code


    print(f"\n{'='*60}")
    print("基金网格回测系统")
    print(f"{'='*60}\n")
    print(f"基金代码: {fund_code}")
    print(f"{'='*60}\n")

    # 1. 获取数据
    print("步骤 1: 获取数据...")
    try: 
        df =jqdatasdk.get_price(fund_code, start_date= '2025-10-25', end_date='2025-12-24 15:00:00',
                                fq='post', frequency='1m',
                                fields=['open','close','low','high'],
                                round=False)
        if df is None or df.empty:
            return None
        # 添加基金代码列
        df['fund_code'] = fund_code
        df = df.reset_index()
        df = df.rename(columns={'index': 'date'})
        # print(df)

    except Exception as e:
        print(f"获取 {fund_code} 数据失败: {e}")
        raise ValueError(f"无法获取基金 {fund_code} 的数据")
        return None


    # 2. 创建回测实例
    print("\n步骤 2: 创建回测引擎...")
    backtest = GridBacktest(fund_code=fund_code)

    # 3. 运行回测
    print("\n步骤 3: 运行回测...")
    results = backtest.run_backtest(df)

    # 4. 显示结果
    print("\n步骤 4: 显示结果...")
    # visualizer = BacktestVisualizer(results)
    # visualizer.print_trade_summary()
    # print(visualizer.generate_summary_report())
    # print(results)
    return 0


if __name__ == '__main__':
    sys.exit(main())
