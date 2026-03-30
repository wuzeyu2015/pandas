import pandas as pd
import numpy as np
from datetime import datetime, timedelta

print("一、基础创建与查看")
print("1. 创建DataFrame")
# 方法1: 从字典创建
data = {
    'date': pd.date_range('2024-01-01', periods=5),
    'open': [2.0, 2.05, 2.03, 2.08, 2.10],
    'high': [2.05, 2.08, 2.06, 2.10, 2.12],
    'low': [1.98, 2.02, 2.00, 2.05, 2.08],
    'close': [2.03, 2.05, 2.04, 2.09, 2.11],
    'volume': [1000000, 1200000, 800000, 1500000, 1100000]
}
df = pd.DataFrame(data)
print(df)

print("2. 查看数据基本信息")
# 基本查看
print("形状:", df.shape)  # (行数, 列数)
print("\n数据类型:")
print(df.dtypes)
print("\n基本信息:")
print(df.info())
print("\n统计描述:")
print(df.describe())

# 查看首尾
print("前3行:")
print(df.head(3))
print("\n后3行:")
print(df.tail(3))

# 随机抽样
print("\n随机2行:")
print(df.sample(2, random_state=42))


print("二、数据筛选与选择")
print("1. 列选择")
# 选择单列
close_prices = df['close']
print("收盘价:", close_prices.tolist())

# 选择多列
ohlc = df[['date', 'open', 'high', 'low', 'close']]
print("\nOHLC数据:")
print(ohlc)

# 通过位置选择
print("\n第2-4行，第1-3列:")
print(df.iloc[1:4, 0:3])

# 通过标签选择
print("\n特定行和列:")
print(df.loc[0:2, ['date', 'close', 'volume']])


print("2. 行筛选（条件过滤）")
# 简单条件
high_volume = df[df['volume'] > 1000000]
print("高成交量日:", len(high_volume))

# 多条件
condition = (df['close'] > 2.05) & (df['volume'] > 1000000)
selected = df[condition]
print("\n收盘>2.05且成交量>100万:")
print(selected)

# 包含特定日期
specific_date = df[df['date'] == '2024-01-03']
print("\n2024-01-03数据:")
print(specific_date)

# 使用query方法
result = df.query('close > 2.05 and volume < 1300000')
print("\n使用query筛选:")
print(result)

print("3. 日期筛选")
# 设置日期为索引
df.set_index('date', inplace=True)

# 按日期范围筛选
print("1月1日到1月3日:")
print(df.loc['2024-01-01':'2024-01-03'])

# 按年份/月份筛选
print("\n2024年1月:")
print(df.loc['2024-01'])

# 特定工作日
print("\n周一的数据:")
print(df[df.index.dayofweek == 0])  # 0=周一

# 重置索引
df.reset_index(inplace=True)

print("三、数据处理与计算")
print("1. 添加新列")
# 计算涨跌幅
df['pct_change'] = df['close'].pct_change() * 100
print("涨跌幅:")
print(df[['date', 'close', 'pct_change']])

# 计算振幅
df['amplitude'] = (df['high'] - df['low']) / df['low'] * 100
print("\n振幅:")
print(df[['date', 'high', 'low', 'amplitude']])

# 计算移动平均
df['ma5'] = df['close'].rolling(window=5).mean()
df['ma10'] = df['close'].rolling(window=10).mean()
print("\n移动平均:")
print(df[['date', 'close', 'ma5', 'ma10']])

# 布尔列（信号）
df['above_ma5'] = df['close'] > df['ma5']
df['volume_spike'] = df['volume'] > df['volume'].rolling(20).mean() * 1.5



print("2. 缺失值处理")
# 检查缺失值
print("缺失值统计:")
print(df.isnull().sum())

# 填充缺失值
df_filled = df.copy()
df_filled['ma5'] = df_filled['ma5'].fillna(method='bfill')  # 向后填充
df_filled['ma10'] = df_filled['ma10'].fillna(df_filled['close'])  # 用收盘价填充

# 删除缺失值
df_clean = df.dropna()
print(f"\n删除缺失值后: {len(df_clean)}/{len(df)} 行")


print("3. 分组与聚合")
# 按周/月分组
df.set_index('date', inplace=True)

# 周统计
weekly = df.resample('W').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
    'pct_change': 'sum'
})
print("周度统计:")
print(weekly)

# 月统计
monthly = df.resample('M').agg({
    'open': 'first',
    'high': 'max',
    'low': 'min',
    'close': 'last',
    'volume': 'sum',
    'pct_change': lambda x: (x + 1).prod() - 1  # 月收益率
})
print("\n月度统计:")
print(monthly)