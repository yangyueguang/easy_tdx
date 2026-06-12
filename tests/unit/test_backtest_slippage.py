"""滑点模型单元测试。"""

from __future__ import annotations

import pytest

from easy_tdx.backtest.slippage import (
    FixedSlippage,
    PercentSlippage,
    SlippageModel,
)


class TestSlippageBase:
    """基类验证。"""

    def test_cannot_instantiate_abc(self) -> None:
        """不能直接实例化 ABC。"""
        with pytest.raises(TypeError):
            SlippageModel()  # type: ignore[abstract]

    def test_subclass_must_implement_compute(self) -> None:
        """子类必须实现 compute。"""

        class BadModel(SlippageModel):
            pass

        with pytest.raises(TypeError):
            BadModel()  # type: ignore[abstract]


class TestFixedSlippage:
    """固定每股滑点。"""

    def test_zero_per_share(self) -> None:
        """per_share=0 时无滑点。"""
        model = FixedSlippage(per_share=0.0)
        cost = model.compute(price=10.0, size=100, volume=10000, volatility=0.3, direction="BUY")
        assert cost == 0.0

    def test_basic(self) -> None:
        """基本计算：100 股 × 0.01 元/股 = 1.0。"""
        model = FixedSlippage(per_share=0.01)
        cost = model.compute(price=10.0, size=100, volume=10000, volatility=0.3, direction="BUY")
        assert cost == pytest.approx(1.0)

    def test_large_size(self) -> None:
        """大单。"""
        model = FixedSlippage(per_share=0.05)
        cost = model.compute(
            price=50.0, size=10000, volume=500000, volatility=0.2, direction="SELL"
        )
        assert cost == pytest.approx(500.0)

    def test_direction_irrelevant(self) -> None:
        """方向不影响固定滑点。"""
        model = FixedSlippage(per_share=0.01)
        buy_cost = model.compute(
            price=10.0, size=100, volume=10000, volatility=0.3, direction="BUY"
        )
        sell_cost = model.compute(
            price=10.0, size=100, volume=10000, volatility=0.3, direction="SELL"
        )
        assert buy_cost == sell_cost


class TestPercentSlippage:
    """按成交金额百分比滑点。"""

    def test_zero_rate(self) -> None:
        """rate=0 时无滑点。"""
        model = PercentSlippage(rate=0.0)
        cost = model.compute(price=10.0, size=100, volume=10000, volatility=0.3, direction="BUY")
        assert cost == 0.0

    def test_basic(self) -> None:
        """10元 × 100股 × 0.001 = 1.0。"""
        model = PercentSlippage(rate=0.001)
        cost = model.compute(price=10.0, size=100, volume=10000, volatility=0.3, direction="BUY")
        assert cost == pytest.approx(1.0)

    def test_high_price(self) -> None:
        """高价股。"""
        model = PercentSlippage(rate=0.002)
        cost = model.compute(price=100.0, size=500, volume=20000, volatility=0.25, direction="BUY")
        # 100 × 500 × 0.002 = 100.0
        assert cost == pytest.approx(100.0)
