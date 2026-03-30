#!/usr/bin/env python3
"""
主程序入口
"""
import logging
import pandas as pd
from data_fetcher import fetch_etf_data, load_data_from_csv, save_data_to_csv
from grid_backtest import GridBacktest
from result_analyzer import ResultAnalyzer

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数"""
    print("="*60)
    print("ETF网格交易回测系统")
    print("标的: 广发创业板ETF (159952)")
    print("="*60)
    
    try:
        # 1. 获取数据
        logger.info("步骤1: 获取数据")
        data_file = "data/159952.csv"
        
        # 尝试从文件加载，如果不存在则从网络获取
        df = load_data_from_csv(data_file)
        if df is None:
            logger.info("本地数据不存在，从网络获取...")
            df = fetch_etf_data(symbol="sz159952", start_date="2023-01-01")
            if df is not None:
                save_data_to_csv(df, data_file)
            else:
                logger.error("无法获取数据，程序退出")
                return
        
        print(f"\n数据概览:")
        print(f"时间范围: {df['date'].min().date()} 到 {df['date'].max().date()}")
        print(f"数据条数: {len(df)}")
        print(f"价格范围: {df['close'].min():.3f} ~ {df['close'].max():.3f}")
        print(f"最新价格: {df['close'].iloc[-1]:.3f}")
        
        # 2. 运行回测
        logger.info("\n步骤2: 运行回测")
        backtest = GridBacktest("config.yaml")
        results = backtest.run(df)
        
        if not results:
            logger.error("回测失败")
            return
        
        # 3. 分析结果
        logger.info("\n步骤3: 分析回测结果")
        analyzer = ResultAnalyzer(backtest)
        
        # 打印摘要
        analyzer.print_summary()
        
        # 显示详细交易记录
        trade_df = backtest.get_trade_dataframe()
        if not trade_df.empty:
            print("\n最近5笔交易记录:")
            pd.set_option('display.float_format', '{:.3f}'.format)
            print(trade_df[['date', 'trade_type', 'price', 'shares', 'amount']].tail(5))
        
        # 4. 可视化
        logger.info("\n步骤4: 生成图表")
        analyzer.plot_results(save_path="results/backtest_results.png")
        
        # 5. 导出结果
        logger.info("\n步骤5: 导出结果")
        analyzer.export_results("results")
        
        print("\n✅ 回测完成!")
        
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()