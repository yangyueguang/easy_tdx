"""除权除息信息命令。

修复 pytdx Bug #1：循环内从正确的 pos 位置读取 market/code，
不再始终读取 body[:7]。
"""
from codec import _decode_volume
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from typing import Final
"""同步 TCP 连接（基于 socket）。"""

import socket
import threading
import time
import asyncio
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar
from codec import *

T = TypeVar("T")
"""握手命令原始字节（从 pytdx/parser/setup_commands.py 移植，已在真实服务器验证）。

连接建立后必须按序发送三条握手命令，每条均需读取并丢弃响应。
"""


# 从 pytdx 源码原文复制，去除空格
SETUP_CMD1: Final[bytes] = bytes.fromhex("0c0218930001030003000d0001")
SETUP_CMD2: Final[bytes] = bytes.fromhex("0c0218940001030003000d0002")
SETUP_CMD3: Final[bytes] = bytes.fromhex("0c031899000120002000db0fd5d0c9ccd6a4a8af0000008fc22540130000d500c9ccbdf0d7ea00000002")

SETUP_COMMANDS: Final[tuple[bytes, ...]] = (SETUP_CMD1, SETUP_CMD2, SETUP_CMD3)
"""获取实时五档行情命令（最多 80 只/次）。

所有未知字段（unknown_N）保留原始解析值，供逆向分析。
"""


"""获取证券列表命令（每页最多1000条，按 start 分页）。

修复 pytdx Bug #2：GBK 解码使用 errors='replace'，截断多字节序列不再崩溃。
修复 pytdx Bug #3：pre_close 保持使用通达信自定义浮点解码。
"""


_RECORD_SIZE = 29
"""获取市场股票/证券总数命令。"""

"""今日分时 / 历史分时数据命令。

unknown_1 字段：pytdx 中被完全丢弃，保留供分析（疑似均价）。
"""


# 财务字段 struct 格式：1f + 2H + 2I + 30f
_FIN_FMT = "<fHHII" + "f" * 30
_FIN_SIZE = struct.calcsize(_FIN_FMT)

"""公司信息目录与内容命令。"""


"""板块信息获取命令（元数据获取与分片下载）。

板块文件（如 block_zs.dat）包含行业、概念、风格等 A 股分类信息。
"""
"""命令基类：只含请求构造与响应解析，不含任何 IO。

transport 层负责：发送请求、接收帧头、接收 body、解压，
然后调用 command.parse_response(body) 得到结果。
"""


"""easy-tdx 异常层次"""


class TdxError(Exception):
    """所有 easy-tdx 异常的基类"""


class TdxConnectionError(TdxError):
    """TCP 连接失败或超时"""


class TdxDecodeError(TdxError):
    """响应报文解析失败"""


class TdxCommandError(TdxError):
    """命令执行失败（服务器返回错误）"""


class TdxFileNotFoundError(TdxError):
    """本地数据文件不存在"""


class TdxOfflineError(TdxError):
    """离线数据读取失败（路径未配置、文件格式错误等）"""

"""集中管理服务器地址、端口、超时等配置。

优先级：环境变量 > ~/.easy_tdx/config.json > 源码内嵌默认值。

配置文件示例::

    {
      "best_host": "180.153.18.170", "best_host_updated_at": "2026-05-22T10:30:00", "known_hosts": ["111.229.247.189", ...], "calc_hosts": ["120.76.152.87"], "mac_hosts": ["121.36.248.138", ...], "port": 7709, "timeout": 15.0
    }

环境变量覆盖::

    EASY_TDX_HOST        -- 单台主机地址
    EASY_TDX_PORT        -- 端口
    EASY_TDX_TIMEOUT     -- 超时秒数
    EASY_TDX_KNOWN_HOSTS -- 逗号分隔的候选主机列表
    EASY_TDX_CONFIG_DIR  -- 配置文件目录（默认 ~/.easy_tdx）
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

_CONFIG_DIR = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# 源码内嵌默认值（config.json 不存在或字段缺失时的兜底）
# ---------------------------------------------------------------------------

_FALLBACK_HOSTS: list[str] = [
    "111.229.247.189", "150.158.160.2", "180.153.18.170", "124.71.187.122", "180.153.18.171", "180.153.18.172", "119.147.212.81", "115.238.56.198", "115.238.90.165", "218.75.126.9", "47.107.75.159", "59.175.238.38", "110.41.147.114", "110.41.2.72", "101.33.225.16", "175.178.112.197", "175.178.128.227", "43.139.95.83", "124.223.163.242", "122.51.120.217", "123.60.164.122", "124.70.199.56", "62.234.50.143", "81.70.151.186", "82.156.214.79", "159.75.29.111", "43.139.18.171", "81.71.32.47", "122.51.232.182", "118.25.98.114", "121.36.225.169", "123.60.70.228", "123.60.73.44", "124.70.133.119", "124.71.187.72", "119.97.185.59", "129.204.230.128", "101.42.240.54", "124.71.9.153", "123.60.84.66", "111.230.186.52", "101.43.159.194", "120.53.8.251", "152.136.191.169", "116.205.163.254", "116.205.171.132", "116.205.183.150", "49.232.15.141", "82.156.174.84", "101.42.164.241", "101.35.121.35", "111.231.113.208", ]

_FALLBACK_CALC_HOSTS: list[str] = [
    "120.76.152.87", ]

_FALLBACK_MAC_HOSTS: list[str] = [
    "121.36.248.138", "123.60.47.136", "121.37.207.165", ]

_FALLBACK_EX_HOSTS: list[str] = [
    "112.74.214.43", "120.25.218.6", "43.139.173.246", "159.75.90.107", "106.52.170.195", "139.9.191.175", "175.24.47.69", "150.158.9.199", "150.158.20.127", "49.235.119.116", "49.234.13.160", "116.205.143.214", "124.71.223.19", "113.45.175.47", "123.60.173.210", "118.89.69.202", ]

_FALLBACK_MAC_EX_HOSTS: list[str] = [
    "116.205.135.205", "121.37.232.167", ]

_FALLBACK_PORT = 7709
_FALLBACK_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# 内部读写
# ---------------------------------------------------------------------------


def _load() -> dict[str, Any]:
    try:
        if _CONFIG_FILE.exists():
            return cast(dict[str, Any], json.loads(_CONFIG_FILE.read_text("utf-8")))
    except Exception:
        pass
    return {}


def _save(data: dict[str, Any]):
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(_CONFIG_FILE)


# ---------------------------------------------------------------------------
# 公开 getter
# ---------------------------------------------------------------------------


def get_best_host() -> str:
    """返回当前最佳主机地址。优先级：环境变量 > config.json > 默认列表首个。"""
    env = os.environ.get("EASY_TDX_HOST")
    if env:
        return env
    cfg = _load()
    return cast(str, cfg.get("best_host", _FALLBACK_HOSTS[0]))


def get_known_hosts() -> list[str]:
    """返回候选行情主机列表。"""
    env = os.environ.get("EASY_TDX_KNOWN_HOSTS")
    if env:
        return [h.strip() for h in env.split(",") if h.strip()]
    cfg = _load()
    return cast(list[str], cfg.get("known_hosts", list(_FALLBACK_HOSTS)))


def get_calc_hosts() -> list[str]:
    """返回计算服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("calc_hosts", list(_FALLBACK_CALC_HOSTS)))


def get_mac_hosts() -> list[str]:
    """返回 MAC 行情服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("mac_hosts", list(_FALLBACK_MAC_HOSTS)))


def get_ex_hosts() -> list[str]:
    """返回扩展行情服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("ex_hosts", list(_FALLBACK_EX_HOSTS)))


def get_best_ex_host() -> str:
    """返回当前最佳扩展行情主机。"""
    env = os.environ.get("EASY_TDX_EX_HOST")
    if env:
        return env
    cfg = _load()
    return cast(str, cfg.get("best_ex_host", _FALLBACK_EX_HOSTS[0]))


def get_mac_ex_hosts() -> list[str]:
    """返回 MAC 协议扩展行情服务器列表。"""
    cfg = _load()
    return cast(list[str], cfg.get("mac_ex_hosts", list(_FALLBACK_MAC_EX_HOSTS)))


def get_best_mac_ex_host() -> str:
    """返回当前最佳 MAC 协议扩展行情主机。"""
    env = os.environ.get("EASY_TDX_MAC_EX_HOST")
    if env:
        return env
    cfg = _load()
    return cast(str, cfg.get("best_mac_ex_host", _FALLBACK_MAC_EX_HOSTS[0]))


def get_port() -> int:
    """返回默认端口。"""
    env = os.environ.get("EASY_TDX_PORT")
    if env:
        return int(env)
    cfg = _load()
    return cast(int, cfg.get("port", _FALLBACK_PORT))


def get_timeout() -> float:
    """返回默认超时秒数。"""
    env = os.environ.get("EASY_TDX_TIMEOUT")
    if env:
        return float(env)
    cfg = _load()
    return cast(float, cfg.get("timeout", _FALLBACK_TIMEOUT))


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def save_best_host(host: str):
    """保存最佳主机到配置文件；首次写入时同时补全默认配置。"""
    cfg = _load()
    cfg["best_host"] = host
    cfg["best_host_updated_at"] = datetime.now().isoformat()
    if "known_hosts" not in cfg:
        cfg["known_hosts"] = list(_FALLBACK_HOSTS)
    if "calc_hosts" not in cfg:
        cfg["calc_hosts"] = list(_FALLBACK_CALC_HOSTS)
    if "mac_hosts" not in cfg:
        cfg["mac_hosts"] = list(_FALLBACK_MAC_HOSTS)
    if "port" not in cfg:
        cfg["port"] = _FALLBACK_PORT
    if "ex_hosts" not in cfg:
        cfg["ex_hosts"] = list(_FALLBACK_EX_HOSTS)
    if "mac_ex_hosts" not in cfg:
        cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)
    _save(cfg)


def save_best_ex_host(host: str):
    """保存最佳扩展行情主机到配置文件。"""
    cfg = _load()
    cfg["best_ex_host"] = host
    cfg["best_ex_host_updated_at"] = datetime.now().isoformat()
    if "ex_hosts" not in cfg:
        cfg["ex_hosts"] = list(_FALLBACK_EX_HOSTS)
    if "mac_ex_hosts" not in cfg:
        cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)
    _save(cfg)


def save_best_mac_ex_host(host: str):
    """保存最佳 MAC 协议扩展行情主机到配置文件。"""
    cfg = _load()
    cfg["best_mac_ex_host"] = host
    cfg["best_mac_ex_host_updated_at"] = datetime.now().isoformat()
    if "mac_ex_hosts" not in cfg:
        cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)
    _save(cfg)

_DEFAULT_HEARTBEAT_INTERVAL = 15.0
_MAX_CONSECUTIVE_HEARTBEATS = 20

# 在 import 时从配置读取一次；用户修改 config.json 后需重启生效。
KNOWN_HOSTS = get_known_hosts()
CALC_HOSTS = get_calc_hosts()
MAC_HOSTS = get_mac_hosts()


def ping_host(host: str, port: int = None, timeout: float = 5.0) -> float:
    """测量连接到指定服务器并完成握手所需的时间（秒）。

    返回延迟（秒），连接失败时返回 None。
    """
    if port is None:
        port = get_port()
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        # 发送第一条握手命令并等待响应作为可用性验证
        sock.sendall(SETUP_COMMANDS[0])
        hdr_buf = _recv_exact_sock(sock, HEADER_SIZE)
        hdr = parse_header(hdr_buf)
        if hdr.zipsize > 0:
            _recv_exact_sock(sock, hdr.zipsize)
        return time.monotonic() - t0
    except (OSError, TdxConnectionError):
        # OSError: 连接/超时层失败；TdxConnectionError: 握手期服务器关闭连接
        # （_recv_exact_sock 抛出，继承自 TdxError 而非 OSError）。
        # 两者均属"服务器不可用"，按 docstring 返回 None，不拖垮整个 ping_all。
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def ping_all(hosts: list[str] = None, port: int = None, timeout: float = 5.0) -> list[tuple[str, float]]:
    """并发测量多台服务器延迟，返回按延迟排序的 (host, latency_seconds) 列表。

    不可达的服务器不包含在结果中。
    """
    if hosts is None:
        hosts = get_known_hosts()
    if port is None:
        port = get_port()
    import concurrent.futures

    results: list[tuple[str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {pool.submit(ping_host, h, port, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            host = futures[fut]
            try:
                latency = fut.result()
            except Exception:
                # 防御层：即使 ping_host 因意外原因抛异常，也只跳过该 host，
                # 不让单个服务器拖垮整个 ping_all / `easy-tdx ping` 命令。
                continue
            if latency is not None:
                results.append((host, latency))
    results.sort(key=lambda t: t[1])
    return results


def ping_mac_all(hosts: list[str] = None, port: int = None, timeout: float = 5.0) -> list[tuple[str, float]]:
    """并发测量多台 MAC 服务器延迟，返回按延迟排序的 (host, latency_seconds) 列表。"""
    if hosts is None:
        hosts = get_mac_hosts()
    return ping_all(hosts=hosts, port=port, timeout=timeout)


def _recv_exact_sock(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise TdxConnectionError("连接被服务器关闭")
        buf.extend(chunk)
    return bytes(buf)


class TdxConnection:
    """同步通达信 TCP 连接。

    使用示例::

        with TdxConnection("180.153.18.170") as conn:
            result = conn.execute(SomeCommand(...))
    """

    def __init__(self, host: str = None, port: int = None, timeout: float = None):
        self.host = host if host is not None else get_best_host()
        self.port = port if port is not None else get_port()
        self.timeout = timeout if timeout is not None else get_timeout()
        self._sock: socket.socket = None
        self._lock = threading.Lock()
        self._heartbeat_interval: float = 0  # 0 = disabled
        self._stop_event: threading.Event = None
        self._heartbeat_thread: threading.Thread = None
        self._last_active: float = 0.0
        self._consecutive_heartbeats: int = 0

    def connect(self):
        """建立 TCP 连接并完成握手（发送3条 setup 命令）。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as e:
            sock.close()
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
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

    def close(self):
        """关闭连接。"""
        self.stop_heartbeat()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        with self._lock:
            self._last_active = time.monotonic()
            self._consecutive_heartbeats = 0
            if self._sock is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            request = cmd.build_request()
            try:
                self._sock.sendall(request)
                header_buf = self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = self._recv_exact(header.zipsize)
            except OSError as e:
                raise TdxConnectionError(f"通信错误: {e}") from e
            body = decompress_body(header, raw_body)
            return cmd.parse_response(body)

    # ------------------------------------------------------------------ #
    # context manager
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "TdxConnection":
        self.connect()
        return self

    def __exit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        self.close()

    # ------------------------------------------------------------------ #
    # heartbeat
    # ------------------------------------------------------------------ #

    def start_heartbeat(self, interval: float = _DEFAULT_HEARTBEAT_INTERVAL):
        """启动心跳守护线程，定期发送 setup 包保活。"""
        self._heartbeat_interval = interval
        self._last_active = time.monotonic()
        self._stop_event = threading.Event()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="tdx-heartbeat")
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        """停止心跳线程。"""
        stop_event = self._stop_event
        thread = self._heartbeat_thread
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)
        self._stop_event = None
        self._heartbeat_thread = None
        self._heartbeat_interval = 0

    def _heartbeat_loop(self):
        """心跳循环：在后台线程中运行。"""
        assert self._stop_event is not None
        interval = self._heartbeat_interval
        while not self._stop_event.wait(timeout=interval):
            if time.monotonic() - self._last_active <= interval:
                continue
            with self._lock:
                if self._sock is None:
                    return
                self._consecutive_heartbeats += 1
                if self._consecutive_heartbeats >= _MAX_CONSECUTIVE_HEARTBEATS:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
                    return
                try:
                    self._sock.sendall(SETUP_COMMANDS[0])
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

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _send_setup(self):
        """按序发送三条握手命令并丢弃响应。"""
        assert self._sock is not None
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

"""异步 TCP 连接（基于 asyncio）。"""




class AsyncTdxConnection:
    """异步通达信 TCP 连接（asyncio）。

    使用示例::

        async with AsyncTdxConnection("180.153.18.170") as conn:
            result = await conn.execute(SomeCommand(...))
    """

    def __init__(self, host: str = None, port: int = None, timeout: float = None):
        self.host = host if host is not None else get_best_host()
        self.port = port if port is not None else get_port()
        self.timeout = timeout if timeout is not None else get_timeout()
        self._reader: asyncio.StreamReader = None
        self._writer: asyncio.StreamWriter = None
        # 单连接不支持请求复用；所有 IO 在连接内串行执行。
        self._io_lock = asyncio.Lock()

    async def connect(self):
        """建立 TCP 连接并完成握手。"""
        async with self._io_lock:
            if self._writer is not None and not self._writer.is_closing():
                return
            await self._connect_unlocked()

    async def close(self):
        """关闭连接。"""
        async with self._io_lock:
            await self._close_unlocked()

    async def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令（异步版本）。

        同一连接上的并发调用会在此处串行化，避免 StreamReader 并发读取冲突。
        """
        async with self._io_lock:
            if self._writer is None or self._reader is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            request = cmd.build_request()
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

    async def _connect_unlocked(self):
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout=self.timeout)
        except (OSError, asyncio.TimeoutError) as e:
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._reader = reader
        self._writer = writer
        try:
            await self._send_setup()
        except Exception:
            await self._close_unlocked()
            raise

    async def _close_unlocked(self):
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            self._reader = None
            self._writer = None

    # ------------------------------------------------------------------ #
    # context manager
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "AsyncTdxConnection":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: type[BaseException], exc_val: BaseException, exc_tb: TracebackType):
        await self.close()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    async def _send_setup(self):
        """按序发送三条握手命令并丢弃响应。"""
        assert self._writer is not None
        assert self._reader is not None
        for cmd_bytes in SETUP_COMMANDS:
            self._writer.write(cmd_bytes)
            await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
            try:
                hdr_buf = await self._recv_exact(HEADER_SIZE)
                hdr = parse_header(hdr_buf)
                if hdr.zipsize > 0:
                    await self._recv_exact(hdr.zipsize)
            except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
                pass

    async def _recv_exact(self, n: int) -> bytes:
        """读满 n 字节。"""
        assert self._reader is not None
        data = await asyncio.wait_for(self._reader.readexactly(n), timeout=self.timeout)
        return data

class BaseCommand(ABC, Generic[T]):
    """所有行情命令的基类。

    子类实现：
      build_request()  → 返回要发送的原始字节
      parse_response() → 从解压后的 body 返回强类型结果
    """

    @abstractmethod
    def build_request(self) -> bytes:
        """构造请求包（含完整帧头）。"""
        ...

    @abstractmethod
    def parse_response(self, body: bytes) -> T:
        """解析解压后的响应 body，返回强类型结果。"""
        ...


class GetBlockInfoMetaCmd(BaseCommand[tuple[int, str]]):
    """获取板块文件的元数据（大小与 MD5 哈希）。

    Args:
        filename: 板块文件名，如 'block_zs.dat', 'block_gn.dat' 等。
    """

    def __init__(self, filename: str):
        self.filename = filename.encode("ascii")

    def build_request(self) -> bytes:
        # 固定头 12 字节
        header = bytes.fromhex("0c39186900012a002a00c502")
        # Payload 为文件名
        payload = (self.filename + b"\x00" * 40)[:40]
        return header + payload

    def parse_response(self, body: bytes) -> tuple[int, str]:
        if len(body) < 38:
            raise TdxDecodeError(f"GetBlockInfoMeta 响应过短: {len(body)}")

        size, _, hash_b, _ = struct.unpack("<I1s32s1s", body[:38])
        return size, hash_b.decode("ascii").strip("\x00")


class GetBlockInfoCmd(BaseCommand[bytes]):
    """分段获取板块文件二进制内容。

    Args:
        filename: 板块文件名。
        start: 起始偏移量（字节）。
        length: 请求数据长度。
    """

    def __init__(self, filename: str, start: int, length: int):
        self.filename = filename.encode("ascii")
        self.start = start
        self.length = length

    def build_request(self) -> bytes:
        # 固定头 12 字节
        header = bytes.fromhex("0c37186a00016e006e00b906")
        payload = struct.pack("<II", self.start, self.length)
        payload += (self.filename + b"\x00" * 100)[:100]
        return header + payload

    def parse_response(self, body: bytes) -> bytes:
        if len(body) < 4:
            return b""
        return body[4:]

class GetCompanyInfoCategoryCmd(BaseCommand[list[CompanyInfoCategory]]):
    """获取公司信息文件目录（文件名列表 + 每段偏移/长度）。"""

    def __init__(self, market: Market, code: str):
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c0f109b00010e000e00cf02".replace(" ", ""))
        return header + struct.pack("<H6sI", int(self.market), self.code, 0)

    def parse_response(self, body: bytes) -> list[CompanyInfoCategory]:
        if len(body) < 2:
            raise TdxDecodeError("company_info_category body 过短")
        (num,) = unpack_from("<H", body, 0, "company_info_category header")
        pos = 2
        results: list[CompanyInfoCategory] = []

        # 每条记录：64字节name + 80字节filename + 4字节start + 4字节length = 152字节
        _RECORD_SIZE = 152
        for _ in range(num):
            raw = slice_bytes(body, pos, _RECORD_SIZE, "company_info_category record")
            name_b, filename_b, start, length = struct.unpack("<64s80sII", raw)
            pos += _RECORD_SIZE

            def _decode(b: bytes) -> str:
                nul = b.find(b"\x00")
                raw = b[:nul] if nul != -1 else b
                return raw.decode("gbk", errors="replace")

            results.append(CompanyInfoCategory(name=_decode(name_b), filename=_decode(filename_b), start=start, length=length))

        return results


class GetCompanyInfoContentCmd(BaseCommand[str]):
    """按文件名、偏移、长度读取公司信息文本（GBK 编码）。"""

    def __init__(self, market: Market, code: str, filename: str, offset: int, length: int):
        self.market = market
        self.code = code.encode("utf-8")
        self.filename = filename.encode("gbk")
        self.offset = offset
        self.length = length

    def build_request(self) -> bytes:
        fname_padded = (self.filename + b"\x00" * 80)[:80]
        header = bytes.fromhex("0c07109c0001680068 00d002".replace(" ", ""))
        return header + struct.pack("<H6sH80sIII", int(self.market), self.code, 0, fname_padded, self.offset, self.length, 0)

    def parse_response(self, body: bytes) -> str:
        # 前12字节：10字节未知 + 2字节长度
        if len(body) < 12:
            raise TdxDecodeError("company_info_content body 过短")
        _, length = unpack_from("<10sH", body, 0, "company_info_content header")
        content = slice_bytes(body, 12, length, "company_info_content body")
        return content.decode("gbk", errors="replace")

class GetFinanceInfoCmd(BaseCommand[FinanceInfo]):
    """获取单只股票最新财务数据。"""

    def __init__(self, market: Market, code: str):
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c1f18760001 0b000b001000 0100".replace(" ", ""))
        return header + struct.pack("<B6s", int(self.market), self.code)

    def parse_response(self, body: bytes) -> FinanceInfo:
        pos = 2  # 跳过前2字节（记录数）
        market_b, code_b = unpack_from("<B6s", body, pos, "finance_info header")
        pos += 7

        fields = struct.unpack(_FIN_FMT, slice_bytes(body, pos, _FIN_SIZE, "finance_info body"))
        (liutong_guben, province, industry, updated_date, ipo_date, zong_guben, guojia_gu, faqiren_faren_gu, faren_gu, b_gu, h_gu, zhigong_gu, zong_zichan, liudong_zichan, guding_zichan, wuxing_zichan, gudong_renshu, liudong_fuzhai, changqi_fuzhai, ziben_gongjijin, jing_zichan, zhuying_shouru, zhuying_lirun, yingshou_zhangkuan, yingye_lirun, touzi_shouyu, jingying_xianjinliu, zong_xianjinliu, cunhuo, lirun_zonghe, shuihou_lirun, jing_lirun, weifen_lirun, meigujing_zichan, reserve2) = fields

        _SCALE = 10000.0  # 财务数据单位：万元/万股
        try:
            market = Market(market_b)
        except ValueError as e:
            raise TdxDecodeError(f"finance_info 非法 market 值: {market_b}") from e

        return FinanceInfo(market=market, code=code_b.decode("utf-8").rstrip("\x00"), liutong_guben=liutong_guben * _SCALE, zong_guben=zong_guben * _SCALE, guojia_gu=guojia_gu * _SCALE, faqiren_faren_gu=faqiren_faren_gu * _SCALE, faren_gu=faren_gu * _SCALE, b_gu=b_gu * _SCALE, h_gu=h_gu * _SCALE, zhigong_gu=zhigong_gu * _SCALE, province=province, industry=industry, updated_date=updated_date, ipo_date=ipo_date, gudong_renshu=gudong_renshu, zong_zichan=zong_zichan * _SCALE, liudong_zichan=liudong_zichan * _SCALE, guding_zichan=guding_zichan * _SCALE, wuxing_zichan=wuxing_zichan * _SCALE, liudong_fuzhai=liudong_fuzhai * _SCALE, changqi_fuzhai=changqi_fuzhai * _SCALE, ziben_gongjijin=ziben_gongjijin * _SCALE, jing_zichan=jing_zichan * _SCALE, zhuying_shouru=zhuying_shouru * _SCALE, zhuying_lirun=zhuying_lirun * _SCALE, yingshou_zhangkuan=yingshou_zhangkuan * _SCALE, yingye_lirun=yingye_lirun * _SCALE, touzi_shouyu=touzi_shouyu * _SCALE, jingying_xianjinliu=jingying_xianjinliu * _SCALE, zong_xianjinliu=zong_xianjinliu * _SCALE, cunhuo=cunhuo * _SCALE, lirun_zonghe=lirun_zonghe * _SCALE, shuihou_lirun=shuihou_lirun * _SCALE, jing_lirun=jing_lirun * _SCALE, weifen_lirun=weifen_lirun * _SCALE, meigujing_zichan=meigujing_zichan, reserve2=reserve2, _raw=body[pos : pos + _FIN_SIZE])


class GetHistoryFundFlowCmd(BaseCommand[list[HistoricalFundFlow]]):
    """获取历史日线资金流向序列。"""

    def __init__(self, market: Market, code: str, start: int, count: int):
        self.market = market
        self.code = code.encode("utf-8")
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # Header (12 bytes) + Payload (28 bytes) = 40 bytes
        return struct.pack("<HIHHHH6sHHHHIIH", 0x010C, 0x01016408, 0x001C, 0x001C, 0x052D, int(self.market), self.code, 22, 1, self.start, self.count, 0, 0, 0)

    def parse_response(self, body: bytes) -> list[HistoricalFundFlow]:
        # 响应格式：9字节头 + 2字节数量 + 每条记录 36 字节
        if len(body) < 11:
            return []

        (num,) = struct.unpack("<H", body[9:11])
        pos = 11
        results = []

        for _ in range(num):
            if len(body) < pos + 36:
                break

            # 记录格式：4字节日期 + 8个4字节自定义浮点金额
            # [0]日期, [1..4]流入(超/大/中/小), [5..8]流出(超/大/中/小)
            raw_data = struct.unpack("<IIIIIIIII", body[pos : pos + 36])

            raw_date = raw_data[0]
            year = raw_date // 10000
            month = (raw_date // 100) % 100
            day = raw_date % 100

            results.append(HistoricalFundFlow(year=year, month=month, day=day, super_in=_decode_volume(raw_data[1]), large_in=_decode_volume(raw_data[2]), medium_in=_decode_volume(raw_data[3]), small_in=_decode_volume(raw_data[4]), super_out=_decode_volume(raw_data[5]), large_out=_decode_volume(raw_data[6]), medium_out=_decode_volume(raw_data[7]), small_out=_decode_volume(raw_data[8])))
            pos += 36

        return results

class GetMinuteTimeDataCmd(BaseCommand[list[MinuteBar]]):
    """获取今日分时数据（全天 240 条）。"""

    def __init__(self, market: Market, code: str):
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c1b08000101 0e000e001d05".replace(" ", ""))
        return header + struct.pack("<H6sI", int(self.market), self.code, 0)

    def parse_response(self, body: bytes) -> list[MinuteBar]:
        return _parse_minute_body(body, skip=4)


class GetHistoryMinuteTimeDataCmd(BaseCommand[list[MinuteBar]]):
    """获取历史某日分时数据（date 格式 YYYYMMDD）。"""

    def __init__(self, market: Market, code: str, date: int):
        self.market = market
        self.code = code.encode("utf-8")
        self.date = date

    def build_request(self) -> bytes:
        # 历史分时：header + pack("<IB6s", date, market, code)
        header = bytes.fromhex("0c013000010 10d000d00b40f".replace(" ", ""))
        return header + struct.pack("<IB6s", self.date, int(self.market), self.code)

    def parse_response(self, body: bytes) -> list[MinuteBar]:
        # 历史分时：pytdx 中 pos 跳过 6 字节（2 num + 4 未知）
        return _parse_minute_body(body, skip=6)


def _parse_minute_body(body: bytes, skip: int = 4) -> list[MinuteBar]:
    (num,) = unpack_from("<H", body, 0, "minute_time header")
    pos = skip  # 今日分时 skip=4，历史分时 skip=6
    last_price = 0
    bars: list[MinuteBar] = []

    for _ in range(num):
        record_start = pos
        price_diff, pos = get_price(body, pos)
        unknown_1, pos = get_price(body, pos)  # pytdx 原丢弃，保留
        vol, pos = get_price(body, pos)

        last_price += price_diff
        bars.append(MinuteBar(price=last_price / 100.0, vol=vol, _unknown_1=unknown_1, _raw=body[record_start:pos]))

    return bars

class GetReportFileCmd(BaseCommand[bytes]):
    """分段获取服务器上的报表或基础信息文件。

    Args:
        filename: 远程文件名。
        start: 起始偏移量。
        length: 请求数据长度（建议 30000）。
    """

    def __init__(self, filename: str, start: int, length: int = 30000):
        self.filename = filename.encode("ascii")
        self.start = start
        self.length = length

    def build_request(self) -> bytes:
        # 使用与 GetBlockInfo 相同的格式：0x06B9
        header = bytes.fromhex("0c37186a00016e006e00b906")
        payload = struct.pack("<II", self.start, self.length)
        payload += (self.filename + b"\x00" * 100)[:100]
        return header + payload

    def parse_response(self, body: bytes) -> bytes:
        if len(body) < 4:
            return b""
        return body[4:]


class GetSecurityBarsCmd(BaseCommand[list[SecurityBar]]):
    """获取指定股票的 K 线数据。

    Args:
        market:   市场（SH/SZ）
        code:     6位股票代码（字符串）
        category: K线周期
        start:    起始行（0 = 最新；分页时递增）
        count:    返回条数（最多 800）
    """

    def __init__(self, market: Market, code: str, category: KlineCategory, start: int, count: int = 800):
        self.market = market
        self.code = code.encode("utf-8")
        self.category = category
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # Header (12 bytes) + Payload (28 bytes) = 40 bytes
        return struct.pack("<HIHHHH6sHHHHIIH", 0x010C, 0x01016408, 0x001C, 0x001C, 0x052D, int(self.market), self.code, int(self.category), 1, self.start, self.count, 0, 0, 0)

    def parse_response(self, body: bytes) -> list[SecurityBar]:
        (ret_count,) = unpack_from("<H", body, 0, "security_bars header")
        pos = 2
        bars: list[SecurityBar] = []
        pre_diff_base = 0
        cat = int(self.category)

        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(cat, body, pos)

            open_diff, pos = get_price(body, pos)
            close_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            vol, pos = get_volume(body, pos)
            amount, pos = get_volume(body, pos)

            # 差分还原（与 pytdx 完全一致）
            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = open_abs + close_diff

            bars.append(SecurityBar(open=open_abs / 1000.0, close=close_abs / 1000.0, high=high_abs / 1000.0, low=low_abs / 1000.0, vol=vol, amount=amount, year=year, month=month, day=day, hour=hour, minute=minute, _raw=body[record_start:pos]))

        return bars


class GetIndexBarsCmd(GetSecurityBarsCmd):
    """获取指数 K 线。

    请求格式与股票 K 线相同，但响应每条记录在 vol+amt 后多 4 字节
    （上涨家数 uint16 + 下跌家数 uint16），必须跳过否则后续记录错位。
    """

    def parse_response(self, body: bytes) -> list[SecurityBar]:
        (ret_count,) = unpack_from("<H", body, 0, "security_bars header")
        pos = 2
        bars: list[SecurityBar] = []
        pre_diff_base = 0
        cat = int(self.category)

        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(cat, body, pos)

            open_diff, pos = get_price(body, pos)
            close_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            vol, pos = get_volume(body, pos)
            amount, pos = get_volume(body, pos)

            # 指数记录额外 4 字节：上涨家数 + 下跌家数（各 uint16 LE）
            pos += 4

            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = open_abs + close_diff

            bars.append(SecurityBar(open=open_abs / 1000.0, close=close_abs / 1000.0, high=high_abs / 1000.0, low=low_abs / 1000.0, vol=vol, amount=amount, year=year, month=month, day=day, hour=hour, minute=minute, _raw=body[record_start:pos]))

        return bars

class GetSecurityCountCmd(BaseCommand[int]):
    """返回指定市场的证券总数。

    心跳命令也可复用此命令（pytdx 用随机 market 发心跳）。
    """

    def __init__(self, market: Market):
        self.market = market

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c0c186c000108000800 4e04".replace(" ", ""))
        return header + struct.pack("<H", int(self.market)) + b"\x75\xc7\x33\x01"

    def parse_response(self, body: bytes) -> int:
        (count,) = unpack_from("<H", body, 0, "security_count")
        return int(count)


class GetSecurityListCmd(BaseCommand[list[SecurityInfo]]):
    """获取指定市场从 start 开始的证券列表。"""

    def __init__(self, market: Market, start: int):
        self.market = market
        self.start = start

    def build_request(self) -> bytes:
        # Header (12 bytes) + Payload (6 bytes) = 18 bytes
        # Payload: Market(H), Start(H), Unknown(H)=0
        header = bytes.fromhex("0c0118640101060006005004".replace(" ", ""))
        return header + struct.pack("<HHH", int(self.market), self.start, 0)

    def parse_response(self, body: bytes) -> list[SecurityInfo]:
        (num,) = unpack_from("<H", body, 0, "security_list header")
        pos = 2
        results: list[SecurityInfo] = []

        for _ in range(num):
            raw = slice_bytes(body, pos, _RECORD_SIZE, "security_list record")
            (code_bytes, volunit, name_bytes, _unknown1,  # 4字节，排序/分组字段（非用户可见数据）
                decimal_point, pre_close_raw, _unknown2,  # 4字节，私有时间戳（非用户可见数据）) = struct.unpack("<6sH8s4sBI4s", raw)

            code = code_bytes.decode("utf-8", errors="replace").rstrip("\x00")
            # Bug #2 修复：errors='replace' 避免截断 GBK 多字节序列时崩溃
            name = name_bytes.decode("gbk", errors="replace").rstrip("\x00")

            # pre_close_raw 与协议里的成交量/股本字段一样，使用通达信自定义浮点编码。
            pre_close = _decode_volume(pre_close_raw)

            results.append(SecurityInfo(market=self.market, code=code, name=name, volunit=volunit, decimal_point=decimal_point, pre_close=pre_close, _raw=raw))
            pos += _RECORD_SIZE

        return results

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


class GetSecurityQuotesCmd(BaseCommand[list[SecurityQuote]]):
    """批量获取实时行情（最多 80 只）。

    Args:
        stocks: [(market, code), ...] 列表
    """

    def __init__(self, stocks: list[tuple[Market, str]]):
        if not stocks:
            raise ValueError("stocks 不能为空")
        if len(stocks) > 80:
            raise ValueError("单次最多查询 80 只股票")
        self.stocks = stocks

    def build_request(self) -> bytes:
        n = len(self.stocks)
        payload_len = n * 7 + 12
        header = struct.pack("<HIHHIIHH", 0x010C, 0x02006320, payload_len, payload_len, 0x0005053E, 0, 0, n)
        body = bytearray(header)
        for market, code in self.stocks:
            body.extend(struct.pack("<B6s", int(market), code.encode("utf-8")))
        return bytes(body)

    def parse_response(self, body: bytes) -> list[SecurityQuote]:
        pos = 0
        # pytdx 跳过前2字节（b1 cb 魔数）
        pos += 2
        (num,) = unpack_from("<H", body, pos, "security_quotes header")
        pos += 2

        results: list[SecurityQuote] = []

        for _ in range(num):
            record_start = pos

            market_b, code_b, active1 = unpack_from("<B6sH", body, pos, "security_quotes record header")
            pos += 9

            price_raw, pos = get_price(body, pos)
            last_close_diff, pos = get_price(body, pos)
            open_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            # unknown_0: 服务器时间戳原始整数（get_price 解码）
            unknown_0, pos = get_price(body, pos)
            # unknown_1: 通常等于 -price_raw（pytdx 注释推测）
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

            # 尾部：2字节 H（交易状态标志，0x8020=停牌）+ 4个 get_price + 2字节 h + 2字节 H
            (trading_status,) = unpack_from("<H", body, pos, "security_quotes tail flag")
            pos += 2
            unknown_5, pos = get_price(body, pos)
            unknown_6, pos = get_price(body, pos)
            unknown_7, pos = get_price(body, pos)
            unknown_8, pos = get_price(body, pos)
            rise_speed_raw, active2 = unpack_from("<hH", body, pos, "security_quotes tail")
            pos += 4

            p = price_raw / 100.0
            try:
                market = Market(market_b)
            except ValueError as e:
                raise TdxDecodeError(f"security_quotes 非法 market 值: {market_b}") from e

            results.append(SecurityQuote(market=market, code=code_b.decode("utf-8").rstrip("\x00"), price=p, pre_close=(price_raw + last_close_diff) / 100.0, open=(price_raw + open_diff) / 100.0, high=(price_raw + high_diff) / 100.0, low=(price_raw + low_diff) / 100.0, vol=float(vol), cur_vol=float(cur_vol), amount=amount, s_vol=float(s_vol), b_vol=float(b_vol), active1=active1, active2=active2, bid1=(price_raw + bid1_d) / 100.0, bid_vol1=float(bv1), bid2=(price_raw + bid2_d) / 100.0, bid_vol2=float(bv2), bid3=(price_raw + bid3_d) / 100.0, bid_vol3=float(bv3), bid4=(price_raw + bid4_d) / 100.0, bid_vol4=float(bv4), bid5=(price_raw + bid5_d) / 100.0, bid_vol5=float(bv5), ask1=(price_raw + ask1_d) / 100.0, ask_vol1=float(av1), ask2=(price_raw + ask2_d) / 100.0, ask_vol2=float(av2), ask3=(price_raw + ask3_d) / 100.0, ask_vol3=float(av3), ask4=(price_raw + ask4_d) / 100.0, ask_vol4=float(av4), ask5=(price_raw + ask5_d) / 100.0, ask_vol5=float(av5), rise_speed=rise_speed_raw / 100.0, limit_up=None, limit_down=None, unknown_2=unknown_2, unknown_3=unknown_3, unknown_5=unknown_5, unknown_6=unknown_6, unknown_7=unknown_7, unknown_8=unknown_8, server_time=_format_server_time(unknown_0), trading_status=trading_status, open_amount=unknown_3 * 100.0, _raw=body[record_start:pos]))

        return results

class GetTransactionDataCmd(BaseCommand[list[TransactionRecord]]):
    """获取当日逐笔成交（分页，每次最多 800 条）。"""

    def __init__(self, market: Market, code: str, start: int, count: int = 800):
        self.market = market
        self.code = code.encode("utf-8")
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c170801010 10e000e00c50f".replace(" ", ""))
        return header + struct.pack("<H6sHH", int(self.market), self.code, self.start, self.count)

    def parse_response(self, body: bytes) -> list[TransactionRecord]:
        return _parse_transaction_body(body)


class GetHistoryTransactionDataCmd(BaseCommand[list[TransactionRecord]]):
    """获取历史某日逐笔成交（date 格式 YYYYMMDD，分页）。"""

    def __init__(self, market: Market, code: str, date: int, start: int, count: int = 800):
        self.market = market
        self.code = code.encode("utf-8")
        self.date = date
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # 历史逐笔：header + pack("<IH6sHH", date, market, code, start, count)
        header = bytes.fromhex("0c013001000112001200b50f".replace(" ", ""))
        return header + struct.pack("<IH6sHH", self.date, int(self.market), self.code, self.start, self.count)

    def parse_response(self, body: bytes) -> list[TransactionRecord]:
        # 历史逐笔：num(2) + 4字节填充；无"成交笔数"字段
        return _parse_history_transaction_body(body)


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


def _parse_history_transaction_body(body: bytes) -> list[TransactionRecord]:
    """历史逐笔：num(2) + skip(4) + [time + price + vol + buyorsell + unknown]"""
    (num,) = unpack_from("<H", body, 0, "history_transaction header")
    pos = 6  # 2(num) + 4(skip)
    last_price = 0
    records: list[TransactionRecord] = []

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


class GetXdxrInfoCmd(BaseCommand[list[XdxrRecord]]):
    """获取除权除息历史记录。"""

    def __init__(self, market: Market, code: str):
        self.market = market
        self.code = code.encode("utf-8")

    def build_request(self) -> bytes:
        header = bytes.fromhex("0c1f18760001 0b000b000f000100".replace(" ", ""))
        return header + struct.pack("<B6s", int(self.market), self.code)

    def parse_response(self, body: bytes) -> list[XdxrRecord]:
        if len(body) < 11:
            raise TdxDecodeError("xdxr_info body 过短")

        pos = 9  # 跳过9字节（market+code+未知）
        (num,) = unpack_from("<H", body, pos, "xdxr_info header")
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
            (category,) = unpack_from("<B", body, pos, "xdxr_info category")
            pos += 1

            chunk = slice_bytes(body, pos, 16, "xdxr_info record body")
            pos += 16
            try:
                market = Market(market_b)
            except ValueError as e:
                raise TdxDecodeError(f"xdxr_info 非法 market 值: {market_b}") from e

            rec = XdxrRecord(market=market, code=code_b.decode("utf-8").rstrip("\x00"), year=year, month=month, day=day, category=category, name=XDXR_CATEGORY_NAMES.get(category, str(category)), _raw=body[record_start:pos])

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

            records.append(rec)

        return records


def _decode_share_count(raw: int) -> float:
    """股本数量解码（通达信自定义4字节浮点 → 万股）。

    xdxr_info 的股本字段与成交量字段使用相同的自定义浮点编码，
    解码结果单位为万股，与 FinanceInfo.zong_guben / 10000 一致。
    """
    return _decode_volume(raw)


def _normalize_per_10_shares(value: float) -> float:
    """将协议里的“每10股”口径归一化为“每股”口径。"""
    return value / 10.0
