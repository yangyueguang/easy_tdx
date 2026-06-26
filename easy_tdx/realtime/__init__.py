"""实时数据推送模块。

提供事件驱动的行情推送框架，基于 asyncio 实现。
这是 API 骨架设计，实际协议层订阅功能待实现。

核心组件：
- EventBus: 事件总线，发布/订阅行情事件
- RealtimeStrategy: 实时策略基类
- MarketEvent: 行情事件数据结构
"""
