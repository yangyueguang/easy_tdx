"""通达信 4 字节自定义浮点格式解码（成交量专用）。

格式：4 字节小端 uint32，分三段：
  [3] logpoint  — 指数部分
  [2] hleax     — 高精度部分
  [1] lheax     — 中精度部分
  [0] lleax     — 低精度部分

警告：此函数专为成交量设计，不可用于价格字段（pytdx Bug #3）。
"""

"""A 股价格限制规则引擎。"""
"""分时与逐笔成交模型"""
from dataclasses import dataclass, field
from enum import IntEnum
from dataclasses import asdict, is_dataclass
import pandas as pd
from typing import Any
# from commands import TdxDecodeError
class TdxDecodeError(Exception):
    """响应报文解析失败"""
class Market(IntEnum):
    SZ = 0  # 深圳
    SH = 1  # 上海
    BJ = 2  # 北京


class KlineCategory(IntEnum):
    MIN_5 = 0
    MIN_15 = 1
    MIN_30 = 2
    MIN_60 = 3
    DAY = 4
    WEEK = 5
    MONTH = 6
    MIN_1 = 7
    MIN_3 = 8  # 通达信内部用，实际同 MIN_1
    YEAR = 9
    SEASON = 10
    YEAR_ALT = 11
"""K 线数据模型"""


@dataclass
class SecurityBar:
    """单根 K 线（适用于 1m/5m/15m/30m/60m/日/周/月/季/年）"""

    open: float
    close: float
    high: float
    low: float
    vol: float  # 成交量（股）
    amount: float  # 成交额（元）

    year: int
    month: int
    day: int
    hour: int
    minute: int

    # 原始字节，供字段逆向分析使用
    _raw: bytes = field(default=b"", repr=False, compare=False)

    @property
    def datetime_str(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}"


@dataclass
class XdxrRecord:
    """除权除息记录（一只股票可有多条）

    pytdx Bug #1 已修复：循环内不再从 body[:7] 读 market/code，
    而是从当前 pos 正确读取。
    """

    market: Market
    code: str
    year: int
    month: int
    day: int
    category: int  # 事件类型（见下方 CATEGORY_NAMES）
    name: str  # 事件类型名称

    # category == 1（除权除息）
    fenhong: float = None  # 每股分红（元；协议原值按每10股）
    peigujia: float = None  # 配股价（元/股）
    songzhuangu: float = None  # 每股送转股比例（协议原值按每10股）
    peigu: float = None  # 每股配股比例（协议原值按每10股）

    # category in [11, 12]（扩缩股）
    suogu: float = None  # 缩股比例

    # category in [13, 14]（权证）
    xingquanjia: float = None  # 行权价
    fenshu: float = None  # 分数

    # category in [2..10]（股本变动类，单位：万股）
    panqian_liutong: float = None  # 盘前流通股本（万股）
    panhou_liutong: float = None  # 盘后流通股本（万股）
    qian_zongguben: float = None  # 前总股本（万股）
    hou_zongguben: float = None  # 后总股本（万股）

    _raw: bytes = field(default=b"", repr=False, compare=False)


XDXR_CATEGORY_NAMES: dict[int, str] = {
    1: "除权除息", 2: "送配股上市", 3: "非流通股上市", 4: "未知股本变动", 5: "股本变化", 6: "增发新股", 7: "股份回购", 8: "增发新股上市", 9: "转配股上市", 10: "可转债上市", 11: "扩缩股", 12: "非流通股缩股", 13: "送认购权证", 14: "送认沽权证", }


@dataclass
class FinanceInfo:
    """最新财务数据（单只股票）"""

    market: Market
    code: str

    # 股本（万股）
    liutong_guben: float  # 流通股本
    zong_guben: float  # 总股本
    guojia_gu: float  # 国家股
    faqiren_faren_gu: float  # 发起人法人股
    faren_gu: float  # 法人股
    b_gu: float  # B股
    h_gu: float  # H股
    zhigong_gu: float  # 职工股

    # 基本信息
    province: int  # 所属省份代码
    industry: int  # 所属行业代码
    updated_date: int  # 财务更新日期 YYYYMMDD
    ipo_date: int  # 上市日期 YYYYMMDD
    gudong_renshu: float  # 股东人数

    # 资产负债（元）
    zong_zichan: float  # 总资产
    liudong_zichan: float  # 流动资产
    guding_zichan: float  # 固定资产
    wuxing_zichan: float  # 无形资产
    liudong_fuzhai: float  # 流动负债
    changqi_fuzhai: float  # 长期负债
    ziben_gongjijin: float  # 资本公积金
    jing_zichan: float  # 净资产

    # 利润（元）
    zhuying_shouru: float  # 主营收入
    zhuying_lirun: float  # 主营利润
    yingshou_zhangkuan: float  # 应收账款
    yingye_lirun: float  # 营业利润
    touzi_shouyu: float  # 投资收益
    jingying_xianjinliu: float  # 经营现金流
    zong_xianjinliu: float  # 总现金流
    cunhuo: float  # 存货
    lirun_zonghe: float  # 利润总额
    shuihou_lirun: float  # 税后利润
    jing_lirun: float  # 净利润
    weifen_lirun: float  # 未分配利润

    # 每股指标
    meigujing_zichan: float  # 每股净资产（原 baoliu1）

    # 协议保留字段（含义未完全确认）
    reserve2: float = field(default=0.0, repr=False)  # 原 baoliu2

    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class CompanyInfoCategory:
    """公司信息文件目录条目"""

    name: str = ""  # 目录名（如“最新提示”）
    filename: str = ""  # 文件名（如 '600000.txt'）
    start: int = 0  # 内容起始偏移
    length: int = 0  # 内容长度（字节）


@dataclass
class FinancialFileInfo:
    """财报 zip 文件索引条目（来自 tdxfin/gpcw.txt）。"""

    filename: str  # "gpcw20260331.zip"
    hash: str  # MD5 hex digest
    filesize: int  # 字节


@dataclass
class FinancialRecord:
    """单只股票的一期历史专业财报记录。"""

    code: str  # 6 位股票代码
    market: Market  # 市场
    report_date: int  # 报告期 YYYYMMDD
    fields: list[float]  # N 个浮点字段（N = report_size / 4）


@dataclass
class TdxBlock:
    """通达信板块信息（行业、概念、风格等）"""

    name: str  # 板块名称（如“房地产”）
    category: int  # 板块分类（0=行业, 1=地域, 2=概念, 3=风格, 等）
    count: int  # 板块包含股票数量
    codes: list[str]  # 股票代码列表（6位数字代码）

@dataclass
class SecurityQuote:
    """单只股票实时五档行情。

    带 unknown_ 前缀的字段保留原始协议值，其含义已在逆向分析中确认：
      unknown_2: 指数→集合竞价成交金额/100；个股→舍入残差≈0
      unknown_3: 个股→集合竞价成交金额/100；指数→负值/无意义
      unknown_5-8: 保留字段，恒为 0
    _raw 为该股票记录的原始字节切片。
    """

    market: Market
    code: str

    # 价格
    price: float  # 现价
    pre_close: float  # 昨收
    open: float  # 今开
    high: float  # 最高
    low: float  # 最低

    # 量额
    vol: float  # 总成交量（手）
    cur_vol: float  # 当前成交量
    amount: float  # 成交额（元）
    s_vol: float  # 内盘（主动卖）
    b_vol: float  # 外盘（主动买）

    # 活跃度指标（含义来自社区逆向，仅供参考）
    active1: int
    active2: int

    # 买盘五档
    bid1: float
    bid_vol1: float
    bid2: float
    bid_vol2: float
    bid3: float
    bid_vol3: float
    bid4: float
    bid_vol4: float
    bid5: float
    bid_vol5: float

    # 卖盘五档
    ask1: float
    ask_vol1: float
    ask2: float
    ask_vol2: float
    ask3: float
    ask_vol3: float
    ask4: float
    ask_vol4: float
    ask5: float
    ask_vol5: float

    # 价格指标
    rise_speed: float  # 涨速（原 reversed_bytes9 / 100）
    limit_up: float  # 涨停价（业务规则计算）
    limit_down: float  # 跌停价（业务规则计算）

    # 协议原始值（含义已确认，保留以供高级分析）
    unknown_2: int = field(default=0, repr=False)  # 指数: IndexOpenAmount/100; 个股: 舍入残差
    unknown_3: int = field(default=0, repr=False)  # 个股: StockOpenAmount/100; 指数: 负值

    # 尾部保留字段
    unknown_5: int = field(default=0, repr=False)  # 保留，恒为 0
    unknown_6: int = field(default=0, repr=False)  # 保留，恒为 0
    unknown_7: int = field(default=0, repr=False)  # 保留，恒为 0
    unknown_8: int = field(default=0, repr=False)  # 保留，恒为 0

    # 服务器时间字符串（从 unknown_0 原始整数解析，格式 HH:MM:SS.mmm）
    server_time: str = field(default="", repr=True)

    # 已确认语义的新字段
    trading_status: int = field(default=0, repr=False)  # 交易状态标志，0x8020=停牌
    open_amount: float = field(default=0.0, repr=False)  # 集合竞价成交金额（元），个股有效

    # 原始字节（该股票记录切片）
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class SecurityInfo:
    """证券列表条目（来自 get_security_list）"""

    market: Market
    code: str
    name: str  # 股票名称（GBK 解码，截断字节用 replacement char 替代）
    volunit: int  # 成交量单位（手 = volunit 股）
    decimal_point: int  # 价格小数位数
    pre_close: float  # 昨收价（通达信自定义浮点解码）

    # 扩展字段（通过 get_security_list_all 关联 tdxhy.cfg 获得）
    industry_tdx: str = ""  # 通达信行业代码 (如 T1001)
    industry_sw: str = ""  # 申万行业代码 (如 X500102)

    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class MarketStat:
    """全市场涨跌统计概况。"""

    up_count: int  # 上涨家数
    down_count: int  # 下跌家数
    neutral_count: int  # 平盘家数
    suspended_count: int  # 由 total-(up+down+neutral) 得到的残差项，近似表示停牌/未参与统计家数
    total_count: int  # 总计（包含停牌）
    total_amount: float  # 总成交额
    total_volume: float  # 总成交量
    total_market_cap: float  # 总市值（亿元），来自 880001 收盘价，÷100 得万亿
    limit_up_count: int  # 涨停家数，来自 880006 close
    limit_down_count: int  # 跌停家数，来自 880006 open


@dataclass
class FundFlow:
    """个股资金流向统计（基于 Tick 数据加权计算）。"""

    # 流入项 (Buy)
    super_in: float  # 超大单流入 (>100万)
    large_in: float  # 大单流入 (>20万 且 <=100万)
    medium_in: float  # 中单流入 (>4万 且 <=20万)
    small_in: float  # 小单流入 (<=4万)

    # 流出项 (Sell)
    super_out: float
    large_out: float
    medium_out: float
    small_out: float

    @property
    def main_net_inflow(self) -> float:
        """主力净流入 (超大单 + 大单)。"""
        return (self.super_in + self.large_in) - (self.super_out + self.large_out)

    @property
    def total_net_inflow(self) -> float:
        """全单净流入。"""
        return (self.super_in + self.large_in + self.medium_in + self.small_in) - (self.super_out + self.large_out + self.medium_out + self.small_out)


@dataclass
class HistoricalFundFlow:
    """历史日线资金流向条目。"""

    year: int
    month: int
    day: int

    # 金额项 (单位：元)
    super_in: float
    super_out: float
    large_in: float
    large_out: float
    medium_in: float
    medium_out: float
    small_in: float
    small_out: float

    @property
    def main_net_inflow(self) -> float:
        """当日主力净流入。"""
        return (self.super_in + self.large_in) - (self.super_out + self.large_out)


@dataclass
class MinuteBar:
    """今日/历史分时（每分钟一条，共 240 条）

    unknown_1: 协议中第二个变长整数，含义未明（疑似均价的编码形式）。
    """

    price: float  # 价格
    vol: int  # 成交量

    # pytdx 中被完全丢弃的字段，保留以供分析
    _unknown_1: int = field(default=0, repr=False)  # 原 reversed1

    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class TransactionRecord:
    """逐笔成交记录

    unknown_last: pytdx 中被 _ 丢弃的最后一个变长整数，保留以供分析。
    时间精度仅到分钟（协议限制），unknown_last 可能含秒或序号信息。
    """

    hour: int
    minute: int
    price: float
    vol: int
    buyorsell: int  # 0=买, 1=卖, 2=中性/撮合, 8=集合竞价

    # pytdx 中被丢弃的字段
    unknown_last: int = field(default=0, repr=False)

    _raw: bytes = field(default=b"", repr=False, compare=False)

"""变长有符号整数编解码（通达信 TCP 价格编码）。

协议规则：
  - 首字节：bit7=继续标记，bit6=符号（1=负），bit5~0=低6位数据
  - 后续字节：bit7=继续标记，bit6~0=7位数据
  - 所有数据位低位在前（小端 bit 顺序）

典型用途：价格差分、成交量差分、买卖档位数量。
"""


"""MAC 协议请求帧构建。

MAC 协议请求帧格式（10 字节头 + body）：
  struct "<BIBHH"
  偏移 0: B (1字节) — head_flag (MAC=0x1c, 标准=0x0c)
  偏移 1: I (4字节) — customize（通常为 0）
  偏移 5: B (1字节) — version（通常为 1）
  偏移 6: H (2字节) — zipsize（body 长度）
  偏移 8: H (2字节) — unzipsize（同 zipsize，MAC 不压缩请求）

MAC 响应复用标准 16 字节帧头（<IIIHH），直接使用 frame.py 的 parse_header/decompress_body。
"""



def _to_df(data: Any) -> pd.DataFrame:
    """将 list[dataclass] 或单个 dataclass 转为 DataFrame。

    自动丢弃以 ``_`` 开头的内部字段（如 ``_raw``）。
    仅处理 year/month/day（无 hour/minute）→ date 的合并；
    SecurityBar 的完整 datetime 合并由调用方按周期决定。
    """
    if isinstance(data, list):
        if not data:
            return pd.DataFrame()
        rows = []
        for item in data:
            d = _clean_dict(item)
            rows.append(d)
        return pd.DataFrame(rows)
    if is_dataclass(data) and not isinstance(data, type):
        return pd.DataFrame([_clean_dict(data)])
    raise TypeError(f"不支持转换为 DataFrame 的类型: {type(data)}")


def _clean_dict(item: Any) -> dict[str, Any]:
    d = asdict(item)
    d = {k: v for k, v in d.items() if not k.startswith("_")}
    return _merge_datetime_fields(d)


def _merge_datetime_fields(d: dict[str, Any]) -> dict[str, Any]:
    """将仅含 year/month/day（无 hour/minute）的模型合并为 date 列。"""
    if all(k in d for k in ("year", "month", "day")) and not all(k in d for k in ("hour", "minute")):
        dt = pd.Timestamp(year=d["year"], month=d["month"], day=d["day"])
        result: dict[str, Any] = {"date": dt}
        result.update({k: v for k, v in d.items() if k not in {"year", "month", "day"}})
        return result
    return d


def _merge_bar_datetime(df: pd.DataFrame, daily_plus: bool) -> pd.DataFrame:
    """根据 K 线周期将 SecurityBar 的分散字段合并为 date 或 datetime。

    Args:
        daily_plus: True 表示日线及以上周期（DAY/WEEK/MONTH/YEAR），只保留 date；
                    False 表示分钟线（MIN_1/5/15/30/60），保留完整 datetime。
    """
    if df.empty or "year" not in df.columns:
        return df
    date_str = (df["year"].astype(str)
        + "-"
        + df["month"].astype(str).str.zfill(2)
        + "-"
        + df["day"].astype(str).str.zfill(2))
    if daily_plus:
        df.insert(0, "date", pd.to_datetime(date_str))
    else:
        full_str = (date_str
            + " "
            + df["hour"].astype(str).str.zfill(2)
            + ":"
            + df["minute"].astype(str).str.zfill(2))
        df.insert(0, "datetime", pd.to_datetime(full_str))
    df.drop(columns=["year", "month", "day", "hour", "minute"], inplace=True)
    return df


def _merge_txn_datetime(df: pd.DataFrame, date_int: int) -> pd.DataFrame:
    """将逐笔成交的 date + hour:minute 合并为 datetime 列。"""
    if df.empty or "hour" not in df.columns:
        return df
    year = date_int // 10000
    month = (date_int // 100) % 100
    day = date_int % 100
    base = pd.Timestamp(year=year, month=month, day=day)
    offsets = pd.to_timedelta(df["hour"] * 3600 + df["minute"] * 60, unit="s")
    df.insert(0, "datetime", base + offsets)
    df.drop(columns=["hour", "minute"], inplace=True)
    return df


def _add_minute_datetime(df: pd.DataFrame, date_int: int) -> pd.DataFrame:
    """为分时 DataFrame 添加 datetime 列（从 bar 索引计算时间）。

    A 股分时 240 条：0-119 = 9:30~11:29（上午），120-239 = 13:00~14:59（下午）。
    """
    if df.empty:
        return df
    year = date_int // 10000
    month = (date_int // 100) % 100
    day = date_int % 100
    base = pd.Timestamp(year=year, month=month, day=day)
    n = len(df)
    morning = list(range(9 * 60 + 30, 9 * 60 + 30 + 120))
    afternoon = list(range(13 * 60, 13 * 60 + 120))
    all_minutes = (morning + afternoon)[:n]
    offsets = pd.to_timedelta(all_minutes, unit="m")
    df.insert(0, "datetime", base + offsets)
    return df

_MAC_HEADER_FMT = "<BIBHH"
_MAC_HEADER_SIZE = 10
_MAC_HEAD_FLAG = 0x1C
_MAC_CUSTOMIZE = 0
_MAC_VERSION = 1



def require_bytes(data: bytes, pos: int, size: int, context: str):
    """确保从 pos 起至少还能读取 size 字节。"""
    if pos < 0:
        raise TdxDecodeError(f"{context}: 非法偏移 {pos}")
    end = pos + size
    if end > len(data):
        remaining = max(len(data) - pos, 0)
        raise TdxDecodeError(f"{context}: 数据不足，需要 {size} 字节，偏移 {pos}，实际剩余 {remaining} 字节")


def unpack_from(fmt: str, data: bytes, pos: int, context: str) -> tuple[Any, ...]:
    """带边界检查的 struct.unpack_from。"""
    require_bytes(data, pos, struct.calcsize(fmt), context)
    try:
        return struct.unpack_from(fmt, data, pos)
    except struct.error as e:  # pragma: no cover - require_bytes 已覆盖大部分路径
        raise TdxDecodeError(f"{context}: 解析失败: {e}") from e


def slice_bytes(data: bytes, pos: int, size: int, context: str) -> bytes:
    """带边界检查的切片读取。"""
    require_bytes(data, pos, size, context)
    return bytes(data[pos : pos + size])

def build_mac_request(msg_id: int, body: bytes, *, head_flag: int = _MAC_HEAD_FLAG) -> bytes:
    """构建 MAC 协议请求帧。

    Parameters
    ----------
    msg_id : int
        MAC 命令 ID（如 0x122B）。
    body : bytes
        命令特有的请求体（不含 msg_id 前缀）。
    head_flag : int
        帧头标识字节，默认 0x1C（标准 MAC）。部分命令（如 0x1218）
        使用不同的 head_flag 区分子协议。

    Returns
    -------
    bytes
        完整的请求帧（10 字节头 + 2 字节 msg_id + body）。
    """
    inner = struct.pack("<H", msg_id) + body
    header = struct.pack(_MAC_HEADER_FMT, head_flag, _MAC_CUSTOMIZE, _MAC_VERSION, len(inner), len(inner))
    return header + inner
"""通达信行业配置文件 (tdxhy.cfg) 解析器。"""

"""响应帧头解析与 zlib 解压。

响应帧格式（16 字节固定头 + body），字节级结构（gotdx 交叉验证）：
  偏移  0: I (4字节) — magic = 7654321 (0x0074CBB1)，协议标识
  偏移  4: B (1字节) — ZipFlag：bit4=1 表示 body 已压缩，0x0C=未压缩, 0x1C=已压缩
  偏移  5: I (4字节) — SeqID：请求 bytes 1-4 的回显（命令标识）
  偏移  9: B (1字节) — 保留（观察到恒为 0x00）
  偏移 10: H (2字节) — Method：请求 bytes 10-11 的回显
  偏移 12: H (2字节) — zipsize（body 实际长度）
  偏移 14: H (2字节) — unzipsize（解压后长度；等于 zipsize 表示未压缩）

兼容说明：使用 IIIHH 解码可正确提取 zipsize/unzipsize。前三个 uint32 中：
  u0 = magic, u1 = ZipFlag(1B) + SeqID(3B 低字节), u2 = SeqID(1B 高字节) + 保留(1B) + Method(2B)
"""

import zlib
from dataclasses import dataclass


HEADER_SIZE: int = 16
_HEADER_FMT = "<IIIHH"

"""专业财务数据解析（tdxfin/gpcw.txt 列表 + .dat 二进制记录）。"""

import struct

"""日期时间解码（通达信 TCP 两种格式）。

分钟级（category < 4 或 == 7/8）：4 字节 = 2 字节压缩日期 + 2 字节分钟数
  zipday: year=(>>11)+2004, month=(% 2048)//100, day=(% 2048)%100
  tminutes: hour=//60, minute=%60

日线及以上（其余 category）：4 字节 YYYYMMDD 整数
"""

"""板块文件 (.dat) 解析逻辑。"""
import struct

"""MAC 协议字段位图编解码。

提供 FieldBit 定义、预定义字段集合（PresetField）、字段选择器（FieldSelection），
以及 20 字节请求位图的构建与响应位图解析。
"""

from collections.abc import Iterable, Iterator
from enum import Enum, IntEnum

# ── 统一的字段选择类型 ──
Fields = "FieldBit | PresetField | FieldSelection | Iterable[FieldBit]"


class FieldBit(IntEnum):
    """字段位定义，自带格式和描述，单一数据源。"""

    fmt: str  # 由 __new__ 设置
    desc: str  # 由 __new__ 设置

    def __new__(cls, value: int, fmt: str = "<f", desc: str = "") -> "FieldBit":
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.fmt = fmt
        obj.desc = desc
        return obj

    @property
    def field_name(self) -> str:
        """返回英文字段名，用于 DataFrame 列名等。"""
        return self.name.lower()

    # ── 基础字段 (0x00-0x05) ──
    PRE_CLOSE = 0x00, "<f", "昨收"
    OPEN = 0x01, "<f", "开盘价"
    HIGH = 0x02, "<f", "最高价"
    LOW = 0x03, "<f", "最低价"
    CLOSE = 0x04, "<f", "收盘价"
    VOL = 0x05, "<I", "成交量"
    VOL_RATIO = 0x06, "<f", "量比"
    AMOUNT = 0x07, "<f", "总金额(元)"

    # ── 扩展字段 (0x08-0x0F) ──
    INSIDE_VOLUME = 0x08, "<I", "内盘"
    OUTSIDE_VOLUME = 0x09, "<I", "外盘"
    TOTAL_SHARES = 0x0A, "<f", "总股数(单位万)"
    FLOAT_SHARES = 0x0B, "<f", "流通股(单位万)"
    EPS = 0x0C, "<f", "每股收益"
    NET_ASSETS = 0x0D, "<f", "净资产"
    SECURITY_TYPE_PRICE = 0x0E, "<f", "证券类型价"
    TOTAL_MARKET_CAP_AB = 0x0F, "<f", "AB股总市值"

    # ── 0x10-0x1F ──
    PE_DYNAMIC = 0x10, "<f", "市盈率(动)"
    BID_PRICE = 0x11, "<f", "买一价"
    ASK_PRICE = 0x12, "<f", "卖一价"
    SERVER_UPDATE_DATE = 0x13, "<I", "服务器更新日期 YYYYMMDD"
    SERVER_UPDATE_TIME = 0x14, "<I", "服务器更新时间 HHMMSS"
    LOT_SIZE_INFO = 0x15, "<I", "未确定"
    BOARD_STRENGTH = 0x16, "<f", "板块强度(涨跌家数差)"
    DIVIDEND_YIELD = 0x17, "<f", "每股股息(元)"
    BID_VOLUME = 0x18, "<I", "买量"
    ASK_VOLUME = 0x19, "<I", "卖量"
    LAST_VOLUME = 0x1A, "<I", "现量"
    TURNOVER = 0x1B, "<f", "换手"
    INDUSTRY = 0x1C, "<I", "行业分类代码"
    INDUSTRY_CHANGE_UP = 0x1D, "<f", "行业涨跌幅"
    STOCK_TAG_FLAGS = 0x1E, "<I", "股票标签位图"
    DECIMAL_POINT = 0x1F, "<I", "数据精度"

    # ── 0x20-0x2F ──
    BUY_PRICE_LIMIT = 0x20, "<f", "涨停价"
    SELL_PRICE_LIMIT = 0x21, "<f", "跌停价"
    PRICE_DECIMAL_INFO = 0x22, "<I", "价格精度标志"
    LOT_SIZE = 0x23, "<I", "所属地区板块/每手股数"
    PRE_IOPV = 0x24, "<f", "昨IOPV"
    SPEED_PCT = 0x25, "<f", "涨速"
    AVG_PRICE = 0x26, "<f", "均价"
    IOPV = 0x27, "<f", "IOPV"
    PE_TTM_VOL_RELATED = 0x28, "<f", "前参考价(美股适用)"
    EX_PRICE_PLACEHOLDER = 0x29, "<f", "前金额参考"
    OPERATING_REVENUE = 0x2A, "<f", "营业收入(万)"
    FLAG_KCB = 0x2B, "<I", "科创板标志"
    FLAG_BJ = 0x2C, "<I", "北交所标志"
    CIRCULATING_CAPITAL_Z = 0x2D, "<f", "流通股本Z（单位：万股）"
    AFTER_HOURS_VOLUME = 0x2E, "<i", "盘后量"

    # ── 0x30-0x3F ──
    PE_TTM = 0x30, "<f", "市盈率TTM"
    PE_STATIC = 0x31, "<f", "市盈率静"
    INDEX_METRIC = 0x37, "<f", "指数指标"
    MAIN_NET_AMOUNT = 0x38, "<f", "今日主力净流入"
    BID_ASK_RATIO = 0x39, "<f", "委比"
    NON_INDEX_FLAG = 0x3A, "<I", "非指数标志"
    CHANGE_20D_PCT = 0x3B, "<f", "20日涨幅%"
    YTD_PCT = 0x3C, "<f", "年初至今%"
    STOCK_CLASS_CODE = 0x3E, "<I", "证券子分类码"
    PERCENT_BASE = 0x3F, "<I", "百分比基底"

    # ── 0x40-0x4F ──
    MTD_PCT = 0x40, "<f", "月初至今%"
    CHANGE_1Y_PCT = 0x41, "<f", "一年涨幅%"
    PREV_CHANGE_PCT = 0x42, "<f", "昨涨幅%"
    CHANGE_3D_PCT = 0x43, "<f", "3日涨幅%"
    CHANGE_60D_PCT = 0x44, "<f", "60日涨幅%"
    CHANGE_5D_PCT = 0x45, "<f", "5日涨幅%"
    CHANGE_10D_PCT = 0x46, "<f", "10日涨幅%"
    PREV2_CHANGE_PCT = 0x47, "<f", "前日涨幅%"
    BID2_PRICE = 0x48, "<f", "买二价"
    ASK2_PRICE = 0x49, "<f", "卖二价"
    AH_CODE = 0x4A, "<I", "对应A/H股code"
    UNKNOWN_CODE = 0x4B, "<I", "少部分有数据"

    # ── 0x50-0x6F ──
    OPEN_AMOUNT = 0x57, "<f", "开盘金额(元)"
    ANNUAL_LIMIT_UP_DAYS = 0x58, "<i", "年涨停天数"
    ACTIVITY = 0x59, "<I", "活跃度"
    DIVIDEND_YIELD_RATE = 0x5B, "<f", "股息率%"
    CONSECUTIVE_UP_DAYS = 0x5C, "<i", "连涨天"
    LIMIT_UP_COUNT = 0x5D, "<I", "涨停数(板块) / 买二量(个股)"
    BID2_VOLUME = 0x5D, "<I", "买二量(个股)"
    LIMIT_DOWN_COUNT = 0x5E, "<I", "跌停数(板块) / 卖二量(个股)"
    ASK2_VOLUME = 0x5E, "<I", "卖二量(个股)"
    INDUSTRY_SUB = 0x5F, "<I", "行业二级分类"
    AUCTION_BUY_LIMIT = 0x66, "<f", "连续竞价买入上限"
    AUCTION_SELL_LIMIT = 0x67, "<f", "连续竞价卖出下限"
    VOL_SPEED_PCT = 0x68, "<f", "量涨速%"
    SHORT_TURNOVER_PCT = 0x69, "<f", "短换手%"
    AMOUNT_2M = 0x6A, "<f", "2分钟金额(元)"
    MAIN_NET_AMOUNT_COPY = 0x6B, "<f", "今日主力净流入(副本)"
    MAIN_NET_RATIO = 0x6C, "<f", "主力净比%"
    RETAIL_NET_AMOUNT = 0x6D, "<f", "散户单增比"
    MAIN_NET_5M_AMOUNT = 0x6E, "<f", "5分钟主力净额"
    MAIN_NET_3D_AMOUNT = 0x6F, "<f", "近三日主力净额"

    # ── 0x70-0x7F ──
    MAIN_NET_5D_AMOUNT = 0x70, "<f", "近五日主力净额"
    MAIN_NET_10D_AMOUNT = 0x71, "<f", "近十日主买金额(待确定)"
    MAIN_BUY_NET_AMOUNT = 0x72, "<f", "今日主买净额"
    DDX = 0x73, "<f", "DDX"
    DDY = 0x74, "<f", "DDY"
    DDZ = 0x75, "<f", "DDZ"
    DDF = 0x76, "<f", "DDF"
    STOCK_FLAG_A = 0x77, "<f", "个股标志位A"
    STOCK_FLAG_B = 0x78, "<f", "个股标志位B(副本)"
    AUCTION_VOL_RATIO = 0x7A, "<f", "竞价昨比"
    PREV_AMOUNT = 0x7B, "<f", "昨成交额(元)"
    RECENT_INDICATOR = 0x7D, "<f", "近日指标提示"

    # ── 0x80-0x8F ──
    BID3_PRICE = 0x80, "<f", "买三价"
    BID4_PRICE = 0x81, "<f", "买四价"
    BID5_PRICE = 0x82, "<f", "买五价"
    ASK3_PRICE = 0x83, "<f", "卖三价"
    ASK4_PRICE = 0x84, "<f", "卖四价"
    ASK5_PRICE = 0x85, "<f", "卖五价"
    BID3_VOLUME = 0x86, "<I", "买三量"
    BID4_VOLUME = 0x87, "<I", "买四量"
    UP_COUNT = 0x88, "<I", "上涨家数(板块) / 买五量(个股)"
    BID5_VOLUME = 0x88, "<I", "买五量(个股)"
    ASK3_VOLUME = 0x89, "<I", "卖三量"
    ASK4_VOLUME = 0x8A, "<I", "卖四量"
    DOWN_COUNT = 0x8B, "<I", "下跌家数(板块) / 卖五量(个股)"
    ASK5_VOLUME = 0x8B, "<I", "卖五量(个股)"
    BID_ASK_DIFF = 0x8C, "<i", "委差"
    CHANGE_UP_TYPE = 0x8D, "<i", "封板状态"
    SAFETY_SCORE = 0x8E, "<f", "安全分"
    HIGHLIGHT_COUNT = 0x8F, "<f", "亮点数"

    # ── 0x90-0x96: 日内时间涨幅(从昨收算) ──
    CHANGE_AT_1000 = 0x90, "<f", "日内涨幅% 10:00"
    CHANGE_AT_1030 = 0x91, "<f", "日内涨幅% 10:30"
    CHANGE_AT_1100 = 0x92, "<f", "日内涨幅% 11:00"
    CHANGE_AT_1130 = 0x93, "<f", "日内涨幅% 11:30"
    CHANGE_AT_1330 = 0x94, "<f", "日内涨幅% 13:30"
    CHANGE_AT_1400 = 0x95, "<f", "日内涨幅% 14:00"
    CHANGE_AT_1430 = 0x96, "<f", "日内涨幅% 14:30"


# 从 FieldBit 自动生成
FIELD_BITMAP_MAP: dict[int, tuple[str, str, str]] = {
    bit.value: (bit.name.lower(), bit.fmt, bit.desc) for bit in FieldBit
}


# ── 字段后处理钩子 ──
def _post_ah_code(value: int, market: int = 0) -> str:
    """A/H股代码补齐位数。"""
    if not value:
        return ""
    # 沪深北 5 位，其他 6 位
    width = 5 if market in (0, 1) else 6
    return str(value).zfill(width)


FIELD_POSTPROCESS: dict[int, object] = {
    0x4A: _post_ah_code,  # AH_CODE: 补齐0
}


# ── 控制区(位128-159, 4字节) ──
# 前16字节(位0-127)是字段位图, 后4字节(位128-159)是控制区:
#   字节16(位128-135): 盘口深度(bid3_price~bid4_volume)
#   字节17(位136-143): 排除/限流位
#   字节18(位144-151): 日内涨幅(change_at_1000~1430)
#   字节19(位152-159): 控制字节(CTRL_EXTENDED等)

CTRL_BYTE = 0  # 控制字节起始位(152)
CTRL_EXTENDED = 1  # 非0=扩展模式(含北交所等)，0=标准模式(仅A股)


# ── 预定义字段集合 ──
class PresetField(Enum):
    """预定义字段集合，支持 + / | 链式组合。

    Usage:
        PresetField.BASIC + PresetField.VOLUME          # 两个预设合并
        PresetField.OHLC + FieldBit.AH_CODE             # 预设 + 单字段
        FieldBit.OPEN + FieldBit.HIGH + FieldBit.LOW    # 纯字段组合
    """

    NONE = ()
    OHLC = (FieldBit.OPEN, FieldBit.HIGH, FieldBit.LOW, FieldBit.CLOSE)
    BASIC = (FieldBit.OPEN, FieldBit.HIGH, FieldBit.LOW, FieldBit.CLOSE, FieldBit.PRE_CLOSE, FieldBit.VOL)
    QUOTE = (FieldBit.BID_PRICE, FieldBit.ASK_PRICE, FieldBit.BID_VOLUME, FieldBit.ASK_VOLUME, FieldBit.LAST_VOLUME)
    VOLUME = (FieldBit.VOL, FieldBit.AMOUNT, FieldBit.TURNOVER, FieldBit.VOL_RATIO)
    FUNDAMENTAL = (FieldBit.TOTAL_SHARES, FieldBit.FLOAT_SHARES, FieldBit.EPS, FieldBit.NET_ASSETS)
    ENHANCED = (FieldBit.OPEN, FieldBit.HIGH, FieldBit.LOW, FieldBit.CLOSE, FieldBit.VOL, FieldBit.FLOAT_SHARES, FieldBit.ACTIVITY)
    AH_CODE_FIELDS = (FieldBit.OPEN, FieldBit.HIGH, FieldBit.LOW, FieldBit.CLOSE, FieldBit.VOL, FieldBit.AH_CODE, FieldBit.LOT_SIZE, FieldBit.INDUSTRY)
    BOARD_STATS = (FieldBit.LIMIT_UP_COUNT, FieldBit.LIMIT_DOWN_COUNT, FieldBit.UP_COUNT, FieldBit.DOWN_COUNT)
    HANDICAP = (FieldBit.BID_PRICE, FieldBit.BID2_PRICE, FieldBit.BID3_PRICE, FieldBit.BID4_PRICE, FieldBit.BID5_PRICE, FieldBit.ASK_PRICE, FieldBit.ASK2_PRICE, FieldBit.ASK3_PRICE, FieldBit.ASK4_PRICE, FieldBit.ASK5_PRICE, FieldBit.BID_VOLUME, FieldBit.BID2_VOLUME, FieldBit.BID3_VOLUME, FieldBit.BID4_VOLUME, FieldBit.BID5_VOLUME, FieldBit.ASK_VOLUME, FieldBit.ASK2_VOLUME, FieldBit.ASK3_VOLUME, FieldBit.ASK4_VOLUME, FieldBit.ASK5_VOLUME)
    COMMON = (FieldBit.PRE_CLOSE, FieldBit.OPEN, FieldBit.HIGH, FieldBit.LOW, FieldBit.CLOSE, FieldBit.VOL, FieldBit.VOL_RATIO, FieldBit.AMOUNT, FieldBit.TOTAL_SHARES, FieldBit.FLOAT_SHARES, FieldBit.EPS, FieldBit.NET_ASSETS, FieldBit.SECURITY_TYPE_PRICE, FieldBit.TOTAL_MARKET_CAP_AB, FieldBit.PE_DYNAMIC, FieldBit.LOT_SIZE_INFO, FieldBit.DIVIDEND_YIELD, FieldBit.LAST_VOLUME, FieldBit.TURNOVER, FieldBit.STOCK_TAG_FLAGS, FieldBit.DECIMAL_POINT, FieldBit.BUY_PRICE_LIMIT, FieldBit.SELL_PRICE_LIMIT, FieldBit.PRICE_DECIMAL_INFO, FieldBit.LOT_SIZE, FieldBit.PRE_IOPV, FieldBit.SPEED_PCT, FieldBit.FLAG_KCB, FieldBit.PE_TTM, FieldBit.PE_STATIC, FieldBit.MAIN_NET_AMOUNT, FieldBit.VOL_SPEED_PCT, FieldBit.SHORT_TURNOVER_PCT, FieldBit.CIRCULATING_CAPITAL_Z)
    DEBUG = (-1, "", "调试用全字段")
    ALL = tuple(FieldBit)

    def __add__(self, other: object) -> "FieldSelection":
        if isinstance(other, (FieldBit, PresetField, FieldSelection)):
            return FieldSelection(self, other)
        return NotImplemented

    def __or__(self, other: object) -> "FieldSelection":
        return self.__add__(other)

    def __radd__(self, other: object) -> "FieldSelection":
        if isinstance(other, (FieldBit, FieldSelection)):
            return FieldSelection(other, self)
        return NotImplemented

    def __ror__(self, other: object) -> "FieldSelection":
        return self.__radd__(other)


class FieldSelection:
    """字段选择器，支持 PresetField + FieldBit 组合。

    Usage:
        PresetField.BASIC + FieldBit.AH_CODE
        PresetField.BASIC | FieldBit.INDUSTRY
        FieldBit.OPEN + FieldBit.HIGH + FieldBit.LOW
    """

    __slots__ = ("_fields",)

    def __init__(self, *parts: "FieldBit | PresetField | FieldSelection"):
        seen: set[FieldBit] = set()
        result: list[FieldBit] = []
        for part in parts:
            if isinstance(part, PresetField):
                source: Iterable[FieldBit] = part.value
            elif isinstance(part, FieldBit):
                source = (part,)
            else:
                source = part._fields
            for bit in source:
                if bit not in seen:
                    seen.add(bit)
                    result.append(bit)
        self._fields: tuple[FieldBit, ...] = tuple(result)

    def __add__(self, other: object) -> "FieldSelection":
        if isinstance(other, (FieldBit, PresetField, FieldSelection)):
            return FieldSelection(self, other)
        return NotImplemented

    def __or__(self, other: object) -> "FieldSelection":
        return self.__add__(other)

    def __radd__(self, other: object) -> "FieldSelection":
        if isinstance(other, (FieldBit, PresetField)):
            return FieldSelection(other, self)
        return NotImplemented

    def __ror__(self, other: object) -> "FieldSelection":
        return self.__radd__(other)

    def __iter__(self) -> Iterator[FieldBit]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __bool__(self) -> bool:
        return bool(self._fields)

    def __contains__(self, item: object) -> bool:
        return item in self._fields

    def __repr__(self) -> str:
        names = [bit.name for bit in self._fields]
        return f"FieldSelection([{', '.join(names)}])"


def normalize_fields(fields: "Fields") -> FieldSelection:
    """将任意字段选择形式归一化为 FieldSelection。"""
    if fields is None:
        return FieldSelection()
    if isinstance(fields, FieldSelection):
        return fields
    if isinstance(fields, PresetField):
        return FieldSelection(*fields.value)
    if isinstance(fields, FieldBit):
        return FieldSelection(fields)
    return FieldSelection(*fields)


def build_bitmap(fields: "Fields", exclude_flags: int = 0) -> bytearray:
    """将字段选择转换为 20 字节请求位图。

    Parameters
    ----------
    fields : Fields
        字段选择，可以是 PresetField、FieldBit、FieldSelection 或可迭代对象。
    exclude_flags : int
        控制区 4 字节（位 128-159）的值，默认 0。

    Returns
    -------
    bytearray
        20 字节位图。
    """
    if isinstance(fields, PresetField) and fields is PresetField.DEBUG:
        return bytearray(b"\xff" * 20)
    selection = normalize_fields(fields)
    bitmap_int = 0
    for bit in selection:
        bitmap_int |= 1 << bit.value
    ba = bytearray(bitmap_int.to_bytes(16, "little"))
    ba.extend(exclude_flags.to_bytes(4, "little"))
    return ba


def build_exclude_flags(exclude_flags: int = 0) -> bytes:
    """构建 4 字节控制区。

    Parameters
    ----------
    exclude_flags : int
        控制区原始值，默认 0。

    Returns
    -------
    bytes
        4 字节控制区。
    """
    return exclude_flags.to_bytes(4, "little")


def get_active_fields(bitmap_bytes: bytes) -> list[tuple[FieldBit, str]]:
    """从响应位图解析活跃字段。

    Parameters
    ----------
    bitmap_bytes : bytes
        响应中的位图字节（通常 16 或 20 字节）。

    Returns
    -------
    list[tuple[FieldBit, str]]
        活跃字段及其格式说明符，按位序升序。
    """
    bitmap_int = int.from_bytes(bitmap_bytes, "little")
    active: list[tuple[FieldBit, str]] = []
    while bitmap_int:
        lowbit = bitmap_int & -bitmap_int
        bit_pos = lowbit.bit_length() - 1
        bitmap_int ^= lowbit
        field = FieldBit._value2member_map_.get(bit_pos)
        if field is not None and isinstance(field, FieldBit):
            active.append((field, field.fmt))
    return active

def parse_block_dat(data: bytes, filename: str = "") -> list["TdxBlock"]:
    """解析通达信 .dat 板块文件内容。

    格式：
      Header: 384 字节（跳过）
      Count:  2 字节 (uint16 LE)
      Body:   每条记录 2813 字节 (9s + H + H + 2800s)
    """

    if len(data) < 386:
        return []

    pos = 384
    (count,) = struct.unpack("<H", data[pos : pos + 2])
    pos += 2

    results: list[TdxBlock] = []

    # 推断板块分类 (0=行业, 1=地域, 2=概念, 3=风格)
    category = 0
    if "zs" in filename:
        category = 0
    elif "gn" in filename:
        category = 2
    elif "fg" in filename:
        category = 3

    for _ in range(count):
        if len(data) < pos + 2813:
            break

        # 板块元数据 (9 字节名称 + 2 字节股票数 + 2 字节类型)
        name_b = data[pos : pos + 9]
        stock_count, _type = struct.unpack("<HH", data[pos + 9 : pos + 13])
        name = name_b.decode("gbk", errors="replace").strip("\x00")

        # 股票代码区 (2800 字节，每只股票 7 字节)
        codes: list[str] = []
        codes_start = pos + 13
        # 安全检查：stock_count 不应超过 400 (2800 / 7)
        actual_count = min(stock_count, 400)
        for i in range(actual_count):
            c_start = codes_start + i * 7
            c_raw = data[c_start : c_start + 7]
            code = c_raw.decode("ascii", errors="replace").strip("\x00")
            if code:
                codes.append(code)

        results.append(TdxBlock(name=name, category=category, count=stock_count, codes=codes))

        # 跳过整个 2813 字节的记录块
        pos += 2813

    return results


def get_datetime_minute(data: bytes, pos: int) -> tuple[int, int, int, int, int, int]:
    """解析分钟级时间戳（4 字节）。

    Returns:
        (year, month, day, hour, minute, new_pos)
    """
    zipday, tminutes = unpack_from("<HH", data, pos, "minute datetime")
    year = (zipday >> 11) + 2004
    month = (zipday % 2048) // 100
    day = (zipday % 2048) % 100
    hour = tminutes // 60
    minute = tminutes % 60
    return year, month, day, hour, minute, pos + 4


def get_datetime_day(data: bytes, pos: int) -> tuple[int, int, int, int]:
    """解析日期（4 字节 YYYYMMDD）。

    Returns:
        (year, month, day, new_pos)
    """
    (zipday,) = unpack_from("<I", data, pos, "day datetime")
    year = zipday // 10000
    month = (zipday % 10000) // 100
    day = zipday % 100
    return year, month, day, pos + 4


def get_datetime(category: int, data: bytes, pos: int) -> tuple[int, int, int, int, int, int]:
    """根据 KlineCategory 选择解析格式。

    Returns:
        (year, month, day, hour, minute, new_pos)
        日线及以上时 hour=15, minute=0（收盘时间，与 pytdx 保持一致）
    """
    if category < 4 or category in (7, 8):
        return get_datetime_minute(data, pos)
    else:
        year, month, day, new_pos = get_datetime_day(data, pos)
        return year, month, day, 15, 0, new_pos


def get_time(data: bytes, pos: int) -> tuple[int, int, int]:
    """解析 2 字节时间（分钟数）。

    Returns:
        (hour, minute, new_pos)
    """
    (tminutes,) = unpack_from("<H", data, pos, "trade time")
    return tminutes // 60, tminutes % 60, pos + 2

def parse_financial_file_list(data: bytes) -> list[tuple[str, str, int]]:
    """解析 tdxfin/gpcw.txt 的内容。

    每行格式: filename,md5hash,filesize

    Returns:
        [(filename, hash, filesize), ...]
    """
    if not data:
        return []
    text = data.decode("utf-8", errors="replace").strip()
    results: list[tuple[str, str, int]] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) >= 3:
            results.append((parts[0], parts[1], int(parts[2])))
    return results


def parse_financial_dat(data: bytes, report_date: int = 0) -> list[tuple[str, int, int, list[float]]]:
    """解析 gpcw*.zip 内的 .dat 二进制文件。

    二进制格式（参考 pytdx.crawler.history_financial_crawler）：
      Header: 20 bytes  <1h I 1H 3L
        - unknown:     int16   (h)
        - report_date: uint32  (I)
        - max_count:   uint16  (H)   -- 股票索引条目数
        - unknown1:    uint32  (L)
        - report_size: uint32  (L)   -- 每条股票数据字节长度
        - unknown2:    uint32  (L)
      Index: max_count 条，每条 11 bytes  <6s 1c 1L
        - code:        6 bytes       -- 股票代码
        - market:      1 byte        -- 市场标识 (0=SZ, 1=SH)
        - file_offset: uint32        -- 绝对偏移（从文件开头算）
      Data: 在 file_offset 位置读取 report_size/4 个 float32

    Args:
        data: .dat 文件的完整字节
        report_date: 报告期 YYYYMMDD（从文件名提取，0 则用 header 中的值）

    Returns:
        [(code, market_byte, report_date, [float, ...]), ...]
    """
    header_fmt = "<1hI1H3L"
    header_size = struct.calcsize(header_fmt)
    if len(data) < header_size:
        return []

    header = struct.unpack(header_fmt, data[:header_size])
    max_count = header[2]
    dat_report_date = header[1]
    report_size = header[4]

    if report_date == 0:
        report_date = dat_report_date

    num_fields = report_size // 4
    if num_fields <= 0:
        return []

    index_fmt = "<6s1c1L"
    index_size = struct.calcsize(index_fmt)
    index_base = header_size

    results: list[tuple[str, int, int, list[float]]] = []
    report_fmt = f"<{num_fields}f"
    report_pack_size = struct.calcsize(report_fmt)

    for i in range(max_count):
        idx_pos = index_base + i * index_size
        if idx_pos + index_size > len(data):
            break

        code_bytes, market_byte, file_offset = struct.unpack(index_fmt, data[idx_pos : idx_pos + index_size])
        code = code_bytes.decode("ascii", errors="replace").rstrip("\x00")

        if not code or file_offset == 0:
            continue

        # file_offset 是绝对偏移（从文件开头算）
        data_pos = file_offset
        if data_pos + report_pack_size > len(data):
            continue

        floats = list(struct.unpack(report_fmt, data[data_pos : data_pos + report_pack_size]))
        results.append((code, market_byte, report_date, floats))

    return results

@dataclass(frozen=True)
class FrameHeader:
    magic: int  # 协议魔数，恒为 7654321
    seq_id: int  # ZipFlag(1B) + 请求 bytes 1-4 回显(3B)
    method: int  # 请求回显(1B) + 保留(1B) + Method(2B)
    zipsize: int
    unzipsize: int


def parse_header(buf: bytes) -> FrameHeader:
    """解析 16 字节响应帧头。"""
    magic, seq_id, method, zipsize, unzipsize = unpack_from(_HEADER_FMT, buf, 0, "frame header")
    return FrameHeader(magic, seq_id, method, zipsize, unzipsize)


def decompress_body(header: FrameHeader, raw_body: bytes) -> bytes:
    """按需 zlib 解压 body。

    zipsize == unzipsize 时直接返回原始字节；否则 zlib 解压。
    """
    if len(raw_body) != header.zipsize:
        raise TdxDecodeError(f"frame body 长度不符: header={header.zipsize}, actual={len(raw_body)}")
    if header.zipsize == header.unzipsize:
        body = raw_body
    else:
        try:
            body = zlib.decompress(raw_body)
        except zlib.error as e:
            raise TdxDecodeError(f"frame body zlib 解压失败: {e}") from e

    if len(body) != header.unzipsize:
        raise TdxDecodeError(f"frame body 解压长度不符: header={header.unzipsize}, actual={len(body)}")
    return body

def parse_tdxhy_cfg(content: bytes) -> dict[str, tuple[str, str]]:
    """解析 tdxhy.cfg 字节内容。

    返回字典: { "code": (tdx_industry, sw_industry), ... }
    """
    results = {}
    try:
        text = content.decode("gbk", errors="replace")
        for line in text.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3:
                # 格式: 市场|代码|行业1|||行业2
                # 我们只关心 A 股 6 位代码
                code = parts[1]
                if len(code) == 6:
                    tdx_ind = parts[2]
                    sw_ind = parts[5] if len(parts) >= 6 else ""
                    results[code] = (tdx_ind, sw_ind)
    except Exception:
        pass
    return results

def get_price(data: bytes, pos: int) -> tuple[int, int]:
    """解码一个变长有符号整数。

    Returns:
        (value, new_pos)
    """
    bit_shift = 6
    start = pos
    try:
        b = data[pos]
        value = b & 0x3F
        negative = bool(b & 0x40)

        if b & 0x80:
            while True:
                pos += 1
                b = data[pos]
                value |= (b & 0x7F) << bit_shift
                bit_shift += 7
                if not (b & 0x80):
                    break
    except IndexError as e:
        raise TdxDecodeError(f"price varint 截断: offset={start}") from e

    pos += 1
    return (-value if negative else value), pos


def put_price(value: int) -> bytes:
    """将整数编码为变长格式（用于构造请求包）。"""
    negative = value < 0
    value = abs(value)

    # 首字节：低6位数据 + 符号位
    first = value & 0x3F
    value >>= 6
    if negative:
        first |= 0x40
    if value:
        first |= 0x80

    result = bytearray([first])

    while value:
        b = value & 0x7F
        value >>= 7
        if value:
            b |= 0x80
        result.append(b)

    return bytes(result)


def get_no_limit_window_days(market: Market, code: str, name: str) -> int:
    """返回上市初期不设涨跌幅限制的交易日窗口。

    返回值:
        0: 默认按常规涨跌幅限制处理
        1: 北交所上市首日不设涨跌幅限制
        5: 沪深主板/创业板/科创板上市前 5 个交易日不设涨跌幅限制
    """
    if _is_index_like(market, code, name):
        return 0

    if code.startswith(("43", "83", "87", "92")):
        return 1

    if market == Market.SH and code.startswith(("60", "68")):
        return 5
    if market == Market.SZ and code.startswith(("00", "30")):
        return 5

    return 0


def _is_index_like(market: Market, code: str, name: str) -> bool:
    """判断是否为指数/板块类代码。"""
    if market == Market.SH and code.startswith(("000", "880", "881", "882", "883", "884", "885", "999")):
        return True
    if market == Market.SZ and code.startswith(("395", "399")):
        return True
    return "指数" in name or "板块" in name


def compute_price_limits(market: Market, code: str, name: str, pre_close: float, finance_info: FinanceInfo = None, listed_days: int = None) -> tuple[float, float]:
    """根据板块规则计算涨跌停价。

    Returns:
        (limit_up, limit_down)

    无涨跌幅限制或当前规则无法可靠判断时返回 ``(None, None)``。

    Args:
        listed_days:
            已上市交易天数（按交易日计，首日=1）。
            若提供该值，函数会按上市初期无涨跌幅限制规则优先返回 ``(None, None)``。
    """
    if pre_close <= 0:
        return None, None

    upper_name = name.upper()

    # 指数/板块类代码通常无涨跌停。
    if _is_index_like(market, code, name):
        return None, None

    no_limit_window_days = get_no_limit_window_days(market, code, name)
    if listed_days is not None and 0 < listed_days <= no_limit_window_days:
        return None, None

    limit_pct = 0.10  # 默认 10%

    # 2. ST / *ST 判断
    if "ST" in upper_name:
        limit_pct = 0.05
    # 3. 科创板 (688) / 创业板 (300, 301)
    elif code.startswith("688") or code.startswith("300") or code.startswith("301"):
        limit_pct = 0.20
    # 4. 北交所 (43, 83, 87, 92)
    elif code.startswith(("43", "83", "87", "92")):
        limit_pct = 0.30

    # `listed_days` 是更可靠的交易日维度输入；finance_info 仍保留给上层调用方扩展。
    _ = finance_info

    def _round_price(p: float) -> float:
        return round(p + 0.00001, 2)

    limit_up = _round_price(pre_close * (1 + limit_pct))
    limit_down = _round_price(pre_close * (1 - limit_pct))

    return limit_up, limit_down


def get_volume(data: bytes, pos: int) -> tuple[float, int]:
    """从 data[pos:pos+4] 解码成交量。

    Returns:
        (volume_float, new_pos)
    """
    (ivol,) = unpack_from("<I", data, pos, "volume")
    return _decode_volume(ivol), pos + 4


def _decode_volume(ivol: int) -> float:
    if ivol == 0:
        return 0.0

    logpoint = (ivol >> 24) & 0xFF
    hleax = (ivol >> 16) & 0xFF
    lheax = (ivol >> 8) & 0xFF
    lleax = ivol & 0xFF

    exp = logpoint * 2 - 0x7F
    base = _pow2(exp)

    exp_h = logpoint * 2 - 0x86
    if hleax > 0x80:
        hi = _pow2(exp_h) * 128 + (hleax & 0x7F) * _pow2(exp_h + 1)
    else:
        hi = _pow2(exp_h) * hleax

    mid = _pow2(logpoint * 2 - 0x8E) * lheax
    lo = _pow2(logpoint * 2 - 0x96) * lleax

    if hleax & 0x80:
        mid *= 2.0
        lo *= 2.0

    return base + hi + mid + lo


def _pow2(exp: int) -> float:
    if exp >= 0:
        return float(1 << exp) if exp < 63 else 2.0**exp
    return 1.0 / (1 << (-exp)) if -exp < 63 else 2.0**exp
