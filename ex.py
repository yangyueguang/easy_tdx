"""MAC 协议扩展市场高层 API：MacExClient（同步）和 AsyncMacExClient（asyncio）。

期货/港股/美股等扩展市场通过 MAC 协议命令（0x122B/0x122E/0x122D/0x122F/0x2562）
获取数据，使用 ExTdxConnection（端口 7727，单包握手）。
"""

from datetime import date
from mac import *

_DEFAULT_PORT = 7727
_T = TypeVar("_T")
"""扩展行情高层 API：ExTdxClient（同步）和 AsyncExTdxClient（asyncio）。"""
"""ex — 通达信扩展行情（期货、港股、外股等，端口 7727）。"""

"""扩展行情握手命令。"""

from typing import Final

EX_SETUP_CMD: Final[bytes] = bytes.fromhex(
    "01 01 48 65 00 01 52 00 52 00 54 24"
    "1f 32 c6 e5 d5 3d fb 41"
    "1f 32 c6 e5 d5 3d fb 41"
    "1f 32 c6 e5 d5 3d fb 41"
    "1f 32 c6 e5 d5 3d fb 41"
    "1f 32 c6 e5 d5 3d fb 41"
    "1f 32 c6 e5 d5 3d fb 41"
    "1f 32 c6 e5 d5 3d fb 41"
    "cc e1 6d ff d5 ba 3f b8"
    "cb c5 7a 05 4f 77 48 ea"
)
"""MAC EX 扩展行情登录命令（msg_id=0x2454）。

MAC EX 服务器（端口 7727）在数据查询前要求先完成 Login，
否则后续所有命令都会被服务器断开连接。
"""
from collections import OrderedDict
from commands import *
from codec import _to_df
T = TypeVar("T")

_DEFAULT_EX_PORT = 7727
_DEFAULT_TIMEOUT = 15.0

"""扩展行情数据模型与常量。"""

from dataclasses import dataclass, field


KNOWN_EX_HOSTS = get_ex_hosts()

# 已知扩展行情市场代码
KNOWN_EX_MARKETS: dict[int, str] = {
    0: "深圳",
    1: "上海",
    28: "郑州商品",
    29: "大连商品",
    30: "上海期货",
    31: "香港主板",
    47: "中金所",
    48: "香港创业板",
    49: "香港基金",
    71: "沪港通",
    74: "外盘",
}

# MAC 协议扩展行情服务器（端口 7727）
MAC_EX_HOSTS: list[str] = get_mac_ex_hosts()

_DEFAULT_EX_PORT = 7727


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

def ping_ex_host(
    host: str,
    port: int = _DEFAULT_EX_PORT,
    timeout: float = 5.0,
) -> float:
    """测量扩展行情服务器延迟（秒）。通过发送 get_instrument_count 验证可用性。"""
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        cmd = GetExInstrumentCountCmd()
        sock.sendall(cmd.build_request())
        hdr_buf = _recv_exact_sock(sock, HEADER_SIZE)
        hdr = parse_header(hdr_buf)
        if hdr.zipsize > 0:
            _recv_exact_sock(sock, hdr.zipsize)
        return time.monotonic() - t0
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def ping_ex_all(
    hosts: list[str] = None,
    port: int = _DEFAULT_EX_PORT,
    timeout: float = 5.0,
) -> list[tuple[str, float]]:
    """并发测量多台扩展行情服务器延迟，按延迟排序返回。"""
    import concurrent.futures

    if hosts is None:
        hosts = get_ex_hosts()
    results: list[tuple[str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {pool.submit(ping_ex_host, h, port, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            host = futures[fut]
            latency = fut.result()
            if latency is not None:
                results.append((host, latency))
    results.sort(key=lambda t: t[1])
    return results


def _recv_exact_sock(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise TdxConnectionError("连接被服务器关闭")
        buf.extend(chunk)
    return bytes(buf)


class ExTdxConnection:
    """扩展行情同步 TCP 连接（端口 7727，单包握手）。

    Parameters
    ----------
    mac_ex_mode : bool
        为 True 时自动将 MAC 命令的 head_flag 从 0x1C 转为 0x01，
        以兼容 MAC EX 服务器（需要 head_flag=0x01）。
    """

    def __init__(
        self,
        host: str = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
        *,
        mac_ex_mode: bool = False,
    ) -> None:
        self.host = host if host is not None else get_best_ex_host()
        self.port = port
        self.timeout = timeout
        self.mac_ex_mode = mac_ex_mode
        self._sock: socket.socket = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """建立 TCP 连接。扩展行情服务器不需要握手命令。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as e:
            sock.close()
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._sock = sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        with self._lock:
            if self._sock is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            request = cmd.build_request()
            if self.mac_ex_mode and len(request) > 0 and request[0] == 0x1C:
                request = b"\x01" + request[1:]
            try:
                self._sock.sendall(request)
                header_buf = self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = self._recv_exact(header.zipsize)
            except OSError as e:
                raise TdxConnectionError(f"通信错误: {e}") from e
            body = decompress_body(header, raw_body)
            return cmd.parse_response(body)

    def __enter__(self) -> "ExTdxConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        self.close()

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        return _recv_exact_sock(self._sock, n)

"""扩展行情异步 TCP 连接（asyncio，端口 7727）。"""



class AsyncExTdxConnection:
    """扩展行情异步 TCP 连接（asyncio，端口 7727，单包握手）。

    Parameters
    ----------
    mac_ex_mode : bool
        为 True 时自动将 MAC 命令的 head_flag 从 0x1C 转为 0x01，
        以兼容 MAC EX 服务器（需要 head_flag=0x01）。
    """

    def __init__(
        self,
        host: str = None,
        port: int = 7727,
        timeout: float = 15,
        *,
        mac_ex_mode: bool = False,
    ) -> None:
        self.host = host if host is not None else get_best_ex_host()
        self.port = port
        self.timeout = timeout
        self.mac_ex_mode = mac_ex_mode
        self._reader: asyncio.StreamReader = None
        self._writer: asyncio.StreamWriter = None
        self._io_lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._io_lock:
            if self._writer is not None and not self._writer.is_closing():
                return
            await self._connect_unlocked()

    async def close(self) -> None:
        async with self._io_lock:
            await self._close_unlocked()

    async def execute(self, cmd: "BaseCommand[T]") -> T:
        async with self._io_lock:
            if self._writer is None or self._reader is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            request = cmd.build_request()
            if self.mac_ex_mode and len(request) > 0 and request[0] == 0x1C:
                request = b"\x01" + request[1:]
            try:
                self._writer.write(request)
                await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
                header_buf = await self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = await self._recv_exact(header.zipsize)
            except asyncio.TimeoutError as e:
                await self._close_unlocked()
                raise TdxConnectionError(f"通信超时: {self.timeout}s") from e
            except (OSError, asyncio.IncompleteReadError) as e:
                await self._close_unlocked()
                raise TdxConnectionError(f"通信错误: {e}") from e

            body = decompress_body(header, raw_body)
            return cmd.parse_response(body)

    async def _connect_unlocked(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._reader = reader
        self._writer = writer

    async def _close_unlocked(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._reader = None
            self._writer = None

    async def __aenter__(self) -> "AsyncExTdxConnection":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self.close()

    async def _recv_exact(self, n: int) -> bytes:
        assert self._reader is not None
        return await asyncio.wait_for(
            self._reader.readexactly(n),
            timeout=self.timeout,
        )

class GetExHistoryInstrumentBarsRangeCmd(BaseCommand[list[ExInstrumentBar]]):
    """按日期范围获取历史K线数据。"""

    _seqid: int = 1

    def __init__(self, market: int, code: str, start_date: int, end_date: int) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.start_date = start_date
        self.end_date = end_date

    def build_request(self) -> bytes:
        pkg = bytearray.fromhex("01")
        pkg.extend(struct.pack("<B", self._seqid))
        self.__class__._seqid += 1
        pkg.extend(bytearray.fromhex("38 92 00 01 16 00 16 00 0D 24"))
        pkg.extend(struct.pack("<B9s", self.market, self.code))
        pkg.extend(bytearray.fromhex("07 00"))
        pkg.extend(struct.pack("<II", self.start_date, self.end_date))
        return bytes(pkg)

    @staticmethod
    def _parse_date(num: int) -> tuple[int, int, int]:
        year = num // 2048 + 2004
        month = (num % 2048) // 100
        day = (num % 2048) % 100
        return year, month, day

    @staticmethod
    def _parse_time(num: int) -> tuple[int, int]:
        return num // 60, num % 60

    def parse_response(self, body: bytes) -> list[ExInstrumentBar]:
        pos = 12  # skip 12-byte header
        if pos + 2 > len(body):
            return []
        (ret_count,) = struct.unpack("<H", body[pos : pos + 2])
        pos += 2
        results: list[ExInstrumentBar] = []
        for _ in range(ret_count):
            if pos + 32 > len(body):
                break
            record_start = pos
            (d1, d2, open_p, high, low, close_p, position, trade, settlement) = struct.unpack(
                "<HHffffIIf",
                body[pos : pos + 32],
            )
            pos += 32
            year, month, day = self._parse_date(d1)
            hour, minute = self._parse_time(d2)
            results.append(
                ExInstrumentBar(
                    open=open_p,
                    high=high,
                    low=low,
                    close=close_p,
                    position=position,
                    trade=trade,
                    amount=settlement,
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    _raw=body[record_start:pos],
                )
            )
        return results

class GetExInstrumentBarsCmd(BaseCommand[list[ExInstrumentBar]]):
    """获取K线数据（扩展行情版本，支持期货/港股等）。"""

    def __init__(
        self,
        category: int,
        market: int,
        code: str,
        start: int = 0,
        count: int = 700,
    ) -> None:
        self.category = category
        self.market = market
        self.code = code.encode("utf-8")
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 08 6a 01 01 16 00 16 00 ff 23")
        return header + struct.pack(
            "<B9sHHIH",
            self.market,
            self.code,
            self.category,
            1,
            self.start,
            self.count,
        )

    def parse_response(self, body: bytes) -> list[ExInstrumentBar]:
        pos = 18  # skip 18-byte header
        if pos + 2 > len(body):
            return []
        (ret_count,) = struct.unpack("<H", body[pos : pos + 2])
        pos += 2
        results: list[ExInstrumentBar] = []
        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(self.category, body, pos)
            if pos + 28 > len(body):
                break
            (open_p, high, low, close_p, position, trade, _price) = struct.unpack(
                "<ffffIIf",
                body[pos : pos + 28],
            )
            (amount,) = struct.unpack("<f", body[pos + 16 : pos + 20])
            pos += 28
            results.append(
                ExInstrumentBar(
                    open=open_p,
                    high=high,
                    low=low,
                    close=close_p,
                    position=position,
                    trade=trade,
                    amount=amount,
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    _raw=body[record_start:pos],
                )
            )
        return results

class GetExInstrumentCountCmd(BaseCommand[int]):
    """获取扩展行情市场中商品总数。"""

    def build_request(self) -> bytes:
        return bytes.fromhex("01 03 48 66 00 01 02 00 02 00 f0 23")

    def parse_response(self, body: bytes) -> int:
        if len(body) < 23:
            return 0
        (count,) = unpack_from("<I", body, 19, "ex instrument count")
        return int(count)


class GetExInstrumentInfoCmd(BaseCommand[list[ExInstrumentInfo]]):
    """获取扩展行情市场中的商品信息列表。"""

    def __init__(self, start: int, count: int = 100) -> None:
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
            (category, market, _unused, raw_code, raw_name, raw_desc) = struct.unpack(
                "<BB3s9s17s9s",
                raw[:40],
            )
            pos += 64
            code = raw_code.decode("gbk", errors="replace").rstrip("\x00")
            name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
            desc = raw_desc.decode("gbk", errors="replace").rstrip("\x00")
            results.append(
                ExInstrumentInfo(
                    category=category,
                    market=market,
                    code=code,
                    name=name,
                    desc=desc,
                    _raw=raw,
                )
            )
        return results

class GetExInstrumentQuoteCmd(BaseCommand[ExInstrumentQuote]):
    """获取单个商品的五档实时行情。"""

    def __init__(self, market: int, code: str) -> None:
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 08 02 02 01 0c 00 0c 00 fa 23")
        return header + struct.pack("<B9s", self.market, self.code)

    def parse_response(self, body: bytes) -> ExInstrumentQuote:
        if len(body) < 150:
            return None
        pos = 0
        (market, raw_code) = struct.unpack("<B9s", body[pos : pos + 10])
        pos += 10
        pos += 4  # skip 4 unknown bytes
        record_start = pos - 14
        (
            pre_close,
            open_price,
            high,
            low,
            price,
            kaicang,
            _unk1,
            zongliang,
            xianliang,
            _unk2,
            neipan,
            waipan,
            _unk3,
            chicang,
            b1,
            b2,
            b3,
            b4,
            b5,
            bv1,
            bv2,
            bv3,
            bv4,
            bv5,
            a1,
            a2,
            a3,
            a4,
            a5,
            av1,
            av2,
            av3,
            av4,
            av5,
        ) = struct.unpack(
            "<fffffIIIIIIIIIfffffIIIIIfffffIIIII",
            body[pos : pos + 136],
        )
        code = raw_code.decode("utf-8", errors="replace").rstrip("\x00")
        return ExInstrumentQuote(
            market=market,
            code=code,
            pre_close=pre_close,
            open=open_price,
            high=high,
            low=low,
            price=price,
            kaicang=kaicang,
            zongliang=zongliang,
            xianliang=xianliang,
            neipan=neipan,
            waipan=waipan,
            chicang=chicang,
            bid1=b1,
            bid2=b2,
            bid3=b3,
            bid4=b4,
            bid5=b5,
            bid_vol1=bv1,
            bid_vol2=bv2,
            bid_vol3=bv3,
            bid_vol4=bv4,
            bid_vol5=bv5,
            ask1=a1,
            ask2=a2,
            ask3=a3,
            ask4=a4,
            ask5=a5,
            ask_vol1=av1,
            ask_vol2=av2,
            ask_vol3=av3,
            ask_vol4=av4,
            ask_vol5=av5,
            _raw=body[record_start : pos + 136],
        )

class GetExInstrumentQuoteListCmd(BaseCommand[list[OrderedDict[str, object]]]):
    """按类别获取商品行情列表（期货/港股等）。"""

    def __init__(
        self,
        market: int,
        category: int,
        start: int = 0,
        count: int = 80,
    ) -> None:
        self.market = market
        self.category = category
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 c1 06 0b 00 02 0b 00 0b 00 00 24")
        return header + struct.pack(
            "<BHHHH",
            self.market,
            0,
            self.start,
            self.count,
            1,
        )

    def parse_response(self, body: bytes) -> list[OrderedDict[str, object]]:
        if len(body) < 2:
            return []
        (num,) = struct.unpack("<H", body[0:2])
        pos = 2
        results: list[OrderedDict[str, object]] = []
        for _ in range(num):
            if pos + 10 > len(body):
                break
            (market, raw_code) = struct.unpack("<B9s", body[pos : pos + 10])
            code = raw_code.strip(b"\x00").decode("gbk", errors="replace")
            pos += 10
            if self.category == 3:
                pos = self._parse_futures(market, code, body, pos, results)
            elif self.category == 2:
                pos = self._parse_hk_stocks(market, code, body, pos, results)
            else:
                raise TdxCommandError(f"不支持的扩展行情类别: {self.category}")
        return results

    @staticmethod
    def _parse_futures(
        market: int,
        code: str,
        body: bytes,
        pos: int,
        results: list[OrderedDict[str, object]],
    ) -> int:
        if pos + 140 > len(body):
            return pos + 290
        (
            bi_shu,
            zuo_jie,
            jin_kai,
            zui_gao,
            zui_di,
            mai_chu,
            kai_cang,
            _unk1,
            zong_liang,
            xian_liang,
            zong_jin_e,
            nei_pan,
            wai_pan,
            _unk2,
            chi_cang_liang,
            mai_ru_jia,
            _u1,
            _u2,
            _u3,
            _u4,
            mai_ru_liang,
            _u5,
            _u6,
            _u7,
            _u8,
            mai_chu_jia,
            _u9,
            _u10,
            _u11,
            _u12,
            mai_chu_liang,
            _u13,
            _u14,
            _u15,
        ) = struct.unpack("<IfffffIIIIfIIfIfIIIIIIIIIfIIIIIIIII", body[pos : pos + 140])
        pos += 290
        results.append(
            OrderedDict(
                [
                    ("market", market),
                    ("code", code),
                    ("BiShu", bi_shu),
                    ("ZuoJie", zuo_jie),
                    ("JinKai", jin_kai),
                    ("ZuiGao", zui_gao),
                    ("ZuiDi", zui_di),
                    ("MaiChu", mai_chu),
                    ("KaiCang", kai_cang),
                    ("ZongLiang", zong_liang),
                    ("XianLiang", xian_liang),
                    ("ZongJinE", zong_jin_e),
                    ("NeiPan", nei_pan),
                    ("WaiPan", wai_pan),
                    ("ChiCangLiang", chi_cang_liang),
                    ("MaiRuJia", mai_ru_jia),
                    ("MaiRuLiang", mai_ru_liang),
                    ("MaiChuJia", mai_chu_jia),
                    ("MaiChuLiang", mai_chu_liang),
                ]
            )
        )
        return pos

    @staticmethod
    def _parse_hk_stocks(
        market: int,
        code: str,
        body: bytes,
        pos: int,
        results: list[OrderedDict[str, object]],
    ) -> int:
        if pos + 140 > len(body):
            return pos + 290
        (
            huo_yue_du,
            zuo_shou,
            jin_kai,
            zui_gao,
            zui_di,
            xian_jia,
            _unk1,
            mai_ru_jia,
            zong_liang,
            xian_liang,
            zong_jin_e,
            _unk2,
            _unk3,
            nei,
            wai,
            mrj1,
            mrj2,
            mrj3,
            mrj4,
            mrj5,
            mrl1,
            mrl2,
            mrl3,
            mrl4,
            mrl5,
            mcj1,
            mcj2,
            mcj3,
            mcj4,
            mcj5,
            mcl1,
            mcl2,
            mcl3,
            mcl4,
            mcl5,
        ) = struct.unpack("<IfffffIfIIfIIIIfffffIIIIIfffffIIIII", body[pos : pos + 140])
        pos += 290
        results.append(
            OrderedDict(
                [
                    ("market", market),
                    ("code", code),
                    ("HuoYueDu", huo_yue_du),
                    ("ZuoShou", zuo_shou),
                    ("JinKai", jin_kai),
                    ("ZuiGao", zui_gao),
                    ("ZuiDi", zui_di),
                    ("XianJia", xian_jia),
                    ("MaiRuJia", mai_ru_jia),
                    ("ZongLiang", zong_liang),
                    ("XianLiang", xian_liang),
                    ("ZongJinE", zong_jin_e),
                    ("Nei", nei),
                    ("Wai", wai),
                    ("MaiRuJia1", mrj1),
                    ("MaiRuJia2", mrj2),
                    ("MaiRuJia3", mrj3),
                    ("MaiRuJia4", mrj4),
                    ("MaiRuJia5", mrj5),
                    ("MaiRuLiang1", mrl1),
                    ("MaiRuLiang2", mrl2),
                    ("MaiRuLiang3", mrl3),
                    ("MaiRuLiang4", mrl4),
                    ("MaiRuLiang5", mrl5),
                    ("MaiChuJia1", mcj1),
                    ("MaiChuJia2", mcj2),
                    ("MaiChuJia3", mcj3),
                    ("MaiChuJia4", mcj4),
                    ("MaiChuJia5", mcj5),
                    ("MaiChuLiang1", mcl1),
                    ("MaiChuLiang2", mcl2),
                    ("MaiChuLiang3", mcl3),
                    ("MaiChuLiang4", mcl4),
                    ("MaiChuLiang5", mcl5),
                ]
            )
        )
        return pos

class GetExMarketsCmd(BaseCommand[list[ExMarketInfo]]):
    """获取扩展行情支持的市场列表。"""

    def build_request(self) -> bytes:
        return bytes.fromhex("01 02 48 69 00 01 02 00 02 00 f4 23")

    def parse_response(self, body: bytes) -> list[ExMarketInfo]:
        if len(body) < 2:
            return []
        (count,) = unpack_from("<H", body, 0, "ex markets count")
        pos = 2
        results: list[ExMarketInfo] = []
        for _ in range(count):
            if pos + 64 > len(body):
                break
            raw = body[pos : pos + 64]
            (category, raw_name, market, raw_short_name) = struct.unpack("<B32sB2s", raw[:36])
            pos += 64
            if category == 0 and market == 0:
                continue
            name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
            short_name = raw_short_name.decode("gbk", errors="replace").rstrip("\x00")
            results.append(
                ExMarketInfo(
                    market=market,
                    category=category,
                    name=name,
                    short_name=short_name,
                    _raw=raw,
                )
            )
        return results

class GetExMinuteTimeDataCmd(BaseCommand[list[ExMinuteBar]]):
    """获取当日分时行情数据。"""

    def __init__(self, market: int, code: str) -> None:
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 07 08 00 01 01 0c 00 0c 00 0b 24")
        return header + struct.pack("<B9s", self.market, self.code)

    def parse_response(self, body: bytes) -> list[ExMinuteBar]:
        if len(body) < 12:
            return []
        pos = 0
        (market, raw_code, num) = struct.unpack("<B9sH", body[pos : pos + 12])
        pos += 12
        return self._parse_records(body, pos, num)

    @staticmethod
    def _parse_records(body: bytes, pos: int, num: int) -> list[ExMinuteBar]:
        results: list[ExMinuteBar] = []
        for _ in range(num):
            if pos + 18 > len(body):
                break
            record_start = pos
            (raw_time, price, avg_price, volume, amount) = struct.unpack(
                "<HffII",
                body[pos : pos + 18],
            )
            pos += 18
            hour = raw_time // 60
            minute = raw_time % 60
            results.append(
                ExMinuteBar(
                    hour=hour,
                    minute=minute,
                    price=price,
                    avg_price=avg_price,
                    volume=volume,
                    open_interest=amount,
                    _raw=body[record_start:pos],
                )
            )
        return results


class GetExHistoryMinuteTimeDataCmd(BaseCommand[list[ExMinuteBar]]):
    """获取历史某日分时行情数据。"""

    def __init__(self, market: int, code: str, date: int) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.date = date

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 30 00 01 01 10 00 10 00 0c 24")
        return header + struct.pack("<IB9s", self.date, self.market, self.code)

    def parse_response(self, body: bytes) -> list[ExMinuteBar]:
        if len(body) < 20:
            return []
        pos = 0
        (_market, _code, _unk, num) = struct.unpack("<B9s8sH", body[pos : pos + 20])
        pos += 20
        return GetExMinuteTimeDataCmd._parse_records(body, pos, num)

class GetExTransactionDataCmd(BaseCommand[list[ExTransactionRecord]]):
    """获取当日分笔成交数据。"""

    def __init__(self, market: int, code: str, start: int = 0, count: int = 1800) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 08 00 03 01 12 00 12 00 fc 23")
        return header + struct.pack("<B9siH", self.market, self.code, self.start, self.count)

    def parse_response(self, body: bytes) -> list[ExTransactionRecord]:
        if len(body) < 16:
            return []
        pos = 0
        (_market, _code, _unk, num) = struct.unpack("<B9s4sH", body[pos : pos + 16])
        pos += 16
        return self._parse_records(body, pos, num)

    @staticmethod
    def _parse_records(body: bytes, pos: int, num: int) -> list[ExTransactionRecord]:
        results: list[ExTransactionRecord] = []
        for _ in range(num):
            if pos + 16 > len(body):
                break
            record_start = pos
            (raw_time, price, volume, zengcang, direction) = struct.unpack(
                "<HIIiH",
                body[pos : pos + 16],
            )
            pos += 16
            hour = raw_time // 60
            minute = raw_time % 60
            second = direction % 10000
            if second > 59:
                second = 0
            nature = direction // 10000
            results.append(
                ExTransactionRecord(
                    hour=hour,
                    minute=minute,
                    second=second,
                    price=price,
                    volume=volume,
                    zengcang=zengcang,
                    nature=nature,
                    _raw=body[record_start:pos],
                )
            )
        return results


class GetExHistoryTransactionDataCmd(BaseCommand[list[ExTransactionRecord]]):
    """获取历史某日分笔成交数据。"""

    def __init__(
        self,
        market: int,
        code: str,
        date: int,
        start: int = 0,
        count: int = 1800,
    ) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.date = date
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 30 00 02 01 16 00 16 00 06 24")
        return header + struct.pack(
            "<IB9siH",
            self.date,
            self.market,
            self.code,
            self.start,
            self.count,
        )

    def parse_response(self, body: bytes) -> list[ExTransactionRecord]:
        if len(body) < 16:
            return []
        pos = 0
        (_market, _code, _unk, num) = struct.unpack("<B9s4sH", body[pos : pos + 16])
        pos += 16
        return GetExTransactionDataCmd._parse_records(body, pos, num)



class MacExLoginCmd(BaseCommand[bool]):
    """MAC EX 扩展行情登录命令。"""

    def build_request(self) -> bytes:
        # 80 字节 Login body，来自 opentdx 参考实现，已通过实际测试验证。
        _LOGIN_BODY = bytes(
            bytearray.fromhex(
                "e5bb1c2fafe52594"
                "1f32c6e5d53dfb41"
                "5b734cc9cdbf0ac9"
                "2021bfdd1eb06d22"
                "d008884c1611cb13"
                "78f6abd824d899d2"
                "1f32c6e5d53dfb41"
                "1f32c6e5d53dfb41"
                "a9325ac935dc0837"
                "335a16e4ce17c1bb"
            )
        )

        inner = struct.pack("<H", 0x2454) + _LOGIN_BODY

        # EX 协议帧头格式: head_flag(1B) + customize(4B) + version(1B) + zipsize(2B) + unzipsize(2B)
        _EX_HEADER_FMT = "<BIBHH"
        header = struct.pack(
            _EX_HEADER_FMT,
            0x01,
            0,  # customize
            1,  # version
            len(inner),
            len(inner),
        )
        return header + inner

    def parse_response(self, body: bytes) -> bool:
        # Login 响应 body 非空即视为成功
        return len(body) >= 2

_DEFAULT_EX_PORT = 7727
_T = TypeVar("_T")


# ============================================================
# 同步客户端
# ============================================================


class ExTdxClient:
    """同步扩展行情客户端（期货、港股、外股等，端口 7727）。

    使用示例::

        with ExTdxClient("61.152.107.141") as c:
            markets = c.get_markets()
            quote = c.get_instrument_quote(47, "IFL0")
    """

    def __init__(
        self,
        host: str = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
    ) -> None:
        self._host = host if host is not None else get_best_ex_host()
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._conn = ExTdxConnection(self._host, port, timeout)

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
    ) -> "ExTdxClient":
        """测量所有扩展行情服务器延迟，选最低延迟建立连接。自动保存最佳主机。"""
        if hosts is None:
            hosts = get_ex_hosts()
        ranked = ping_ex_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_ex_host(best)
        return cls(best, port, timeout, auto_reconnect)

    @staticmethod
    def ping_all(
        hosts: list[str] = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        return ping_ex_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        self._conn.connect()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ExTdxClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        self.close()

    def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError:
            if not self._auto_reconnect:
                raise
            self._conn.close()
            self._conn = ExTdxConnection(self._host, self._port, self._timeout)
            self._conn.connect()
            return self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    def get_markets(self) -> list[ExMarketInfo]:
        """获取扩展行情支持的市场列表。"""
        return self._execute(GetExMarketsCmd())

    def get_instrument_count(self) -> int:
        """获取扩展行情商品总数。"""
        return self._execute(GetExInstrumentCountCmd())

    def get_instrument_info(self, start: int, count: int = 100) -> list[ExInstrumentInfo]:
        """获取商品信息列表（分页）。"""
        return self._execute(GetExInstrumentInfoCmd(start, count))

    # ------------------------------------------------------------------ #
    # 行情
    # ------------------------------------------------------------------ #

    def get_instrument_quote(self, market: int, code: str) -> ExInstrumentQuote:
        """获取单个商品五档实时行情。"""
        return self._execute(GetExInstrumentQuoteCmd(market, code))

    def get_instrument_quote_list(
        self,
        market: int,
        category: int,
        start: int = 0,
        count: int = 80,
    ) -> list[OrderedDict[str, object]]:
        """按类别获取商品行情列表。"""
        return self._execute(GetExInstrumentQuoteListCmd(market, category, start, count))

    # ------------------------------------------------------------------ #
    # K线
    # ------------------------------------------------------------------ #

    def get_instrument_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int = 0,
        count: int = 700,
    ) -> list[ExInstrumentBar]:
        """获取K线数据。"""
        return self._execute(GetExInstrumentBarsCmd(category, market, code, start, count))

    def get_history_instrument_bars_range(
        self,
        market: int,
        code: str,
        start_date: int,
        end_date: int,
    ) -> list[ExInstrumentBar]:
        """按日期范围获取历史K线。"""
        return self._execute(GetExHistoryInstrumentBarsRangeCmd(market, code, start_date, end_date))

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_minute_time_data(self, market: int, code: str) -> list[ExMinuteBar]:
        """获取当日分时行情数据。"""
        return self._execute(GetExMinuteTimeDataCmd(market, code))

    def get_history_minute_time_data(
        self,
        market: int,
        code: str,
        date: int,
    ) -> list[ExMinuteBar]:
        """获取历史某日分时行情数据（date: YYYYMMDD）。"""
        return self._execute(GetExHistoryMinuteTimeDataCmd(market, code, date))

    # ------------------------------------------------------------------ #
    # 成交
    # ------------------------------------------------------------------ #

    def get_transaction_data(
        self,
        market: int,
        code: str,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        """获取当日分笔成交数据。"""
        return self._execute(GetExTransactionDataCmd(market, code, start, count))

    def get_history_transaction_data(
        self,
        market: int,
        code: str,
        date: int,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        """获取历史某日分笔成交数据（date: YYYYMMDD）。"""
        return self._execute(GetExHistoryTransactionDataCmd(market, code, date, start, count))


# ============================================================
# 异步客户端
# ============================================================


class AsyncExTdxClient:
    """异步扩展行情客户端（asyncio，端口 7727）。

    使用示例::

        async with AsyncExTdxClient("61.152.107.141") as c:
            markets = await c.get_markets()
    """

    def __init__(
        self,
        host: str = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> None:
        self._host = host if host is not None else get_best_ex_host()
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = AsyncExTdxConnection(self._host, port, timeout)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] = None

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> "AsyncExTdxClient":
        if hosts is None:
            hosts = get_ex_hosts()
        ranked = ping_ex_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_ex_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        return ping_ex_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        await self._conn.connect()
        self._start_heartbeat()

    async def close(self) -> None:
        await self._stop_heartbeat()
        await self._conn.close()

    async def __aenter__(self) -> "AsyncExTdxClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self.close()

    def _start_heartbeat(self) -> None:
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self.get_instrument_count()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError:
                if not self._auto_reconnect:
                    raise
                await self._conn.close()
                self._conn = AsyncExTdxConnection(self._host, self._port, self._timeout)
                await self._conn.connect()
                return await self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    async def get_markets(self) -> list[ExMarketInfo]:
        return await self._execute(GetExMarketsCmd())

    async def get_instrument_count(self) -> int:
        return await self._execute(GetExInstrumentCountCmd())

    async def get_instrument_info(
        self,
        start: int,
        count: int = 100,
    ) -> list[ExInstrumentInfo]:
        return await self._execute(GetExInstrumentInfoCmd(start, count))

    # ------------------------------------------------------------------ #
    # 行情
    # ------------------------------------------------------------------ #

    async def get_instrument_quote(
        self,
        market: int,
        code: str,
    ) -> ExInstrumentQuote:
        return await self._execute(GetExInstrumentQuoteCmd(market, code))

    async def get_instrument_quote_list(
        self,
        market: int,
        category: int,
        start: int = 0,
        count: int = 80,
    ) -> list[OrderedDict[str, object]]:
        return await self._execute(GetExInstrumentQuoteListCmd(market, category, start, count))

    # ------------------------------------------------------------------ #
    # K线
    # ------------------------------------------------------------------ #

    async def get_instrument_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int = 0,
        count: int = 700,
    ) -> list[ExInstrumentBar]:
        return await self._execute(GetExInstrumentBarsCmd(category, market, code, start, count))

    async def get_history_instrument_bars_range(
        self,
        market: int,
        code: str,
        start_date: int,
        end_date: int,
    ) -> list[ExInstrumentBar]:
        return await self._execute(
            GetExHistoryInstrumentBarsRangeCmd(market, code, start_date, end_date)
        )

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    async def get_minute_time_data(self, market: int, code: str) -> list[ExMinuteBar]:
        return await self._execute(GetExMinuteTimeDataCmd(market, code))

    async def get_history_minute_time_data(
        self,
        market: int,
        code: str,
        date: int,
    ) -> list[ExMinuteBar]:
        return await self._execute(GetExHistoryMinuteTimeDataCmd(market, code, date))

    # ------------------------------------------------------------------ #
    # 成交
    # ------------------------------------------------------------------ #

    async def get_transaction_data(
        self,
        market: int,
        code: str,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        return await self._execute(GetExTransactionDataCmd(market, code, start, count))

    async def get_history_transaction_data(
        self,
        market: int,
        code: str,
        date: int,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        return await self._execute(GetExHistoryTransactionDataCmd(market, code, date, start, count))


def _quotes_to_df(result: list[MacQuoteField]) -> pd.DataFrame:
    """将 MacQuoteField 列表展开为 DataFrame。"""
    rows: list[dict[str, Any]] = []
    for item in result:
        row: dict[str, Any] = {"market": item.market, "code": item.code, "name": item.name}
        row.update(item.fields)
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ============================================================
# 同步客户端
# ============================================================


class MacExClient:
    """同步 MAC 协议扩展市场客户端（期货/港股/美股，端口 7727）。

    使用示例::

        with MacExClient() as c:
            df = c.goods_kline(ExMarket.CFFEX_FUTURES, "IFL0", Period.DAILY)
            df = c.goods_quotes([(ExMarket.HK_MAIN_BOARD, "00700")])
    """

    def __init__(
        self,
        host: str = None,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
    ) -> None:
        self._host = host if host is not None else get_best_mac_ex_host()
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._conn = ExTdxConnection(self._host, port, timeout, mac_ex_mode=True)

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = None,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
    ) -> "MacExClient":
        """测量所有 MAC 扩展行情服务器延迟，选最低延迟建立连接。"""
        candidates = hosts or get_mac_ex_hosts()
        ranked = ping_ex_all(candidates, port, ping_timeout)
        best = ranked[0][0] if ranked else candidates[0]
        save_best_mac_ex_host(best)
        return cls(best, port, timeout, auto_reconnect)

    @staticmethod
    def ping_all(
        hosts: list[str] = None,
        port: int = _DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        return ping_ex_all(hosts or get_mac_ex_hosts(), port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        self._conn.connect()
        self._login()

    def close(self) -> None:
        self._conn.close()

    def disconnect(self) -> None:
        self.close()

    def ensure_connected(self) -> None:
        """验证连接存活，断线则自动重建。"""
        try:
            self._execute(GetExInstrumentCountCmd())
        except TdxConnectionError:
            self._conn.close()
            self._conn = ExTdxConnection(self._host, self._port, self._timeout, mac_ex_mode=True)
            self._conn.connect()
            self._login()

    def __enter__(self) -> "MacExClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        self.close()

    def _login(self) -> None:
        """执行 MAC EX 登录命令。"""
        self._conn.execute(MacExLoginCmd())

    def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError:
            if not self._auto_reconnect:
                raise
            self._conn.close()
            self._conn = ExTdxConnection(self._host, self._port, self._timeout, mac_ex_mode=True)
            self._conn.connect()
            self._login()
            return self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 商品列表
    # ------------------------------------------------------------------ #

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
        collected: list[Any] = []
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

    # ------------------------------------------------------------------ #
    # 行情
    # ------------------------------------------------------------------ #

    def goods_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: Any = None,
    ) -> pd.DataFrame:
        """批量获取扩展市场自定义字段报价。

        Parameters
        ----------
        stocks : list[tuple[int, str]]
            [(ExMarketcode, code), ...] 列表，最多 80 只。
        fields : Fields
            字段选择，默认 PresetField.COMMON。
        """
        cmd = SymbolQuotesCmd(stocks, fields)
        result: list[MacQuoteField] = self._execute(cmd)
        return _quotes_to_df(result)

    def goods_quotes_list(
        self,
        market: int,
        start: int = 0,
        count: int = 100,
        sort_type: SortType = SortType.CODE,
        sort_order: SortOrder = SortOrder.NONE,
    ) -> pd.DataFrame:
        """获取扩展市场排序报价列表（通过 GoodsList + Quotes 组合）。

        先获取商品列表，再批量查询报价。

        Parameters
        ----------
        market : int
            ExMarket 枚举值。
        start : int
            起始偏移。
        count : int
            返回条数（最大 80，受报价批量限制）。
        sort_type : SortType
            排序字段（暂未实现排序，预留接口）。
        sort_order : SortOrder
            排序方向（暂未实现排序，预留接口）。
        """
        page_size = min(count, 80)
        items_df = self.goods_list(market, start=start, count=page_size)
        if items_df.empty:
            return pd.DataFrame()
        stocks: list[tuple[int, str]] = []
        for _, row in items_df.iterrows():
            stocks.append((market, row["code"]))
        cmd = SymbolQuotesCmd(stocks)
        result: list[MacQuoteField] = self._execute(cmd)
        return _quotes_to_df(result)

    def goods_kline(
        self,
        market: int,
        code: str,
        period: Period = Period.DAILY,
        start: int = 0,
        count: int = 800,
        adjust: Adjust = Adjust.NONE,
    ) -> pd.DataFrame:
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
        cmd = SymbolBarCmd(
            market=market,
            code=code,
            period=period,
            start=start,
            count=count,
            fq=adjust,
        )
        result = self._execute(cmd)
        return _to_df(result)

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def goods_tick_chart(
        self,
        market: int,
        code: str,
        query_date: date = None,
    ) -> pd.DataFrame:
        """获取单日分时图。

        Parameters
        ----------
        market : int
            ExMarket 枚举值。
        code : str
            证券代码。
        query_date : date
            查询日期，None 表示今天。
        """
        cmd = SymbolTickChartCmd(market=market, code=code, query_date=query_date)
        result = self._execute(cmd)
        return _to_df(result)

    def goods_chart_sampling(
        self,
        market: int,
        code: str,
    ) -> pd.DataFrame:
        """获取分时缩略采样价格点（约 240 个点）。

        Parameters
        ----------
        market : int
            ExMarket 枚举值。
        code : str
            证券代码。
        """
        cmd = ChartSamplingCmd(market=market, code=code)
        prices: list[float] = self._execute(cmd)
        if not prices:
            return pd.DataFrame()
        return pd.DataFrame({"price": prices})

    # ------------------------------------------------------------------ #
    # 成交
    # ------------------------------------------------------------------ #

    def goods_transaction(
        self,
        market: int,
        code: str,
        query_date: date = None,
        start: int = 0,
        count: int = 2000,
    ) -> pd.DataFrame:
        """获取逐笔成交数据。

        Parameters
        ----------
        market : int
            ExMarket 枚举值。
        code : str
            证券代码。
        query_date : date
            查询日期，None 表示今天。
        start : int
            起始偏移。
        count : int
            返回条数。
        """
        cmd = SymbolTransactionCmd(
            market=market,
            code=code,
            query_date=query_date,
            start=start,
            count=count,
        )
        result = self._execute(cmd)
        return _to_df(result)


# ============================================================
# 异步客户端
# ============================================================


class AsyncMacExClient:
    """异步 MAC 协议扩展市场客户端（asyncio，端口 7727）。

    使用示例::

        async with AsyncMacExClient() as c:
            df = await c.goods_kline(ExMarket.CFFEX_FUTURES, "IFL0", Period.DAILY)
    """

    def __init__(
        self,
        host: str = None,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> None:
        self._host = host if host is not None else get_best_mac_ex_host()
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = AsyncExTdxConnection(self._host, port, timeout, mac_ex_mode=True)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] = None

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] = None,
        port: int = _DEFAULT_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> "AsyncMacExClient":
        candidates = hosts or get_mac_ex_hosts()
        ranked = ping_ex_all(candidates, port, ping_timeout)
        best = ranked[0][0] if ranked else candidates[0]
        save_best_mac_ex_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] = None,
        port: int = _DEFAULT_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        return ping_ex_all(hosts or get_mac_ex_hosts(), port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        await self._conn.connect()
        await self._login()
        self._start_heartbeat()

    async def close(self) -> None:
        await self._stop_heartbeat()
        await self._conn.close()

    async def __aenter__(self) -> "AsyncMacExClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_val: BaseException,
        exc_tb: TracebackType,
    ) -> None:
        await self.close()

    def _start_heartbeat(self) -> None:
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self._execute(GetExInstrumentCountCmd())
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _login(self) -> None:
        """执行 MAC EX 登录命令。"""
        await self._conn.execute(MacExLoginCmd())

    async def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError:
                if not self._auto_reconnect:
                    raise
                await self._conn.close()
                self._conn = AsyncExTdxConnection(
                    self._host, self._port, self._timeout, mac_ex_mode=True
                )
                await self._conn.connect()
                await self._login()
                return await self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 商品列表
    # ------------------------------------------------------------------ #

    async def goods_count(self, market: int = None) -> int:
        """获取商品总数。market=None 时返回全市场总数，否则返回指定市场的数量。"""
        if market is None:
            return await self._execute(GetExInstrumentCountCmd())
        offset = await self._find_market_offset(market)
        if offset < 0:
            return 0
        total = await self._execute(GetExInstrumentCountCmd())
        n = 0
        page = 1000
        pos = offset
        while pos < total:
            batch = await self._execute(GetExInstrumentInfoCmd(start=pos, count=page))
            if not batch:
                break
            for item in batch:
                if item.market == market:
                    n += 1
                elif item.market > market:
                    return n
            pos += page
        return n

    async def goods_list(self, market: int, start: int = 0, count: int = 600) -> pd.DataFrame:
        """获取扩展市场商品列表（期货合约/港股/美股等）。"""
        offset = await self._find_market_offset(market)
        if offset < 0:
            return pd.DataFrame()
        total = await self._execute(GetExInstrumentCountCmd())
        page_size = 1000
        collected: list[Any] = []
        skipped = 0
        pos = offset
        while pos < total and len(collected) < count:
            batch = await self._execute(GetExInstrumentInfoCmd(start=pos, count=page_size))
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

    async def _find_market_offset(self, market: int) -> int:
        """二分查找定位指定市场在全局商品列表中的起始偏移。"""
        total = await self._execute(GetExInstrumentCountCmd())
        if total == 0:
            return -1
        lo, hi = 0, total
        while lo < hi:
            mid = (lo + hi) // 2
            items = await self._execute(GetExInstrumentInfoCmd(start=mid, count=1))
            if not items:
                hi = mid
                continue
            m = items[0].market
            if m < market:
                lo = mid + 1
            else:
                hi = mid
        return lo

    # ------------------------------------------------------------------ #
    # 行情
    # ------------------------------------------------------------------ #

    async def goods_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: Any = None,
    ) -> pd.DataFrame:
        cmd = SymbolQuotesCmd(stocks, fields)
        result: list[MacQuoteField] = await self._execute(cmd)
        return _quotes_to_df(result)

    async def goods_quotes_list(
        self,
        market: int,
        start: int = 0,
        count: int = 100,
        sort_type: SortType = SortType.CODE,
        sort_order: SortOrder = SortOrder.NONE,
    ) -> pd.DataFrame:
        page_size = min(count, 80)
        items_df = await self.goods_list(market, start=start, count=page_size)
        if items_df.empty:
            return pd.DataFrame()
        stocks: list[tuple[int, str]] = [(market, row["code"]) for _, row in items_df.iterrows()]
        cmd = SymbolQuotesCmd(stocks)
        result: list[MacQuoteField] = await self._execute(cmd)
        return _quotes_to_df(result)

    # ------------------------------------------------------------------ #
    # K 线
    # ------------------------------------------------------------------ #

    async def goods_kline(
        self,
        market: int,
        code: str,
        period: Period = Period.DAILY,
        start: int = 0,
        count: int = 800,
        adjust: Adjust = Adjust.NONE,
    ) -> pd.DataFrame:
        cmd = SymbolBarCmd(
            market=market,
            code=code,
            period=period,
            start=start,
            count=count,
            fq=adjust,
        )
        result = await self._execute(cmd)
        return _to_df(result)

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    async def goods_tick_chart(
        self,
        market: int,
        code: str,
        query_date: date = None,
    ) -> pd.DataFrame:
        cmd = SymbolTickChartCmd(market=market, code=code, query_date=query_date)
        result = await self._execute(cmd)
        return _to_df(result)

    async def goods_chart_sampling(
        self,
        market: int,
        code: str,
    ) -> pd.DataFrame:
        cmd = ChartSamplingCmd(market=market, code=code)
        prices: list[float] = await self._execute(cmd)
        if not prices:
            return pd.DataFrame()
        return pd.DataFrame({"price": prices})

    # ------------------------------------------------------------------ #
    # 成交
    # ------------------------------------------------------------------ #

    async def goods_transaction(
        self,
        market: int,
        code: str,
        query_date: date = None,
        start: int = 0,
        count: int = 2000,
    ) -> pd.DataFrame:
        cmd = SymbolTransactionCmd(
            market=market,
            code=code,
            query_date=query_date,
            start=start,
            count=count,
        )
        result = await self._execute(cmd)
        return _to_df(result)
