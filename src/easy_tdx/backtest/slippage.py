"""可插拔滑点模型。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SlippageModel(ABC):
    """滑点模型基类。

    所有滑点模型必须实现 compute() 方法，返回总滑点成本（金额）。
    """

    @abstractmethod
    def compute(
        self,
        price: float,
        size: float,
        volume: float,
        volatility: float,
        direction: str,
    ) -> float:
        """计算滑点成本。

        Args:
            price: 成交价格
            size: 订单数量（股）
            volume: 当日成交量（股），0 表示无数据
            volatility: 近期年化波动率，0 表示无数据
            direction: 交易方向 BUY / SELL

        Returns:
            总滑点成本（金额，非比率）
        """
        ...


class FixedSlippage(SlippageModel):
    """固定每股滑点（向后兼容）。"""

    def __init__(self, per_share: float = 0.01) -> None:
        self._per_share = per_share

    def compute(
        self,
        price: float,
        size: float,
        volume: float,
        volatility: float,
        direction: str,
    ) -> float:
        return size * self._per_share


class PercentSlippage(SlippageModel):
    """按成交金额百分比滑点。"""

    def __init__(self, rate: float = 0.001) -> None:
        self._rate = rate

    def compute(
        self,
        price: float,
        size: float,
        volume: float,
        volatility: float,
        direction: str,
    ) -> float:
        return price * size * self._rate
