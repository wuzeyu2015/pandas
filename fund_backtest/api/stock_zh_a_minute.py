import akshare as ak
import pandas as pd

df_daily = ak.stock_zh_a_minute(
    symbol='sz159952',
    period=15,
    adjust=""
)
print(df_daily.to_markdown())
print(f"数据量: {len(df_daily)} 条")
