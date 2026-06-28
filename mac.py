"""MAC 协议高层 API：MacClient（同步）和 AsyncMacClient（asyncio）。"""

from __future__ import annotations
import logging


_RETRY_DELAYS = (0.1, 0.5, 1.0, 2.0)
_KLINE_PAGE_SIZE = 700
_BOARD_MEMBERS_PAGE_SIZE = 80

_logger = logging.getLogger(__name__)


from commands import *
from codec import _to_df
"""MAC 协议数据模型。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
"""MAC 协议枚举常量。"""


from enum import IntEnum


class Period(IntEnum):
    """K线周期。"""

    MIN_5 = 0
    MIN_15 = 1
    MIN_30 = 2
    MIN_60 = 3
    DAILY = 4
    WEEKLY = 5
    MONTHLY = 6
    MIN_1 = 7
    MINS = 8  # 多分钟（配合 times 参数）
    DAYS = 9  # 多日（配合 times 参数）
    QUARTERLY = 10
    YEARLY = 11
    SECONDS = 13  # 多秒（配合 times 参数）


class Adjust(IntEnum):
    """复权类型。"""

    NONE = 0
    QFQ = 1  # 前复权
    HFQ = 2  # 后复权


class BoardType(IntEnum):
    """板块类型。"""

    HY = 0  # 行业一级
    HY2 = 1  # 行业二级
    GN = 3  # 概念
    FG = 4  # 风格
    DQ = 5  # 地区
    OTHER = 6  # 其他
    YJ_LEVEL1 = 7  # 业绩一级
    YJ_LEVEL2 = 8  # 业绩二级
    YJ_LEVEL3 = 9  # 业绩三级
    ALL = 255  # 全部


class ExBoardType(IntEnum):
    """扩展市场板块类型。"""

    HK_ALL = 0  # 港股板块
    HK_GN = 1  # 港股概念
    HK_HY = 2  # 港股行业
    US_ALL = 3  # 美股板块
    US_GN = 4  # 美股概念
    US_HY = 5  # 美股行业


class Category(IntEnum):
    """市场分类。"""

    SH = 0  # 上证A
    SZ = 2  # 深证A
    A = 6  # 全部A股
    B = 7  # B股
    KCB = 8  # 科创板
    BJ = 12  # 北证A
    CYB = 14  # 创业板

    BOARD_ALL = 10000  # 全部板块
    BOARD_HY = 10001  # 行业一级
    BOARD_HY2 = 10002  # 行业二级
    BOARD_GN = 10004  # 概念
    BOARD_FG = 10005  # 风格
    BOARD_DQ = 10006  # 地区
    BOARD_OTHER = 10007  # 其他
    BOARD_YJ_LEVEL1 = 10008  # 业绩一级
    BOARD_YJ_LEVEL2 = 10009  # 业绩二级
    BOARD_YJ_LEVEL3 = 10010  # 业绩三级

    HGT = 0x2AF9  # 沪股通
    SGT = 0x2B01  # 深股通
    FXJS = 0x2AFF  # 风险警示
    ETF = 0x2AFD  # ETF基金
    LOF = 0x2B04  # LOF基金
    ZS = 0x2B2C  # 沪深系列指数


class SortType(IntEnum):
    """排序字段。"""

    CODE = 0x00
    NAME = 0x01
    PRE_CLOSE = 0x02
    OPEN = 0x03
    HIGH = 0x04
    LOW = 0x05
    PRICE = 0x06
    BID = 0x07
    ASK = 0x08
    VOLUME = 0x09
    TOTAL_AMOUNT = 0x0A
    LAST_VOLUME = 0x0B
    CHANGE = 0x0C
    CHANGE_PCT = 0x0E  # 涨幅%
    AMPLITUDE_PCT = 0x0F  # 振幅%
    AVG = 0x10  # 均价
    PE_DYNAMIC = 0x11  # 市盈(动)
    ENTRUST_RATIO = 0x12  # 委比%
    INSIDE_VOLUME = 0x13  # 内盘
    OUTSIDE_VOLUME = 0x14  # 外盘
    IN_OUT_RATIO = 0x15  # 内外比
    BID_VOLUME = 0x17  # 买量
    ASK_VOLUME = 0x18  # 卖量
    LOCKED_RATIO = 0x1B  # 封成比
    LOCKED_AMOUNT = 0x1C  # 封单额
    OPEN_AMOUNT = 0x1D  # 开盘金额
    OPEN_TURNOVER_PCT = 0x1E  # 开盘换手%
    VOL_RATIO = 0x23  # 量比
    TURNOVER_RATE = 0x24  # 换手%
    FLOAT_SHARES = 0x25  # 流通股(亿)
    FLOAT_MARKET_CAP = 0x26  # 流通市值
    TOTAL_MARKET_CAP_AB = 0x27  # AB股总市值
    UNMATCHED_VOLUME = 0x2A  # 未匹配量
    STRENGTH_PCT = 0x2D  # 强弱度%
    SPEED_PCT = 0x2E  # 涨速%
    ACTIVITY = 0x2F  # 活跃度
    SHORT_TURNOVER_PCT = 0xCC  # 短换手%
    VOL_SPEED_PCT = 0xD0  # 量涨速%
    MAIN_NET_AMOUNT = 0xD4  # 主力净额
    MAIN_NET_RATIO = 0xD7  # 主力净比%
    AUCTION_LIMIT_BUY = 0x102  # 竞价涨停买
    AMOUNT_2M = 0x10C  # 2分钟金额
    OPEN_SNATCH_PCT = 0x10A  # 开盘抢筹%
    OPEN_PCT = 0x119  # 开盘%
    HIGH_PCT = 0x11A  # 最高%
    LOW_PCT = 0x11B  # 最低%
    AVG_CHANGE_PCT = 0x11C  # 均涨幅%
    DRAWDOWN_PCT = 0x11E  # 回撤%
    ATTACK_PCT = 0x11F  # 攻击%


class SortOrder(IntEnum):
    """排序方向。"""

    NONE = 0
    DESC = 1
    ASC = 2


class FilterType(IntEnum):
    """过滤标志（位掩码，可组合）。"""

    NEW = 1  # 次新股
    KC = 2  # 科创板
    ST = 4  # ST/*ST
    CY = 8  # 创业板
    HK_CONNECT = 16  # 互联互通标的(仅核准制)
    BJ = 32  # 北交所
    APPROVAL = 64  # 核准制股票
    REGISTRATION = 128  # 注册制股票


class ExMarket(IntEnum):
    """扩展市场代码。"""

    TEMP_STOCK = 1  # 临时股
    ZZ_FUTURES_OPTION = 4  # 郑州商品期权
    DL_FUTURES_OPTION = 5  # 大连商品期权
    SH_FUTURES_OPTION = 6  # 上海商品期权
    CFFEX_OPTION = 7  # 中金所期权
    SH_STOCK_OPTION = 8  # 上海股票期权
    SZ_STOCK_OPTION = 9  # 深圳股票期权
    BASIC_FX = 10  # 基本汇率
    CROSS_FX = 11  # 交叉汇率
    INTL_INDEX = 12  # 国际指数
    COMEX_FUTURES = 16  # 纽约COMEX
    NYMEX_FUTURES = 17  # 纽约NYMEX
    CBOT_FUTURES = 18  # 芝加哥CBOT
    HK_FINANCIAL_FUTURES = 23  # 香港金融期货
    HK_FINANCIAL_OPTIONS = 24  # 香港金融期权
    HK_STOCK_FUTURES = 25  # 香港股票期货
    HK_STOCK_OPTIONS = 26  # 香港股票期权
    HK_INDEX = 27  # 香港指数
    ZZ_FUTURES = 28  # 郑州商品
    DL_FUTURES = 29  # 大连商品
    SH_FUTURES = 30  # 上海期货
    HK_MAIN_BOARD = 31  # 香港主板
    OPEN_END_FUND = 33  # 开放式基金
    MONETARY_FUND = 34  # 货币型基金
    MACRO_INDICATOR = 38  # 宏观指标
    FUTURES_INDEX = 42  # 商品指数
    B_TO_H = 43  # B股转H股
    NEEQ = 44  # 股转系统
    SH_GOLD = 46  # 上海黄金
    CFFEX_FUTURES = 47  # 中金所期货
    HK_GEM = 48  # 香港创业板
    HK_FUND = 49  # 香港基金
    TREASURY_VALUATION = 54  # 国债预发行
    SUNSHINE_PRIVATE_FUND = 56  # 阳光私募基金
    BROKER_COLLECTIVE_FINANCE = 57  # 券商集合理财
    BROKER_MONETARY_FINANCE = 58  # 券商货币理财
    MAIN_FUTURES_CONTRACT = 60  # 主力期货合约
    CSI_INDEX = 62  # 中证指数
    GZ_ARBITRAGE_FUTURES = 65  # 广州套利期货
    GZ_FUTURES = 66  # 广州期货
    GZ_OPTIONS = 67  # 广州期权
    RISK_CONTROL_INDEX = 68  # 风控指数
    HUAZHENG_INDEX = 69  # 华证指数
    EXTENDED_SECTOR_INDEX = 70  # 扩展板块指数
    HK_STOCK_GGT = 71  # 港股-港股通
    GE_STOCK = 73  # 德国股票
    US_STOCK = 74  # 美国股票
    SG_STOCK = 78  # 新加坡股票
    MONEY_MARKET = 91  # 资金市场
    FUND_VALUATION = 93  # 基金估值
    HK_DARK_POOL = 98  # 港股暗盘
    CODE_MIRROR = 100  # 代码镜像
    SZSE_INDEX = 102  # 国证指数


@dataclass(frozen=True)
class MacQuoteField:
    """MAC 协议自定义字段报价中的一条记录。"""

    market: int
    code: str
    name: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MacSymbolInfo:
    """个股简要特征。"""

    market: int
    code: str
    name: str
    time: datetime
    activity: int
    pre_close: float
    open: float
    high: float
    low: float
    close: float
    momentum: float
    vol: int
    amount: float
    inside_volume: int
    outside_volume: int
    turnover: float
    avg: float


@dataclass(frozen=True)
class MacBar:
    """MAC 协议 K 线数据。"""

    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    vol: float
    amount: float
    float_shares: float = 0.0


@dataclass(frozen=True)
class MacTick:
    """分时数据点。"""

    time: time
    price: float
    avg: float
    vol: int
    momentum: float = 0.0


@dataclass(frozen=True)
class MacTickChart:
    """单日分时图。"""

    market: int
    code: str
    name: str
    pre_close: float
    open: float
    high: float
    low: float
    close: float
    vol: int
    amount: float
    turnover: float = 0.0
    avg: float = 0.0
    charts: list[MacTick] = field(default_factory=list)


@dataclass(frozen=True)
class MacMultiTickDay:
    """多日分时图中的一天。"""

    date: date
    pre_close: float
    ticks: list[MacTick] = field(default_factory=list)


@dataclass(frozen=True)
class MacMultiTickChart:
    """多日分时图。"""

    market: int
    code: str
    name: str
    pre_close: float
    open: float
    high: float
    low: float
    close: float
    vol: int
    amount: float
    turnover: float = 0.0
    avg: float = 0.0
    charts: list[MacMultiTickDay] = field(default_factory=list)


@dataclass(frozen=True)
class MacTransaction:
    """逐笔成交。"""

    time: time
    price: float
    vol: int
    trade_count: int
    bs_flag: int  # 0=买入 / 1=卖出 / 2=中性 / 5=盘后


@dataclass(frozen=True)
class BoardInfo:
    """板块信息。"""

    market: int
    code: str
    name: str
    price: float
    rise_speed: float
    pre_close: float
    symbol_market: int
    symbol_code: str
    symbol_name: str
    symbol_price: float
    symbol_rise_speed: float
    symbol_pre_close: float


@dataclass(frozen=True)
class AuctionItem:
    """集合竞价数据。"""

    time: time
    price: float
    matched: int
    unmatched: int


@dataclass(frozen=True)
class UnusualItem:
    """异动数据。"""

    index: int
    market: int
    code: str
    name: str
    time: time
    desc: str
    value: str
    unusual_type: int


@dataclass(frozen=True)
class CapitalFlowData:
    """资金流向数据。"""

    date: str
    main_in: float = 0.0
    main_out: float = 0.0
    main_net: float = 0.0
    small_in: float = 0.0
    small_out: float = 0.0
    small_net: float = 0.0
    mid_in: float = 0.0
    mid_out: float = 0.0
    mid_net: float = 0.0
    large_in: float = 0.0
    large_out: float = 0.0
    large_net: float = 0.0


@dataclass(frozen=True)
class BelongBoardInfo:
    """个股所属板块信息。"""

    board_type: int
    market: int
    board_code: str
    board_name: str
    close: float
    pre_close: float


@dataclass(frozen=True)
class ServerSession:
    """服务器交易时段信息。"""

    today: str
    last_trading_day: str
    sessions_1: list[dict[str, Any]] = field(default_factory=list)
    sessions_2: list[dict[str, Any]] = field(default_factory=list)
    market_param_1: int = 0
    market_param_2: int = 0


@dataclass(frozen=True)
class KlineOffsetInfo:
    """K线偏移信息。"""

    total: int
    returned: int


class BoardListCmd(BaseCommand[list[BoardInfo]]):
    """查询板块列表。

    Parameters
    ----------
    board_type : BoardType
        板块类型（行业、概念、风格等）。
    start : int
        起始偏移量。
    page_size : int
        每页数量。
    """

    def __init__(self, board_type: BoardType = BoardType.ALL, start: int = 0, page_size: int = 150):
        self._board_type = board_type
        self._start = start
        self._page_size = page_size

    def build_request(self) -> bytes:
        # <HHBBHH8x: page_size, board_type, sort_col(0), sort_order(0), start, flag(1)
        body = struct.pack("<HHBBHH8x", self._page_size, int(self._board_type), 0,  # sort_column: 0 = rise_speed
            0,  # sort_order
            self._start, 1,  # flag)
        return build_mac_request(0x1231, body)

    def parse_response(self, body: bytes) -> list[BoardInfo]:
        count_all, total = unpack_from("<HH", body, 0, "board_list header")
        # 服务器返回 count_all = 2 * actual_count（board_info + symbol_info 各一份）
        count = count_all // 2

        # 板板信息 + 领涨股信息，每组 160 字节
        # fmt: H(2) + 6s(6) + 16s(16) + 44s(44) + f(4) + f(4) + f(4) = 80
        # x2 for board + symbol = 160
        _RECORD_FMT = "<H6s16s44sfffH6s16s44sfff"
        _RECORD_SIZE = struct.calcsize(_RECORD_FMT)  # 160
        results: list[BoardInfo] = []
        for i in range(count):
            offset = 4 + i * _RECORD_SIZE
            (market, code_raw, _pad1, name_raw, price, rise_speed, pre_close, symbol_market, symbol_code_raw, _pad2, symbol_name_raw, symbol_price, symbol_rise_speed, symbol_pre_close) = unpack_from(_RECORD_FMT, body, offset, f"board_list record[{i}]")

            results.append(BoardInfo(market=market, code=code_raw.decode("gbk", errors="replace").rstrip("\x00"), name=name_raw.decode("gbk", errors="replace").rstrip("\x00"), price=price, rise_speed=rise_speed, pre_close=pre_close, symbol_market=symbol_market, symbol_code=symbol_code_raw.decode("gbk", errors="replace").rstrip("\x00"), symbol_name=symbol_name_raw.decode("gbk", errors="replace").rstrip("\x00"), symbol_price=symbol_price, symbol_rise_speed=symbol_rise_speed, symbol_pre_close=symbol_pre_close))

        return results


class BoardMembersQuotesCmd(BaseCommand[list[MacQuoteField]]):
    """查询板块成分股报价。

    Parameters
    ----------
    board_code : int
        板块代码（如 int("881001")）。
    sort_type : SortType
        排序字段。
    start : int
        起始偏移量。
    page_size : int
        每页数量。
    sort_order : SortOrder
        排序方向。
    fields : Fields
        请求的字段集合。
    exclude_flags : list[FilterType]
        排除条件列表（如排除科创板、创业板等）。
    """

    def __init__(self, board_code: int, sort_type: SortType = SortType.CHANGE_PCT, start: int = 0, page_size: int = 80, sort_order: SortOrder = SortOrder.NONE, fields: Fields = PresetField.NONE, exclude_flags: list[FilterType] = None):
        self._board_code = board_code
        self._sort_type = sort_type
        self._start = start
        self._page_size = page_size
        self._sort_order = sort_order
        self._fields = fields
        self._exclude_flags = exclude_flags or []

    def build_request(self) -> bytes:
        # I:board_code, 9x padding, H:sort_type, I:start, H:page_size, B:sort_order, B:pad
        body = struct.pack("<I9xHIHBB", self._board_code, int(self._sort_type), self._start, self._page_size, int(self._sort_order), 0)

        # 16 字节字段位图
        bitmap = build_bitmap(self._fields)
        body += bytes(bitmap[:16])

        # 4 字节控制区: byte0=盘口, byte1=排除位, byte2=日内, byte3=控制(CTRL_EXTENDED=1)
        b1 = sum(f.value for f in self._exclude_flags)
        body += struct.pack("<BBBB", 0, b1, 0, 1)

        return build_mac_request(0x122C, body)

    def parse_response(self, body: bytes) -> list[MacQuoteField]:
        # 响应位图（20 字节）
        resp_bitmap = body[:20]

        total, row_count = unpack_from("<IH", body, 20, "board_members header")

        active_fields = get_active_fields(resp_bitmap[:16])
        field_count = len(active_fields)

        # 每行: market(2) + code(22) + name(44) = 68 + field_count * 4
        row_len = 68 + field_count * 4

        results: list[MacQuoteField] = []
        for i in range(row_count):
            row_start = 26 + i * row_len
            market_raw = unpack_from("<H", body, row_start, f"board_members row[{i}] market")[0]
            code_raw = body[row_start + 2 : row_start + 24]
            name_raw = body[row_start + 24 : row_start + 68]

            fields_dict: dict[str, object] = {}
            for idx, (field_bit, fmt) in enumerate(active_fields):
                val_bytes = body[row_start + 68 + idx * 4 : row_start + 68 + (idx + 1) * 4]
                if len(val_bytes) < 4:
                    break
                (value,) = struct.unpack(fmt, val_bytes)
                fields_dict[field_bit.field_name] = value

            results.append(MacQuoteField(market=market_raw, code=code_raw.decode("gbk", errors="replace").rstrip("\x00"), name=name_raw.decode("gbk", errors="replace").rstrip("\x00"), fields=fields_dict))

        return results


class ChartSamplingCmd(BaseCommand[list[float]]):
    """获取分时缩略采样价格点。

    返回 240 个 float 价格值（每分钟一个采样点）。

    Args:
        market: 扩展市场代码（ExMarket 枚举值）。
        code: 证券代码（GBK 编码）。
    """

    def __init__(self, market: int, code: str):
        self.market = market
        self.code = code

    def build_request(self) -> bytes:
        raw_code = self.code.encode("gbk")
        _CODE_LEN = 22
        padded = (raw_code + b"\x00" * _CODE_LEN)[:_CODE_LEN]
        body = struct.pack("<H22sHH9x", self.market, padded, 1, 20)
        return build_mac_request(0x254D, body)

    def parse_response(self, body: bytes) -> list[float]:

        _RESPONSE_HEADER_SIZE = 42  # H(2) + 22s(22) + 9*H(18) = 42
        if len(body) < _RESPONSE_HEADER_SIZE:
            return []
        require_bytes(body, 0, _RESPONSE_HEADER_SIZE, "ChartSamplingCmd header")
        (count,) = unpack_from("<H", body, 40, "chart_sampling count")
        prices: list[float] = []
        for i in range(count):
            pos = _RESPONSE_HEADER_SIZE + i * 4
            require_bytes(body, pos, 4, f"ChartSamplingCmd price[{i}]")
            (p,) = unpack_from("<f", body, pos, f"chart_sampling price[{i}]")
            prices.append(p)
        return prices



@dataclass(frozen=True)
class FileMeta:
    """文件列表查询结果。"""

    offset: int
    size: int
    flag: int
    hash: str


class FileListCmd(BaseCommand[FileMeta]):
    """查询远程文件元信息（大小、哈希等）。

    Args:
        filename: 远程文件名（GBK 编码）。
        offset: 文件偏移（默认 0）。
    """

    def __init__(self, filename: str, offset: int = 0):
        self.filename = filename
        self.offset = offset

    def build_request(self) -> bytes:
        _FILENAME_PAD = 30
        raw_name = self.filename.encode("gbk")
        _FILENAME_LEN = 70
        padded = (raw_name + b"\x00" * _FILENAME_LEN)[:_FILENAME_LEN]
        body = struct.pack("<I", self.offset) + padded + b"\x00" * _FILENAME_PAD
        _FILELIST_MSG_ID = 0x1215
        return build_mac_request(_FILELIST_MSG_ID, body)

    def parse_response(self, body: bytes) -> FileMeta:
        require_bytes(body, 0, 4 + 4 + 1 + 32, "FileListCmd")
        offset, size, flag = unpack_from("<IIb", body, 0, "FileListCmd meta")
        raw_hash = body[9:41]
        hash_str = raw_hash.decode("ascii", errors="replace").rstrip("\x00")
        return FileMeta(offset=offset, size=size, flag=flag, hash=hash_str)


class FileDownloadCmd(BaseCommand[bytes]):
    """分段下载远程文件内容。

    Args:
        filename: 远程文件名（GBK 编码）。
        index: 分段序号（1-based）。
        offset: 字节偏移。
        size: 请求块大小（默认 30000）。
    """

    def __init__(self, filename: str, index: int = 1, offset: int = 0, size: int = 30000):
        self.filename = filename
        self.index = index
        self.offset = offset
        self.size = size

    def build_request(self) -> bytes:
        raw_name = self.filename.encode("gbk")
        _FILENAME_LEN = 70
        _FILENAME_PAD = 30
        padded = (raw_name + b"\x00" * _FILENAME_LEN)[:_FILENAME_LEN]
        body = (struct.pack("<III", self.index, self.offset, self.size)
            + padded
            + b"\x00" * _FILENAME_PAD)
        _FILEDL_MSG_ID = 0x1217
        return build_mac_request(_FILEDL_MSG_ID, body)

    def parse_response(self, body: bytes) -> bytes:
        if len(body) < 8:
            return b""
        return body[8:]


@dataclass(frozen=True)
class GoodsItem:
    """扩展市场商品信息。"""

    name: str
    category: int
    u: int
    index: int
    switch: int
    code: list[float]
    c1: int
    c2: int


class GoodsListCmd(BaseCommand[list[GoodsItem]]):
    """获取扩展市场（期货/期权等）商品列表。

    Args:
        market: 扩展市场代码（ExMarket 枚举值）。
        start: 起始偏移（默认 0）。
        count: 请求数量（最大 1000，默认 600）。
    """

    def __init__(self, market: int, start: int = 0, count: int = 600):
        if count > 1000:
            raise ValueError(f"count 不能超过 1000，当前: {count}")
        self.market = market
        self.start = start
        self.count = count
        self.total: int = 0

    def build_request(self) -> bytes:
        body = struct.pack("<HII", self.market, self.start, self.count)
        return build_mac_request(0x2562, body)

    def parse_response(self, body: bytes) -> list[GoodsItem]:
        _RECORD_SIZE = 48
        _RECORD_FMT = "<H23sHIBfffHH"
        require_bytes(body, 0, 2, "GoodsListCmd header")
        (total,) = unpack_from("<H", body, 0, "GoodsListCmd total")
        self.total = total
        items: list[GoodsItem] = []
        for i in range(total):
            offset = 2 + i * _RECORD_SIZE
            require_bytes(body, offset, _RECORD_SIZE, f"GoodsListCmd record[{i}]")
            category, raw_name, u, index, switch, v1, v2, v3, c1, c2 = unpack_from(_RECORD_FMT, body, offset, f"GoodsListCmd record[{i}]")
            name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
            items.append(GoodsItem(name=name, category=category, u=u, index=index, switch=switch, code=[v1, v2, v3], c1=c1, c2=c2))
        return items

class KlineOffsetCmd(BaseCommand[KlineOffsetInfo]):
    """查询K线数据偏移。

    Parameters
    ----------
    offset : int
        偏移量（必须为 0）。
    count : int
        请求数量。
    """

    def __init__(self, offset: int = 0, count: int = 128000):
        self._offset = offset
        self._count = count

    def build_request(self) -> bytes:
        # I:offset, I:count, 5 bytes padding
        body = struct.pack("<II5x", self._offset, self._count)
        return build_mac_request(0x124A, body)

    def parse_response(self, body: bytes) -> KlineOffsetInfo:
        if len(body) < 8:
            return KlineOffsetInfo(total=0, returned=0)

        # total 字段为大端序!
        total = struct.unpack(">I", body[:4])[0]
        returned = struct.unpack("<I", body[4:8])[0]

        return KlineOffsetInfo(total=total, returned=returned)

class ServerInfoCmd(BaseCommand[ServerSession]):
    """查询服务器交易时段信息。"""

    def build_request(self) -> bytes:
        # 固定 68 字节请求体
        header = bytes.fromhex("04002d31")
        body = header + b"\x00" * 8 + b"\x00\x27\x06\x0e" + b"\x00" * 52
        return build_mac_request(0x120F, body)

    def parse_response(self, body: bytes) -> ServerSession:
        if len(body) < 87:
            return ServerSession(today="", last_trading_day="")

        pos = 0
        _count = unpack_from("<H", body, pos, "server_info count")[0]
        pos += 2
        # 8 bytes flags
        pos += 8
        # 3 bytes tag ("-1")
        pos += 3
        # 9 bytes reserved
        pos += 9

        def _parse_date(p: int) -> tuple[str, int]:
            d = unpack_from("<I", body, p, "server_info date")[0]
            return f"{d // 10000}-{d % 10000 // 100:02d}-{d % 100:02d}", p + 4

        def _parse_session(p: int) -> tuple[list[dict[str, object]], int]:
            vals = unpack_from("<8H", body, p, "server_info session")
            sessions: list[dict[str, object]] = []
            for i in range(0, 8, 2):
                sessions.append({
                        "open": f"{vals[i] // 60}:{vals[i] % 60:02d}", "close": f"{vals[i + 1] // 60}:{vals[i + 1] % 60:02d}", })
            return sessions, p + 16

        today, pos = _parse_date(pos)
        pos += 4  # ts1

        sessions_1, pos = _parse_session(pos)
        sessions_2, pos = _parse_session(pos)

        pos += 1  # flag byte

        last_trading_day, pos = _parse_date(pos)
        pos += 4  # ts2

        # Skip remaining fields
        market_param_1 = 0
        market_param_2 = 0
        if pos + 8 <= len(body):
            market_param_1 = unpack_from("<I", body, pos, "server_info param1")[0]
            pos += 4
            market_param_2 = unpack_from("<I", body, pos, "server_info param2")[0]

        return ServerSession(today=today, last_trading_day=last_trading_day, sessions_1=sessions_1, sessions_2=sessions_2, market_param_1=market_param_1, market_param_2=market_param_2)

class SymbolAuctionCmd(BaseCommand[list[AuctionItem]]):
    """查询集合竞价数据。

    Parameters
    ----------
    market : int
        市场代码。
    code : str
        证券代码。
    start : int
        起始偏移量。
    count : int
        请求数量。
    """

    def __init__(self, market: int, code: str, start: int = 0, count: int = 500):
        self._market = market
        self._code = code
        self._start = start
        self._count = count

    def build_request(self) -> bytes:
        # H: market, 22s: code in GBK, I: start, I: count, 10 bytes padding
        body = struct.pack("<H22sII10x", self._market, self._code.encode("gbk"), self._start, self._count)
        return build_mac_request(0x123D, body)

    def parse_response(self, body: bytes) -> list[AuctionItem]:
        # 响应头: H:market, 22s:code, I:count, 8 bytes padding (zeros)
        _market, _code, count = unpack_from("<H22sI", body, 0, "auction header")

        items: list[AuctionItem] = []
        for i in range(count):
            offset = 36 + i * 16
            if offset + 16 > len(body):
                break
            time_sec, price, matched, unmatched = unpack_from("<IfIi", body, offset, f"auction item[{i}]")

            items.append(AuctionItem(time=time(time_sec // 3600, (time_sec % 3600) // 60, time_sec % 60), price=price, matched=matched, unmatched=unmatched))

        return items



def _combine_datetime(ymd: int, time_num: int, is_intraday: bool) -> datetime:
    """将日期和可选时间组合为 datetime。

    日线及以上周期 time_num 为 0，分时周期 time_num 含 HHMM 信息。
    """
    year = ymd // 10000
    month = (ymd % 10000) // 100
    day = ymd % 100
    if is_intraday and time_num:
        hour = time_num // 3600
        minute = (time_num % 3600) // 60
        return datetime(year, month, day, hour, minute)
    return datetime(year, month, day)


class SymbolBarCmd(BaseCommand[list[MacBar]]):
    """获取单只股票的 K 线数据。

    Args:
        market: 市场代码。
        code:   6 位股票代码。
        period: K 线周期。
        times:  周期倍数（Period.MINS / Period.DAYS 时有效）。
        start:  起始偏移（0 = 最新）。
        count:  返回条数。
        fq:     复权方式。
    """

    def __init__(self, market: int, code: str, period: Period = Period.DAILY, times: int = 1, start: int = 0, count: int = 700, fq: Adjust = Adjust.NONE):
        self._market = market
        self._code = code
        self._period = period
        self._times = times
        self._start = start
        self._count = count
        self._fq = fq

    def build_request(self) -> bytes:
        body = struct.pack("<H22sHH I HH bbb bH4s", self._market, self._code.encode("gbk"), self._period, self._times, self._start, self._count, self._fq, 1, 1, 0, 1, 0, b"")
        return build_mac_request(0x122E, body)

    def parse_response(self, body: bytes) -> list[MacBar]:
        # 头部: market(2) + code(22) + category(2) + flag(1) + count(2) + start(4) = 33
        (category_flag, _flag, count, start) = unpack_from("<HBHI", body, 24, "symbol_bar header")

        # 防止 count 异常导致越界读取
        count = min(count, (len(body) - 33) // 36)
        if count < 0:
            count = 0

        is_intraday = (self._period < Period.DAILY
            or self._period == Period.MIN_1
            or self._period == Period.MINS)

        results: list[MacBar] = []
        for i in range(count):
            offset = 33 + i * 36
            if offset + 36 > len(body):
                break
            (ymd, time_num, open_, high, low, close, amount, vol, float_shares) = unpack_from("<II7f", body, offset, f"symbol_bar bar[{i}]")
            if ymd < 19900101 or ymd > 20991231:
                continue
            dt = _combine_datetime(ymd, time_num, is_intraday)
            results.append(MacBar(datetime=dt, open=open_, high=high, low=low, close=close, vol=vol, amount=amount, float_shares=float_shares))

        return results


def _to_float(value: object) -> float:
    """Safely convert JSON value to float."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0.0


def _to_int(value: object) -> int:
    """Safely convert JSON value to int."""
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0


class SymbolBelongBoardCmd(BaseCommand[list[BelongBoardInfo]]):
    """查询个股所属板块。

    Parameters
    ----------
    market : int
        市场代码。
    code : str
        证券代码。
    """

    def __init__(self, market: int, code: str):
        self._market = market
        self._code = code

    def build_request(self) -> bytes:
        # H:market, 8s:code padded with spaces, 16s:padding, 21s:"Stock_GLHQ"
        body = struct.pack("<H8s16x21s", self._market, self._code.encode("gbk"), b"Stock_GLHQ")
        # head=1 用于区分 symbol_belong_board 与 symbol_capital_flow (head=2)
        return build_mac_request(0x1218, body, head_flag=1)

    def parse_response(self, body: bytes) -> list[BelongBoardInfo]:
        # 响应头: H:market, 12s:query_info, 5x padding, 8s:ext = 27 bytes
        if len(body) < 27:
            return []

        json_bytes = body[27:]
        python_list: list[list[object]] = json.loads(json_bytes.decode("gbk", errors="replace"))

        results: list[BelongBoardInfo] = []
        if not python_list:
            return results

        for row in python_list:
            n = len(row)
            if n not in (9, 13):
                continue

            bt = _to_int(row[0])
            mkt = _to_int(row[1])
            board_code = str(row[2])
            board_name = str(row[3])
            close = _to_float(row[4]) if n > 4 and row[4] else 0.0
            pre_close = _to_float(row[5]) if n > 5 and row[5] else 0.0

            results.append(BelongBoardInfo(board_type=bt, market=mkt, board_code=board_code, board_name=board_name, close=close, pre_close=pre_close))

        return results


def _to_float(value: object) -> float:
    """Safely convert JSON value to float."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0.0


class SymbolCapitalFlowCmd(BaseCommand[CapitalFlowData]):
    """查询个股资金流向。

    Parameters
    ----------
    market : int
        市场代码。
    code : str
        证券代码。
    """

    def __init__(self, market: int, code: str):
        self._market = market
        self._code = code

    def build_request(self) -> bytes:
        # H:market, 8s:code padded with spaces, 16s:padding, 21s:"Stock_ZJLX"
        body = struct.pack("<H8s16x21s", self._market, self._code.encode("gbk"), b"Stock_ZJLX")
        # head=2 用于区分 symbol_capital_flow 与 symbol_belong_board (head=1)
        _HEAD_FLAG = 2
        return build_mac_request(0x1218, body, head_flag=_HEAD_FLAG)

    def parse_response(self, body: bytes) -> CapitalFlowData:
        # 响应头: H:market, 12s:query_info, 5x padding, 8s:ext = 27 bytes
        if len(body) < 27:
            return None

        json_bytes = body[27:]
        python_list: list[list[object]] = json.loads(json_bytes.decode("gbk"))

        if len(python_list) < 2:
            return None

        today_data = python_list[0]
        five_days_data = python_list[1]

        # today_data: [main_in, main_out, retail_in, retail_out]
        # five_days_data: [buy_5d, sell_5d, super_large, large, mid, small]
        main_in = _to_float(today_data[0]) if len(today_data) > 0 else 0.0
        main_out = _to_float(today_data[1]) if len(today_data) > 1 else 0.0
        retail_in = _to_float(today_data[2]) if len(today_data) > 2 else 0.0
        retail_out = _to_float(today_data[3]) if len(today_data) > 3 else 0.0

        mid_net_5d = _to_float(five_days_data[4]) if len(five_days_data) > 4 else 0.0
        large_net_5d = _to_float(five_days_data[3]) if len(five_days_data) > 3 else 0.0

        return CapitalFlowData(date="", main_in=main_in, main_out=main_out, main_net=main_in - main_out, small_in=retail_in, small_out=retail_out, small_net=retail_in - retail_out, mid_in=0.0, mid_out=0.0, mid_net=mid_net_5d, large_in=0.0, large_out=0.0, large_net=large_net_5d)


class SymbolInfoCmd(BaseCommand[MacSymbolInfo]):
    """获取个股简要特征。

    Args:
        market: 市场代码。
        code:   6 位股票代码。
    """

    def __init__(self, market: int, code: str):
        self._market = market
        self._code = code

    def build_request(self) -> bytes:
        body = struct.pack("<H22sI12x", self._market, self._code.encode("gbk"), 1)
        return build_mac_request(0x122A, body)

    def parse_response(self, body: bytes) -> MacSymbolInfo:
        # data[0:8]  padding (zeros)
        # data[8:74] market(2) + code(22) + name(44)
        (market, code_raw, name_raw) = unpack_from("<H22s44s", body, 8, "symbol_info identity")

        # data[76:96] padding (zeros)
        # data[96:..] core fields
        (date_raw, time_raw, activity, pre_close, open, high, low, close, momentum, vol, amount, inside_volume, outside_volume) = unpack_from("<III5ffIfII", body, 96, "symbol_info core")

        # data[148:..]
        (_decimal, _a, _b, _c, _vr, turnover, avg) = unpack_from("<HIf20xI3f", body, 148, "symbol_info extra")

        dt = datetime(date_raw // 10000, (date_raw % 10000) // 100, date_raw % 100, time_raw // 10000, (time_raw % 10000) // 100, time_raw % 100)

        return MacSymbolInfo(market=market, code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""), name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""), time=dt, activity=activity, pre_close=pre_close, open=open, high=high, low=low, close=close, momentum=momentum, vol=int(vol), amount=amount, inside_volume=inside_volume, outside_volume=outside_volume, turnover=turnover, avg=avg)


class SymbolQuotesCmd(BaseCommand[list[MacQuoteField]]):
    """批量获取自定义字段报价。

    Args:
        stocks: [(market, code), ...] 列表。
        fields: 字段选择，默认 PresetField.COMMON。
    """

    def __init__(self, stocks: list[tuple[int, str]], fields: Fields = None):
        if not stocks:
            raise ValueError("stocks 不能为空")
        self._stocks = stocks
        # 默认不请求任何字段时使用 COMMON 需要导入 PresetField，
        # 这里延迟导入避免循环。
        if fields is None:
            fields = PresetField.COMMON
        self._fields = fields
        self._bitmap = bytes(build_bitmap(fields))

    def build_request(self) -> bytes:
        body = bytearray(self._bitmap)
        body += struct.pack("<H", len(self._stocks))
        for market, code in self._stocks:
            body += struct.pack("<H22s", market, code.encode("gbk"))
        return build_mac_request(0x122B, bytes(body))

    def parse_response(self, body: bytes) -> list[MacQuoteField]:
        pos = 0
        field_bitmap = body[pos : pos + 20]
        pos += 20

        (total_stocks, row_count) = unpack_from("<IH", body, pos, "symbol_quotes header")
        pos += 6

        active = get_active_fields(field_bitmap[:16])
        field_count = len(active)
        row_len = 68 + 4 * field_count

        results: list[MacQuoteField] = []
        for _ in range(row_count):
            row_end = pos + row_len
            if row_end > len(body):
                break
            row_data = body[pos:row_end]
            pos = row_end

            (market, code_raw, name_raw) = unpack_from("<H22s44s", row_data, 0, "symbol_quotes row")
            code = code_raw.decode("gbk", errors="ignore").replace("\x00", "")
            name = name_raw.decode("gbk", errors="ignore").replace("\x00", "")

            fields_dict: dict[str, Any] = {}
            if field_count:
                for idx, (field_bit, fmt) in enumerate(active):
                    value_bytes = row_data[68 + idx * 4 : 68 + (idx + 1) * 4]
                    (value,) = struct.unpack(fmt, value_bytes)

                    # 后处理钩子
                    post_fn = FIELD_POSTPROCESS.get(field_bit.value)
                    if post_fn is not None:
                        value = post_fn(value, market)  # type: ignore[operator]

                    fields_dict[field_bit.field_name] = value

            results.append(MacQuoteField(market=market, code=code, name=name, fields=fields_dict))

        return results


class SymbolTickChartCmd(BaseCommand[MacTickChart]):
    """获取单日分时图。

    Args:
        market:    市场代码。
        code:      6 位股票代码。
        query_date: 查询日期（None 或 date(0,0,0) 表示今天）。
    """

    def __init__(self, market: int, code: str, query_date: date = None):
        self._market = market
        self._code = code
        if query_date is not None:
            self._ymd = query_date.year * 10000 + query_date.month * 100 + query_date.day
        else:
            self._ymd = 0

    def build_request(self) -> bytes:
        body = struct.pack("<H22sI5H", self._market, self._code.encode("gbk"), self._ymd, 1, 0, 0, 0, 0)
        return build_mac_request(0x122D, body)

    def parse_response(self, body: bytes) -> MacTickChart:
        # 头部: market(2) + code(22) + query_date(4) + reserved(1) + ref_price(4) + count(2)
        (market, code_raw, query_date, reserved, ref_price, count) = unpack_from("<H22sIBfH", body, 0, "tick_chart header")

        ticks: list[MacTick] = []
        for i in range(count):
            offset = 35 + i * 18
            (minutes, price, avg, vol, momentum) = unpack_from("<HffIf", body, offset, f"tick_chart tick[{i}]")
            ticks.append(MacTick(time=time(minutes // 60 % 24, minutes % 60), price=price, avg=avg, vol=vol, momentum=momentum))

        # 尾部元数据
        tail_offset = 35 + count * 18
        (name_raw, _decimal, _category, _vol_unit, _date_raw, _time_raw, pre_close, open, high, low, close, _momentum_tail, vol, amount, _tail_pad2, turnover, avg_tail, _industry) = unpack_from("<44sBHf5x2I5ffIf12s2fI", body, tail_offset, "tick_chart tail")

        return MacTickChart(market=market, code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""), name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""), pre_close=pre_close, open=open, high=high, low=low, close=close, vol=int(vol), amount=amount, turnover=turnover, avg=avg_tail, charts=ticks)


class SymbolTransactionCmd(BaseCommand[list[MacTransaction]]):
    """获取逐笔成交数据。

    Args:
        market:     市场代码。
        code:       6 位股票代码。
        query_date: 查询日期（None 表示今天）。
        start:      起始偏移。
        count:      返回条数。
    """

    def __init__(self, market: int, code: str, query_date: date = None, start: int = 0, count: int = 1000):
        self._market = market
        self._code = code
        if query_date is not None:
            self._ymd = query_date.year * 10000 + query_date.month * 100 + query_date.day
        else:
            self._ymd = 0
        self._start = start
        self._count = count

    def build_request(self) -> bytes:
        body = struct.pack("<H22sIIH10x", self._market, self._code.encode("gbk"), self._ymd, self._start, self._count)
        return build_mac_request(0x122F, body)

    def parse_response(self, body: bytes) -> list[MacTransaction]:
        # 头部: market(2) + code(22) + query_date(4) + flag(1) + count(2) + start(4) + total(4) = 39
        (count,) = unpack_from("<H", body, 29, "transaction count")

        results: list[MacTransaction] = []
        for i in range(count):
            offset = 39 + i * 18
            (time_sec, price, volume, trade_count, bs_flag) = unpack_from("<IfIIH", body, offset, f"transaction item[{i}]")
            results.append(MacTransaction(time=time(time_sec // 3600, time_sec % 3600 // 60, time_sec % 60), price=price, vol=volume, trade_count=trade_count, bs_flag=bs_flag))

        return results


class TickChartsCmd(BaseCommand[MacMultiTickChart]):
    """获取多日分时图。

    Args:
        market:     市场代码。
        code:       6 位股票代码。
        start_date: 起始日期（None 表示从最新交易日开始）。
        days:       天数（最多 5）。
    """

    def __init__(self, market: int, code: str, start_date: date = None, days: int = 5):
        self._market = market
        self._code = code
        if start_date is not None:
            self._start_ymd = start_date.year * 10000 + start_date.month * 100 + start_date.day
        else:
            self._start_ymd = 0
        self._days = days

    def build_request(self) -> bytes:
        body = struct.pack("<H22sIHH6x", self._market, self._code.encode("gbk"), self._start_ymd, self._days, 1)
        return build_mac_request(0x123E, body)

    def parse_response(self, body: bytes) -> MacMultiTickChart:
        # 头部
        (market, code_raw) = unpack_from("<H22s", body, 0, "tick_charts header")

        # 每日日期(5 x I) + 每日前收(5 x f) = 40 bytes
        date_ints = unpack_from("<5I", body, 24, "tick_charts dates")
        pre_close_floats = unpack_from("<5f", body, 44, "tick_charts pre_closes")

        # count(2) + send_last(1) + page_size(2) + total(2)
        (count, send_last, page_size, total) = unpack_from("<HBHH", body, 64, "tick_charts header2")

        days: list[MacMultiTickDay] = []
        for d in range(count):
            ticks: list[MacTick] = []
            for t in range(page_size):
                index = d * page_size + t
                offset = 71 + index * 14
                (minutes, price, avg, vol, tick_reserved) = unpack_from("<HffHH", body, offset, f"tick_charts tick[{d}][{t}]")
                ticks.append(MacTick(time=time(minutes // 60, minutes % 60), price=price, avg=avg, vol=vol))

            ymd = date_ints[d]
            day_date = date(ymd // 10000, (ymd % 10000) // 100, ymd % 100)
            days.append(MacMultiTickDay(date=day_date, pre_close=pre_close_floats[d], ticks=ticks))

        # 尾部元数据
        tail_offset = 71 + count * page_size * 14
        (name_raw, _decimal, _category, _vol_unit, _date_raw, _time_raw, pre_close, open, high, low, close, _momentum, vol, amount, _tail_pad2, turnover, avg, _industry) = unpack_from("<44sBHf5x2I5ffIf12s2fI", body, tail_offset, "tick_charts tail")

        return MacMultiTickChart(market=market, code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""), name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""), pre_close=pre_close, open=open, high=high, low=low, close=close, vol=int(vol), amount=amount, turnover=turnover, avg=avg, charts=days)

def _describe_unusual(unusual_type: int, data: bytes) -> tuple[str, str]:
    """根据异动类型解析描述和数值。"""
    if len(data) < 13:
        return "", ""
    v1, v2, v3, v4 = struct.unpack_from("<B2fI", data)

    if unusual_type == 0x03:
        desc = f"主力{'买入' if v1 == 0x00 else '卖出'}"
        val = f"{v2:.2f}/{v3:.2f}"
    elif unusual_type == 0x04:
        desc = "加速拉升"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x05:
        desc = "加速下跌"
        val = ""
    elif unusual_type == 0x06:
        desc = "低位反弹"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x07:
        desc = "高位回落"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x08:
        desc = "撑杆跳高"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x09:
        desc = "平台跳水"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x0A:
        desc = f"单笔冲{'跌' if v2 < 0 else '涨'}"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x0B:
        direction = "平" if v3 == 0 else "跌" if v3 < 0 else "涨"
        desc = f"区间放量{direction}"
        val = f"{v2:.1f}倍" + ("" if v3 == 0 else f"{v3 * 100:.2f}%")
    elif unusual_type == 0x0C:
        desc = "区间缩量"
        val = ""
    elif unusual_type == 0x10:
        desc = "大单托盘"
        val = f"{v4:.2f}/{v3:.2f}"
    elif unusual_type == 0x11:
        desc = "大单压盘"
        val = f"{v2:.2f}/{v3:.2f}"
    elif unusual_type == 0x12:
        desc = "大单锁盘"
        val = ""
    elif unusual_type == 0x13:
        desc = "竞价试买"
        val = f"{v2:.2f}/{v3:.2f}"
    elif unusual_type == 0x14:
        direction = "涨" if v1 == 0x00 else "跌"
        if len(data) >= 10:
            sub_type, v2_alt, v3_alt = struct.unpack_from("<Bff", data, 1)
        else:
            sub_type, v2_alt, v3_alt = 0, 0.0, 0.0
        if sub_type == 0x01:
            desc = f"逼近{direction}停"
        elif sub_type == 0x02:
            desc = f"封{direction}停板"
        elif sub_type == 0x04:
            desc = f"封{direction}大减"
        elif sub_type == 0x05:
            desc = f"打开{direction}停"
        else:
            desc = f"涨跌停({direction})"
        val = f"{v2_alt:.2f}/{v3_alt:.2f}"
    else:
        desc = f"异动类型{unusual_type:#04x}"
        val = ""

    return desc, val


class UnusualCmd(BaseCommand[list[UnusualItem]]):
    """查询异动数据。

    Parameters
    ----------
    market : int
        市场代码。
    start : int
        起始偏移量。
    count : int
        请求数量（最大 600）。
    """

    def __init__(self, market: int, start: int = 0, count: int = 600):
        self._market = market
        self._start = start
        self._count = min(count, 600)

    def build_request(self) -> bytes:
        # H:market, H:start, 2x padding, H:count, 2x padding, 5×H monitoring params
        body = struct.pack("<HH2xH2xH5H", self._market, self._start, self._count, 1,  # monitor param 1
            200,  # monitor param 2
            30,  # monitor param 3
            40,  # monitor param 4
            50,  # monitor param 5
            200,  # monitor param 6)
        return build_mac_request(0x1237, body)

    def parse_response(self, body: bytes) -> list[UnusualItem]:
        (count,) = unpack_from("<H", body, 0, "unusual count")

        results: list[UnusualItem] = []
        for i in range(count):
            offset = 2 + i * 32
            if offset + 32 > len(body):
                break

            market, code_raw, _, unusual_type, _, index, _z = unpack_from("<H6sBBBHH", body, offset, f"unusual record[{i}]")

            desc, value = _describe_unusual(unusual_type, body[offset + 15 : offset + 28])

            hour, minute_sec = unpack_from("<BH", body, offset + 29, f"unusual time[{i}]")

            results.append(UnusualItem(index=index, market=market, code=code_raw.decode("gbk", errors="replace").rstrip("\x00"), name="",  # populated below from text section
                    time=time(hour, minute_sec // 100, minute_sec % 100), desc=desc, value=value, unusual_type=unusual_type))

        # Text section: stock names in GBK, comma-separated
        binary_length = 2 + count * 32
        text_bytes = body[binary_length:]
        text_list = text_bytes.decode("gbk", errors="ignore").strip(",").split(",")

        # Fill names from text section
        populated: list[UnusualItem] = []
        for i, item in enumerate(results):
            name = text_list[i] if i < len(text_list) else ""
            populated.append(UnusualItem(index=item.index, market=item.market, code=item.code, name=name, time=item.time, desc=item.desc, value=item.value, unusual_type=item.unusual_type))

        return populated

def _convert_board_code(board_symbol: str) -> int:
    """将用户可见的板块代码转换为服务器协议代码。

    转换规则（来自 opentdx exchange_board_code）：
      US0401   → 30401   (30000 + N)
      HK0283   → 20283   (20000 + N)
      000686   → 31686   (31000 + N)
      399372   → 30372   (N - 399000 + 30000)
      899050   → 32050   (N - 899000 + 32000)
      880686   → 20686   (N - 880000 + 20000)
      其他      → int(N)
    """
    s = board_symbol.strip()
    if s.startswith("US"):
        return 30000 + int(s[2:])
    if s.startswith("HK"):
        return 20000 + int(s[2:])
    if len(s) == 6:
        if s.startswith("88"):
            return int(s) - 880000 + 20000
        if s.startswith("399"):
            return int(s) - 399000 + 30000
        if s.startswith("899"):
            return int(s) - 899000 + 32000
        if s.startswith("000"):
            return 31000 + int(s)
    return int(s)


_TRANSACTION_PAGE_SIZE = 1000

_T = TypeVar("_T")


def _flatten_quote_fields(quotes: list[MacQuoteField]) -> list[dict[str, Any]]:
    """将 MacQuoteField 展平为 DataFrame 友好的 dict 列表。"""
    rows: list[dict[str, Any]] = []
    for q in quotes:
        d: dict[str, Any] = {"market": q.market, "code": q.code, "name": q.name}
        d.update(q.fields)
        rows.append(d)
    return rows


def _quotes_to_df(quotes: list[MacQuoteField]) -> pd.DataFrame:
    return pd.DataFrame(_flatten_quote_fields(quotes))


def _flatten_tick_chart(chart: MacTickChart) -> list[dict[str, Any]]:
    """将 MacTickChart 的 ticks 展平为 DataFrame 行。"""
    rows: list[dict[str, Any]] = []
    for tick in chart.charts:
        rows.append(asdict(tick))
    return rows


def _flatten_multi_tick_chart(chart: MacMultiTickChart) -> list[dict[str, Any]]:
    """将 MacMultiTickChart 的所有天的 ticks 展平为 DataFrame 行。"""
    rows: list[dict[str, Any]] = []
    for day in chart.charts:
        for tick in day.ticks:
            d = asdict(tick)
            d["date"] = day.date
            d["pre_close"] = day.pre_close
            rows.append(d)
    return rows


# ============================================================
# 同步客户端
# ============================================================


class MacClient:
    """同步 MAC 协议客户端，支持 IP 优选与断线自动重连。

    使用示例::

        with MacClient("121.36.248.138") as c:
            df = c.get_stock_kline(0, "600000", Period.DAILY, count=100)

        # 自动选延迟最低的 MAC 服务器
        with MacClient.from_best_host() as c:
            df = c.get_board_list()
    """

    def __init__(self, host: str = None, port: int = None, timeout: float = None, auto_reconnect: bool = True, heartbeat_interval: float = 15.0):
        self._host = host if host is not None else get_best_host()
        self._port = port if port is not None else get_port()
        self._timeout = timeout if timeout is not None else get_timeout()
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = TdxConnection(self._host, self._port, self._timeout)

    # ------------------------------------------------------------------ #
    # 工厂方法
    # ------------------------------------------------------------------ #

    @classmethod
    def from_best_host(cls, hosts: list[str] = None, port: int = None, timeout: float = None, ping_timeout: float = 5.0, auto_reconnect: bool = True, heartbeat_interval: float = 15.0) -> MacClient:
        """测量所有 MAC 服务器延迟，选最低延迟的建立客户端。自动保存最佳主机。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        if timeout is None:
            timeout = get_timeout()
        ranked = ping_mac_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(hosts: list[str] = None, port: int = None, timeout: float = 5.0) -> list[tuple[str, float]]:
        """测量多台 MAC 服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        return ping_mac_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    def connect(self):
        self._conn.connect()
        if self._heartbeat_interval > 0:
            self._conn.start_heartbeat(self._heartbeat_interval)

    def close(self):
        self._conn.stop_heartbeat()
        self._conn.close()

    def disconnect(self):
        """Alias for close()."""
        self.close()

    def ensure_connected(self):
        """验证连接存活，断线则自动重建。"""
        try:
            self._execute(KlineOffsetCmd(0, 1))
        except TdxConnectionError:
            self._conn.stop_heartbeat()
            self._conn.close()
            self._conn = TdxConnection(self._host, self._port, self._timeout)
            self._conn.connect()
            if self._heartbeat_interval > 0:
                self._conn.start_heartbeat(self._heartbeat_interval)

    def __enter__(self) -> MacClient:
        self.connect()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.close()

    # ------------------------------------------------------------------ #
    # 内部执行：含自动重连
    # ------------------------------------------------------------------ #

    def _execute(self, cmd: BaseCommand[_T]) -> _T:
        """执行命令；断线时指数退避重试。"""
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError:
            if not self._auto_reconnect:
                raise
            last_exc: TdxConnectionError = None
            for delay in _RETRY_DELAYS:
                time.sleep(delay)
                self._conn.close()
                self._conn = TdxConnection(self._host, self._port, self._timeout)
                self._conn.connect()
                if self._heartbeat_interval > 0:
                    self._conn.start_heartbeat(self._heartbeat_interval)
                try:
                    return self._conn.execute(cmd)
                except TdxConnectionError as e:
                    last_exc = e
            raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # 报价
    # ------------------------------------------------------------------ #

    def get_stock_quotes(self, stocks: list[tuple[int, str]], fields: object = None) -> pd.DataFrame:
        """批量获取自定义字段报价（最多80只/次）。

        Args:
            stocks: [(market, code), ...] 列表。
            fields: 字段选择，默认 PresetField.COMMON。
        """
        quotes = self._execute(SymbolQuotesCmd(stocks, fields))  # type: ignore[arg-type]
        return _quotes_to_df(quotes)

    def get_stock_quotes_list(self, category: Category, start: int = 0, count: int = 80, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC, exclude_flags: list[FilterType] = None, fields: Fields = None) -> pd.DataFrame:
        """获取市场分类报价列表（自动分页）。

        Args:
            category: 市场分类（如 Category.A, Category.SH, Category.KCB 等）。
            start: 起始偏移。
            count: 请求总数。
            sort_type: 排序字段。
            sort_order: 排序方向。
            exclude_flags: 过滤标志列表。
            fields: 请求字段集合，默认 PresetField.BASIC + PresetField.VOLUME。
        """
        if fields is None:
            fields = PresetField.BASIC + PresetField.VOLUME
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        page_size = min(count, _BOARD_MEMBERS_PAGE_SIZE)
        offset = start

        while fetched < count:
            batch = self._execute(BoardMembersQuotesCmd(board_code=int(category), sort_type=sort_type, start=offset, page_size=page_size, sort_order=sort_order, fields=fields, exclude_flags=exclude_flags))
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    # ------------------------------------------------------------------ #
    # K 线（支持复权）
    # ------------------------------------------------------------------ #

    def get_stock_kline(self, market: int, code: str, period: Period = Period.DAILY, start: int = 0, count: int = 800, times: int = 1, adjust: Adjust = Adjust.NONE) -> pd.DataFrame:
        """获取 K 线数据（自动分页，每页最多 700 条）。

        Args:
            market: 市场代码。
            code: 股票代码。
            period: K 线周期。
            start: 起始偏移（0 = 最新）。
            count: 总请求条数。
            times: 周期倍数（Period.MINS/DAYS 时有效）。
            adjust: 复权方式。
        """
        all_bars: list[MacBar] = []
        fetched = 0
        offset = start

        while fetched < count:
            page_size = min(count - fetched, _KLINE_PAGE_SIZE)
            bars = self._execute(SymbolBarCmd(market=market, code=code, period=period, times=times, start=offset, count=page_size, fq=adjust))
            if not bars:
                break
            all_bars = bars + all_bars
            fetched += len(bars)
            offset += len(bars)
            if len(bars) < page_size:
                break

        return _to_df(all_bars)

    def get_stock_kline_with_indicators(self, market: int, code: str, indicators: list[str], period: Period = Period.DAILY, count: int = 30, adjust: Adjust = Adjust.QFQ, params: dict[str, dict[str, float]] = None) -> pd.DataFrame:
        """获取 K 线数据并计算技术指标。

        自动获取足够的历史数据用于指标预热（EMA 至少需要 120 周期）。

        Args:
            market: 市场代码。
            code: 股票代码。
            indicators: 指标名称列表，如 ``["MACD", "KDJ"]``。
            period: K 线周期。
            count: 返回条数（默认30）。
            adjust: 复权方式（默认前复权）。
            params: 可选指标参数覆盖。
        """

        fetch_count = max(120 + count, 200)
        df = self.get_stock_kline(market, code, period=period, count=fetch_count, adjust=adjust)
        return df

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_tick_chart(self, market: int, code: str, date: int = None) -> pd.DataFrame:
        """获取单日分时图。

        Args:
            market: 市场代码。
            code: 股票代码。
            date: 查询日期（YYYYMMDD），None 表示今天。
        """
        from datetime import date as date_cls

        query_date = (date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None)
        chart = self._execute(SymbolTickChartCmd(market, code, query_date))
        return pd.DataFrame(_flatten_tick_chart(chart))

    def get_tick_charts(self, market: int, code: str, date: int = None, days: int = 5) -> pd.DataFrame:
        """获取多日分时图（最多 5 天）。

        Args:
            market: 市场代码。
            code: 股票代码。
            date: 起始日期（YYYYMMDD），None 表示从最新交易日开始。
            days: 天数。
        """
        from datetime import date as date_cls

        start_date = (date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None)
        chart = self._execute(TickChartsCmd(market, code, start_date, days))
        return pd.DataFrame(_flatten_multi_tick_chart(chart))

    def get_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        """获取分时缩略采样价格点（240 个点）。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        prices = self._execute(ChartSamplingCmd(market, code))
        return pd.DataFrame({"price": prices})

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    def get_transactions(self, market: int, code: str, count: int = 2000, start: int = 0, date: int = None) -> pd.DataFrame:
        """获取逐笔成交数据（自动分页）。

        Args:
            market: 市场代码。
            code: 股票代码。
            count: 请求总数。
            start: 起始偏移。
            date: 查询日期（YYYYMMDD），None 表示今天。
        """
        from datetime import date as date_cls

        query_date = (date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None)
        all_items = self._execute(SymbolTransactionCmd(market, code, query_date, start, min(count, _TRANSACTION_PAGE_SIZE)))
        fetched = len(all_items)
        offset = start + fetched

        while fetched < count:
            page_size = min(count - fetched, _TRANSACTION_PAGE_SIZE)
            batch = self._execute(SymbolTransactionCmd(market, code, query_date, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    # ------------------------------------------------------------------ #
    # 个股信息
    # ------------------------------------------------------------------ #

    def get_symbol_info(self, market: int, code: str) -> pd.DataFrame:
        """获取个股简要特征快照。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        info = self._execute(SymbolInfoCmd(market, code))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 板块
    # ------------------------------------------------------------------ #

    def get_board_list(self, board_type: BoardType = BoardType.ALL, count: int = 10000) -> pd.DataFrame:
        """获取板块列表（自动分页）。

        Args:
            board_type: 板块类型。
            count: 请求总数。
        """
        all_items = self._execute(BoardListCmd(board_type, 0, min(count, 150)))
        fetched = len(all_items)
        offset = fetched

        while fetched < count:
            page_size = min(count - fetched, 150)
            batch = self._execute(BoardListCmd(board_type, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    def get_board_members(self, board_symbol: str, count: int = 100000, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC, fields: object = PresetField.COMMON, exclude_flags: list[FilterType] = None) -> pd.DataFrame:
        """获取板块成分股报价（自动分页）。

        Args:
            board_symbol: 板块代码（如 "881001"）。
            count: 请求总数。
            sort_type: 排序字段。
            sort_order: 排序方向。
            fields: 字段选择。
            exclude_flags: 过滤标志列表。
        """
        board_code = _convert_board_code(board_symbol)
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        offset = 0

        while fetched < count:
            page_size = min(count - fetched, _BOARD_MEMBERS_PAGE_SIZE)
            batch = self._execute(BoardMembersQuotesCmd(board_code=board_code, sort_type=sort_type, start=offset, page_size=page_size, sort_order=sort_order, fields=fields,  # type: ignore[arg-type]
                    exclude_flags=exclude_flags))
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    def get_belong_board(self, market: int, code: str) -> pd.DataFrame:
        """获取个股所属板块列表。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        items = self._execute(SymbolBelongBoardCmd(market, code))
        return _to_df(items)

    def get_board_summary(self, board_symbol: str, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC) -> dict[str, Any]:
        """获取板块汇总：总成交金额、主力资金流向等（聚合成分股数据）。

        基于 ``get_board_members`` 获取全部成分股报价，对成交额和资金流字段求和。

        Args:
            board_symbol: 板块代码（如 "881001"）。
            sort_type: 排序字段。
            sort_order: 排序方向。

        Returns:
            包含以下键的字典::

                member_count    成分股数量
                amount          板块总成交额（元）
                vol             板块总成交量（股）
                main_net_amount 板块主力净流入（元）
                main_net_3d     板块近3日主力净流入（元）
                main_net_5d     板块近5日主力净流入（元）
                up_count        上涨家数
                down_count      下跌家数
                members         成分股明细 DataFrame
        """

        fields = (PresetField.BASIC
            + FieldBit.AMOUNT
            + FieldBit.MAIN_NET_AMOUNT
            + FieldBit.MAIN_NET_3D_AMOUNT
            + FieldBit.MAIN_NET_5D_AMOUNT)
        df = self.get_board_members(board_symbol, sort_type=sort_type, sort_order=sort_order, fields=fields)

        agg_keys = ("amount", "main_net_amount", "main_net_3d_amount", "main_net_5d_amount")
        numeric_cols = [c for c in agg_keys if c in df.columns]
        sums = df[numeric_cols].sum() if numeric_cols else pd.Series(dtype=float)

        close_col = "close" if "close" in df.columns else None
        pre_close_col = "pre_close" if "pre_close" in df.columns else None
        if close_col and pre_close_col:
            diff = df[close_col] - df[pre_close_col]
            up_count = int((diff > 0).sum())
            down_count = int((diff < 0).sum())
        else:
            up_count = down_count = 0

        return {
            "member_count": len(df), "amount": float(sums.get("amount", 0.0)), "vol": int(df["vol"].sum()) if "vol" in df.columns else 0, "main_net_amount": float(sums.get("main_net_amount", 0.0)), "main_net_3d": float(sums.get("main_net_3d_amount", 0.0)), "main_net_5d": float(sums.get("main_net_5d_amount", 0.0)), "up_count": up_count, "down_count": down_count, "members": df, }

    def get_board_ranking(self, board_type: BoardType = BoardType.HY, top_n: int = 50, sort_by: str = "change_pct", ascending: bool = False) -> pd.DataFrame:
        """获取板块涨跌幅排行榜（含成交额、成交量、资金流入流出、涨跌家数）。

        先通过 ``get_board_list`` 获取全部板块，再逐个调用
        ``get_board_summary`` 聚合成分股数据，合并为排行榜 DataFrame。

        Args:
            board_type: 板块类型（``BoardType.HY`` 行业 / ``BoardType.GN`` 概念）。
            top_n: 聚合的板块数量上限。概念板块有 300+ 个，
                全部聚合网络开销大，建议按需限制。
            sort_by: 排序字段，可选 ``change_pct`` / ``amount``
                / ``main_net_amount`` / ``vol``。
            ascending: 排序方向，默认降序。

        Returns:
            DataFrame，列::

                code             板块代码
                name             板块名称
                change_pct       涨跌幅%
                amount           板块总成交额（元）
                vol              板块总成交量（股）
                main_net_amount  板块主力净流入（元）
                up_count         上涨家数
                down_count       下跌家数
                member_count     成分股数量
        """
        _VALID_SORT = {"change_pct", "amount", "main_net_amount", "vol"}
        if sort_by not in _VALID_SORT:
            raise ValueError(f"sort_by 必须是 {_VALID_SORT} 之一， got {sort_by!r}")

        boards_df = self.get_board_list(board_type)
        if boards_df.empty:
            return pd.DataFrame()

        # 从 board_list 的 price / pre_close 计算涨跌幅
        if "price" in boards_df.columns and "pre_close" in boards_df.columns:
            pre = boards_df["pre_close"].replace(0, float("nan"))
            boards_df["change_pct"] = (boards_df["price"] - boards_df["pre_close"]) / pre * 100
        else:
            boards_df["change_pct"] = 0.0

        # 按涨跌幅初排，取 top_n 减少后续聚合开销
        boards_df = boards_df.sort_values("change_pct", ascending=ascending).head(top_n)

        rows: list[dict[str, Any]] = []
        for _, row in boards_df.iterrows():
            code = str(row["code"])
            summary = self.get_board_summary(code)
            rows.append({
                    "code": code, "name": row.get("name", ""), "change_pct": round(float(row.get("change_pct", 0.0)), 2), "amount": summary["amount"], "vol": summary["vol"], "main_net_amount": summary["main_net_amount"], "up_count": summary["up_count"], "down_count": summary["down_count"], "member_count": summary["member_count"], })

        result = pd.DataFrame(rows)
        if not result.empty:
            result = result.sort_values(sort_by, ascending=ascending).reset_index(drop=True)
        return result

    def get_board_change_ranking(self, board_type: BoardType = BoardType.HY, target_date: int = None, days: int = 20, top_n: int = None, ascending: bool = False) -> pd.DataFrame:
        """获取板块 N 日涨跌幅排行榜。

        对每个板块获取日 K 线，计算指定日期前 N 个交易日的涨跌幅并排行。
        利用板块指数自身的 K 线数据，无需逐个聚合成分股。

        Args:
            board_type: 板块类型（行业 / 概念 / 风格 / 地区 / 全部）。
            target_date: 截止日期（YYYYMMDD），``None`` 表示最新交易日。
            days: 回溯交易日数（默认 20）。
            top_n: 返回排行数量，``None`` 表示全部（默认）。
            ascending: 排序方向，默认降序（涨幅最大排前）。

        Returns:
            DataFrame，列::

                code         板块代码
                name         板块名称
                close_end    截止日收盘价
                close_start  N 日前收盘价
                change_pct   涨跌幅%
        """
        if days < 1:
            raise ValueError(f"days 必须 >= 1，got {days}")

        boards_df = self.get_board_list(board_type)
        if boards_df.empty:
            return pd.DataFrame(columns=["code", "name", "close_end", "close_start", "change_pct"])

        fetch_count = days + 10  # 缓冲节假日
        target_ts: pd.Timestamp = None
        if target_date is not None:
            target_ts = pd.Timestamp(year=target_date // 10000, month=(target_date // 100) % 100, day=target_date % 100)

        rows: list[dict[str, Any]] = []
        for _, row in boards_df.iterrows():
            board_code = str(row["code"])
            board_market = int(row["market"]) if "market" in row.index else 1
            try:
                kline_df = self.get_stock_kline(market=board_market, code=board_code, period=Period.DAILY, count=fetch_count, adjust=Adjust.NONE)
            except Exception:
                _logger.debug("板块 %s K线获取失败，跳过", board_code, exc_info=True)
                continue

            if kline_df.empty or len(kline_df) < 2:
                continue

            kline_df = kline_df.sort_values("datetime").reset_index(drop=True)

            if target_ts is not None:
                mask = kline_df["datetime"] <= target_ts
                if not mask.any():
                    continue
                end_pos = int(mask[mask].index[-1])
            else:
                end_pos = len(kline_df) - 1

            start_pos = max(0, end_pos - days)
            close_end = float(kline_df.loc[end_pos, "close"])
            close_start = float(kline_df.loc[start_pos, "close"])
            if close_start == 0:
                continue

            change_pct = round((close_end - close_start) / close_start * 100, 2)
            rows.append({
                    "code": board_code, "name": row.get("name", ""), "close_end": close_end, "close_start": close_start, "change_pct": change_pct, })

        result = pd.DataFrame(rows, columns=["code", "name", "close_end", "close_start", "change_pct"])
        if not result.empty:
            result = result.sort_values("change_pct", ascending=ascending)
            if top_n is not None:
                result = result.head(top_n)
            result = result.reset_index(drop=True)
        return result

    # ------------------------------------------------------------------ #
    # 资金流向
    # ------------------------------------------------------------------ #

    def get_capital_flow(self, market: int, code: str) -> pd.DataFrame:
        """获取个股资金流向。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        data = self._execute(SymbolCapitalFlowCmd(market, code))
        if data is None:
            return pd.DataFrame()
        return _to_df(data)

    # ------------------------------------------------------------------ #
    # 集合竞价
    # ------------------------------------------------------------------ #

    def get_auction(self, market: int, code: str) -> pd.DataFrame:
        """获取集合竞价数据。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        items = self._execute(SymbolAuctionCmd(market, code))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 异动
    # ------------------------------------------------------------------ #

    def get_unusual(self, market: int, start: int = 0, count: int = 0) -> pd.DataFrame:
        """获取市场异动数据。

        Args:
            market: 市场代码。
            start: 起始偏移。
            count: 请求数量（0 表示使用默认值 600）。
        """
        items = self._execute(UnusualCmd(market, start, count or 600))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 服务器信息
    # ------------------------------------------------------------------ #

    def get_server_info(self) -> pd.DataFrame:
        """获取服务器交易时段信息。"""
        info = self._execute(ServerInfoCmd())
        return _to_df(info)

    def get_kline_offset(self, offset: int = 0, count: int = 128000) -> pd.DataFrame:
        """获取 K 线数据偏移信息。

        Args:
            offset: 偏移量。
            count: 请求数量。
        """
        info = self._execute(KlineOffsetCmd(offset, count))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 文件操作
    # ------------------------------------------------------------------ #

    def get_file_meta(self, filename: str) -> pd.DataFrame:
        """查询远程文件元信息。

        Args:
            filename: 远程文件名。
        """
        meta = self._execute(FileListCmd(filename))
        return _to_df(meta)

    def download_file_chunk(self, filename: str, index: int, offset: int, size: int) -> bytes:
        """下载远程文件的一个分片。

        Args:
            filename: 远程文件名。
            index: 分段序号（1-based）。
            offset: 字节偏移。
            size: 请求块大小。
        """
        return self._execute(FileDownloadCmd(filename, index, offset, size))

    def download_file(self, filename: str, filesize: int = 0) -> bytearray:
        """下载完整远程文件。

        Args:
            filename: 远程文件名。
            filesize: 预期文件大小（0 表示自动检测）。
        """
        if filesize <= 0:
            meta = self._execute(FileListCmd(filename))
            filesize = meta.size

        full_data = bytearray()
        chunk_size = 30000
        pos = 0
        idx = 1

        while pos < filesize:
            chunk = self._execute(FileDownloadCmd(filename, idx, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            idx += 1
            if len(chunk) < chunk_size:
                break

        return full_data

    # ------------------------------------------------------------------ #
    # 扩展市场
    # ------------------------------------------------------------------ #

    def get_goods_list(self, market: int, start: int = 0, count: int = 600) -> pd.DataFrame:
        """获取扩展市场（期货/期权等）商品列表。

        Args:
            market: 扩展市场代码（ExMarket 枚举值）。
            start: 起始偏移。
            count: 请求数量（最大 1000）。
        """
        items = self._execute(GoodsListCmd(market, start, count))
        return _to_df(items)


# ============================================================
# 异步客户端
# ============================================================


class AsyncMacClient:
    """异步 MAC 协议客户端（asyncio）。

    使用示例::

        async with AsyncMacClient("121.36.248.138") as c:
            df = await c.get_stock_kline(0, "600000", Period.DAILY, count=100)

    注意：
        单个 AsyncMacClient 仅维护一条 TCP 连接；并发调用会在连接内串行执行。
    """

    def __init__(self, host: str = None, port: int = None, timeout: float = None, auto_reconnect: bool = True, heartbeat_interval: float = 15.0):
        self._host = host if host is not None else get_best_host()
        self._port = port if port is not None else get_port()
        self._timeout = timeout if timeout is not None else get_timeout()
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] = None

    # ------------------------------------------------------------------ #
    # 工厂方法
    # ------------------------------------------------------------------ #

    @classmethod
    def from_best_host(cls, hosts: list[str] = None, port: int = None, timeout: float = None, ping_timeout: float = 5.0, auto_reconnect: bool = True, heartbeat_interval: float = 15.0) -> AsyncMacClient:
        """测量所有 MAC 服务器延迟，选最低延迟的建立客户端。自动保存最佳主机。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        if timeout is None:
            timeout = get_timeout()
        ranked = ping_mac_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(hosts: list[str] = None, port: int = None, timeout: float = 5.0) -> list[tuple[str, float]]:
        """测量多台 MAC 服务器延迟。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        return ping_mac_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    async def connect(self):
        await self._conn.connect()
        self._start_heartbeat()

    async def close(self):
        await self._stop_heartbeat()
        await self._conn.close()

    async def disconnect(self):
        """Alias for close()."""
        await self.close()

    async def ensure_connected(self):
        """验证连接存活，断线则自动重建。"""
        try:
            await self._execute(KlineOffsetCmd(0, 1))
        except TdxConnectionError:
            await self._stop_heartbeat()
            await self._conn.close()
            self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
            await self._conn.connect()
            self._start_heartbeat()

    async def __aenter__(self) -> AsyncMacClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        await self.close()

    # ------------------------------------------------------------------ #
    # 心跳
    # ------------------------------------------------------------------ #

    def _start_heartbeat(self):
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self):
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self._execute(KlineOffsetCmd(0, 1))
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 内部执行
    # ------------------------------------------------------------------ #

    async def _execute(self, cmd: BaseCommand[_T]) -> _T:
        """执行命令；断线时指数退避重试。"""
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError:
                if not self._auto_reconnect:
                    raise
                last_exc: TdxConnectionError = None
                for delay in _RETRY_DELAYS:
                    await asyncio.sleep(delay)
                    await self._conn.close()
                    self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
                    await self._conn.connect()
                    try:
                        return await self._conn.execute(cmd)
                    except TdxConnectionError as e:
                        last_exc = e
                raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # 报价
    # ------------------------------------------------------------------ #

    async def get_stock_quotes(self, stocks: list[tuple[int, str]], fields: object = None) -> pd.DataFrame:
        quotes = await self._execute(SymbolQuotesCmd(stocks, fields))  # type: ignore[arg-type]
        return _quotes_to_df(quotes)

    async def get_stock_quotes_list(self, category: Category, start: int = 0, count: int = 80, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC, exclude_flags: list[FilterType] = None, fields: Fields = None) -> pd.DataFrame:
        if fields is None:
            fields = PresetField.BASIC + PresetField.VOLUME
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        page_size = min(count, _BOARD_MEMBERS_PAGE_SIZE)
        offset = start

        while fetched < count:
            batch = await self._execute(BoardMembersQuotesCmd(board_code=int(category), sort_type=sort_type, start=offset, page_size=page_size, sort_order=sort_order, fields=fields, exclude_flags=exclude_flags))
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    # ------------------------------------------------------------------ #
    # K 线
    # ------------------------------------------------------------------ #

    async def get_stock_kline(self, market: int, code: str, period: Period = Period.DAILY, start: int = 0, count: int = 800, times: int = 1, adjust: Adjust = Adjust.NONE) -> pd.DataFrame:
        all_bars: list[MacBar] = []
        fetched = 0
        offset = start

        while fetched < count:
            page_size = min(count - fetched, _KLINE_PAGE_SIZE)
            bars = await self._execute(SymbolBarCmd(market=market, code=code, period=period, times=times, start=offset, count=page_size, fq=adjust))
            if not bars:
                break
            all_bars = bars + all_bars
            fetched += len(bars)
            offset += len(bars)
            if len(bars) < page_size:
                break

        return _to_df(all_bars)

    async def get_stock_kline_with_indicators(self, market: int, code: str, indicators: list[str], period: Period = Period.DAILY, count: int = 30, adjust: Adjust = Adjust.QFQ, params: dict[str, dict[str, float]] = None) -> pd.DataFrame:
        """获取 K 线数据并计算技术指标（异步）。

        自动获取足够的历史数据用于指标预热（EMA 至少需要 120 周期）。
        """
        fetch_count = max(120 + count, 200)
        df = await self.get_stock_kline(market, code, period=period, count=fetch_count, adjust=adjust)
        return df

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    async def get_tick_chart(self, market: int, code: str, date: int = None) -> pd.DataFrame:
        from datetime import date as date_cls

        query_date = (date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None)
        chart = await self._execute(SymbolTickChartCmd(market, code, query_date))
        return pd.DataFrame(_flatten_tick_chart(chart))

    async def get_tick_charts(self, market: int, code: str, date: int = None, days: int = 5) -> pd.DataFrame:
        from datetime import date as date_cls

        start_date = (date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None)
        chart = await self._execute(TickChartsCmd(market, code, start_date, days))
        return pd.DataFrame(_flatten_multi_tick_chart(chart))

    async def get_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        prices = await self._execute(ChartSamplingCmd(market, code))
        return pd.DataFrame({"price": prices})

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    async def get_transactions(self, market: int, code: str, count: int = 2000, start: int = 0, date: int = None) -> pd.DataFrame:
        from datetime import date as date_cls

        query_date = (date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None)
        all_items = await self._execute(SymbolTransactionCmd(market, code, query_date, start, min(count, _TRANSACTION_PAGE_SIZE)))
        fetched = len(all_items)
        offset = start + fetched

        while fetched < count:
            page_size = min(count - fetched, _TRANSACTION_PAGE_SIZE)
            batch = await self._execute(SymbolTransactionCmd(market, code, query_date, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    # ------------------------------------------------------------------ #
    # 个股信息
    # ------------------------------------------------------------------ #

    async def get_symbol_info(self, market: int, code: str) -> pd.DataFrame:
        info = await self._execute(SymbolInfoCmd(market, code))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 板块
    # ------------------------------------------------------------------ #

    async def get_board_list(self, board_type: BoardType = BoardType.ALL, count: int = 10000) -> pd.DataFrame:
        all_items = await self._execute(BoardListCmd(board_type, 0, min(count, 150)))
        fetched = len(all_items)
        offset = fetched

        while fetched < count:
            page_size = min(count - fetched, 150)
            batch = await self._execute(BoardListCmd(board_type, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    async def get_board_members(self, board_symbol: str, count: int = 100000, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC, fields: object = PresetField.COMMON, exclude_flags: list[FilterType] = None) -> pd.DataFrame:
        board_code = _convert_board_code(board_symbol)
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        offset = 0

        while fetched < count:
            page_size = min(count - fetched, _BOARD_MEMBERS_PAGE_SIZE)
            batch = await self._execute(BoardMembersQuotesCmd(board_code=board_code, sort_type=sort_type, start=offset, page_size=page_size, sort_order=sort_order, fields=fields,  # type: ignore[arg-type]
                    exclude_flags=exclude_flags))
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    async def get_belong_board(self, market: int, code: str) -> pd.DataFrame:
        items = await self._execute(SymbolBelongBoardCmd(market, code))
        return _to_df(items)

    async def get_board_summary(self, board_symbol: str, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC) -> dict[str, Any]:
        """获取板块汇总：总成交金额、主力资金流向等（聚合成分股数据）。

        基于 ``get_board_members`` 获取全部成分股报价，对成交额和资金流字段求和。

        Args:
            board_symbol: 板块代码（如 "881001"）。
            sort_type: 排序字段。
            sort_order: 排序方向。

        Returns:
            包含以下键的字典::

                member_count    成分股数量
                amount          板块总成交额（元）
                vol             板块总成交量（股）
                main_net_amount 板块主力净流入（元）
                main_net_3d     板块近3日主力净流入（元）
                main_net_5d     板块近5日主力净流入（元）
                up_count        上涨家数
                down_count      下跌家数
                members         成分股明细 DataFrame
        """

        fields = (PresetField.BASIC
            + FieldBit.AMOUNT
            + FieldBit.MAIN_NET_AMOUNT
            + FieldBit.MAIN_NET_3D_AMOUNT
            + FieldBit.MAIN_NET_5D_AMOUNT)
        df = await self.get_board_members(board_symbol, sort_type=sort_type, sort_order=sort_order, fields=fields)

        agg_keys = ("amount", "main_net_amount", "main_net_3d_amount", "main_net_5d_amount")
        numeric_cols = [c for c in agg_keys if c in df.columns]
        sums = df[numeric_cols].sum() if numeric_cols else pd.Series(dtype=float)

        close_col = "close" if "close" in df.columns else None
        pre_close_col = "pre_close" if "pre_close" in df.columns else None
        if close_col and pre_close_col:
            diff = df[close_col] - df[pre_close_col]
            up_count = int((diff > 0).sum())
            down_count = int((diff < 0).sum())
        else:
            up_count = down_count = 0

        return {
            "member_count": len(df), "amount": float(sums.get("amount", 0.0)), "vol": int(df["vol"].sum()) if "vol" in df.columns else 0, "main_net_amount": float(sums.get("main_net_amount", 0.0)), "main_net_3d": float(sums.get("main_net_3d_amount", 0.0)), "main_net_5d": float(sums.get("main_net_5d_amount", 0.0)), "up_count": up_count, "down_count": down_count, "members": df, }

    async def get_board_ranking(self, board_type: BoardType = BoardType.HY, top_n: int = 50, sort_by: str = "change_pct", ascending: bool = False) -> pd.DataFrame:
        """获取板块涨跌幅排行榜（含成交额、成交量、资金流入流出、涨跌家数）。

        先通过 ``get_board_list`` 获取全部板块，再并发调用
        ``get_board_summary`` 聚合成分股数据，合并为排行榜 DataFrame。

        Args:
            board_type: 板块类型（``BoardType.HY`` 行业 / ``BoardType.GN`` 概念）。
            top_n: 聚合的板块数量上限。概念板块有 300+ 个，
                全部聚合网络开销大，建议按需限制。
            sort_by: 排序字段，可选 ``change_pct`` / ``amount``
                / ``main_net_amount`` / ``vol``。
            ascending: 排序方向，默认降序。

        Returns:
            DataFrame，列::

                code             板块代码
                name             板块名称
                change_pct       涨跌幅%
                amount           板块总成交额（元）
                vol              板块总成交量（股）
                main_net_amount  板块主力净流入（元）
                up_count         上涨家数
                down_count       下跌家数
                member_count     成分股数量
        """
        _VALID_SORT = {"change_pct", "amount", "main_net_amount", "vol"}
        if sort_by not in _VALID_SORT:
            raise ValueError(f"sort_by 必须是 {_VALID_SORT} 之一， got {sort_by!r}")

        boards_df = await self.get_board_list(board_type)
        if boards_df.empty:
            return pd.DataFrame()

        if "price" in boards_df.columns and "pre_close" in boards_df.columns:
            pre = boards_df["pre_close"].replace(0, float("nan"))
            boards_df["change_pct"] = (boards_df["price"] - boards_df["pre_close"]) / pre * 100
        else:
            boards_df["change_pct"] = 0.0

        boards_df = boards_df.sort_values("change_pct", ascending=ascending).head(top_n)

        async def _fetch_row(row: pd.Series) -> dict[str, Any]:
            code = str(row["code"])
            summary = await self.get_board_summary(code)
            return {
                "code": code, "name": row.get("name", ""), "change_pct": round(float(row.get("change_pct", 0.0)), 2), "amount": summary["amount"], "vol": summary["vol"], "main_net_amount": summary["main_net_amount"], "up_count": summary["up_count"], "down_count": summary["down_count"], "member_count": summary["member_count"], }

        rows = await asyncio.gather(*[_fetch_row(row) for _, row in boards_df.iterrows()])

        result = pd.DataFrame(rows)
        if not result.empty:
            result = result.sort_values(sort_by, ascending=ascending).reset_index(drop=True)
        return result

    async def get_board_change_ranking(self, board_type: BoardType = BoardType.HY, target_date: int = None, days: int = 20, top_n: int = None, ascending: bool = False) -> pd.DataFrame:
        """获取板块 N 日涨跌幅排行榜（异步）。

        对每个板块获取日 K 线，计算指定日期前 N 个交易日的涨跌幅并排行。

        Args:
            board_type: 板块类型。
            target_date: 截止日期（YYYYMMDD），``None`` 表示最新交易日。
            days: 回溯交易日数（默认 20）。
            top_n: 返回排行数量，``None`` 表示全部（默认）。
            ascending: 排序方向，默认降序。

        Returns:
            DataFrame，列：code, name, close_end, close_start, change_pct
        """
        if days < 1:
            raise ValueError(f"days 必须 >= 1，got {days}")

        boards_df = await self.get_board_list(board_type)
        if boards_df.empty:
            return pd.DataFrame(columns=["code", "name", "close_end", "close_start", "change_pct"])

        fetch_count = days + 10
        target_ts: pd.Timestamp = None
        if target_date is not None:
            target_ts = pd.Timestamp(year=target_date // 10000, month=(target_date // 100) % 100, day=target_date % 100)

        rows: list[dict[str, Any]] = []
        for _, row in boards_df.iterrows():
            board_code = str(row["code"])
            board_market = int(row["market"]) if "market" in row.index else 1
            try:
                kline_df = await self.get_stock_kline(market=board_market, code=board_code, period=Period.DAILY, count=fetch_count, adjust=Adjust.NONE)
            except Exception:
                _logger.debug("板块 %s K线获取失败，跳过", board_code, exc_info=True)
                continue

            if kline_df.empty or len(kline_df) < 2:
                continue

            kline_df = kline_df.sort_values("datetime").reset_index(drop=True)

            if target_ts is not None:
                mask = kline_df["datetime"] <= target_ts
                if not mask.any():
                    continue
                end_pos = int(mask[mask].index[-1])
            else:
                end_pos = len(kline_df) - 1

            start_pos = max(0, end_pos - days)
            close_end = float(kline_df.loc[end_pos, "close"])
            close_start = float(kline_df.loc[start_pos, "close"])
            if close_start == 0:
                continue

            change_pct = round((close_end - close_start) / close_start * 100, 2)
            rows.append({
                    "code": board_code, "name": row.get("name", ""), "close_end": close_end, "close_start": close_start, "change_pct": change_pct, })

        result = pd.DataFrame(rows, columns=["code", "name", "close_end", "close_start", "change_pct"])
        if not result.empty:
            result = result.sort_values("change_pct", ascending=ascending)
            if top_n is not None:
                result = result.head(top_n)
            result = result.reset_index(drop=True)
        return result

    # ------------------------------------------------------------------ #
    # 资金流向
    # ------------------------------------------------------------------ #

    async def get_capital_flow(self, market: int, code: str) -> pd.DataFrame:
        data = await self._execute(SymbolCapitalFlowCmd(market, code))
        if data is None:
            return pd.DataFrame()
        return _to_df(data)

    # ------------------------------------------------------------------ #
    # 集合竞价
    # ------------------------------------------------------------------ #

    async def get_auction(self, market: int, code: str) -> pd.DataFrame:
        items = await self._execute(SymbolAuctionCmd(market, code))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 异动
    # ------------------------------------------------------------------ #

    async def get_unusual(self, market: int, start: int = 0, count: int = 0) -> pd.DataFrame:
        items = await self._execute(UnusualCmd(market, start, count or 600))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 服务器信息
    # ------------------------------------------------------------------ #

    async def get_server_info(self) -> pd.DataFrame:
        info = await self._execute(ServerInfoCmd())
        return _to_df(info)

    async def get_kline_offset(self, offset: int = 0, count: int = 128000) -> pd.DataFrame:
        info = await self._execute(KlineOffsetCmd(offset, count))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 文件操作
    # ------------------------------------------------------------------ #

    async def get_file_meta(self, filename: str) -> pd.DataFrame:
        meta = await self._execute(FileListCmd(filename))
        return _to_df(meta)

    async def download_file_chunk(self, filename: str, index: int, offset: int, size: int) -> bytes:
        return await self._execute(FileDownloadCmd(filename, index, offset, size))

    async def download_file(self, filename: str, filesize: int = 0) -> bytearray:
        if filesize <= 0:
            meta = await self._execute(FileListCmd(filename))
            filesize = meta.size

        full_data = bytearray()
        chunk_size = 30000
        pos = 0
        idx = 1

        while pos < filesize:
            chunk = await self._execute(FileDownloadCmd(filename, idx, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            idx += 1
            if len(chunk) < chunk_size:
                break

        return full_data

    # ------------------------------------------------------------------ #
    # 扩展市场
    # ------------------------------------------------------------------ #

    async def get_goods_list(self, market: int, start: int = 0, count: int = 600) -> pd.DataFrame:
        items = await self._execute(GoodsListCmd(market, start, count))
        return _to_df(items)
