# 问题分析文档

本目录包含 LinguaCoach 项目的各种问题分析和调试文档。

## 文档列表

### 性能延迟分析

1. **NETWORK_DELAY_ANALYSIS.md**
   - 网络传输延迟分析
   - 分析 11.74s 延迟的根本原因
   - 包含时间轴数据和日志分析

2. **DELAY_ANALYSIS_FROM_LOGS.md**
   - 基于日志的延迟分析
   - 详细的时间线分析
   - 前端接收延迟问题

3. **DELAY_ROOT_CAUSE_ANALYSIS.md**
   - 延迟根因分析
   - 前端 WebSocket 接收阻塞问题
   - 可能的解决方案

### Bug 分析

4. **BUG_ANALYSIS.md**
   - 初始 Bug 分析报告
   - 包含多个性能指标异常

5. **BUG_ANALYSIS_FIXED.md**
   - 修复后的 Bug 分析
   - 区分代码问题 vs 日志记录问题
   - 已修复的问题列表

## 相关截图

相关截图文件位于 `../screenshots/` 目录：
- `linguacoach-connected.png` - 连接页面截图
- `linguacoach-homepage.png` - 首页截图
- `monitor-page.png` - 监控页面截图
- `monitor-fixed.png` - 修复后的监控页面截图
