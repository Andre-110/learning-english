"""
API 端点层

精简的端点实现，只负责：
1. WebSocket/HTTP 协议处理
2. 请求参数解析
3. 响应格式化
4. 调用 services/tracks 层

不包含业务逻辑。
"""

from .conversation import router as conversation_router

__all__ = [
    "conversation_router",
]

