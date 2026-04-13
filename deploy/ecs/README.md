# ECS / 单机生产目录约定（版本库追踪）

本目录纳入 Git，用于**统一远端路径、验收脚本与发布清单格式**；服务器上的 `RELEASE_MANIFEST` 由部署脚本生成，**勿**将含机密的远端文件提交回仓库。

## 目录与模式

| 模式 | 说明 |
|------|------|
| **Tar**（默认） | 本机打包 `backend` + Flutter Web，上传解压；每次写入 `RELEASE_MANIFEST`。 |
| **Git** | 远端 `$RemoteAppRoot` 为完整 `git clone`；仅执行 `fetch` + `checkout`/`pull` 更新代码；Web 仍可 Tar 发布。 |

远端推荐布局（与 `scripts/deploy_full_to_ecs.ps1` 默认一致）：

- `RemoteAppRoot`：如 `/opt/clothing-assistant/clothing-assistant-main`（含 `backend/`；Git 模式下含 `.git` 与 `scripts/`）
- `RemoteWebRoot`：如 `/usr/share/nginx/html`

## SSH 免密（BatchMode）

脚本使用 `ssh -o BatchMode=yes`，**必须**配置密钥：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/clothing_ecs -N ""
ssh-copy-id -i ~/.ssh/clothing_ecs.pub root@YOUR_ECS_IP
```

PowerShell 部署时传入：

```powershell
.\scripts\deploy_full_to_ecs.ps1 -IdentityFile "$env:USERPROFILE\.ssh\clothing_ecs"
```

## 发布后验收

`deploy/ecs/post_deploy_verify.sh`：`/health`、`/health/ready`、根路径关键字，并调用 `scripts/full_chain_consistency_audit.sh`。
由 `deploy_full_to_ecs.ps1` 在成功后自动上传并执行（可用 `-SkipPostDeployVerify` 跳过，不推荐）。

## RELEASE_MANIFEST

见同目录 `RELEASE_MANIFEST.example`。Tar 部署会写入 `$RemoteAppRoot/RELEASE_MANIFEST`（与 `backend` 同级）。
