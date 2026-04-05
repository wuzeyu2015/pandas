
import backtrader as bt
import akshare as ak
import pandas as pd

def GetStockDatApi(code, start='20240425', end='20240426'):

    df = ak.fund_etf_hist_min_em(symbol=code, start_date=start, end_date=end)

    # 将交易日期设置为索引值
    df.index = pd.to_datetime(df["时间"])
    df.sort_index(inplace=True)
    df.drop(axis=1, columns='时间', inplace=True)

    recon_data = {'High': df.最高, 'Low': df.最低, 'Open': df.开盘, 'Close': df.收盘, \
                  'Volume': df.成交量}
    df_recon = pd.DataFrame(recon_data)

    return df_recon