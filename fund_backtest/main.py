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

# 从环境变量读取凭据，避免硬编码
JQ_USER = os.getenv('JQ_USER', '18380280516')
JQ_PASS = os.getenv('JQ_PASS', '306116315yY')
jqdatasdk.auth(JQ_USER, JQ_PASS)



def main():
    """主函数"""

    code = '159952'
    print(f"\n{'='*60}")
    print("基金网格回测系统")
    print(f"{'='*60}\n")
    print(f"基金代码: {code}")
    print(f"{'='*60}\n")

    # 1. 获取数据
    print("步骤 1: 获取数据...")
    try: 
            # 处理代码格式，添加交易所后缀
        if '.' not in code:
            if code.startswith('6'):
                code = f"{code}.XSHG"  # 上海交易所
            elif code.startswith('sz') or code.startswith('sh'):
                # 如果已经有sz/sh前缀，去掉它
                clean_code = code[2:]
                if clean_code.startswith('6'):
                    code = f"{clean_code}.XSHG"
                else:
                    code = f"{clean_code}.XSHE"
            else:
                code = f"{code}.XSHE"  # 深圳交易所
        else:
            code = code
        df =jqdatasdk.get_price(code, start_date= '20251023', end_date='20251119',
                                fq='post', frequency='1m',
                                fields=['open','close','low','high', 'volume'],
                                round=False)
        if df.empty:
            print(f"未获取到数据 [{code}]，请检查代码和日期范围")
            return pd.DataFrame()
        # 处理时间索引
        if not isinstance(df.index, pd.DatetimeIndex):
            for col in ['time', 'day', 'date', 'datetime']:
                if col in df.columns:
                    df.index = pd.to_datetime(df[col])
                    df = df.drop(columns=[col])
                    break
            else:
                raise ValueError("数据中找不到可用于时间索引的列")

        # 确保数据类型正确
        for col in ['open', 'close', 'high', 'low', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        print(f"成功获取 {len(df)} 条数据，时间范围: {df.index[0]} 至 {df.index[-1]}")
        
        
        # df = ak.stock_zh_a_minute(
        #     symbol='sz159952',
        #     period=3,
        #     adjust=""
        # )
        # if df is None or df.empty:
        #     return None
        
        # df['open'] = df['open'].astype(float)
        # df['close'] = df['close'].astype(float)
        # df['high'] = df['high'].astype(float)
        # df['low'] = df['low'].astype(float)
        
        # df = df.rename(columns={'day': 'date'})
        # df['date'] = pd.to_datetime(df['date'])


    except Exception as e:
        print(f"获取 {code} 数据失败: {e}")
        raise ValueError(f"无法获取基金 {code} 的数据")
        return None


    # 2. 创建回测实例
    print("\n步骤 2: 创建回测引擎...")
    backtest = GridBacktest(fund_code=code)

    # 3. 运行回测
    print("\n步骤 3: 运行回测...")
    backtest.run_backtest(df)



if __name__ == '__main__':
    sys.exit(main())
