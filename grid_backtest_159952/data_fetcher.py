#!/usr/bin/env python3
"""
获取广发创业板ETF(159952)历史数据
"""
import pandas as pd
import akshare as ak
import os
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_etf_data(symbol="sz159952", start_date="2020-01-01", end_date=None):
    """
    获取ETF历史数据
    
    Args:
        symbol: 股票代码，sz159952 或 sh510300
        start_date: 开始日期
        end_date: 结束日期，默认今天
    
    Returns:
        DataFrame with columns: date, open, high, low, close, volume
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        logger.info(f"开始获取 {symbol} 数据，时间范围: {start_date} 到 {end_date}")
        
        # 使用akshare获取数据
        df = ak.fund_etf_hist_sina(symbol=symbol, period="daily")
        
        if df.empty:
            logger.error("获取的数据为空")
            return None
        
        # 重命名列
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume'
        })
        
        # 确保日期格式
        df['date'] = pd.to_datetime(df['date'])
        
        # 筛选日期范围
        mask = (df['date'] >= pd.Timestamp(start_date)) & (df['date'] <= pd.Timestamp(end_date))
        df = df[mask].copy()
        
        # 排序
        df = df.sort_values('date').reset_index(drop=True)
        
        # 转换数据类型
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        logger.info(f"成功获取 {len(df)} 条数据")
        logger.info(f"数据时间范围: {df['date'].min()} 到 {df['date'].max()}")
        logger.info(f"价格范围: {df['close'].min():.3f} ~ {df['close'].max():.3f}")
        
        return df
        
    except Exception as e:
        logger.error(f"获取数据失败: {e}")
        return None

def save_data_to_csv(df, filename="data/159952.csv"):
    """保存数据到CSV文件"""
    if df is not None:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        df.to_csv(filename, index=False)
        logger.info(f"数据已保存到 {filename}")
        return True
    return False

def load_data_from_csv(filename="data/159952.csv"):
    """从CSV文件加载数据"""
    try:
        df = pd.read_csv(filename, parse_dates=['date'])
        logger.info(f"从 {filename} 加载了 {len(df)} 条数据")
        return df
    except Exception as e:
        logger.error(f"加载数据失败: {e}")
        return None

if __name__ == "__main__":
    # 测试数据获取
    df = fetch_etf_data(symbol="sz159952", start_date="2023-01-01")
    if df is not None:
        save_data_to_csv(df)
        print("\n前5行数据:")
        print(df.head())
        print("\n数据基本信息:")
        print(df.info())