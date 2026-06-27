"""Dependency injection for Web API routers."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from easy_tdx.client import AsyncTdxClient


def get_client(request: Request) -> AsyncTdxClient:
    """从 app.state 获取共享的 AsyncTdxClient 实例。"""
    client: AsyncTdxClient = request.app.state.tdx_client
    return client


def get_mac_client(request: Request) -> Any:
    """从 app.state 获取共享的 AsyncMacClient 实例。"""
    from easy_tdx.exceptions import TdxConnectionError

    client: Any = request.app.state.mac_client
    if client is None:
        raise TdxConnectionError("MAC 客户端未连接")
    return client


def get_ex_client(request: Request) -> Any:
    """从 app.state 获取共享的 AsyncExTdxClient 实例（可选）。"""
    client: Any = request.app.state.ex_client
    if client is None:
        from easy_tdx.exceptions import TdxConnectionError

        raise TdxConnectionError("扩展市场客户端未启用")
    return client
