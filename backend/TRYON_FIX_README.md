# 虚拟试衣功能修复指南

## 问题描述

虚拟试衣功能的"真实贴身"（replace模式）和"稳定"（balanced模式）无法使用，系统返回错误："替换试衣上游不可用或未成功"。

## 根本原因

**dashscope 包未安装**，导致百炼（DashScope）API无法工作。

## 修复步骤

### 方法1：使用安装脚本（推荐）

#### Windows:
```bash
cd backend
install_dashscope.bat
```

#### Linux/Mac:
```bash
cd backend
chmod +x install_dashscope.sh
./install_dashscope.sh
```

### 方法2：手动安装

```bash
cd backend
pip install "dashscope>=1.20.0,<2.0.0"
```

### 方法3：从requirements.txt安装

```bash
cd backend
pip install -r requirements.txt
```

## 验证安装

安装完成后，运行以下命令验证：

```bash
python -c "from dashscope.aigc.image_synthesis import ImageSynthesis; print('dashscope 已成功安装')"
```

如果看到"dashscope 已成功安装"，说明安装成功。

## 重启服务

安装完成后，重启后端服务：

```bash
# 停止当前运行的服务（Ctrl+C）
# 然后重新启动
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

## 配置检查

确保 `.env` 文件中包含以下配置：

```env
DASHSCOPE_TRYON_ENABLED=true
DASHSCOPE_API_KEY=your-api-key-here
```

## 代码改进

本次修复还改进了错误处理逻辑：

1. **更详细的错误诊断**：当百炼API调用失败时，系统会提供具体的错误原因（如"dashscope包未安装"、"API key无效"、"额度不足"等）

2. **增强的错误响应**：`replace_debug.bailian` 字段现在包含：
   - `error_type`: 错误类型（dependency_missing, api_error等）
   - `specific_hint`: 具体的错误提示
   - `status_code`: HTTP状态码
   - `exception_message`: 异常消息

3. **智能错误提示**：根据错误类型自动提供相应的解决方案

## 测试

安装完成后，可以通过以下方式测试：

1. 打开Flutter应用
2. 进入虚拟试衣页面
3. 选择"真实贴身"或"稳定"模式
4. 上传人物照片和衣服照片
5. 点击"开始试衣"

如果仍然遇到问题，请查看错误响应中的 `replace_debug.bailian` 字段获取详细诊断信息。

## 常见问题

### Q: 安装后仍然报错怎么办？

A: 检查以下几点：
1. 确认 `DASHSCOPE_API_KEY` 是否有效
2. 检查API额度是否充足
3. 确认网络连接正常
4. 查看错误响应中的 `specific_hint` 字段获取具体原因

### Q: 如何获取 DashScope API Key？

A: 访问 [阿里云百炼控制台](https://dashscope.console.aliyun.com/) 获取API Key。

### Q: 是否需要配置远程VTON服务？

A: 不需要。安装dashscope后，百炼API即可正常工作。远程VTON服务是可选的备用方案。

## 技术细节

### 修改的文件

1. `backend/app/services/bailian_tryon_client.py`
   - 改进了错误处理逻辑
   - 添加了详细的错误诊断信息
   - 增强了异常捕获和分类

2. `backend/app/api/tryon_v2.py`
   - 改进了replace模式的错误响应
   - 添加了更具体的错误提示
   - 增强了 `replace_debug` 字段的信息

### 错误类型分类

- `dependency_missing`: 依赖包未安装
- `api_error`: API调用错误
- `network_error`: 网络连接问题
- `auth_error`: 认证失败
- `quota_error`: 额度不足

## 联系支持

如果问题仍未解决，请提供以下信息：

1. 错误响应中的 `replace_debug` 完整内容
2. 后端日志（查找包含"Bailian try-on failed"的行）
3. Python版本和操作系统信息
