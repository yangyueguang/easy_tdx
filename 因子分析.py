# src/easy_tdx/factor/transform.py
"""因子预处理 — 纯函数管道。"""
from __future__ import annotations
import numpy as np
import pandas as pd



def _resolve_factor(f: str):
    """将因子名或实例解析为 返回有compute方法的对象用于计算因子。TODO"""
    return {'compute': lambda x: x}


def _datetime_to_int(dt_val: object) -> int:
    """将 datetime 值转为 YYYYMMDD 整数。"""
    if hasattr(dt_val, "strftime"):
        strftime = getattr(dt_val, "strftime")
        return int(strftime("%Y%m%d"))
    if isinstance(dt_val, (int, float)):
        return int(dt_val)
    return 0


_ALL_DATES: object = object()


class FactorEngine:
    """批量因子计算引擎。"""

    def compute_single(self, df: pd.DataFrame, factors: list[str]) -> pd.DataFrame:
        """单股票多因子计算。"""
        if not factors:
            return df.copy()

        result = df.copy()
        for f in factors:
            factor = _resolve_factor(f)
            result[factor.name] = factor.compute(df)

        return result

    def compute_cross_section(self, data: dict[str, pd.DataFrame], factors: list[str], date: int = _ALL_DATES,  # type: ignore[assignment]) -> pd.DataFrame:
        """多股票截面因子计算。

        Args:
            date: int 精确匹配日期；None 仅最新一行；默认(不传)全部日期。
        """
        if not data:
            return pd.DataFrame()

        filter_latest = date is None
        all_frames: list[pd.DataFrame] = []

        for code, df in data.items():
            if df.empty:
                continue

            computed = self.compute_single(df, factors)
            computed["_date_int"] = computed["datetime"].apply(_datetime_to_int)

            if date is not None and date is not _ALL_DATES:
                computed = computed[computed["_date_int"] == date]
            elif filter_latest:
                computed = computed.iloc[[-1]]

            factor_names = [_resolve_factor(f).name for f in factors]
            keep_cols = ["_date_int"] + factor_names
            sub = computed[keep_cols].copy()
            sub["_code"] = code
            all_frames.append(sub)

        if not all_frames:
            return pd.DataFrame()

        combined = pd.concat(all_frames, ignore_index=True)
        combined = combined.rename(columns={"_date_int": "date", "_code": "code"})

        col_order = ["date", "code"] + [_resolve_factor(f).name for f in factors]
        combined = combined[col_order].sort_values(["date", "code"]).reset_index(drop=True)

        return combined

    def compute_forward_returns(self, data: dict[str, pd.DataFrame], period: int = 5) -> pd.DataFrame:
        """计算远期收益率。"""
        if not data:
            return pd.DataFrame()

        col_name = f"forward_{period}d"
        all_frames: list[pd.DataFrame] = []

        for code, df in data.items():
            if df.empty or len(df) < period + 1:
                continue

            close = df["close"].to_numpy()
            forward = np.full(len(close), np.nan)
            forward[: len(close) - period] = close[period:] / close[: len(close) - period] - 1

            dates = df["datetime"].apply(_datetime_to_int)

            sub = pd.DataFrame({
                    "date": dates, "code": code, col_name: forward, })
            all_frames.append(sub)

        if not all_frames:
            return pd.DataFrame(columns=["date", "code", col_name])

        combined = pd.concat(all_frames, ignore_index=True)
        combined = combined.sort_values(["date", "code"]).reset_index(drop=True)
        return combined


# src/easy_tdx/factor/analysis.py
"""因子有效性分析引擎。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class FactorReport:
    """单因子分析报告。"""

    name: str
    ic_mean: float
    ic_std: float
    ir: float
    ic_positive_rate: float
    quantile_returns: dict[str, float]
    top_minus_bottom: float
    turnover_rate: float
    autocorr: float
    ic_series: pd.Series


class FactorAnalyzer:
    """因子有效性分析引擎。"""

    def __init__(self, factor_data: pd.DataFrame, return_data: pd.DataFrame, factor_col: str = "momentum_20d", return_col: str = "forward_5d", n_quantiles: int = 5):
        self._factor_col = factor_col
        self._return_col = return_col
        self._n_quantiles = n_quantiles
        self._merged = factor_data.merge(return_data[["date", "code", return_col]], on=["date", "code"], how="inner")

    def compute_ic(self, method: str = "spearman") -> pd.Series:
        """逐截面计算 Rank IC。"""
        dates = sorted(self._merged["date"].unique())
        ic_values: list[float] = []
        for date in dates:
            sub = self._merged[self._merged["date"] == date]
            valid = sub[[self._factor_col, self._return_col]].dropna()
            if len(valid) < 5:
                ic_values.append(np.nan)
                continue
            if method == "spearman":
                try:
                    import scipy  # noqa: F401  # pandas spearman lazy import
                except ImportError as e:
                    raise ImportError("Rank IC (spearman) 需要 scipy，请执行 `pip install easy-tdx[science]`") from e
                corr = valid[self._factor_col].corr(valid[self._return_col], method="spearman")
            else:
                corr = valid[self._factor_col].corr(valid[self._return_col], method="pearson")
            ic_values.append(corr)
        return pd.Series(ic_values, index=dates, name="IC")

    def compute_quantile_returns(self) -> pd.DataFrame:
        """分层收益分析。"""
        dates = sorted(self._merged["date"].unique())
        q_names = [f"q{i + 1}" for i in range(self._n_quantiles)]
        rows: list[list[float]] = []
        for date in dates:
            sub = self._merged[self._merged["date"] == date]
            valid = sub[[self._factor_col, self._return_col]].dropna()
            if len(valid) < self._n_quantiles:
                rows.append([np.nan] * self._n_quantiles)
                continue
            valid = valid.copy()
            valid["_q"] = pd.qcut(valid[self._factor_col], self._n_quantiles, labels=False, duplicates="drop")
            means = valid.groupby("_q")[self._return_col].mean()
            rows.append([float(means.get(q, np.nan)) for q in range(self._n_quantiles)])
        return pd.DataFrame(rows, index=dates, columns=q_names)

    def compute_turnover(self) -> float:
        """因子换手率。"""
        dates = sorted(self._merged["date"].unique())
        if len(dates) < 2:
            return 0.0
        n_top = max(self._n_quantiles, 5)
        overlaps: list[float] = []
        prev_top: set[str] = set()
        for date in dates:
            sub = self._merged[self._merged["date"] == date]
            valid = sub[[self._factor_col, "code"]].dropna()
            if len(valid) < n_top:
                continue
            top = set(valid.nlargest(n_top, self._factor_col)["code"].tolist())
            if prev_top:
                overlaps.append(len(top & prev_top) / len(top | prev_top))
            prev_top = top
        if not overlaps:
            return 0.0
        return 1.0 - float(np.mean(overlaps))

    def compute_decay(self, max_lag: int = 10) -> pd.DataFrame:
        """因子衰减分析。"""
        ic_series = self.compute_ic()
        autocorr_values: list[float] = []
        for lag in range(1, max_lag + 1):
            if lag < len(ic_series):
                ac = ic_series.autocorr(lag=lag)
                autocorr_values.append(ac if not np.isnan(ac) else 0.0)
            else:
                autocorr_values.append(0.0)
        return pd.DataFrame({"lag": range(1, max_lag + 1), "autocorr": autocorr_values})

    def full_report(self) -> FactorReport:
        """一键生成完整分析报告。"""
        ic_series = self.compute_ic()
        qr = self.compute_quantile_returns()

        ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else 0.0
        ic_std = float(ic_series.std()) if len(ic_series) > 1 else 0.0
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        ic_positive_rate = float((ic_series > 0).mean()) if len(ic_series) > 0 else 0.0

        quantile_means = qr.mean()
        quantile_returns = {
            f"q{i + 1}": float(quantile_means.iloc[i]) for i in range(len(quantile_means))
        }
        top_minus_bottom = quantile_returns.get("q5", 0.0) - quantile_returns.get("q1", 0.0)

        turnover = self.compute_turnover()
        autocorr = float(ic_series.autocorr(lag=1)) if len(ic_series) > 1 else 0.0

        return FactorReport(name=self._factor_col, ic_mean=ic_mean, ic_std=ic_std, ir=ir, ic_positive_rate=ic_positive_rate, quantile_returns=quantile_returns, top_minus_bottom=top_minus_bottom, turnover_rate=turnover, autocorr=autocorr if not np.isnan(autocorr) else 0.0, ic_series=ic_series)


def winsorize(factor_data: pd.DataFrame, columns: str, method: str = "mad", threshold: float = 3.0) -> pd.DataFrame:
    """截面去极值。"""
    if isinstance(columns, str):
        columns = [columns]
    result = factor_data.copy()

    for col in columns:
        if col not in result.columns:
            continue

        def _clip_group(group: pd.Series) -> pd.Series:
            valid = group.dropna()
            if len(valid) < 3:
                return group
            if method == "mad":
                median = valid.median()
                mad = (valid - median).abs().median() * 1.4826
                lower = median - threshold * mad
                upper = median + threshold * mad
            elif method == "sigma":
                mean = valid.mean()
                std = valid.std()
                lower = mean - threshold * std
                upper = mean + threshold * std
            elif method == "percentile":
                lower = valid.quantile(0.025)
                upper = valid.quantile(0.975)
            else:
                raise ValueError(f"未知去极值方法: {method!r}")
            return group.clip(lower, upper)

        if "date" in result.columns:
            result[col] = result.groupby("date")[col].transform(_clip_group)
        else:
            result[col] = _clip_group(result[col])

    return result


def zscore(factor_data: pd.DataFrame, columns: str, cross_section: bool = True) -> pd.DataFrame:
    """标准化。"""
    if isinstance(columns, str):
        columns = [columns]
    result = factor_data.copy()

    for col in columns:
        if col not in result.columns:
            continue

        def _zscore_group(group: pd.Series) -> pd.Series:
            std = group.std()
            if std == 0 or pd.isna(std):
                return group * 0
            return (group - group.mean()) / std

        if cross_section and "date" in result.columns:
            result[col] = result.groupby("date")[col].transform(_zscore_group)
        else:
            result[col] = _zscore_group(result[col])

    return result


def rank_normalize(factor_data: pd.DataFrame, columns: str) -> pd.DataFrame:
    """排名归一化 [0, 1]。"""
    if isinstance(columns, str):
        columns = [columns]
    result = factor_data.copy()

    for col in columns:
        if col not in result.columns:
            continue

        def _rank_group(group: pd.Series) -> pd.Series:
            return group.rank(pct=True)

        if "date" in result.columns:
            result[col] = result.groupby("date")[col].transform(_rank_group)
        else:
            result[col] = _rank_group(result[col])

    return result


def fill_missing(factor_data: pd.DataFrame, columns: str, method: str = "cross_mean") -> pd.DataFrame:
    """缺失值填充。"""
    if isinstance(columns, str):
        columns = [columns]
    result = factor_data.copy()

    for col in columns:
        if col not in result.columns:
            continue
        if method == "cross_mean":
            if "date" in result.columns:

                def _fill_mean(group: pd.Series) -> pd.Series:
                    return group.fillna(group.mean())

                result[col] = result.groupby("date")[col].transform(_fill_mean)
            else:
                result[col] = result[col].fillna(result[col].mean())
        elif method == "forward_fill":
            if "code" in result.columns:
                result[col] = result.groupby("code")[col].ffill()
            else:
                result[col] = result[col].ffill()
        else:
            raise ValueError(f"未知填充方法: {method!r}")

    return result


def orthogonalize(factor_data: pd.DataFrame, target: str, by: str) -> pd.DataFrame:
    """因子正交化。"""
    if isinstance(by, str):
        by = [by]
    result = factor_data.copy()

    if target not in result.columns:
        return result
    for b in by:
        if b not in result.columns:
            return result

    y = result[target].to_numpy(dtype=np.float64)
    X_cols = [result[b].to_numpy(dtype=np.float64) for b in by]
    X = np.column_stack([np.ones(len(y))] + X_cols)

    mask = ~np.isnan(y)
    for xc in X_cols:
        mask &= ~np.isnan(xc)

    if mask.sum() < len(by) + 2:
        return result

    coef, _, _, _ = np.linalg.lstsq(X[mask], y[mask], rcond=None)
    predicted = X @ coef
    residual = y - predicted
    residual[~mask] = np.nan
    result[target] = residual

    return result


def preprocess(factor_data: pd.DataFrame, columns: list[str], steps: list[str] = None) -> pd.DataFrame:
    """一键预处理管道。"""
    if steps is None:
        steps = ["winsorize", "zscore", "fill_missing"]

    result = factor_data.copy()
    for step in steps:
        if step == "winsorize":
            result = winsorize(result, columns)
        elif step == "zscore":
            result = zscore(result, columns)
        elif step == "rank_normalize":
            result = rank_normalize(result, columns)
        elif step == "fill_missing":
            result = fill_missing(result, columns)
        else:
            raise ValueError(f"未知预处理步骤: {step!r}")

    return result
