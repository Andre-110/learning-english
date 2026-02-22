# 日志系统说明

## 📁 日志存储位置

### 1. 测试日志
**位置**: `logs/` 目录（项目根目录下）

**文件命名格式**: `test_{test_name}_{timestamp}.log`

**示例**:
```
logs/test_full_flow_20251203_061504.log
logs/test_api_integration_20251203_061504.log
```

**创建方式**:
```python
from utils.logger import create_test_logger

# 创建测试日志器
logger = create_test_logger("full_flow", log_dir="logs")
```

### 2. 应用日志
**位置**: 默认输出到控制台（stdout）

**配置方式**:
- 在 `api/main.py` 中使用 `setup_logger()` 创建日志器
- 默认只输出到控制台
- 可以通过 `log_file` 参数指定文件路径

**示例**:
```python
from utils.logger import setup_logger

# 只输出到控制台
logger = setup_logger(level="INFO")

# 输出到文件
logger = setup_logger(level="INFO", log_file="logs/app.log")
```

### 3. 服务运行日志
**位置**: 如果使用 `nohup` 或重定向，日志会保存到指定位置

**示例**:
```bash
# 保存到 /tmp/lingua_coach.log
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > /tmp/lingua_coach.log 2>&1 &

# 查看日志
tail -f /tmp/lingua_coach.log
```

## 📊 日志内容

### 测试日志包含的内容

1. **用户输入输出**
   - 用户输入的所有文本
   - 系统返回的所有响应

2. **API调用记录**
   - API请求和响应
   - 请求参数和响应数据

3. **模块输入输出**
   - 每个模块的输入参数
   - 每个模块的输出结果

4. **评估结果**
   - 评估分数
   - CEFR等级
   - 强项和弱项
   - 维度评分详情

5. **性能指标**
   - API响应时间
   - 各步骤耗时

## 🔍 查看日志

### 查看测试日志
```bash
# 列出所有日志文件
ls -lh logs/

# 查看最新日志
tail -f logs/test_full_flow_*.log

# 查看日志内容
cat logs/test_full_flow_20251203_061504.log

# 搜索特定内容
grep "评估" logs/test_full_flow_*.log
grep "ERROR" logs/test_full_flow_*.log
```

### 查看应用日志
```bash
# 如果使用nohup运行
tail -f /tmp/lingua_coach.log

# 如果直接运行（输出到控制台）
uvicorn api.main:app --reload
```

## 📝 日志格式

### 日志格式说明
```
时间戳 | 日志器名称 | 日志级别 | 消息内容
```

**示例**:
```
2025-12-03 06:15:04 | test_full_flow | INFO     | [TEST_STEP] 1. Starting conversation
2025-12-03 06:15:06 | test_full_flow | INFO     | [API.start_conversation] OUTPUT:
{
  "response": {
    "conversation_id": "3885a1b8-f371-45c0-9b53-4e8b12d59552",
    ...
  }
}
```

### 日志级别
- **DEBUG**: 详细的调试信息
- **INFO**: 一般信息
- **WARNING**: 警告信息
- **ERROR**: 错误信息
- **CRITICAL**: 严重错误

## 🛠️ 日志配置

### 在代码中使用日志

#### 1. 获取日志器
```python
from utils.logger import get_logger

logger = get_logger("module_name")
logger.info("信息")
logger.debug("调试信息")
logger.error("错误信息")
```

#### 2. 记录模块输入输出
```python
from utils.logger import log_module_io

log_module_io(
    logger=logger,
    module_name="API",
    function_name="start_conversation",
    inputs={"user_id": "test_001"},
    outputs={"conversation_id": "xxx"}
)
```

#### 3. 记录用户交互
```python
from utils.logger import log_user_interaction

log_user_interaction(
    logger=logger,
    conversation_id="xxx",
    user_id="test_001",
    user_input="I am a student.",
    system_output={"assessment": {...}}
)
```

#### 4. 创建测试日志器
```python
from utils.logger import create_test_logger

logger = create_test_logger("test_name", log_dir="logs")
```

## 📂 目录结构

```
learning_english/
├── logs/                          # 日志目录
│   ├── test_full_flow_*.log      # 完整流程测试日志
│   ├── test_api_integration_*.log # API集成测试日志
│   └── app.log                    # 应用日志（如果配置）
├── utils/
│   └── logger.py                  # 日志工具模块
└── ...
```

## 🔧 日志管理

### 清理旧日志
```bash
# 删除7天前的日志
find logs/ -name "*.log" -mtime +7 -delete

# 压缩旧日志
gzip logs/*.log
```

### 日志轮转
可以配置日志轮转，避免单个日志文件过大：

```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'logs/app.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
```

## 📋 当前日志文件

查看当前有哪些日志文件：

```bash
# 列出所有日志文件
ls -lh logs/

# 查看日志文件大小
du -sh logs/
```

## 🎯 最佳实践

1. **测试日志**: 使用 `create_test_logger()` 创建测试专用日志
2. **应用日志**: 使用 `get_logger()` 获取应用日志器
3. **日志级别**: 生产环境使用 INFO，开发环境使用 DEBUG
4. **日志清理**: 定期清理旧日志，避免磁盘空间不足
5. **敏感信息**: 不要在日志中记录API密钥等敏感信息

## 📖 相关文件

- `utils/logger.py` - 日志工具实现
- `test/test_with_logging.py` - 带日志记录的测试脚本
- `api/main.py` - API应用日志配置





