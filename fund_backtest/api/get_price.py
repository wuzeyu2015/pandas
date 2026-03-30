import jqdatasdk
jqdatasdk.auth('18380280516', '306116315yY')
df =jqdatasdk.get_price("159952.XSHE", start_date= '2025-10-25', end_date='2025-12-24 15:00:00',
                                fq='post', frequency='1m',
                                fields=['open','close','low','high'],
                                round=False)# df = df.reset_index()
print(df.to_markdown())


# import pandas as pd
# import numpy as np
# from datetime import datetime, timedelta
# data = {
#     'date': pd.date_range('2024-01-01', periods=5),
#     'open': [2.0, 2.05, 2.03, 2.08, 2.10],
#     'high': [2.05, 2.08, 2.06, 2.10, 2.12],
#     'low': [1.98, 2.02, 2.00, 2.05, 2.08],
#     'close': [2.03, 2.05, 2.04, 2.09, 2.11],
#     'volume': [1000000, 1200000, 800000, 1500000, 1100000]
# }
# df = pd.DataFrame(data)
# print(df.to_markdown())