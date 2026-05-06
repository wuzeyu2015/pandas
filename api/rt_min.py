import tushare as ts
print(ts.__version__)
ts.set_token('68bfb2cf8339b7530d8285e5929f6bfd240ce0adae5b2bc1e69632b0')

pro = ts.pro_api()

#获取科创新能源ETF易方达589960.SH的实时分钟数据
df = pro.fund_daily(ts_code='589960.SH', freq='1MIN')