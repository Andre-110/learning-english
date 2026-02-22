import asyncio
import os
import logging
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page, ConsoleMessage, Request, Response

# 配置日志
logger = logging.getLogger("BrowserDebugger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

class BrowserDebugger:
    def __init__(self, output_dir: str = "logs/debug_snapshots"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console_logs = []
        self.network_logs = []
        self.js_errors = []

    async def attach_to_page(self, page: Page):
        """将调试器附加到页面"""
        self.page = page
        
        # 1. 监听 Console 日志
        page.on("console", self._handle_console)
        
        # 2. 监听未捕获异常
        page.on("pageerror", self._handle_page_error)
        
        # 3. 监听网络请求失败
        page.on("requestfailed", self._handle_request_failed)
        page.on("response", self._handle_response)
        
        logger.info(f"🔍 BrowserDebugger 已附加到页面")

    def _handle_console(self, msg: ConsoleMessage):
        """处理控制台日志"""
        log_entry = f"[Console] {msg.type}: {msg.text}"
        self.console_logs.append(log_entry)
        
        # 实时打印到终端
        if msg.type == "error":
            logger.error(f"🔴 {log_entry}")
        elif msg.type == "warning":
            logger.warning(f"🟡 {log_entry}")
        else:
            # Info 级别日志只记录不打印，避免刷屏，除非包含特定关键字
            if "error" in msg.text.lower() or "fail" in msg.text.lower():
                logger.info(f"🔵 {log_entry}")

    def _handle_page_error(self, error):
        """处理页面 JS 错误"""
        err_msg = f"[JS Error] {error}"
        self.js_errors.append(err_msg)
        logger.error(f"❌ {err_msg}")

    async def _handle_request_failed(self, request: Request):
        """处理请求失败"""
        if request.resource_type in ["fetch", "xhr", "websocket"]:
            msg = f"[Network Fail] {request.method} {request.url} - {request.failure}"
            self.network_logs.append(msg)
            logger.error(f"🌐 {msg}")

    async def _handle_response(self, response: Response):
        """处理响应（检查 4xx/5xx）"""
        if response.status >= 400:
            msg = f"[HTTP Error] {response.status} {response.url}"
            self.network_logs.append(msg)
            logger.error(f"🔥 {msg}")

    async def capture_snapshot(self, name: str):
        """抓取快照（截图 + HTML + 状态）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.output_dir / f"{timestamp}_{name}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 1. 截图
            await self.page.screenshot(path=snapshot_dir / "screenshot.png", full_page=True)
            
            # 2. 保存 HTML
            html = await self.page.content()
            with open(snapshot_dir / "dom.html", "w", encoding="utf-8") as f:
                f.write(html)
                
            # 3. 保存调试日志
            with open(snapshot_dir / "debug.log", "w", encoding="utf-8") as f:
                f.write("=== JS Errors ===\n")
                f.write("\n".join(self.js_errors))
                f.write("\n\n=== Network Errors ===\n")
                f.write("\n".join(self.network_logs))
                f.write("\n\n=== Console Logs (Last 50) ===\n")
                f.write("\n".join(self.console_logs[-50:]))
                
            logger.info(f"📸 快照已保存: {snapshot_dir}")
            return snapshot_dir
            
        except Exception as e:
            logger.error(f"快照保存失败: {e}")
