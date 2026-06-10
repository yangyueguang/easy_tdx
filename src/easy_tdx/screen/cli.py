"""screen 命令组 — 策略选股扫描器 CLI。

子命令：
    scan — 纯离线扫描信号
    rank — 回测排名
"""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def screen() -> None:
    """策略选股扫描器 — 用策略扫描全市场触发信号的股票。

    两步走工作流：

      easy-tdx screen scan --strategy strategies/rsi_reversal.py --output signals.json

      easy-tdx screen rank --from signals.json --sort sharpe --top 20 --table
    """


# ── scan 子命令 ──────────────────────────────────────────────────────────────


@screen.command()
@click.option("--strategy", "strategy_file", required=True, help="策略文件路径")
@click.option("--output", "output_file", default=None, help="输出 JSON 文件路径（默认 stdout）")
@click.option(
    "--universe",
    default="all",
    help="股票范围: all/sh/sz/<文件路径>（默认 all）",
)
@click.option("--vipdoc", default=None, help="离线数据目录（默认自动检测）")
@click.option("--cash", default=100_000.0, type=float, help="初始资金")
@click.option("--commission", default=0.0003, type=float, help="佣金率")
@click.option(
    "--workers",
    default=0,
    type=int,
    help="并发工作进程数: 0=串行（默认），2+=ProcessPoolExecutor 并发（推荐 4-8）",
)
@click.option("--cache", "cache_file", default=None, help="增量扫描缓存文件路径（JSON）")
def scan(
    strategy_file: str,
    output_file: str | None,
    universe: str,
    vipdoc: str | None,
    cash: float,
    commission: float,
    workers: int,
    cache_file: str | None,
) -> None:
    """纯离线扫描全市场，找出触发买入信号的股票。

    读取本地通达信 .day 文件，零网络 IO，串行约 30-60 秒，并发可提速 4-8 倍。

    示例：

      easy-tdx screen scan --strategy strategies/rsi_reversal.py

      easy-tdx screen scan --strategy strategies/rsi_reversal.py --output signals.json

      easy-tdx screen scan --strategy strategies/rsi_reversal.py --universe sz --workers 4

      easy-tdx screen scan --strategy strategies/rsi_reversal.py --cache scan_cache.json
    """

    strategy_cls = _load_strategy(strategy_file)
    strategy_name = strategy_cls.__name__
    click.echo(f"策略: {strategy_name}", err=True)
    click.echo(f"范围: {universe}", err=True)
    if workers > 0:
        click.echo(f"并发: {workers} 进程", err=True)
    if workers > 0 and cache_file:
        click.echo("注意: 并发模式暂不支持增量缓存，--cache 参数将被忽略", err=True)
    if cache_file:
        click.echo(f"缓存: {cache_file}", err=True)

    from .scanner import SignalScanner

    scanner = SignalScanner(
        strategy_cls=strategy_cls,
        vipdoc_path=vipdoc,
        cash=cash,
        commission=commission,
        cache_file=cache_file,
    )

    # 进度回调（输出到 stderr，避免污染 stdout 的 JSON）
    total_scanned = 0

    def on_progress(current: int, total: int, name: str) -> None:
        nonlocal total_scanned
        total_scanned = total
        if name == "done":
            click.echo(f"\r扫描完成: {total} 只", err=True)
        else:
            pct = current * 100 // total if total > 0 else 0
            click.echo(f"\r[{current}/{total}] {pct}% scanning {name}", nl=False, err=True)

    results = scanner.scan(universe=universe, progress_callback=on_progress, workers=workers)

    # 生成 JSON
    json_str = scanner.to_json(
        results=results,
        strategy_name=strategy_name,
        strategy_file=strategy_file,
        total_scanned=total_scanned,
    )

    # 输出
    if output_file:
        Path(output_file).write_text(json_str, encoding="utf-8")
        click.echo(f"信号数: {len(results)} → {output_file}")
    else:
        click.echo(json_str)


# ── rank 子命令 ──────────────────────────────────────────────────────────────


@screen.command("rank")
@click.option("--from", "from_source", required=True, help="信号 JSON 文件路径（- 表示 stdin）")
@click.option("--strategy", "strategy_file", default=None, help="覆盖策略文件（默认从 JSON 读取）")
@click.option("--sort", "sort_by", default="sharpe", help="排序指标（默认 sharpe）")
@click.option("--sort-reverse", is_flag=True, help="升序排列（用于回撤等越小越好的指标）")
@click.option("--top", "top_n", default=20, type=int, help="只显示前 N 名（默认 20）")
@click.option("--cash", default=1_000_000.0, type=float, help="初始资金")
@click.option("--count", default=0, type=int, help="使用最近 N 条 K 线，0=全部")
@click.option("--commission", default=0.0003, type=float, help="佣金率")
@click.option("--vipdoc", default=None, help="离线数据目录（默认自动检测）")
@click.option("--names/--no-names", default=False, help="是否在线查询股票名称（默认关闭）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
def rank_cmd(
    from_source: str,
    strategy_file: str | None,
    sort_by: str,
    sort_reverse: bool,
    top_n: int,
    cash: float,
    count: int,
    commission: float,
    vipdoc: str | None,
    names: bool,
    use_table: bool,
) -> None:
    """对扫描结果做历史回测并按指标排名。

    读取 scan 输出的 JSON，对每只股票跑完整回测，按指定指标排序。

    示例：

      easy-tdx screen rank --from signals.json --sort sharpe --top 20 --table

      easy-tdx screen rank --from signals.json --sort max_drawdown --sort-reverse

      easy-tdx screen scan --strategy strats/rsi.py | easy-tdx screen rank --from - --table
    """
    from .ranker import SignalRanker, load_signals

    # 加载信号
    signals, strategy_name, strategy_file_from_json = load_signals(from_source)

    if not signals:
        click.echo("无信号数据，无需排名")
        return

    # 确定策略
    effective_strategy_file = strategy_file or strategy_file_from_json
    if not effective_strategy_file:
        click.echo(
            "错误: 未指定策略文件，请使用 --strategy 或确保 JSON 包含 strategy_file", err=True
        )
        raise SystemExit(1)

    strategy_cls = _load_strategy(effective_strategy_file)
    strategy_name = strategy_cls.__name__

    click.echo(f"策略: {strategy_name} | 信号数: {len(signals)} | 排序: {sort_by}", err=True)

    ranker = SignalRanker(
        strategy_cls=strategy_cls,
        vipdoc_path=vipdoc,
        cash=cash,
        commission=commission,
        count=count,
    )

    # 进度回调（输出到 stderr，避免污染 stdout）
    def on_progress(current: int, total: int, label: str) -> None:
        if label == "done":
            click.echo(f"\r排名完成: {total} 只", err=True)
        else:
            pct = current * 100 // total if total > 0 else 0
            click.echo(f"\r[{current}/{total}] {pct}% backtesting {label}", nl=False, err=True)

    entries = ranker.rank(
        signals=signals,
        sort_by=sort_by,
        sort_reverse=sort_reverse,
        top_n=top_n,
        progress_callback=on_progress,
    )

    # 补齐名称（可选，需要网络）
    if names and entries:
        click.echo("\n正在获取股票名称...", err=True)
        entries = ranker.enrich_names(entries)

    # 输出
    if use_table:
        click.echo(ranker.to_table(entries, sort_by))
    else:
        click.echo(ranker.to_json(entries, strategy_name, sort_by))


# ── 辅助函数 ──────────────────────────────────────────────────────────────────


def _load_strategy(strategy_file: str) -> type:
    """加载策略类（复用 backtest.cli 的加载逻辑）。

    Args:
        strategy_file: 策略文件路径

    Returns:
        Strategy 子类
    """
    import importlib.util

    from easy_tdx.backtest.strategy import Strategy

    file_path = Path(strategy_file)
    if not file_path.exists():
        click.echo(f"错误: 策略文件不存在: {strategy_file}", err=True)
        raise SystemExit(1)

    spec = importlib.util.spec_from_file_location("strategy_module", file_path)
    if spec is None or spec.loader is None:
        click.echo(f"错误: 无法加载策略文件: {strategy_file}", err=True)
        raise SystemExit(1)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 查找 Strategy 子类
    for attr_name in dir(module):
        obj = getattr(module, attr_name)
        try:
            if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy:
                return obj
        except TypeError:
            pass

    click.echo(f"错误: 文件中未找到 Strategy 子类: {strategy_file}", err=True)
    raise SystemExit(1)
