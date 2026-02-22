# 测试目录说明

## 测试脚本

### 1. test_api_integration.py
**用途**: 测试所有API端点

**运行**:
```bash
python test/test_api_integration.py
```

**测试内容**:
- GET / - 健康检查
- POST /conversations/start - 开始对话
- POST /conversations/{id}/respond - 回答问题
- GET /conversations/{id} - 获取对话信息
- POST /conversations/{id}/end - 结束对话
- GET /docs - API文档

### 2. test_full_system.py
**用途**: 完整系统功能测试

**运行**:
```bash
python test/test_full_system.py
```

**测试内容**:
- 健康检查
- 开始对话
- 多轮对话
- 能力进步轨迹
- 对话信息获取
- 难度自适应逻辑
- 中英文混杂处理

### 3. test_api_key.py
**用途**: 测试API密钥有效性

**运行**:
```bash
python test/test_api_key.py
```

**测试内容**:
- API密钥验证
- GPT-4-turbo调用
- JSON格式输出
- Whisper API连接

### 4. test_quick.py
**用途**: 快速功能测试

**运行**:
```bash
python test/test_quick.py
```

**测试内容**:
- 基础对话流程
- 评估功能
- 题目生成

### 5. run_all_tests.sh
**用途**: 运行所有测试

**运行**:
```bash
./test/run_all_tests.sh
```

## 测试前准备

### 1. 确保服务运行
```bash
# 检查服务状态
curl http://localhost:8000/

# 如果未运行，启动服务
source venv/bin/activate
uvicorn api.main:app --reload
```

### 2. 检查配置
```bash
# 检查API配置
python -c "from config.llm_config import llm_config; \
print(f'API密钥: {llm_config.get_openai_api_key()[:10] if llm_config.get_openai_api_key() else \"未配置\"}...'); \
print(f'Base URL: {llm_config.get_openai_base_url() or \"官方API\"}'); \
print(f'模型: {llm_config.get_primary_model()}')"
```

## 测试报告

测试报告保存在：
- `test/TEST_REPORT.md` - 详细测试报告
- `test/SYSTEM_TEST_SUMMARY.md` - 测试总结

## 常见问题

### Q1: 测试失败 - 服务未运行
```bash
# 启动服务
source venv/bin/activate
uvicorn api.main:app --reload
```

### Q2: API调用失败
```bash
# 检查API密钥和配额
python test/test_api_key.py
```

### Q3: 评估结果异常
```bash
# 检查日志
tail -f /tmp/lingua_coach.log
```

## 测试覆盖率

- **API端点**: 100% (6/6)
- **核心功能**: 100% (7/7)
- **错误处理**: 已测试
- **边界情况**: 部分测试





