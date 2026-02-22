"""
三轨领域模块 (Tracks)

LinguaCoach 的核心业务逻辑，采用三轨并行架构：

1. InteractionTrack (交互轨)
   - 职责：ASR → LLM → TTS 三段链路
   - 特点：流式输出，低延迟
   - 输入：用户音频
   - 输出：AI 回复（文本 + 音频）

2. EvaluationTrack (评估轨)
   - 职责：三阶段评估（语音 + 文本 + 综合）
   - 特点：异步执行，不阻塞交互
   - 输入：用户音频 + 转录文本
   - 输出：评估 JSON

3. HotContentTrack (热点轨)
   - 职责：搜索 + 改写 + 注入热点内容
   - 特点：异步执行，可选功能
   - 输入：用户兴趣点
   - 输出：热点内容（用于注入对话）

并行执行图：
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 交互轨      │  │ 评估轨      │  │ 热点轨      │
│ ASR→LLM→TTS │  │ 三阶段评估  │  │ 搜索+注入   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
    前端播放         前端显示         下轮注入
"""

from .interaction import InteractionTrack
from .evaluation import EvaluationTrack
from .hot_content import HotContentTrack

__all__ = [
    "InteractionTrack",
    "EvaluationTrack",
    "HotContentTrack",
]

