import akshare as ak
import pandas as pd

# 示例1：获取“广发创业板ETF”(159952)的日频率历史行情（不复权）
# 这是最基本的调用方式
df_daily = ak.fund_etf_hist_sina(
    symbol='sz159952'
)
print("广发创业板ETF(159952) 日线数据 (不复权):")
print(df_daily.to_markdown())
print(f"数据量: {len(df_daily)} 条")
