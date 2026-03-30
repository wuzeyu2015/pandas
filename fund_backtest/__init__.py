"""
基金网格回测系统
"""
from .data_fetcher import FundDataFetcher
from .grid_backtest import GridBacktest
from .visualizer import BacktestVisualizer

__version__ = '1.0.0'
__author__ = '基金网格回测团队'

__all__ = [
    'FundDataFetcher',
    'GridBacktest',
    'BacktestVisualizer'
]
