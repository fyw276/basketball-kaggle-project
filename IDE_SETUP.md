# IDE 配置指南

本项目已配置为在多个平台和 IDE 上高效工作。

## 支持的 IDE/编辑器

- ✅ VS Code
- ✅ Kiro
- ✅ PyCharm / IntelliJ IDEA
- ✅ Android Studio
- ✅ 任何支持 EditorConfig 的编辑器

## 首次设置

### 1. 清理缓存文件

**Windows (PowerShell):**
```powershell
.\cleanup.ps1
```

**Linux/Mac (Bash):**
```bash
chmod +x cleanup.sh
./cleanup.sh
```

### 2. 重启 IDE

完全关闭并重新打开你的 IDE。

## VS Code 配置

项目已包含 `.vscode/settings.json`，会自动：
- 排除 venv、node_modules 等大目录
- 优化文件监视
- 配置 GitHub Copilot

### 推荐扩展
- Python
- Pylance
- Flutter
- Dart
- GitHub Copilot
- GitHub Copilot Chat

## Kiro 配置

项目已包含 `.kiro/settings.json`，会自动排除不必要的文件。

## PyCharm 配置

PyCharm 会自动识别 `.idea/` 目录（已在 .gitignore 中排除）。

### 手动配置（如需要）：
1. Settings → Project → Project Structure
2. 标记 `venv` 为 Excluded
3. 标记 `backend/uploads` 为 Excluded
4. 标记 `mobile/.dart_tool` 为 Excluded

## 跨平台兼容性

### EditorConfig
项目包含 `.editorconfig`，确保所有编辑器使用一致的：
- 字符编码（UTF-8）
- 行尾符（LF）
- 缩进风格

### Git 属性
`.gitattributes` 确保跨平台的行尾符一致性。

## 性能优化

### 排除的目录
以下目录已在所有配置中排除：
- `venv/`, `env/` - Python 虚拟环境
- `backend/venv/` - 后端虚拟环境
- `backend/uploads/` - 上传文件
- `mobile/.dart_tool/` - Flutter 工具缓存
- `mobile/build/` - Flutter 构建输出
- `__pycache__/` - Python 缓存
- `.pytest_cache/` - Pytest 缓存
- `node_modules/` - Node 依赖
- `logs/` - 日志文件

## 故障排除

### VS Code 聊天加载慢
1. 运行清理脚本
2. 重启 VS Code
3. 确保 `.vscode/settings.json` 存在

### Kiro 响应慢
1. 检查 `.kiro/settings.json` 存在
2. 运行清理脚本
3. 重启 Kiro

### PyCharm 索引慢
1. File → Invalidate Caches / Restart
2. 确保 venv 目录被标记为 Excluded

## 文件统计

清理后，项目应该有：
- 约 1,000-2,000 个源代码文件
- 排除虚拟环境后约 500 MB

如果文件数超过 10,000 或大小超过 1 GB，请运行清理脚本。
