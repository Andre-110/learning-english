import asyncio
import logging
import sys
import os
from playwright.async_api import async_playwright

# 添加项目根目录到 path
sys.path.append(os.getcwd())

from scripts.utils.browser_debugger import BrowserDebugger

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FrontendDiagnose")

async def diagnose_frontend():
    logger.info("🚀 开始前端诊断...")
    
    debugger = BrowserDebugger()
    
    async with async_playwright() as p:
        # 启动浏览器
        try:
            # 尝试使用系统安装的 Chrome
            browser = await p.chromium.launch(
                executable_path="/usr/bin/google-chrome",
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
        except Exception as e:
            logger.error(f"无法启动浏览器: {e}")
            logger.info("尝试安装浏览器依赖...")
            # 这里其实无法自动安装，只能报错
            return

        context = await browser.new_context(
            record_video_dir="logs/debug_snapshots/videos",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        # 挂载调试器
        await debugger.attach_to_page(page)
        
        target_url = "https://userology.xin/english/"
        logger.info(f"正在访问: {target_url}")
        
        try:
            await page.goto(target_url, wait_until="networkidle")
            logger.info("✅ 页面加载完成")
        except Exception as e:
            logger.error(f"页面加载失败: {e}")
            await debugger.capture_snapshot("load_fail")
            return

        # 初始快照
        await debugger.capture_snapshot("initial_load")
        
        # 🆕 检测登录页
        if await page.locator(".auth-container").is_visible():
            logger.info("🔒 检测到登录页，使用指定账号登录...")
            
            test_user = "111111"
            test_pass = "111111"
            
            inputs = page.locator("input.input")
            count = await inputs.count()
            logger.info(f"找到 {count} 个输入框")
            
            # 确保在登录 Tab（默认就是登录，但也可能是注册）
            tabs = page.locator(".auth-tabs .tab")
            active_tab = await tabs.nth(0).get_attribute("class")
            if "active" not in active_tab:
                await tabs.nth(0).click()
                logger.info("🖱️ 切换回登录模式")
                await asyncio.sleep(1)
                # 重新获取输入框
                inputs = page.locator("input.input")
                count = await inputs.count()
            
            if count >= 2:
                # 登录表单: 用户名, 密码
                await inputs.nth(0).fill(test_user)
                await inputs.nth(1).fill(test_pass)
                logger.info(f"📝 填入登录信息: {test_user} / ******")
                
                # 点击提交
                submit_btn = page.locator("button[type='submit']")
                await submit_btn.click()
                logger.info("🖱️ 点击登录按钮")
                
                # 等待跳转
                try:
                    # 🆕 页面改版了，没有 #start-btn，等待 .action-btn.primary 或 .new-chat-btn
                    await page.wait_for_selector(".action-btn.primary", timeout=15000)
                    logger.info("✅ 登录成功，进入主页 (找到开始对话按钮)")
                except:
                    logger.error("❌ 登录后未找到主页元素")
                    await debugger.capture_snapshot("login_fail")
                    return
            else:
                logger.error("❌ 无法定位登录输入框")
                return

        # 检查关键元素
        logger.info("检查关键 UI 元素...")
        
        # 1. 检查开始按钮
        # 🆕 适配新 UI: .action-btn.primary
        start_btn = page.locator(".action-btn.primary")
        if await start_btn.is_visible():
            logger.info("✅ 开始按钮可见")
            # 点击开始
            await start_btn.click()
            logger.info("🖱️ 点击了开始按钮")
            await asyncio.sleep(2)
            await debugger.capture_snapshot("after_click_start")
        else:
            # 尝试找新对话按钮
            new_chat_btn = page.locator(".new-chat-btn")
            if await new_chat_btn.is_visible():
                logger.info("✅ 新对话按钮可见")
                await new_chat_btn.click()
                logger.info("🖱️ 点击了新对话按钮")
                await asyncio.sleep(1)
                # 点击新对话后，开始按钮应该会出现
                start_btn = page.locator(".action-btn.primary")
                if await start_btn.is_visible():
                    await start_btn.click()
                    logger.info("🖱️ 点击了开始按钮")
                    await asyncio.sleep(2)
                    await debugger.capture_snapshot("after_click_start")
                else:
                    logger.error("❌ 开始按钮未找到 (.action-btn.primary)")
            else:
                logger.error("❌ 开始按钮未找到")
        
        # 2. 检查 WebSocket 连接状态
        # (BrowserDebugger 会自动捕获 WebSocket 失败)
        
        # 3. 模拟等待一会
        logger.info("等待 5 秒观察...")
        await asyncio.sleep(5)
        
        # 最终快照
        await debugger.capture_snapshot("final_state")
        
        await browser.close()
        logger.info("🏁 诊断完成，请查看 logs/debug_snapshots/ 下的报告")

if __name__ == "__main__":
    asyncio.run(diagnose_frontend())
