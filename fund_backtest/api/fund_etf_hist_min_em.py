import akshare as ak
import pandas as pd

df = ak.fund_etf_hist_min_em(symbol="159952", period="1", adjust="", start_date="2024-03-20 09:30:00", end_date="2024-03-20 17:40:00")
print(df)
print(f"数据量: {len(df)} 条")
