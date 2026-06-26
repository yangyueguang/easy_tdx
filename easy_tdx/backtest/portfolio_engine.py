"""多标的组合回测引擎。

支持同时回测多只股票，共享资金池，按策略信号分配资金。
每只标的独立产生信号，引擎统一管理仓位和资金。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategy import Strategy
from easy_tdx.backtest.types import BacktestResult


@dataclass
class StockData:
    """单只标的的数据和标识。

    Attributes:
        code: 股票代码（如 "000001"）
        market: 市场（如 "SZ"）
        df: K线 DataFrame
    """

    code: str
    market: str
    df: pd.DataFrame


@dataclass
class PortfolioResult:
    """组合回测结果。

    Attributes:
        total_performance: 组合整体绩效指标
        individual_results: 每只标的的独立回测结果
        equity_allocation: 每只标的的资金分配比例
    """

    total_performance: dict[str, float]
    individual_results: dict[str, BacktestResult]
    equity_allocation: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化字典。"""
        return {
            "total_performance": self.total_performance,
            "individual_results": {k: v.to_dict() for k, v in self.individual_results.items()},
            "equity_allocation": self.equity_allocation,
        }


class PortfolioBacktestEngine:
    """多标的组合回测引擎。

    管理多只股票的共享资金池，独立运行策略，
    按均等或自定义比例分配资金。

    用法::

        engine = PortfolioBacktestEngine(
            strategy_cls=MyStrategy,
            stocks=[
                StockData("000001", "SZ", df1),
                StockData("600000", "SH", df2),
            ],
            total_cash=200000,
        )
        result = engine.run()
        print(result.total_performance)
    """

    def __init__(
        self,
        strategy_cls: type[Strategy],
        stocks: list[StockData],
        total_cash: float = 200_000.0,
        allocation: str = "equal",
        commission: float = 0.0003,
        min_commission: float = 5.0,
        stamp_tax: float = 0.001,
        slippage: float = 0.0,
        execution: str = "next_open",
        chanlun_level: str = None,
    ) -> None:
        """初始化组合回测引擎。

        Args:
            strategy_cls: 策略类
            stocks: 标的列表（StockData）
            total_cash: 总资金
            allocation: 资金分配方式
                - "equal": 均等分配
                - "capitalization": 按市值加权（需额外数据）
            commission: 佣金率
            min_commission: 最低佣金
            stamp_tax: 印花税
            slippage: 滑点
            execution: 执行模式
            chanlun_level: 缠论级别（可选）
        """
        self._strategy_cls = strategy_cls
        self._stocks = stocks
        self._total_cash = total_cash
        self._allocation = allocation
        self._commission = commission
        self._min_commission = min_commission
        self._stamp_tax = stamp_tax
        self._slippage = slippage
        self._execution = execution
        self._chanlun_level = chanlun_level

    def _compute_allocations(self) -> dict[str, float]:
        """计算每只标的的资金分配。"""
        n = len(self._stocks)
        if n == 0:
            return {}

        if self._allocation == "equal":
            per_stock_cash = self._total_cash / n
            return {f"{s.market}{s.code}": per_stock_cash for s in self._stocks}

        # 默认均等分配
        per_stock_cash = self._total_cash / n
        return {f"{s.market}{s.code}": per_stock_cash for s in self._stocks}

    def run(self) -> PortfolioResult:
        """运行组合回测。

        对每只标的独立运行回测，按分配的资金量计算收益，
        最终汇总为组合整体绩效。

        Returns:
            PortfolioResult 包含整体绩效和各标的详细结果
        """
        allocations = self._compute_allocations()
        individual_results: dict[str, BacktestResult] = {}

        for stock in self._stocks:
            key = f"{stock.market}{stock.code}"
            cash = allocations.get(key, 0)

            engine = BacktestEngine(
                strategy=self._strategy_cls,
                cash=cash,
                commission=self._commission,
                min_commission=self._min_commission,
                stamp_tax=self._stamp_tax,
                slippage=self._slippage,
                execution=self._execution,
                chanlun_level=self._chanlun_level,
            )
            result = engine.run(stock.df)
            individual_results[key] = result

        # 汇总整体绩效
        total_perf = self._aggregate_performance(individual_results, allocations)

        # 计算资金占比
        total_alloc = sum(allocations.values())
        equity_pct = {k: v / total_alloc if total_alloc > 0 else 0 for k, v in allocations.items()}

        return PortfolioResult(
            total_performance=total_perf,
            individual_results=individual_results,
            equity_allocation=equity_pct,
        )

    def _aggregate_performance(
        self,
        results: dict[str, BacktestResult],
        allocations: dict[str, float],
    ) -> dict[str, float]:
        """汇总所有标的的绩效为组合整体绩效。

        使用资金加权方式计算组合收益率。

        Args:
            results: 各标的回测结果
            allocations: 各标的资金分配

        Returns:
            组合整体绩效指标
        """
        total_cash = sum(allocations.values())
        if total_cash == 0:
            return {"total_return": 0.0, "annual_return": 0.0}

        # 资金加权收益率
        weighted_return = 0.0
        for key, result in results.items():
            alloc = allocations.get(key, 0)
            weight = alloc / total_cash
            ret = result.performance.get("total_return", 0.0)
            weighted_return += weight * ret

        return {
            "total_return": weighted_return,
            "annual_return": weighted_return,  # 简化，实际应根据周期年化
            "total_stocks": len(results),
            "total_cash": total_cash,
        }
