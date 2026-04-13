# On-Call Quick Reference

## 目标

在 5-15 分钟内判断线上问题属于：

1. 发布未同步
2. 服务未就绪
3. 认证失效
4. 资源加载失败
5. 数据脏链路（图片 URL）

## A. Windows 本地一键流程（推荐）

在仓库根目录执行：

```powershell
# 1) 远端一致性审计（上传并在 ECS 执行）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\push_and_run_remote_audit.ps1 -ServerHost 101.200.127.179 -User root

# 2) 一体化发布（前后端）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_full_to_ecs.ps1

# 3) 已本地构建过 Web 时可跳过重建
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy_full_to_ecs.ps1 -SkipWebBuild
```

如果你当前终端目录不是仓库根目录（例如 C:\\Windows\\System32），用绝对路径执行 -File。

## B. ECS 主机检查（Linux）

```bash
cd /opt/clothing-assistant/clothing-assistant-main

# 1) 快速审计
bash scripts/full_chain_consistency_audit.sh

# 2) 服务状态
systemctl is-active nginx
systemctl status clothing-backend --no-pager | sed -n '1,30p'

# 3) 健康检查
curl -fsS http://127.0.0.1:8010/health

# 4) 最近日志
journalctl -u clothing-backend -n 120 --no-pager
```

## C. 问题定位矩阵

1. 审计结果 fail>0：先修基础设施/发布问题，不要先改业务代码。
2. fail=0 warn=1：通常是 no .git 告警，可继续业务验收。
3. /health 失败：先恢复服务，再看业务接口。
4. 智能穿搭空白图/鞋图失败：执行衣橱坏图修复，再刷新前端。
5. 相机按钮跳相册：确认客户端已更新到包含相机分流修复版本。

## D. 常用修复动作

### D1. 衣橱坏图链接修复（后端）

```bash
# 需带登录 token 从前端触发，或调用 API：
# POST /api/v1/wardrobe/simple/garments/repair-image-urls
```

前端衣橱页也有“修复坏图”按钮，会显示 scanned/changed/skipped。

### D2. 认证失效（401）

现象：天气/一键生成报 Could not validate credentials。

处理：

1. 前端退出登录再登录
2. 重试智能穿搭天气与生成
3. 若仍失败，抓取 network 响应体 + 后端日志

### D3. 发布后页面不更新

1. 浏览器强刷 Ctrl+F5
2. 重新跑 deploy_full_to_ecs.ps1
3. 复跑远端审计脚本确认前端 index 指纹与后端健康

## E. 验收清单

1. 智能穿搭：天气、上传、生成、重生成可用
2. 情绪穿搭：可返回建议与衣橱匹配
3. 衣橱：上传、分类、坏图修复可用
4. 适合度、相似度、虚拟试衣可调用
5. 无大面积白块、无明显 404 静态资源错误

## F. 退出标准

1. 审计结果：fail=0
2. 核心链路人工验证通过
3. hooks/test 通过后再提交推送
