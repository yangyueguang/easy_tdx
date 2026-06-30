import json
import io
import re
import zipfile
import zlib
import socket
import threading
import time
import pandas as pd
import struct
import concurrent.futures
from zoneinfo import ZoneInfo
from enum import Enum, IntEnum
from abc import ABC, abstractmethod
from types import TracebackType
from typing import Union
from collections import OrderedDict
from datetime import date as date_cls, datetime, time as Time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, is_dataclass, dataclass, field
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
HEADER_SIZE: int = 16
config = {
    "best_host": '121.37.207.165',
    "best_ex_host": '',
    "best_mac_ex_host": '',
    "known_hosts": [
        "111.229.247.189", "150.158.160.2", "180.153.18.170", "124.71.187.122", "180.153.18.171", "180.153.18.172", "119.147.212.81", "115.238.56.198", "115.238.90.165", "218.75.126.9", "47.107.75.159", "59.175.238.38",
        "110.41.147.114", "110.41.2.72", "101.33.225.16", "175.178.112.197", "175.178.128.227", "43.139.95.83", "124.223.163.242", "122.51.120.217", "123.60.164.122", "124.70.199.56", "62.234.50.143", "81.70.151.186",
        "82.156.214.79", "159.75.29.111", "43.139.18.171", "81.71.32.47", "122.51.232.182", "118.25.98.114", "121.36.225.169", "123.60.70.228", "123.60.73.44", "124.70.133.119", "124.71.187.72", "119.97.185.59",
        "129.204.230.128", "101.42.240.54", "124.71.9.153", "123.60.84.66", "111.230.186.52", "101.43.159.194", "120.53.8.251", "152.136.191.169", "116.205.163.254", "116.205.171.132", "116.205.183.150", "49.232.15.141",
        "82.156.174.84", "101.42.164.241", "101.35.121.35", "111.231.113.208", "121.36.248.138", "123.60.47.136", "121.37.207.165"],
    "calc_hosts": "120.76.152.87",
    "ex_hosts": ["112.74.214.43", "120.25.218.6", "43.139.173.246", "159.75.90.107", "106.52.170.195", "139.9.191.175", "175.24.47.69", "150.158.9.199", "150.158.20.127", "49.235.119.116", "49.234.13.160", "116.205.143.214", "124.71.223.19", "113.45.175.47", "123.60.173.210", "118.89.69.202"],
    "mac_ex_hosts": ["116.205.135.205", "121.37.232.167"]
}


class Dot(dict):
    def __init__(self, seq=None, **kwargs):
        super(Dot, self).__init__({} if seq is None else seq if isinstance(seq, dict) else {'value': seq}, **kwargs)

    def __getattr__(self, attr):
        res = self.get(attr)
        if isinstance(res, dict):
            return Dot(res)
        return res
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

    def __call__(self, keypath: str, *args, **kwargs):
        temp = self
        for i in keypath.split('.'):
            temp = temp[int(i) if i.isnumeric() else i]
        return temp


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
    MIN_3 = 8
    YEAR = 9
    SEASON = 10
    YEAR_ALT = 11


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


class PresetField(Enum):
    """预定义字段集合，支持 + / | 链式组合 """

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

    def __add__(self, other: object):
        if isinstance(other, (FieldBit, PresetField, FieldSelection)):
            return FieldSelection(self, other)
        return NotImplemented

    def __or__(self, other: object):
        return self.__add__(other)

    def __radd__(self, other: object):
        if isinstance(other, (FieldBit, FieldSelection)):
            return FieldSelection(other, self)
        return NotImplemented

    def __ror__(self, other: object):
        return self.__radd__(other)


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


@dataclass
class FinancialRecord:
    """单只股票的一期历史专业财报记录。"""
    code: str  # 6 位股票代码
    market: Market  # 市场
    report_date: int  # 报告期 YYYYMMDD
    fields: list[float]  # N 个浮点字段（N = report_size / 4）


@dataclass
class SecurityQuote:
    """单只股票实时五档行情 """

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
    """逐笔成交记录 """
    hour: int
    minute: int
    price: float
    vol: int
    buyorsell: int  # 0=买, 1=卖, 2=中性/撮合, 8=集合竞价
    unknown_last: int = field(default=0, repr=False)
    _raw: bytes = field(default=b"", repr=False, compare=False)


class FieldSelection:
    """字段选择器，支持 PresetField + FieldBit 组合。
    Usage:
        PresetField.BASIC + FieldBit.AH_CODE
        PresetField.BASIC | FieldBit.INDUSTRY
        FieldBit.OPEN + FieldBit.HIGH + FieldBit.LOW
    """

    __slots__ = ("_fields",)

    def __init__(self, *parts: Union[FieldBit, PresetField]):
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

    def __add__(self, other: object) :
        if isinstance(other, (FieldBit, PresetField, FieldSelection)):
            return FieldSelection(self, other)
        return NotImplemented

    def __or__(self, other: object):
        return self.__add__(other)

    def __radd__(self, other: object):
        if isinstance(other, (FieldBit, PresetField)):
            return FieldSelection(other, self)
        return NotImplemented

    def __ror__(self, other: object):
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


@dataclass(frozen=True)
class FrameHeader:
    magic: int  # 协议魔数，恒为 7654321
    seq_id: int  # ZipFlag(1B) + 请求 bytes 1-4 回显(3B)
    method: int  # 请求回显(1B) + 保留(1B) + Method(2B)
    zipsize: int
    unzipsize: int


@dataclass(frozen=True)
class MacQuoteField:
    """MAC 协议自定义字段报价中的一条记录。"""

    market: int
    code: str
    name: str
    fields: dict = field(default_factory=dict)


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

    date: date_cls
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
    sessions_1: list[dict] = field(default_factory=list)
    sessions_2: list[dict] = field(default_factory=list)
    market_param_1: int = 0
    market_param_2: int = 0


@dataclass(frozen=True)
class FileMeta:
    """文件列表查询结果。"""
    offset: int
    size: int
    flag: int
    hash: str


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


@dataclass(frozen=True)
class KlineOffsetInfo:
    """K线偏移信息。"""

    total: int
    returned: int


@dataclass
class ExMarketInfo:
    """市场定义（GetMarkets 返回）。"""

    market: int
    category: int
    name: str
    short_name: str
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExInstrumentInfo:
    """合约/证券信息（GetInstrumentInfo 返回）。"""

    category: int
    market: int
    code: str
    name: str
    desc: str
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExInstrumentQuote:
    """五档行情（GetInstrumentQuote 返回）。"""

    market: int
    code: str
    pre_close: float
    open: float
    high: float
    low: float
    price: float
    kaicang: int
    zongliang: int
    xianliang: int
    neipan: int
    waipan: int
    chicang: int
    bid1: float
    bid2: float
    bid3: float
    bid4: float
    bid5: float
    bid_vol1: int
    bid_vol2: int
    bid_vol3: int
    bid_vol4: int
    bid_vol5: int
    ask1: float
    ask2: float
    ask3: float
    ask4: float
    ask5: float
    ask_vol1: int
    ask_vol2: int
    ask_vol3: int
    ask_vol4: int
    ask_vol5: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExInstrumentBar:
    """K线数据（GetInstrumentBars / GetHistoryInstrumentBarsRange 返回）。"""

    open: float
    high: float
    low: float
    close: float
    position: int
    trade: int
    amount: float
    year: int
    month: int
    day: int
    hour: int
    minute: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExMinuteBar:
    """分时数据（GetMinuteTimeData / GetHistoryMinuteTimeData 返回）。"""

    hour: int
    minute: int
    price: float
    avg_price: float
    volume: int
    open_interest: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExTransactionRecord:
    """逐笔成交记录（GetTransactionData / GetHistoryTransactionData 返回）。"""

    hour: int
    minute: int
    second: int
    price: int
    volume: int
    zengcang: int
    nature: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


def _recv_exact_sock(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise Exception("连接被服务器关闭")
        buf.extend(chunk)
    return bytes(buf)


def _parse_minute_body(body: bytes, skip: int = 4) -> list[MinuteBar]:
    (num,) = unpack_from("<H", body, 0, "minute_time header")
    pos = skip  # 今日分时 skip=4，历史分时 skip=6
    last_price = 0
    bars: list[MinuteBar] = []
    for _ in range(num):
        record_start = pos
        price_diff, pos = get_price(body, pos)
        unknown_1, pos = get_price(body, pos)
        vol, pos = get_price(body, pos)
        last_price += price_diff
        bars.append(MinuteBar(price=last_price / 100.0, vol=vol, _unknown_1=unknown_1, _raw=body[record_start:pos]))
    return bars


def _format_server_time(raw: int) -> str:
    """将 reversed_bytes0 整数转换为 HH:MM:SS.mmm 字符串。

    该字段编码为“小时 + 百万分之一小时的小数部分”。
    例如：14999212 → "14:59:57.163"
    """
    hours, fractional_hour = divmod(raw, 1_000_000)
    total_millis = fractional_hour * 3600 // 1000
    minutes, remainder = divmod(total_millis, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _parse_transaction_body(body: bytes) -> list[TransactionRecord]:
    """当日逐笔：time + price + vol + num_orders + buyorsell + unknown"""
    (num,) = unpack_from("<H", body, 0, "transaction header")
    pos = 2
    last_price = 0
    records: list[TransactionRecord] = []

    for _ in range(num):
        record_start = pos
        hour, minute, pos = get_time(body, pos)
        price_diff, pos = get_price(body, pos)
        vol, pos = get_price(body, pos)
        _num_orders, pos = get_price(body, pos)  # 成交笔数（当日独有）
        buyorsell, pos = get_price(body, pos)
        unknown_last, pos = get_price(body, pos)  # Bug #4 修复：不再丢弃
        last_price += price_diff
        records.append(TransactionRecord(hour=hour, minute=minute, price=last_price / 100.0, vol=vol, buyorsell=buyorsell, unknown_last=unknown_last, _raw=body[record_start:pos]))

    return records


def _decode_share_count(raw: int) -> float:
    """股本数量解码（通达信自定义4字节浮点 → 万股）。

    xdxr_info 的股本字段与成交量字段使用相同的自定义浮点编码，
    解码结果单位为万股，与.zong_guben / 10000 一致。
    """
    return _decode_volume(raw)


def _normalize_per_10_shares(value: float) -> float:
    """将协议里的“每10股”口径归一化为“每股”口径。"""
    return value / 10.0


def _to_df(data) -> pd.DataFrame:
    def _clean_dict(item) -> dict:
        d = asdict(item)
        d = {k: v for k, v in d.items() if not k.startswith("_")}
        if all(k in d for k in ("year", "month", "day")) and not all(k in d for k in ("hour", "minute")):
            dt = pd.Timestamp(year=d["year"], month=d["month"], day=d["day"])
            result: dict = {"date": dt}
            result.update({k: v for k, v in d.items() if k not in {"year", "month", "day"}})
            return result
        return d
    if isinstance(data, list):
        rows = []
        for item in data:
            d = _clean_dict(item)
            rows.append(d)
        return pd.DataFrame(rows)
    if is_dataclass(data) and not isinstance(data, type):
        return pd.DataFrame([_clean_dict(data)])
    raise TypeError(f"不支持转换为 DataFrame 的类型: {type(data)}")


def require_bytes(data: bytes, pos: int, size: int, context: str):
    """确保从 pos 起至少还能读取 size 字节。"""
    if pos < 0:
        raise Exception(f"{context}: 非法偏移 {pos}")
    end = pos + size
    if end > len(data):
        remaining = max(len(data) - pos, 0)
        raise Exception(f"{context}: 数据不足，需要 {size} 字节，偏移 {pos}，实际剩余 {remaining} 字节")


def unpack_from(fmt: str, data: bytes, pos: int, context: str) -> tuple:
    """带边界检查的 struct.unpack_from。"""
    require_bytes(data, pos, struct.calcsize(fmt), context)
    try:
        return struct.unpack_from(fmt, data, pos)
    except struct.error as e:  # pragma: no cover - require_bytes 已覆盖大部分路径
        raise Exception(f"{context}: 解析失败: {e}") from e


def slice_bytes(data: bytes, pos: int, size: int, context: str) -> bytes:
    """带边界检查的切片读取。"""
    require_bytes(data, pos, size, context)
    return bytes(data[pos : pos + size])


def build_mac_request(msg_id: int, body: bytes, *, head_flag: int = 0x1C) -> bytes:
    inner = struct.pack("<H", msg_id) + body
    return struct.pack("<BIBHH", head_flag, 0, 1, len(inner), len(inner)) + inner


def build_bitmap(fields, exclude_flags: int = 0) -> bytearray:
    """将字段选择转换为 20 字节请求位图  """
    if isinstance(fields, PresetField) and fields is PresetField.DEBUG:
        return bytearray(b"\xff" * 20)
    if fields is None:
        selection = FieldSelection()
    elif isinstance(fields, FieldSelection):
        selection = fields
    elif isinstance(fields, PresetField):
        selection = FieldSelection(*fields.value)
    elif isinstance(fields, FieldBit):
        selection = FieldSelection(fields)
    else:
        selection = FieldSelection(*fields)
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
    """从响应位图解析活跃字段    """
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
        zipday, tminutes = unpack_from("<HH", data, pos, "minute datetime")
        year = (zipday >> 11) + 2004
        month = (zipday % 2048) // 100
        day = (zipday % 2048) % 100
        hour = tminutes // 60
        minute = tminutes % 60
        return year, month, day, hour, minute, pos + 4
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


def parse_header(buf: bytes) -> FrameHeader:
    """解析 16 字节响应帧头。"""
    _HEADER_FMT = "<IIIHH"
    magic, seq_id, method, zipsize, unzipsize = unpack_from(_HEADER_FMT, buf, 0, "frame header")
    return FrameHeader(magic, seq_id, method, zipsize, unzipsize)


def decompress_body(header: FrameHeader, raw_body: bytes) -> bytes:
    """按需 zlib 解压 body。

    zipsize == unzipsize 时直接返回原始字节；否则 zlib 解压。
    """
    if len(raw_body) != header.zipsize:
        raise Exception(f"frame body 长度不符: header={header.zipsize}, actual={len(raw_body)}")
    if header.zipsize == header.unzipsize:
        body = raw_body
    else:
        try:
            body = zlib.decompress(raw_body)
        except zlib.error as e:
            raise Exception(f"frame body zlib 解压失败: {e}") from e

    if len(body) != header.unzipsize:
        raise Exception(f"frame body 解压长度不符: header={header.unzipsize}, actual={len(body)}")
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
        raise Exception(f"price varint 截断: offset={start}") from e

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
    if (market == Market.SH and code.startswith(("000", "880", "881", "882", "883", "884", "885", "999"))) or (market == Market.SZ and code.startswith(("395", "399"))) or "指数" in name or "板块" in name:
        return 0
    if code.startswith(("43", "83", "87", "92")):
        return 1
    if market == Market.SH and code.startswith(("60", "68")):
        return 5
    if market == Market.SZ and code.startswith(("00", "30")):
        return 5
    return 0


def compute_price_limits(market: Market, code: str, name: str, pre_close: float) -> tuple[float, float]:
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
    if (market == Market.SH and code.startswith(("000", "880", "881", "882", "883", "884", "885", "999"))) or (market == Market.SZ and code.startswith(("395", "399"))) or "指数" in name or "板块" in name:
        return None, None
    no_limit_window_days = get_no_limit_window_days(market, code, name)
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

    def _round_price(p: float) -> float:
        return round(p + 0.00001, 2)

    limit_up = _round_price(pre_close * (1 + limit_pct))
    limit_down = _round_price(pre_close * (1 - limit_pct))

    return limit_up, limit_down


def get_volume(data: bytes, pos: int) -> tuple[float, int]:
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


def _record_signature(record: TransactionRecord) -> tuple[int, int, float, int, int, int]:
    return (record.hour, record.minute, record.price, record.vol, record.buyorsell, record.unknown_last)


def _page_signature(records: list[TransactionRecord]) -> tuple[tuple[int, int, float, int, int, int], tuple[int, int, float, int, int, int]]:
    return (_record_signature(records[0]), _record_signature(records[-1]))


def _classify_fund_flow(records: list[TransactionRecord]) -> FundFlow:
    stats = {"super_in": 0.0, "large_in": 0.0, "medium_in": 0.0, "small_in": 0.0, "super_out": 0.0, "large_out": 0.0, "medium_out": 0.0, "small_out": 0.0}
    for record in records:
        amount = record.price * record.vol * 100.0
        direction = "in" if record.buyorsell == 0 else "out" if record.buyorsell == 1 else None
        if not direction:
            continue
        if amount > 1_000_000:
            stats[f"super_{direction}"] += amount
        elif amount > 200_000:
            stats[f"large_{direction}"] += amount
        elif amount > 40_000:
            stats[f"medium_{direction}"] += amount
        else:
            stats[f"small_{direction}"] += amount
    return FundFlow(**stats)


def _quotes_to_df(result: list['MacQuoteField']) -> pd.DataFrame:
    """将 MacQuoteField 列表展开为 DataFrame"""
    rows: list[dict] = []
    for item in result:
        row: dict = {"market": item.market, "code": item.code, "name": item.name}
        row.update(item.fields)
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


class BaseCommand(ABC):
    @abstractmethod
    def build_request(self) -> bytes:
        ...


class BoardMembersQuotesCmd(BaseCommand):
    """查询板块成分股报价。    """
    def __init__(self, board_code: int, sort_type: SortType = SortType.CHANGE_PCT, start: int = 0, page_size: int = 80, sort_order: SortOrder = SortOrder.NONE, fields = PresetField.NONE, exclude_flags: list[FilterType] = None):
        self._board_code = board_code
        self._sort_type = sort_type
        self._start = start
        self._page_size = page_size
        self._sort_order = sort_order
        self._fields = fields
        self._exclude_flags = exclude_flags or []

    def build_request(self) -> bytes:
        body = struct.pack("<I9xHIHBB", self._board_code, int(self._sort_type), self._start, self._page_size, int(self._sort_order), 0)
        bitmap = build_bitmap(self._fields)
        body += bytes(bitmap[:16])
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


class SymbolBarCmd(BaseCommand):

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
            year = ymd // 10000
            month = (ymd % 10000) // 100
            day = ymd % 100
            if is_intraday and time_num:
                hour = time_num // 3600
                minute = (time_num % 3600) // 60
                return datetime(year, month, day, hour, minute)
            dt = datetime(year, month, day)
            results.append(MacBar(datetime=dt, open=open_, high=high, low=low, close=close, vol=vol, amount=amount, float_shares=float_shares))

        return results


class SymbolQuotesCmd(BaseCommand):
    def __init__(self, stocks: list[tuple[int, str]], fields=None):
        self._stocks = stocks
        self._bitmap = bytes(build_bitmap(fields or PresetField.COMMON))

    def build_request(self) -> bytes:
        body = bytearray(self._bitmap)
        body += struct.pack("<H", len(self._stocks))
        for market, code in self._stocks:
            body += struct.pack("<H22s", market, code.encode("gbk"))
        return build_mac_request(0x122B, bytes(body))

class GetExInstrumentCountCmd(BaseCommand):
    """获取扩展行情市场中商品总数。"""

    def build_request(self) -> bytes:
        return bytes.fromhex("01 03 48 66 00 01 02 00 02 00 f0 23")

    def parse_response(self, body: bytes) -> int:
        if len(body) < 23:
            return 0
        (count,) = unpack_from("<I", body, 19, "ex instrument count")
        return int(count)


class GetExInstrumentInfoCmd(BaseCommand):
    """获取扩展行情市场中的商品信息列表。"""

    def __init__(self, start: int, count: int = 100):
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 04 48 67 00 01 08 00 08 00 f5 23")
        return header + struct.pack("<IH", self.start, self.count)

    def parse_response(self, body: bytes) -> list[ExInstrumentInfo]:
        if len(body) < 6:
            return []
        pos = 0
        (_start, _count) = struct.unpack("<IH", body[pos : pos + 6])
        count = _count
        pos += 6
        results: list[ExInstrumentInfo] = []
        for _ in range(count):
            if pos + 64 > len(body):
                break
            raw = body[pos : pos + 64]
            (category, market, _unused, raw_code, raw_name, raw_desc) = struct.unpack("<BB3s9s17s9s", raw[:40])
            pos += 64
            code = raw_code.decode("gbk", errors="replace").rstrip("\x00")
            name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
            desc = raw_desc.decode("gbk", errors="replace").rstrip("\x00")
            results.append(ExInstrumentInfo(category=category, market=market, code=code, name=name, desc=desc, _raw=raw))
        return results


class TdxConnection:
    def __init__(self, host: str = None, port: int = 7709, mac_ex_mode=False):
        self.mac_ex_mode = mac_ex_mode
        self.host = host or config.get("best_host")
        self.port = port
        self._sock: socket.socket = None
        self._lock = threading.Lock()
        self._stop_event: threading.Event = None
        self._heartbeat_thread: threading.Thread = None
        self._last_active: float = 0.0
        self._consecutive_heartbeats: int = 0

    def connect(self):
        """建立 TCP 连接并完成握手（发送3条 setup 命令）。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        try:
            sock.connect((self.host, self.port))
        except OSError as e:
            sock.close()
            raise Exception(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._sock = sock
        try:
            self._send_setup()
        except Exception:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None
            raise
        """启动心跳守护线程，定期发送 setup 包保活。"""
        self._last_active = time.monotonic()
        self._stop_event = threading.Event()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="tdx-heartbeat")
        self._heartbeat_thread.start()

    def close(self):
        """关闭连接。"""
        stop_event = self._stop_event
        thread = self._heartbeat_thread
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)
        self._stop_event = None
        self._heartbeat_thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def execute(self, pkg: bytes):
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        with self._lock:
            self._last_active = time.monotonic()
            self._consecutive_heartbeats = 0
            if self._sock is None:
                raise Exception("未连接，请先调用 connect()")
            try:
                self._sock.sendall(pkg)
                header_buf = self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = self._recv_exact(header.zipsize)
            except OSError as e:
                raise Exception(f"通信错误: {e}") from e
            body = decompress_body(header, raw_body)
            return body

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.close()

    def _heartbeat_loop(self):
        """心跳循环：在后台线程中运行。"""
        assert self._stop_event is not None
        while not self._stop_event.wait(timeout=15):
            if time.monotonic() - self._last_active <= 15:
                continue
            with self._lock:
                if self._sock is None:
                    return
                self._consecutive_heartbeats += 1
                if self._consecutive_heartbeats >= 20:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
                    return
                try:
                    self._sock.sendall(bytes.fromhex("0c0218930001030003000d0001"))
                    hdr_buf = _recv_exact_sock(self._sock, HEADER_SIZE)
                    hdr = parse_header(hdr_buf)
                    if hdr.zipsize > 0:
                        _recv_exact_sock(self._sock, hdr.zipsize)
                except OSError:
                    try:
                        if self._sock: self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
                    return

    def _send_setup(self):
        """按序发送三条握手命令并丢弃响应。"""
        assert self._sock is not None
        SETUP_COMMANDS = (bytes.fromhex("0c0218930001030003000d0001"), bytes.fromhex("0c0218940001030003000d0002"),
                          bytes.fromhex("0c031899000120002000db0fd5d0c9ccd6a4a8af0000008fc22540130000d500c9ccbdf0d7ea00000002"))
        for cmd_bytes in SETUP_COMMANDS:
            self._sock.sendall(cmd_bytes)
            # 读取并丢弃握手响应
            try:
                hdr_buf = self._recv_exact(HEADER_SIZE)
                hdr = parse_header(hdr_buf)
                if hdr.zipsize > 0:
                    self._recv_exact(hdr.zipsize)
            except OSError:
                # 部分服务器的握手无响应，忽略错误
                pass

    def _recv_exact(self, n: int) -> bytes:
        """循环 recv 直到读满 n 字节。"""
        assert self._sock is not None
        return _recv_exact_sock(self._sock, n)


class ExTdxConnection:
    def __init__(self, host: str = None, mac_ex_mode: bool = False):
        self.host = host if host is not None else config.get("best_ex_host")
        self.mac_ex_mode = mac_ex_mode
        self._sock: socket.socket = None
        self._lock = threading.Lock()

    def connect(self):
        """建立 TCP 连接。扩展行情服务器不需要握手命令。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        try:
            sock.connect((self.host, 7727))
        except OSError as e:
            sock.close()
            raise Exception(f"无法连接 {self.host}: {e}") from e
        self._sock = sock
        if self.mac_ex_mode:
            inner = struct.pack("<H", 0x2454) + bytes(bytearray.fromhex("e5bb1c2fafe525941f32c6e5d53dfb415b734cc9cdbf0ac92021bfdd1eb06d22d008884c1611cb1378f6abd824d899d21f32c6e5d53dfb411f32c6e5d53dfb41a9325ac935dc0837335a16e4ce17c1bb"))
            pkg = struct.pack("<BIBHH", 0x01, 0, 1, len(inner), len(inner)) + inner
            self.execute(pkg)

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def execute(self, pkg: bytes):
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        with self._lock:
            if self._sock is None:
                raise Exception("未连接，请先调用 connect()")
            if self.mac_ex_mode and len(pkg) > 0 and pkg[0] == 0x1C:
                request = b"\x01" + pkg[1:]
            try:
                self._sock.sendall(request)
                header_buf = self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = self._recv_exact(header.zipsize)
            except OSError as e:
                raise Exception(f"通信错误: {e}") from e
            body = decompress_body(header, raw_body)
            return body

    def __enter__(self) -> "ExTdxConnection":
        self.connect()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.close()

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        return _recv_exact_sock(self._sock, n)


class Client:
    def __init__(self, host: str = None):
        self._host = host or config.get("best_host") or self.from_best_host()
        self._conn = TdxConnection(self._host)

    def _parse_quotes(self, body: bytes):
        pos = 0
        field_bitmap = body[pos: pos + 20]
        pos += 20
        (total_stocks, row_count) = unpack_from("<IH", body, pos, "symbol_quotes header")
        pos += 6
        active = get_active_fields(field_bitmap[:16])
        field_count = len(active)
        row_len = 68 + 4 * field_count
        results = []
        for _ in range(row_count):
            row_end = pos + row_len
            if row_end > len(body):
                break
            row_data = body[pos:row_end]
            pos = row_end
            (market, code_raw, name_raw) = unpack_from("<H22s44s", row_data, 0, "symbol_quotes row")
            code = code_raw.decode("gbk", errors="ignore").replace("\x00", "")
            name = name_raw.decode("gbk", errors="ignore").replace("\x00", "")
            fields_dict: dict = {}
            if field_count:
                for idx, (field_bit, fmt) in enumerate(active):
                    value_bytes = row_data[68 + idx * 4: 68 + (idx + 1) * 4]
                    (value,) = struct.unpack(fmt, value_bytes)
                    if field_bit.value == 0x4A:
                        value = '' if not value else str(value).zfill(5 if market in (0, 1) else 6)
                    fields_dict[field_bit.field_name] = value
            results.append(dict(market=market, code=code, name=name, **fields_dict))
        return pd.DataFrame(results)

    @staticmethod
    def ping_host(host: str, port=7709, pkg=None) -> float:
        t0 = time.monotonic()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((host, port))
            sock.sendall(pkg)
            hdr = parse_header(_recv_exact_sock(sock, HEADER_SIZE))
            if hdr.zipsize > 0:
                _recv_exact_sock(sock, hdr.zipsize)
            return time.monotonic() - t0
        except Exception:
            return None
        finally:
            try:
                sock.close()
            except OSError:
                pass

    @classmethod
    def from_best_host(cls, hosts: list = None, port=7709, pkg=None):
        hosts = hosts or config.get("known_hosts")
        results: list[tuple[str, float]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
            futures = {pool.submit(cls.ping_host, h, port, pkg or bytes.fromhex("0c0218930001030003000d0001")): h for h in hosts}
            for fut in concurrent.futures.as_completed(futures):
                results.append((futures[fut], fut.result()))
        ranked = sorted([i for i in results if i[1]], key=lambda t: t[1])
        return ranked[0][0] if ranked else hosts[0]

    def connect(self):
        self._conn.connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.close()

    def _execute(self, pkg: bytes):
        try:
            return self._conn.execute(pkg)
        except Exception:
            last_exc = None
            for delay in (0.1, 0.5, 1.0, 2.0):
                time.sleep(delay)
                self._conn.close()
                self._conn = type(self._conn)(self._host, mac_ex_mode=self._conn.mac_ex_mode)
                self._conn.connect()
                try:
                    return self._conn.execute(pkg)
                except Exception as e:
                    last_exc = e
            raise last_exc


class MacClient(Client):
    def get_stock_quotes(self, stocks: list[tuple[int, str]], fields: object = None) -> pd.DataFrame:
        """批量获取自定义字段报价（最多80只/次）"""
        quotes = self._execute(SymbolQuotesCmd(stocks, fields))
        return self._parse_quotes(quotes)

    def get_stock_quotes_list(self, category: Category, start: int = 0, count: int = 80, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC, exclude_flags: list[FilterType] = None, fields = None) -> pd.DataFrame:
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
        page_size = min(count, 80)
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
            page_size = min(count - fetched, 700)
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

    def get_tick_chart(self, market=Market.SH, code='600600', date: int = 0) -> pd.DataFrame:
        """获取单日分时图。        """
        pkg = build_mac_request(0x122D, struct.pack("<H22sI5H", int(market), code.encode("gbk"), date, 1, 0, 0, 0, 0))
        body = self._execute(pkg)
        (market, code_raw, query_date, reserved, ref_price, count) = unpack_from("<H22sIBfH", body, 0, "tick_chart header")
        ticks: list[MacTick] = []
        for i in range(count):
            offset = 35 + i * 18
            (minutes, price, avg, vol, momentum) = unpack_from("<HffIf", body, offset, f"tick_chart tick[{i}]")
            ticks.append(MacTick(time=Time(minutes // 60 % 24, minutes % 60), price=price, avg=avg, vol=vol, momentum=momentum))
        # 尾部元数据
        tail_offset = 35 + count * 18
        (name_raw, _decimal, _category, _vol_unit, _date_raw, _time_raw, pre_close, open, high, low, close,
         _momentum_tail, vol, amount, _tail_pad2, turnover, avg_tail, _industry) = unpack_from(
            "<44sBHf5x2I5ffIf12s2fI", body, tail_offset, "tick_chart tail")

        chart = MacTickChart(market=market, code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                            name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                            pre_close=pre_close, open=open, high=high, low=low, close=close, vol=int(vol),
                            amount=amount, turnover=turnover, avg=avg_tail, charts=ticks)
        rows: list[dict] = []
        for tick in chart.charts:
            rows.append(asdict(tick))
        return pd.DataFrame(rows)

    def get_tick_charts(self, market=Market.SH, code='600600', date: int = 20260629, days: int = 5) -> pd.DataFrame:
        """获取多日分时图（最多 5 天）        """
        pkg = build_mac_request(0x123E, struct.pack("<H22sIHH6x", int(market), code.encode("gbk"), date, days, 1))
        body = self._execute(pkg)
        (market, code_raw) = unpack_from("<H22s", body, 0, "tick_charts header")
        date_ints = unpack_from("<5I", body, 24, "tick_charts dates")
        pre_close_floats = unpack_from("<5f", body, 44, "tick_charts pre_closes")
        (count, send_last, page_size, total) = unpack_from("<HBHH", body, 64, "tick_charts header2")

        days: list[MacMultiTickDay] = []
        for d in range(count):
            ticks: list[MacTick] = []
            for t in range(page_size):
                index = d * page_size + t
                offset = 71 + index * 14
                (minutes, price, avg, vol, tick_reserved) = unpack_from("<HffHH", body, offset,
                                                                        f"tick_charts tick[{d}][{t}]")
                ticks.append(MacTick(time=Time(min(15,minutes // 60), minutes % 60), price=price, avg=avg, vol=vol))
            ymd = date_ints[d]
            day_date = date_cls(ymd // 10000, (ymd % 10000) // 100, ymd % 100)
            days.append(MacMultiTickDay(date=day_date, pre_close=pre_close_floats[d], ticks=ticks))
        tail_offset = 71 + count * page_size * 14
        (name_raw, _decimal, _category, _vol_unit, _date_raw, _time_raw, pre_close, open, high, low, close,
         _momentum, vol, amount, _tail_pad2, turnover, avg, _industry) = unpack_from("<44sBHf5x2I5ffIf12s2fI",
                                                                                     body, tail_offset,
                                                                                     "tick_charts tail")

        chart = MacMultiTickChart(market=market,
                                 code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                                 name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                                 pre_close=pre_close, open=open, high=high, low=low, close=close, vol=int(vol),
                                 amount=amount, turnover=turnover, avg=avg, charts=days)
        rows: list[dict] = []
        for day in chart.charts:
            for tick in day.ticks:
                d = asdict(tick)
                d["date"] = day.date
                d["pre_close"] = day.pre_close
                rows.append(d)
        return pd.DataFrame(rows)

    def get_chart_sampling(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取分时缩略采样价格点（240 个点）。        """
        pkg = build_mac_request(0x254D, struct.pack("<H22sHH9x", int(market), (code.encode("gbk") + b"\x00" * 22)[:22], 1, 20))
        body = self._execute(pkg)
        sz = 42
        prices: list[float] = []
        if len(body) >= sz:
            require_bytes(body, 0, sz, "ChartSamplingCmd header")
            count = unpack_from("<H", body, 40, "chart_sampling count")[0]
            for i in range(count):
                pos = sz + i * 4
                require_bytes(body, pos, 4, f"ChartSamplingCmd price[{i}]")
                (p,) = unpack_from("<f", body, pos, f"chart_sampling price[{i}]")
                prices.append(p)
        return pd.Series(prices)

    def get_transactions(self, market: int, code: str, count: int = 2000, start: int = 0, date: int = 0) -> pd.DataFrame:
        """获取逐笔成交数据（自动分页 """
        results: list[MacTransaction] = []
        for page in range(20):
            pkg = build_mac_request(0x122F, struct.pack("<H22sIIH10x", int(market), code.encode("gbk"), date, page * 1000, 1000))
            body = self._execute(pkg)
            count = unpack_from("<H", body, 29, "transaction count")[0]
            for i in range(count):
                offset = 39 + i * 18
                (time_sec, price, volume, trade_count, bs_flag) = unpack_from("<IfIIH", body, offset, f"transaction item[{i}]")
                results.append(MacTransaction(time=Time(time_sec // 3600, time_sec % 3600 // 60, time_sec % 60), price=price, vol=volume, trade_count=trade_count, bs_flag=bs_flag))
            if count < 1000:
                break
        return pd.DataFrame(results)

    def get_symbol_info(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取个股简要特征快照        """
        pkg = build_mac_request(0x122A, struct.pack("<H22sI12x", int(market), code.encode("gbk"), 1))
        body = self._execute(pkg)
        (market, code_raw, name_raw) = unpack_from("<H22s44s", body, 8, "symbol_info identity")
        (date_raw, time_raw, activity, pre_close, open, high, low, close, momentum, vol, amount, inside_volume,
         outside_volume) = unpack_from("<III5ffIfII", body, 96, "symbol_info core")
        (_decimal, _a, _b, _c, _vr, turnover, avg) = unpack_from("<HIf20xI3f", body, 148, "symbol_info extra")
        dt = datetime(date_raw // 10000, (date_raw % 10000) // 100, date_raw % 100, time_raw // 10000,
                      (time_raw % 10000) // 100, time_raw % 100)
        return MacSymbolInfo(market=market, code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                             name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""), time=dt,
                             activity=activity, pre_close=pre_close, open=open, high=high, low=low, close=close,
                             momentum=momentum, vol=int(vol), amount=amount, inside_volume=inside_volume,
                             outside_volume=outside_volume, turnover=turnover, avg=avg)


    def get_board_list(self, board_type: BoardType = BoardType.ALL) -> pd.DataFrame:
        """获取板块列表（自动分页） """
        results = []
        for page in range(100):
            pkg = build_mac_request(0x1231, struct.pack("<HHBBHH8x", 150, int(board_type), 0, 0, page * 150, 1))
            body = self._execute(pkg)
            count_all, total = unpack_from("<HH", body, 0, "board_list header")
            count = count_all // 2
            _RECORD_FMT = "<H6s16s44sfffH6s16s44sfff"
            _RECORD_SIZE = struct.calcsize(_RECORD_FMT)  # 160
            for i in range(count):
                offset = 4 + i * _RECORD_SIZE
                (market, code_raw, _pad1, name_raw, price, rise_speed, pre_close, symbol_market, symbol_code_raw,
                 _pad2, symbol_name_raw, symbol_price, symbol_rise_speed, symbol_pre_close) = unpack_from(
                    _RECORD_FMT, body, offset, f"board_list record[{i}]")
                results.append(
                    BoardInfo(market=market, code=code_raw.decode("gbk", errors="replace").rstrip("\x00"),
                              name=name_raw.decode("gbk", errors="replace").rstrip("\x00"), price=price,
                              rise_speed=rise_speed, pre_close=pre_close, symbol_market=symbol_market,
                              symbol_code=symbol_code_raw.decode("gbk", errors="replace").rstrip("\x00"),
                              symbol_name=symbol_name_raw.decode("gbk", errors="replace").rstrip("\x00"),
                              symbol_price=symbol_price, symbol_rise_speed=symbol_rise_speed,
                              symbol_pre_close=symbol_pre_close))
            if count < 150:
                break
        return pd.DataFrame(results)

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

        board_code = _convert_board_code(board_symbol)
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        offset = 0

        while fetched < count:
            page_size = min(count - fetched, 80)
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

    def get_belong_board(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取个股所属板块列表。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        pkg = build_mac_request(0x1218, struct.pack("<H8s16x21s", market, code.encode("gbk"), b"Stock_GLHQ"), head_flag=1)
        body = self._execute(pkg)
        json_bytes = body[27:]
        python_list: list[list[object]] = json.loads(json_bytes.decode("gbk", errors="replace"))
        results: list[BelongBoardInfo] = []
        def _to_float(value: object) -> float:
            try:
                return float(value)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                return 0.0
        for row in python_list:
            n = len(row)
            if n not in (9, 13):
                continue
            try:
                bt = int(row[0])
                mkt = int(row[1])
            except (ValueError, TypeError):
                bt = mkt = 0
            board_code = str(row[2])
            board_name = str(row[3])
            close = _to_float(row[4]) if n > 4 and row[4] else 0.0
            pre_close = _to_float(row[5]) if n > 5 and row[5] else 0.0
            results.append(
                BelongBoardInfo(board_type=bt, market=mkt, board_code=board_code, board_name=board_name,
                                close=close, pre_close=pre_close))
        return pd.DataFrame(results)

    def get_board_summary(self, board_symbol: str, sort_type: SortType = SortType.CHANGE_PCT, sort_order: SortOrder = SortOrder.DESC) -> dict:
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

        rows: list[dict] = []
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

        rows: list[dict] = []
        for _, row in boards_df.iterrows():
            board_code = str(row["code"])
            board_market = int(row["market"]) if "market" in row.index else 1
            try:
                kline_df = self.get_stock_kline(market=board_market, code=board_code, period=Period.DAILY, count=fetch_count, adjust=Adjust.NONE)
            except Exception:
                print("板块 %s K线获取失败，跳过", board_code)
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

    def get_capital_flow(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取个股资金流向        """
        pkg = build_mac_request(0x1218, struct.pack("<H8s16x21s", int(market), code.encode("gbk"), b"Stock_ZJLX"), head_flag=2)

        body = self._execute(pkg)
        json_bytes = body[27:]
        python_list: list[list[object]] = json.loads(json_bytes.decode("gbk"))

        if len(python_list) < 2:
            return None

        today_data = python_list[0]
        five_days_data = python_list[1]

        def _to_float(value: object) -> float:
            try:
                return float(value)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                return 0.0

        main_in = _to_float(today_data[0]) if len(today_data) > 0 else 0.0
        main_out = _to_float(today_data[1]) if len(today_data) > 1 else 0.0
        retail_in = _to_float(today_data[2]) if len(today_data) > 2 else 0.0
        retail_out = _to_float(today_data[3]) if len(today_data) > 3 else 0.0

        mid_net_5d = _to_float(five_days_data[4]) if len(five_days_data) > 4 else 0.0
        large_net_5d = _to_float(five_days_data[3]) if len(five_days_data) > 3 else 0.0

        return dict(main_in=main_in, main_out=main_out, main_net=main_in - main_out,
                               small_in=retail_in, small_out=retail_out, small_net=retail_in - retail_out,
                               mid_in=0.0, mid_out=0.0, mid_net=mid_net_5d, large_in=0.0, large_out=0.0,
                               large_net=large_net_5d)


    def get_auction(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取集合竞价数据        """
        items: list[AuctionItem] = []
        for page in range(10):
            pkg = build_mac_request(0x123D, struct.pack("<H22sII10x", int(market), code.encode("gbk"), page * 500, 500))
            body = self._execute(pkg)
            _market, _code, count = unpack_from("<H22sI", body, 0, "auction header")
            for i in range(count):
                offset = 36 + i * 16
                if offset + 16 > len(body):
                    break
                time_sec, price, matched, unmatched = unpack_from("<IfIi", body, offset, f"auction item[{i}]")
                items.append(AuctionItem(time=Time(time_sec // 3600, (time_sec % 3600) // 60, time_sec % 60), price=price, matched=matched, unmatched=unmatched))
            if count < 500:
                break
        return pd.DataFrame(items)

    def get_unusual(self, market: int = 0) -> pd.DataFrame:
        """个股异动"""
        dfs = []
        for page in range(100):
            body = self._execute(build_mac_request(0x1237, struct.pack("<HH2xH2xH5H", market % 3, page * 600, 600, 1, 200, 30, 40, 50, 200)))
            count = unpack_from("<H", body, 0, "unusual count")[0]
            results = []
            for i in range(count):
                offset = 2 + i * 32
                if offset + 32 > len(body):
                    break
                market, code_raw, _, unusual_type, _, index, _z = unpack_from("<H6sBBBHH", body, offset, f"unusual record[{i}]")
                data = body[offset + 15: offset + 28]
                desc = val = ''
                if len(data) >= 13:
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
                hour, minute_sec = unpack_from("<BH", body, offset + 29, f"unusual time[{i}]")
                results.append(Dot(index=index, market=market, code=code_raw.decode("gbk", errors="replace").rstrip("\x00"), name="", time=Time(hour, minute_sec // 100, minute_sec % 100), desc=desc, value=val, unusual_type=unusual_type))
            binary_length = 2 + count * 32
            text_bytes = body[binary_length:]
            text_list = text_bytes.decode("gbk", errors="ignore").strip(",").split(",")
            dfs.extend([dict(index=item.index, market=item.market, code=item.code, name=text_list[i] if i < len(text_list) else "", time=item.time, desc=item.desc, value=item.value, unusual_type=item.unusual_type) for i, item in enumerate(results)])
            if len(results) < 600:
                break
        return pd.DataFrame(dfs)

    def get_server_info(self) -> pd.DataFrame:
        """获取服务器交易时段信息。"""
        pkg = build_mac_request(0x120F, bytes.fromhex("04002d31") + b"\x00" * 8 + b"\x00\x27\x06\x0e" + b"\x00" * 52)
        body = self._execute(pkg)
        if len(body) < 87:
            return ServerSession(today="", last_trading_day="")
        pos = 0
        _count = unpack_from("<H", body, pos, "server_info count")[0]
        pos += 2
        pos += 8
        pos += 3
        pos += 9

        def _parse_date(p: int) -> tuple[str, int]:
            d = unpack_from("<I", body, p, "server_info date")[0]
            return f"{d // 10000}-{d % 10000 // 100:02d}-{d % 100:02d}", p + 4
        def _parse_session(p: int) -> tuple[list[dict[str, object]], int]:
            vals = unpack_from("<8H", body, p, "server_info session")
            sessions: list[dict[str, object]] = []
            for i in range(0, 8, 2):
                sessions.append({"open": f"{vals[i] // 60}:{vals[i] % 60:02d}", "close": f"{vals[i + 1] // 60}:{vals[i + 1] % 60:02d}", })
            return sessions, p + 16
        today, pos = _parse_date(pos)
        pos += 4  # ts1
        sessions_1, pos = _parse_session(pos)
        sessions_2, pos = _parse_session(pos)
        pos += 1  # flag byte
        last_trading_day, pos = _parse_date(pos)
        pos += 4  # ts2
        market_param_1 = 0
        market_param_2 = 0
        if pos + 8 <= len(body):
            market_param_1 = unpack_from("<I", body, pos, "server_info param1")[0]
            pos += 4
            market_param_2 = unpack_from("<I", body, pos, "server_info param2")[0]
        return ServerSession(today=today, last_trading_day=last_trading_day, sessions_1=sessions_1,
                             sessions_2=sessions_2, market_param_1=market_param_1,
                             market_param_2=market_param_2)

    def get_kline_offset(self) -> pd.DataFrame:
        """获取 K 线数据偏移信息。       """
        pkg = build_mac_request(0x124A, struct.pack("<II5x", 0, 128000))
        body = self._execute(pkg)
        return KlineOffsetInfo(total=0, returned=0) if len(body) < 8 else KlineOffsetInfo(total=struct.unpack(">I", body[:4])[0], returned=struct.unpack("<I", body[4:8])[0])

    def get_goods_list(self, market=ExMarket.HK_MAIN_BOARD) -> pd.DataFrame:
        """获取扩展市场（期货/期权等）商品列表。       """
        items: list[GoodsItem] = []
        for page in range(100):
            pkg = build_mac_request(0x2562, struct.pack("<HII", int(market), page * 1000, 1000))
            body = self._execute(pkg)
            _RECORD_SIZE = 48
            _RECORD_FMT = "<H23sHIBfffHH"
            require_bytes(body, 0, 2, "GoodsListCmd header")
            (total,) = unpack_from("<H", body, 0, "GoodsListCmd total")
            for i in range(total):
                offset = 2 + i * _RECORD_SIZE
                require_bytes(body, offset, _RECORD_SIZE, f"GoodsListCmd record[{i}]")
                category, raw_name, u, index, switch, v1, v2, v3, c1, c2 = unpack_from(_RECORD_FMT, body, offset, f"GoodsListCmd record[{i}]")
                name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
                items.append(GoodsItem(name=name, category=category, u=u, index=index, switch=switch, code=[v1, v2, v3], c1=c1, c2=c2))
            if total < 1000:
                break
        return pd.DataFrame(items)


class TdxClient(Client):
    def get_security_quotes(self, stocks: list[tuple[Market, str]]) -> pd.DataFrame:
        """批量获取实时五档行情（最多80只/次）。"""
        n = len(stocks)
        header = struct.pack("<HIHHIIHH", 0x010C, 0x02006320, n * 7 + 12, n * 7 + 12, 0x0005053E, 0, 0, n)
        body = bytearray(header)
        for market, code in stocks:
            body.extend(struct.pack("<B6s", int(market), code.encode("utf-8")))
        body = self._execute(bytes(body))
        pos = 0
        pos += 2
        (num,) = unpack_from("<H", body, pos, "security_quotes header")
        pos += 2
        results = []
        for _ in range(num):
            record_start = pos
            market_b, code_b, active1 = unpack_from("<B6sH", body, pos, "security_quotes record header")
            pos += 9
            price_raw, pos = get_price(body, pos)
            last_close_diff, pos = get_price(body, pos)
            open_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)
            unknown_0, pos = get_price(body, pos)
            unknown_1, pos = get_price(body, pos)
            vol, pos = get_price(body, pos)
            cur_vol, pos = get_price(body, pos)
            amount, _ = get_volume(body, pos)
            pos += 4

            s_vol, pos = get_price(body, pos)
            b_vol, pos = get_price(body, pos)

            unknown_2, pos = get_price(body, pos)  # IndexOpenAmount(指数)/舍入残差(个股)
            unknown_3, pos = get_price(body, pos)  # StockOpenAmount(个股)/负值(指数)

            # 五档买盘
            bid1_d, pos = get_price(body, pos)
            ask1_d, pos = get_price(body, pos)
            bv1, pos = get_price(body, pos)
            av1, pos = get_price(body, pos)

            bid2_d, pos = get_price(body, pos)
            ask2_d, pos = get_price(body, pos)
            bv2, pos = get_price(body, pos)
            av2, pos = get_price(body, pos)

            bid3_d, pos = get_price(body, pos)
            ask3_d, pos = get_price(body, pos)
            bv3, pos = get_price(body, pos)
            av3, pos = get_price(body, pos)

            bid4_d, pos = get_price(body, pos)
            ask4_d, pos = get_price(body, pos)
            bv4, pos = get_price(body, pos)
            av4, pos = get_price(body, pos)

            bid5_d, pos = get_price(body, pos)
            ask5_d, pos = get_price(body, pos)
            bv5, pos = get_price(body, pos)
            av5, pos = get_price(body, pos)
            (trading_status,) = unpack_from("<H", body, pos, "security_quotes tail flag")
            pos += 2
            unknown_5, pos = get_price(body, pos)
            unknown_6, pos = get_price(body, pos)
            unknown_7, pos = get_price(body, pos)
            unknown_8, pos = get_price(body, pos)
            rise_speed_raw, active2 = unpack_from("<hH", body, pos, "security_quotes tail")
            pos += 4
            p = price_raw / 100.0
            results.append(dict(code=code_b.decode("utf-8").rstrip("\x00"), price=p,
                 pre_close=(price_raw + last_close_diff) / 100.0,
                 open=(price_raw + open_diff) / 100.0,
                 high=(price_raw + high_diff) / 100.0,
                 low=(price_raw + low_diff) / 100.0, vol=float(vol),
                 cur_vol=float(cur_vol), amount=amount, s_vol=float(s_vol),
                 b_vol=float(b_vol), active1=active1, active2=active2,
                 bid1=(price_raw + bid1_d) / 100.0, bid_vol1=float(bv1),
                 bid2=(price_raw + bid2_d) / 100.0, bid_vol2=float(bv2),
                 bid3=(price_raw + bid3_d) / 100.0, bid_vol3=float(bv3),
                 bid4=(price_raw + bid4_d) / 100.0, bid_vol4=float(bv4),
                 bid5=(price_raw + bid5_d) / 100.0, bid_vol5=float(bv5),
                 ask1=(price_raw + ask1_d) / 100.0, ask_vol1=float(av1),
                 ask2=(price_raw + ask2_d) / 100.0, ask_vol2=float(av2),
                 ask3=(price_raw + ask3_d) / 100.0, ask_vol3=float(av3),
                 ask4=(price_raw + ask4_d) / 100.0, ask_vol4=float(av4),
                 ask5=(price_raw + ask5_d) / 100.0, ask_vol5=float(av5),
                 rise_speed=rise_speed_raw / 100.0, limit_up=None, limit_down=None,
                 unknown_2=unknown_2, unknown_3=unknown_3, unknown_5=unknown_5,
                 unknown_6=unknown_6, unknown_7=unknown_7, unknown_8=unknown_8,
                 server_time=_format_server_time(unknown_0),
                 trading_status=trading_status, open_amount=unknown_3 * 100.0))
        return pd.DataFrame(results)

    def get_price_limits(self, market: Market, code: str, name: str, pre_close: float) -> tuple[float, float]:
        """按当前交易状态计算涨跌停价。
        对上市初期不设涨跌幅限制的标的，会先用日 K 线条数估算已上市交易天数。
        """
        return compute_price_limits(market, code, name, pre_close)

    def get_security_bars(self, market=Market.SH, code='600600', category=KlineCategory.DAY) -> pd.DataFrame:
        """获取 K 线数据（最多800条/次，按 start 分页）。"""
        bars: list[SecurityBar] = []
        for page in range(30):
            pkg = struct.pack("<HIHHHH6sHHHHIIH", 0x010C, 0x01016408, 0x001C, 0x001C, 0x052D, int(market), code.encode("utf-8"), int(category), 1, page * 800, 800, 0, 0, 0)
            body = self._execute(pkg)
            ret_count = unpack_from("<H", body, 0, "security_bars header")[0]
            pos = 2
            pre_diff_base = 0
            cat = int(category)
            for _ in range(ret_count):
                record_start = pos
                year, month, day, hour, minute, pos = get_datetime(cat, body, pos)
                open_diff, pos = get_price(body, pos)
                close_diff, pos = get_price(body, pos)
                high_diff, pos = get_price(body, pos)
                low_diff, pos = get_price(body, pos)

                vol, pos = get_volume(body, pos)
                amount, pos = get_volume(body, pos)
                open_abs = open_diff + pre_diff_base
                close_abs = open_abs + close_diff
                high_abs = open_abs + high_diff
                low_abs = open_abs + low_diff
                pre_diff_base = open_abs + close_diff
                bars.append(dict(open=open_abs / 1000.0, close=close_abs / 1000.0, high=high_abs / 1000.0,
                                        low=low_abs / 1000.0, vol=vol, amount=amount, date=datetime(year=year, month=month,
                                        day=day, hour=hour, minute=minute)))
            if ret_count < 800:
                break
        return pd.DataFrame(bars)

    def get_index_bars(self, market=Market.SH, code='000001', category=KlineCategory.DAY, start=0, count: int = 800) -> pd.DataFrame:
        """获取指数 K 线数据。"""
        pkg = struct.pack("<HIHHHH6sHHHHIIH", 0x010C, 0x01016408, 0x001C, 0x001C, 0x052D, int(market), code.encode('utf8'), int(category), 1, start, count, 0, 0, 0)
        body = self._execute(pkg)
        ret_count = unpack_from("<H", body, 0, "security_bars header")[0]
        pos = 2
        bars: list[SecurityBar] = []
        pre_diff_base = 0
        cat = int(category)
        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(cat, body, pos)
            open_diff, pos = get_price(body, pos)
            close_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)
            vol, pos = get_volume(body, pos)
            amount, pos = get_volume(body, pos)
            pos += 4
            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = open_abs + close_diff
            bars.append(dict(open=open_abs / 1000.0, close=close_abs / 1000.0, high=high_abs / 1000.0,
                                    low=low_abs / 1000.0, vol=vol, amount=amount, date=datetime(year=year, month=month,
                                    day=day, hour=hour, minute=minute)))
        return pd.DataFrame(bars)

    def get_history_minute_time_data(self, market=Market.SH, code='600600', date=0) -> pd.DataFrame:
        """获取历史某日分时数据（date: YYYYMMDD）0代表今天 """
        date = date or int(datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"))
        pkg = bytes.fromhex("0c013000010 10d000d00b40f".replace(" ", "")) + struct.pack("<IB6s", date, int(market), code.encode("utf-8"))
        bars = _parse_minute_body(self._execute(pkg), skip=6)
        df = pd.DataFrame(bars)
        base = pd.Timestamp(year=date // 10000, month=(date // 100) % 100, day=date % 100)
        offsets = pd.to_timedelta((list(range(9 * 60 + 30, 9 * 60 + 30 + 120)) + list(range(13 * 60, 13 * 60 + 120)))[:len(df)], unit="m")
        df["date"] = base + offsets
        return df

    def get_transaction_data(self, market=Market.SH, code='600600', page=0) -> pd.DataFrame:
        """获取当日逐笔成交（分页）。"""
        pkg = bytes.fromhex("0c170801010 10e000e00c50f".replace(" ", "")) + struct.pack("<H6sHH", int(market), code.encode("utf-8"), page * 800, 800)
        df = _parse_transaction_body(self._execute(pkg))
        return pd.DataFrame(df)

    def get_history_transaction_data(self, market=Market.SH, code='600600', date=20260629, start=0) -> pd.DataFrame:
        """获取历史逐笔成交（date: YYYYMMDD，分页）。"""
        pkg = bytes.fromhex("0c013001000112001200b50f".replace(" ", "")) + struct.pack("<IH6sHH", date, int(market), code.encode("utf-8"), start, 800)
        body = self._execute(pkg)
        num = unpack_from("<H", body, 0, "history_transaction header")[0]
        pos = 6
        last_price = 0
        records = []
        for _ in range(num):
            record_start = pos
            hour, minute, pos = get_time(body, pos)
            price_diff, pos = get_price(body, pos)
            vol, pos = get_price(body, pos)
            buyorsell, pos = get_price(body, pos)  # 历史无 num_orders
            unknown_last, pos = get_price(body, pos)
            last_price += price_diff
            records.append(TransactionRecord(hour=hour, minute=minute, price=last_price / 100.0, vol=vol, buyorsell=buyorsell, unknown_last=unknown_last, _raw=body[record_start:pos]))
        return records

    def get_xdxr_info(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取除权除息历史记录。"""
        pkg = bytes.fromhex("0c1f18760001 0b000b000f000100".replace(" ", "")) + struct.pack("<B6s", int(market), code.encode("utf-8"))
        body = self._execute(pkg)
        XDXR_CATEGORY_NAMES: dict[int, str] = {
            1: "除权除息", 2: "送配股上市", 3: "非流通股上市", 4: "未知股本变动", 5: "股本变化", 6: "增发新股",
            7: "股份回购", 8: "增发新股上市", 9: "转配股上市", 10: "可转债上市", 11: "扩缩股",
            12: "非流通股缩股",
            13: "送认购权证", 14: "送认沽权证", }

        pos = 9  # 跳过9字节（market+code+未知）
        num = unpack_from("<H", body, pos, "xdxr_info header")[0]
        pos += 2

        records: list[XdxrRecord] = []

        for _ in range(num):
            record_start = pos

            # Bug #1 修复：从当前 pos 读，而非 body[:7]
            market_b, code_b = unpack_from("<B6s", body, pos, "xdxr_info record header")
            pos += 7
            slice_bytes(body, pos, 1, "xdxr_info record padding")
            pos += 1  # 跳过1个未知字节

            year, month, day, _hour, _min, pos = get_datetime(9, body, pos)
            category = unpack_from("<B", body, pos, "xdxr_info category")[0]
            pos += 1

            chunk = slice_bytes(body, pos, 16, "xdxr_info record body")
            pos += 16
            rec = Dot(code=code_b.decode("utf-8").rstrip("\x00"), date=datetime(year=year, month=month,
                             day=day), category=category, name=XDXR_CATEGORY_NAMES.get(category, str(category)))

            if category == 1:
                fenhong, peigujia, songzhuangu, peigu = struct.unpack("<ffff", chunk)
                rec.fenhong = _normalize_per_10_shares(fenhong)
                rec.peigujia = peigujia
                rec.songzhuangu = _normalize_per_10_shares(songzhuangu)
                rec.peigu = _normalize_per_10_shares(peigu)
            elif category in (11, 12):
                _, _, suogu, _ = struct.unpack("<IIfI", chunk)
                rec.suogu = suogu
            elif category in (13, 14):
                xingquanjia, _, fenshu, _ = struct.unpack("<fIfI", chunk)
                rec.xingquanjia = xingquanjia
                rec.fenshu = fenshu
            else:
                # 股本变动类：4个 uint32，代表前后流通/总股本
                ql_raw, qz_raw, hl_raw, hz_raw = struct.unpack("<IIII", chunk)
                rec.panqian_liutong = _decode_share_count(ql_raw)
                rec.qian_zongguben = _decode_share_count(qz_raw)
                rec.panhou_liutong = _decode_share_count(hl_raw)
                rec.hou_zongguben = _decode_share_count(hz_raw)

            records.append(dict(rec))

        return pd.DataFrame(records)

    def get_finance_info(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取最新财务数据。"""
        pkg = bytes.fromhex("0c1f18760001 0b000b001000 0100".replace(" ", "")) + struct.pack("<B6s", int(market), code.encode("utf-8"))
        body = self._execute(pkg)
        fmt = "<fHHII" + "f" * 30
        keys = ['流通股本', '省份', '行业', '更新日期', '上市日期', '总股本', '国家股', '发起人法人股', '法人股', 'B股', 'H股', '职工股', '总资产', '流动资产', '固定资产', '无形资产', '股东人数', '流动负债', '长期负债', '资本公积金', '净资产', '主营收入',
                '主营利润', '应收账款', '营业利润', '投资收益', '经营现金流', '总现金流', '存货', '利润总额', '税后利润', '净利润', '未分配利润', '每股净资产', '保留']
        return dict(zip(keys, struct.unpack(fmt, slice_bytes(body, 9, struct.calcsize(fmt), "finance_info body"))))

    def get_company_info_category(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取公司信息文件目录。"""
        pkg = bytes.fromhex("0c0f109b00010e000e00cf02".replace(" ", "")) + struct.pack("<H6sI", int(market), code.encode('utf8'), 0)
        body = self._execute(pkg)
        num = unpack_from("<H", body, 0, "company_info_category header")[0]
        pos = 2
        results = []
        _RECORD_SIZE = 152
        for _ in range(num):
            raw = slice_bytes(body, pos, _RECORD_SIZE, "company_info_category record")
            name_b, filename_b, start, length = struct.unpack("<64s80sII", raw)
            pos += _RECORD_SIZE
            nul = name_b.find(b"\x00")
            results.append(dict(name=(name_b[:nul] if nul != -1 else name_b).decode("gbk", errors="replace"), filename=f'{code}.txt', start=start, length=length))
        return pd.DataFrame(results)

    def get_company_info_content(self, market=Market.SH, code='600600') -> str:
        """读取公司信息文本。"""
        pkg = bytes.fromhex("0c07109c0001680068 00d002".replace(" ", "")) + struct.pack("<H6sH80sIII", int(market), code.encode("utf-8"), 0, (f'{code}.txt'.encode("gbk") + b"\x00" * 80)[:80], 0, 100000, 0)
        body = self._execute(pkg)
        _, length = unpack_from("<10sH", body, 0, "company_info_content header")
        content = slice_bytes(body, 12, length, "company_info_content body")
        return content.decode("gbk", errors="replace")

    def get_block_info(self) -> pd.DataFrame:
        """获取并解析板块文件（行业、概念、风格等   """
        results = []
        for name in ['zs', 'gn', 'fg']:
            name = f'block_{name}.dat'
            body = self._execute(bytes.fromhex("0c39186900012a002a00c502") + (name.encode("ascii") + b"\x00" * 40)[:40])
            size, _, hash_b, _ = struct.unpack("<I1s32s1s", body[:38])
            full_data = bytearray()
            pos = 0
            chunk_size = 30000
            while pos < size:
                pkg = bytes.fromhex("0c37186a00016e006e00b906") + struct.pack("<II", pos, chunk_size) + (name.encode("ascii") + b"\x00" * 100)[:100]
                body = self._execute(pkg)
                if len(body) < 4:
                    break
                full_data.extend(body[4:])
                pos += len(body[4:])
            data = bytes(full_data)
            if len(data) < 386:
                continue
            pos = 384
            count = struct.unpack("<H", data[pos: pos + 2])[0]
            pos += 2
            for _ in range(count):
                if len(data) < pos + 2813:
                    break
                name_b = data[pos: pos + 9]
                stock_count, _type = struct.unpack("<HH", data[pos + 9: pos + 13])
                name = name_b.decode("gbk", errors="replace").strip("\x00")
                codes: list[str] = []
                codes_start = pos + 13
                actual_count = min(stock_count, 400)
                for i in range(actual_count):
                    c_start = codes_start + i * 7
                    c_raw = data[c_start: c_start + 7]
                    code = c_raw.decode("ascii", errors="replace").strip("\x00")
                    if code:
                        codes.append(code)
                results.append(dict(name=name, count=stock_count, codes=codes))
                pos += 2813
        return pd.DataFrame(results)

    def get_market_stat(self) -> pd.DataFrame:
        # 通达信中 880005 是全市场行情统计，880001 是总市值指数，880006 是涨跌停统计
        quotes = self.get_security_quotes([(Market.SH, "880005"), (Market.SH, "880001"), (Market.SH, "880006")])
        q = quotes.iloc[0]
        up = int(q.price)
        down = int(q.open)
        neutral = int(q.low)
        total = int(q.high)
        market_cap = quotes.iloc[1].price * 1e10
        limit_down = int(quotes.iloc[2].open)
        limit_up = int(quotes.iloc[2].price)
        return dict(up_count=up, down_count=down, neutral_count=neutral, suspended_count=max(0, total - up - down - neutral), total_count=total, total_amount=q.amount, total_volume=q.vol, total_market_cap=market_cap, limit_up_count=limit_up, limit_down_count=limit_down)

    def _collect_transaction_records(self, fetch_page: Callable[[int, int], list[TransactionRecord]], max_start: int = 10000) -> list[TransactionRecord]:
        all_recs: list[TransactionRecord] = []
        seen_sig: set[tuple[int, int, float, int, int, int]] = set()
        seen_page_sigs: set[
            tuple[
                tuple[int, int, float, int, int, int], tuple[int, int, float, int, int, int], ]
        ] = set()
        start = 0

        while start < max_start:
            recs = fetch_page(start)
            if not recs:
                break

            page_sig = _page_signature(recs)
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            new_count = 0
            for record in recs:
                sig = _record_signature(record)
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    all_recs.append(record)
                    new_count += 1

            if new_count == 0:
                break

            start += len(recs)
            if len(recs) < 100:
                break

        return all_recs

    def get_fund_flow(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        records = self._collect_transaction_records(lambda start: _parse_transaction_body(self._execute(bytes.fromhex("0c170801010 10e000e00c50f".replace(" ", "")) + struct.pack("<H6sHH", int(market), code.encode("utf-8"), start, 800))))
        return _to_df(_classify_fund_flow(records))

    def get_history_fund_flow(self, market=Market.SH, code='600600') -> pd.DataFrame:
        """获取个股历史日线资金流向序列 """
        bars = self.get_security_bars(market, code, KlineCategory.DAY)
        results = []
        for i, bar in bars.T.items():
            date = bar.year * 10000 + bar.month * 100 + bar.day
            records = self._collect_transaction_records(lambda page_start: self.get_history_transaction_data(market, code, date, page_start))
            flow = _classify_fund_flow(records)
            year = date // 10000
            month = (date // 100) % 100
            day = date % 100
            res = dict(date=datetime(year=year, month=month, day=day), super_in=flow.super_in,
                                      super_out=flow.super_out, large_in=flow.large_in, large_out=flow.large_out,
                                      medium_in=flow.medium_in, medium_out=flow.medium_out, small_in=flow.small_in,
                                      small_out=flow.small_out)

            results.append(res)
        return _to_df(results)


class ExTdxClient(Client):
    def __init__(self, host: str = None):
        self._host = host or config.get("best_ex_host") or self.from_best_host()
        self._conn = ExTdxConnection(self._host)

    @classmethod
    def from_best_host(cls, hosts: list = None, port=7709, pkg=None):
        super(ExTdxClient, cls).from_best_host(config.get("ex_hosts"), 7727, bytes.fromhex("01 03 48 66 00 01 02 00 02 00 f0 23"))

    def get_markets(self) -> list[ExMarketInfo]:
        """获取扩展行情支持的市场列表。"""
        pkg = bytes.fromhex("01 02 48 69 00 01 02 00 02 00 f4 23")
        body = self._execute(pkg)
        results: list[ExMarketInfo] = []
        if len(body) >= 2:
            count = unpack_from("<H", body, 0, "ex markets count")[0]
            pos = 2
            for _ in range(count):
                if pos + 64 > len(body):
                    break
                raw = body[pos: pos + 64]
                (category, raw_name, market, raw_short_name) = struct.unpack("<B32sB2s", raw[:36])
                pos += 64
                if category == 0 and market == 0:
                    continue
                name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
                short_name = raw_short_name.decode("gbk", errors="replace").rstrip("\x00")
                results.append(
                    ExMarketInfo(market=market, category=category, name=name, short_name=short_name))
        return results


    def get_instrument_count(self) -> int:
        """获取扩展行情商品总数。"""
        return self._execute(GetExInstrumentCountCmd())

    def get_instrument_info(self, start: int, count: int = 100) -> list[ExInstrumentInfo]:
        """获取商品信息列表（分页）。"""
        return self._execute(GetExInstrumentInfoCmd(start, count))

    def get_instrument_quote(self, market=Market.SH, code='600600') -> ExInstrumentQuote:
        """获取单个商品五档实时行情。"""
        pkg = bytes.fromhex("01 01 08 02 02 01 0c 00 0c 00 fa 23") + struct.pack("<B9s", int(market), code.encode("utf-8"))
        body = self._execute(pkg)
        if len(body) < 150:
            return None
        pos = 0
        (market, raw_code) = struct.unpack("<B9s", body[pos: pos + 10])
        pos += 10
        pos += 4  # skip 4 unknown bytes
        record_start = pos - 14
        (pre_close, open_price, high, low, price, kaicang, _unk1, zongliang, xianliang, _unk2, neipan, waipan,
         _unk3, chicang, b1, b2, b3, b4, b5, bv1, bv2, bv3, bv4, bv5, a1, a2, a3, a4, a5, av1, av2, av3, av4,
         av5) = struct.unpack("<fffffIIIIIIIIIfffffIIIIIfffffIIIII", body[pos: pos + 136])
        code = raw_code.decode("utf-8", errors="replace").rstrip("\x00")
        return ExInstrumentQuote(market=market, code=code, pre_close=pre_close, open=open_price, high=high,
                                 low=low, price=price, kaicang=kaicang, zongliang=zongliang,
                                 xianliang=xianliang, neipan=neipan, waipan=waipan, chicang=chicang, bid1=b1,
                                 bid2=b2, bid3=b3, bid4=b4, bid5=b5, bid_vol1=bv1, bid_vol2=bv2, bid_vol3=bv3,
                                 bid_vol4=bv4, bid_vol5=bv5, ask1=a1, ask2=a2, ask3=a3, ask4=a4, ask5=a5,
                                 ask_vol1=av1, ask_vol2=av2, ask_vol3=av3, ask_vol4=av4, ask_vol5=av5,
                                 _raw=body[record_start: pos + 136])


    def get_instrument_quote_list(self, market=Market.SH, category=KlineCategory.DAY, start: int = 0, count: int = 80) -> list[OrderedDict[str, object]]:
        """按类别获取商品行情列表。"""
        pkg = bytes.fromhex("01 c1 06 0b 00 02 0b 00 0b 00 00 24") + struct.pack("<BHHHH", int(market), 0, start, count, 1)
        body = self._execute(pkg)
        if len(body) < 2:
            return []

        def _parse_futures(market: int, code: str, body: bytes, pos: int,
                           results: list[OrderedDict[str, object]]) -> int:
            if pos + 140 > len(body):
                return pos + 290
            (
                bi_shu, zuo_jie, jin_kai, zui_gao, zui_di, mai_chu, kai_cang, _unk1, zong_liang, xian_liang, zong_jin_e,
                nei_pan, wai_pan, _unk2, chi_cang_liang, mai_ru_jia, _u1, _u2, _u3, _u4, mai_ru_liang, _u5, _u6, _u7,
                _u8, mai_chu_jia, _u9, _u10, _u11, _u12, mai_chu_liang, _u13, _u14, _u15) = struct.unpack(
                "<IfffffIIIIfIIfIfIIIIIIIIIfIIIIIIIII", body[pos: pos + 140])
            pos += 290
            results.append(OrderedDict([
                ("market", market), ("code", code), ("BiShu", bi_shu), ("ZuoJie", zuo_jie), ("JinKai", jin_kai),
                ("ZuiGao", zui_gao), ("ZuiDi", zui_di), ("MaiChu", mai_chu), ("KaiCang", kai_cang),
                ("ZongLiang", zong_liang), ("XianLiang", xian_liang), ("ZongJinE", zong_jin_e), ("NeiPan", nei_pan),
                ("WaiPan", wai_pan), ("ChiCangLiang", chi_cang_liang), ("MaiRuJia", mai_ru_jia),
                ("MaiRuLiang", mai_ru_liang), ("MaiChuJia", mai_chu_jia), ("MaiChuLiang", mai_chu_liang), ]))
            return pos

        def _parse_hk_stocks(market: int, code: str, body: bytes, pos: int,
                             results: list[OrderedDict[str, object]]) -> int:
            if pos + 140 > len(body):
                return pos + 290
            (huo_yue_du, zuo_shou, jin_kai, zui_gao, zui_di, xian_jia, _unk1, mai_ru_jia, zong_liang, xian_liang,
             zong_jin_e, _unk2, _unk3, nei, wai, mrj1, mrj2, mrj3, mrj4, mrj5, mrl1, mrl2, mrl3, mrl4, mrl5, mcj1,
             mcj2, mcj3, mcj4, mcj5, mcl1, mcl2, mcl3, mcl4, mcl5) = struct.unpack(
                "<IfffffIfIIfIIIIfffffIIIIIfffffIIIII", body[pos: pos + 140])
            pos += 290
            results.append(OrderedDict([
                ("market", market), ("code", code), ("HuoYueDu", huo_yue_du), ("ZuoShou", zuo_shou),
                ("JinKai", jin_kai), ("ZuiGao", zui_gao), ("ZuiDi", zui_di), ("XianJia", xian_jia),
                ("MaiRuJia", mai_ru_jia), ("ZongLiang", zong_liang), ("XianLiang", xian_liang),
                ("ZongJinE", zong_jin_e), ("Nei", nei), ("Wai", wai), ("MaiRuJia1", mrj1), ("MaiRuJia2", mrj2),
                ("MaiRuJia3", mrj3), ("MaiRuJia4", mrj4), ("MaiRuJia5", mrj5), ("MaiRuLiang1", mrl1),
                ("MaiRuLiang2", mrl2), ("MaiRuLiang3", mrl3), ("MaiRuLiang4", mrl4), ("MaiRuLiang5", mrl5),
                ("MaiChuJia1", mcj1), ("MaiChuJia2", mcj2), ("MaiChuJia3", mcj3), ("MaiChuJia4", mcj4),
                ("MaiChuJia5", mcj5), ("MaiChuLiang1", mcl1), ("MaiChuLiang2", mcl2), ("MaiChuLiang3", mcl3),
                ("MaiChuLiang4", mcl4), ("MaiChuLiang5", mcl5), ]))
            return pos
        (num,) = struct.unpack("<H", body[0:2])
        pos = 2
        results: list[OrderedDict[str, object]] = []
        for _ in range(num):
            if pos + 10 > len(body):
                break
            (market, raw_code) = struct.unpack("<B9s", body[pos: pos + 10])
            code = raw_code.strip(b"\x00").decode("gbk", errors="replace")
            pos += 10
            if category == 3:
                pos = _parse_futures(market, code, body, pos, results)
            elif category == 2:
                pos = _parse_hk_stocks(market, code, body, pos, results)
            else:
                raise Exception(f"不支持的扩展行情类别: {self.category}")
        return results

    def get_instrument_bars(self, category=KlineCategory.DAY, market=Market.SH, code='600600') -> list[ExInstrumentBar]:
        """获取K线数据（扩展行情版本，支持期货/港股等）。"""
        results: list[ExInstrumentBar] = []
        for page in range(10):
            pkg = bytes.fromhex("01 01 08 6a 01 01 16 00 16 00 ff 23") + struct.pack("<B9sHHIH", int(market), code.encode("utf-8"), category, 1, page * 700, 700)
            body = self._execute(pkg)
            pos = 18
            if pos + 2 <= len(body):
                ret_count = struct.unpack("<H", body[pos: pos + 2])[0]
                pos += 2
                for _ in range(ret_count):
                    record_start = pos
                    year, month, day, hour, minute, pos = get_datetime(category, body, pos)
                    if pos + 28 > len(body):
                        break
                    (open_p, high, low, close_p, position, trade, _price) = struct.unpack("<ffffIIf",
                                                                                          body[pos: pos + 28])
                    (amount,) = struct.unpack("<f", body[pos + 16: pos + 20])
                    pos += 28
                    results.append(
                        ExInstrumentBar(open=open_p, high=high, low=low, close=close_p, position=position, trade=trade,
                                        amount=amount, year=year, month=month, day=day, hour=hour, minute=minute,
                                        _raw=body[record_start:pos]))
                if ret_count < 700:
                    break
        return pd.DataFrame(results)

    def get_history_instrument_bars_range(self, market=Market.SH, code='600600', start_date=20250101, end_date=20500101) -> list[ExInstrumentBar]:
        """按日期范围获取历史K线。"""
        if not hasattr(self, '_seqid'):
            self._seqid = 1
        pkg = bytearray.fromhex("01")
        pkg.extend(struct.pack("<B", self._seqid))
        self._seqid += 1
        pkg.extend(bytearray.fromhex("38 92 00 01 16 00 16 00 0D 24"))
        pkg.extend(struct.pack("<B9s", int(market), code.encode("utf-8")))
        pkg.extend(bytearray.fromhex("07 00"))
        pkg.extend(struct.pack("<II", start_date, end_date))
        body = self._execute(bytes(pkg))
        pos = 12
        if pos + 2 <= len(body):
            (ret_count,) = struct.unpack("<H", body[pos: pos + 2])
            pos += 2
            results: list[ExInstrumentBar] = []
            for _ in range(ret_count):
                if pos + 32 > len(body):
                    break
                record_start = pos
                (d1, d2, open_p, high, low, close_p, position, trade, settlement) = struct.unpack("<HHffffIIf", body[pos: pos + 32])
                pos += 32
                year = d1 // 2048 + 2004
                month = (d1 % 2048) // 100
                day = (d1 % 2048) % 100
                hour, minute = d2 // 60, d2 % 60
                results.append(
                    ExInstrumentBar(open=open_p, high=high, low=low, close=close_p, position=position, trade=trade,
                                    amount=settlement, year=year, month=month, day=day, hour=hour, minute=minute,
                                    _raw=body[record_start:pos]))
            return pd.DataFrame(results)


    def get_minute_time_data(self, market: int, code: str) -> list[ExMinuteBar]:
        """获取当日分时行情数据。"""
        pkg = bytes.fromhex("01 07 08 00 01 01 0c 00 0c 00 0b 24") + struct.pack("<B9s", int(market), code.encode("utf-8"))
        body = self._execute(pkg)
        results: list[ExMinuteBar] = []
        if len(body) >= 12:
            pos = 0
            (market, raw_code, num) = struct.unpack("<B9sH", body[pos: pos + 12])
            pos += 12
            for _ in range(num):
                if pos + 18 > len(body):
                    break
                record_start = pos
                (raw_time, price, avg_price, volume, amount) = struct.unpack("<HffII", body[pos: pos + 18])
                pos += 18
                hour = raw_time // 60
                minute = raw_time % 60
                results.append(
                    ExMinuteBar(hour=hour, minute=minute, price=price, avg_price=avg_price, volume=volume,
                                open_interest=amount, _raw=body[record_start:pos]))
        return results


    def get_history_minute_time_data(self, market: int, code: str, date: int) -> list[ExMinuteBar]:
        """获取历史某日分时行情数据（date: YYYYMMDD）。"""
        pkg = bytes.fromhex("01 01 30 00 01 01 10 00 10 00 0c 24") + struct.pack("<IB9s", date, int(market), code.encode("utf-8"))
        body = self._execute(pkg)
        results: list[ExMinuteBar] = []
        if len(body) >= 20:
            pos = 0
            (_market, _code, _unk, num) = struct.unpack("<B9s8sH", body[pos: pos + 20])
            pos += 20
            for _ in range(num):
                if pos + 18 > len(body):
                    break
                (raw_time, price, avg_price, volume, amount) = struct.unpack("<HffII", body[pos: pos + 18])
                pos += 18
                hour = raw_time // 60
                minute = raw_time % 60
                results.append(ExMinuteBar(hour=hour, minute=minute, price=price, avg_price=avg_price, volume=volume, open_interest=amount))
        return results

    def get_transaction_data(self, market: int, code: str, start: int = 0, count: int = 1800) -> list[ExTransactionRecord]:
        """获取当日分笔成交数据。"""
        results: list[ExTransactionRecord] = []
        for page in range(20):
            pkg = bytes.fromhex("01 01 08 00 03 01 12 00 12 00 fc 23") + struct.pack("<B9siH", int(market), code.encode("utf-8"), page * 1800, 1800)
            body = self._execute(pkg)
            if len(body) < 16:
                break
            pos = 0
            (_market, _code, _unk, num) = struct.unpack("<B9s4sH", body[pos: pos + 16])
            pos += 16
            for _ in range(num):
                if pos + 16 > len(body):
                    break
                record_start = pos
                (raw_time, price, volume, zengcang, direction) = struct.unpack("<HIIiH", body[pos: pos + 16])
                pos += 16
                hour = raw_time // 60
                minute = raw_time % 60
                second = direction % 10000
                if second > 59:
                    second = 0
                nature = direction // 10000
                results.append(
                    ExTransactionRecord(hour=hour, minute=minute, second=second, price=price, volume=volume,
                                        zengcang=zengcang, nature=nature, _raw=body[record_start:pos]))
            if num < 1800:
                break
        return results


    def get_history_transaction_data(self, market: int, code: str, date: int) -> list[ExTransactionRecord]:
        """获取历史某日分笔成交数据（date: YYYYMMDD）。"""
        results = []
        for page in range(30):
            pkg = bytes.fromhex("01 01 30 00 02 01 16 00 16 00 06 24") + struct.pack("<IB9siH", date, int(market), code.encode("utf-8"), page * 1800, 1800)
            body = self._execute(pkg)
            if len(body) < 16:
                break
            pos = 0
            (_market, _code, _unk, num) = struct.unpack("<B9s4sH", body[pos: pos + 16])
            pos += 16
            for _ in range(num):
                if pos + 16 > len(body):
                    break
                record_start = pos
                (raw_time, price, volume, zengcang, direction) = struct.unpack("<HIIiH", body[pos: pos + 16])
                pos += 16
                hour = raw_time // 60
                minute = raw_time % 60
                second = direction % 10000
                if second > 59:
                    second = 0
                nature = direction // 10000
                results.append(
                    ExTransactionRecord(hour=hour, minute=minute, second=second, price=price, volume=volume,
                                        zengcang=zengcang, nature=nature, _raw=body[record_start:pos]))
            if num < 1800:
                break
        return results


class MacExClient(Client):
    """同步 MAC 协议扩展市场客户端（期货/港股/美股，端口 7727）。
        with MacExClient() as c:
            df = c.goods_kline(ExMarket.CFFEX_FUTURES, "IFL0", Period.DAILY)
            df = c.goods_quotes([(ExMarket.HK_MAIN_BOARD, "00700")])
    """
    def __init__(self, host: str = None):
        self._host = host or config.get("best_mac_ex_host") or self.from_best_host()
        self._conn = ExTdxConnection(self._host, mac_ex_mode=True)

    @classmethod
    def from_best_host(cls, hosts: list = None, port=7709, pkg=None):
        super(MacExClient, cls).from_best_host(config.get("mac_ex_hosts"), 7727, bytes.fromhex("01 03 48 66 00 01 02 00 02 00 f0 23"))

    def goods_count(self, market: int = None) -> int:
        """获取商品总数。market=None 时返回全市场总数，否则返回指定市场的数量。"""
        if market is None:
            return self._execute(GetExInstrumentCountCmd())
        # 需要二分查找定位市场边界来计数
        offset = self._find_market_offset(market)
        if offset < 0:
            return 0
        total = self._execute(GetExInstrumentCountCmd())
        # 从 offset 开始扫描计数
        n = 0
        page = 1000
        pos = offset
        while pos < total:
            batch = self._execute(GetExInstrumentInfoCmd(start=pos, count=page))
            if not batch:
                break
            for item in batch:
                if item.market == market:
                    n += 1
                elif item.market > market:
                    return n
            pos += page
        return n

    def goods_list(self, market: int, start: int = 0, count: int = 600) -> pd.DataFrame:
        """获取扩展市场商品列表（期货合约/港股/美股等）。

        通过 EX 协议的 GetInstrumentInfo 命令获取，按 market 过滤。

        Parameters
        ----------
        market : int
            ExMarket 枚举值，如 ExMarket.HK_MAIN_BOARD。
        start : int
            市场内起始偏移。
        count : int
            请求数量。
        """
        offset = self._find_market_offset(market)
        if offset < 0:
            return pd.DataFrame()
        total = self._execute(GetExInstrumentCountCmd())
        page_size = 1000
        collected: list = []
        skipped = 0
        pos = offset
        while pos < total and len(collected) < count:
            batch = self._execute(GetExInstrumentInfoCmd(start=pos, count=page_size))
            if not batch:
                break
            for item in batch:
                if item.market == market:
                    if skipped < start:
                        skipped += 1
                    else:
                        collected.append(item)
                        if len(collected) >= count:
                            break
                elif item.market > market:
                    break
            else:
                pos += page_size
                continue
            break
        return _to_df(collected)

    def _find_market_offset(self, market: int) -> int:
        """二分查找定位指定市场在全局商品列表中的起始偏移。"""
        total = self._execute(GetExInstrumentCountCmd())
        if total == 0:
            return -1
        lo, hi = 0, total
        while lo < hi:
            mid = (lo + hi) // 2
            items = self._execute(GetExInstrumentInfoCmd(start=mid, count=1))
            if not items:
                hi = mid
                continue
            m = items[0].market
            if m < market:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def goods_quotes(self, stocks: list[tuple[int, str]], fields=None) -> pd.DataFrame:
        """批量获取扩展市场自定义字段报价。

        Parameters
        ----------
        stocks : list[tuple[int, str]]
            [(ExMarketcode, code), ...] 列表，最多 80 只。
            字段选择，默认 PresetField.COMMON。
        """
        cmd = SymbolQuotesCmd(stocks, fields)
        return self._parse_quotes(self._execute(cmd))

    def goods_quotes_list(self, market: ExMarket, start: int = 0, count: int = 80) -> pd.DataFrame:
        """获取扩展市场排序报价列表（通过 GoodsList + Quotes 组合） 先获取商品列表，再批量查询报价 """
        page_size = min(count, 80)
        items_df = self.goods_list(market, start=start, count=page_size)
        if items_df.empty:
            return pd.DataFrame()
        stocks: list[tuple[int, str]] = []
        for _, row in items_df.iterrows():
            stocks.append((market, row["code"]))
        cmd = SymbolQuotesCmd(stocks)
        return self._parse_quotes(self._execute(cmd))

    def goods_kline(self, market: int, code: str, period: Period = Period.DAILY, start: int = 0, count: int = 800, adjust: Adjust = Adjust.NONE) -> pd.DataFrame:
        """获取扩展市场 K 线数据（支持复权）。

        Parameters
        ----------
        market : int
            ExMarket 枚举值。
        code : str
            证券代码。
        period : Period
            K 线周期。
        start : int
            起始偏移（0=最新）。
        count : int
            返回条数。
        adjust : Adjust
            复权方式（NONE/QFQ/HFQ）。
        """
        cmd = SymbolBarCmd(market=market, code=code, period=period, start=start, count=count, fq=adjust)
        result = self._execute(cmd)
        return _to_df(result)

    def goods_tick_chart(self, market=ExMarket.HK_MAIN_BOARD, code='00616', query_date=0) -> pd.DataFrame:
        """获取单日分时图 """
        pkg = build_mac_request(0x122D, struct.pack("<H22sI5H", int(market), code.encode("gbk"), query_date, 1, 0, 0, 0, 0))
        body = self._execute(pkg)
        (market, code_raw, query_date, reserved, ref_price, count) = unpack_from("<H22sIBfH", body, 0, "tick_chart header")
        ticks: list[MacTick] = []
        for i in range(count):
            offset = 35 + i * 18
            (minutes, price, avg, vol, momentum) = unpack_from("<HffIf", body, offset, f"tick_chart tick[{i}]")
            ticks.append(MacTick(time=Time(minutes // 60 % 24, minutes % 60), price=price, avg=avg, vol=vol, momentum=momentum))

        # 尾部元数据
        tail_offset = 35 + count * 18
        (name_raw, _decimal, _category, _vol_unit, _date_raw, _time_raw, pre_close, open, high, low, close,
         _momentum_tail, vol, amount, _tail_pad2, turnover, avg_tail, _industry) = unpack_from(
            "<44sBHf5x2I5ffIf12s2fI", body, tail_offset, "tick_chart tail")

        return MacTickChart(market=market, code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                            name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""),
                            pre_close=pre_close, open=open, high=high, low=low, close=close, vol=int(vol),
                            amount=amount, turnover=turnover, avg=avg_tail, charts=ticks)


    def goods_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        """获取分时缩略采样价格点（约 240 个点） """
        pkg = build_mac_request(0x254D, struct.pack("<H22sHH9x", market, (code.encode("gbk") + b"\x00" * 22)[:22], 1, 20))
        body = self._execute(pkg)
        sz = 42
        prices: list[float] = []
        if len(body) >= sz:
            require_bytes(body, 0, sz, "ChartSamplingCmd header")
            count = unpack_from("<H", body, 40, "chart_sampling count")[0]
            for i in range(count):
                pos = sz + i * 4
                require_bytes(body, pos, 4, f"ChartSamplingCmd price[{i}]")
                (p,) = unpack_from("<f", body, pos, f"chart_sampling price[{i}]")
                prices.append(p)
        return pd.Series(prices)

    def goods_transaction(self, market: int, code: str, date=0, start: int = 0, count: int = 2000) -> pd.DataFrame:
        """获取逐笔成交数据。"""
        results: list[MacTransaction] = []
        for page in range(20):
            pkg = build_mac_request(0x122F, struct.pack("<H22sIIH10x", int(market), code.encode("gbk"), date, page * 2000, 2000))
            body = self._execute(pkg)
            count = unpack_from("<H", body, 29, "transaction count")[0]
            for i in range(count):
                offset = 39 + i * 18
                (time_sec, price, volume, trade_count, bs_flag) = unpack_from("<IfIIH", body, offset, f"transaction item[{i}]")
                results.append(MacTransaction(time=Time(time_sec // 3600, time_sec % 3600 // 60, time_sec % 60), price=price,
                                   vol=volume, trade_count=trade_count, bs_flag=bs_flag))
            if count < 2000:
                break
        return pd.DataFrame(results)


if __name__ == '__main__':
    with ExTdxClient() as c:
        # 批量报价（最多 80 只/次）
        df = c.get_instrument_quote()
        # 市场分类排序报价
        df = c.get_stock_quotes_list(Category.A, count=20, sort_type=SortType.CHANGE_PCT, sort_order=SortOrder.DESC)
        print('over')
