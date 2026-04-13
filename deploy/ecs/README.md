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

脚本使用 `ssh -o BatchMode=yes`，**必须**配置密钥（**不会提示输入密码**）。若出现 `Permission denied (publickey,...)`，说明服务器未接受你本机提供的任何私钥：

- 先在本机验证：`ssh -i %USERPROFILE%\.ssh\id_ed25519 root@<ECS_IP> "echo ok"`（Linux/Mac 把路径换成 `~/.ssh/...`）
- 若失败：把本机 `*.pub` 追加到服务器 `~/.ssh/authorized_keys`，并确保 `~/.ssh` 权限为 `700`、`authorized_keys` 为 `600`
- 部署时务必传入：`-IdentityFile "$env:USERPROFILE\.ssh\id_ed25519"`（路径以你本机实际密钥名为准）

### 仍然 `Permission denied` 时（按顺序查）

1. **先跑诊断脚本**（与部署相同 BatchMode）：

   ```powershell
   .\scripts\test_ecs_ssh.ps1 -ServerHost "你的ECS公网IP" -User root -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519"
   ```

   需要细节时：`.\scripts\test_ecs_ssh.ps1 -VerboseSsh`

2. **Windows 私钥权限过宽**：OpenSSH 可能**直接不用**该私钥。脚本会提示时用 `icacls` 收紧（见 `test_ecs_ssh.ps1` 输出）。

3. **阿里云镜像登录名不一定是 `root`**：部分镜像为 **`ecs-user`**。控制台「远程连接」旁会写默认用户。若是 `ecs-user`，部署要加 **`-User ecs-user`**，且该用户的 `~/.ssh/authorized_keys` 里要有你的 **同一对** 公钥。

4. **公钥与私钥不是一对**：你在控制台「绑定密钥」或粘贴的是 **A的 .pub**，本机却用 **B 的 id_ed25519**，会一直失败。用 `ssh-keygen -y -f id_ed25519` 打印公钥，与服务器上 `authorized_keys` 逐行对比。

5. **安全组**：本机到 ECS **22 端口**需放行（你若能用Workbench连上，一般已放行）。

6. **`root` 与 `ecs-user` 都失败**：几乎总是 **本机私钥与实例上的公钥不是同一对**。常见情况：实例在控制台绑定的是**密钥对 A**，你本机却用自建的 `id_ed25519`（密钥对 B）。处理二选一：用创建实例时**绑定密钥对所对应的私钥**（多为 `.pem`）做 `-IdentityFile`；或在 **ECS Workbench / 救援** 登录后，把本机 `id_ed25519.pub` 追加到目标用户的 `~/.ssh/authorized_keys`（权限 `700` / `600`）。`.\scripts\test_ecs_ssh.ps1` 会打印本机密钥的 **SHA256 指纹**，可与控制台密钥对详情里的指纹对照。

生成密钥并安装到服务器（在 **本机** 或 WSL 执行 `ssh-copy-id` 均可）：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/clothing_ecs -N ""
ssh-copy-id -i ~/.ssh/clothing_ecs.pub root@YOUR_ECS_IP
```

PowerShell 部署时传入：

```powershell
.\scripts\deploy_full_to_ecs.ps1 -IdentityFile "$env:USERPROFILE\.ssh\clothing_ecs"
```

## Nginx 反代 `/api/v1`（P0，否则 Web 一键生成会 404）

Flutter Web 在公网使用 **当前域名 + `/api/v1`**（见 `mobile/lib/core/services/api_base_resolver_web.dart`）。若 Nginx **只**托管静态文件、没有把 `/api/v1/` 转到本机 Uvicorn（`127.0.0.1:8010`），浏览器请求 `POST /api/v1/smart-outfit/generate` 会得到 **404**，提示类似「Generate failed: 404」。

1. 在服务器上把 **`deploy/ecs/nginx-api-locations.conf`** 里的 `location` 段并入你实际提供 `root /usr/share/nginx/html` 的 `server { }`（或新建 `conf.d` 片段，注意勿与默认站点冲突）。
2. 执行：`sudo nginx -t && sudo systemctl reload nginx`
3. 验收（应返回 JSON，而非 HTML 404 页）：

   ```bash
   curl -sS -X POST "http://<ECS公网IP>/api/v1/agent/intent" \
     -H "Content-Type: application/json" \
     -d '{"query":"智能穿搭"}'
   ```

`deploy_full_to_ecs.ps1` 目前**只**发布静态包并 `reload nginx`，**不会**自动写入上述反代；首次上线需在 ECS 上配置一次。

## 发布台账与后端可读 Manifest

后端 **`GET /release`** 会合并环境变量 `RELEASE_*` 与可选文件 **`RELEASE_MANIFEST_PATH`**（JSON）。字段说明与 Nginx 反代要求见 **[docs/OPS_RELEASE_AND_OBSERVABILITY.md](../docs/OPS_RELEASE_AND_OBSERVABILITY.md)**；示例键名见本目录 **`RELEASE_MANIFEST.example`**。

## Tar 部署与数据安全（衣橱 / 图片 / 数据库）

**现象：** 若打包时把本机或子目录里的 **SQLite（`*.db` / `*.sqlite*`）** 打进 `backend` 压缩包，解压到 ECS 时会**覆盖**线上库，表现为「更新后衣橱空了」。

**脚本已做两层防护：**

1. **打包**：除 `backend/*.db` 外，增加 **`backend/**/*.db`**（及 sqlite）排除，避免深层路径的数据库被打进包。
2. **远端**：解压前将 `$RemoteAppRoot/backend` 下的 **`.env`、`uploads/`、所有 `*.db`/`*.sqlite*`** 打成快照到 **`/var/lib/clothing-assistant/backend-data-<UTC时间>.tar.gz`**，解压发布包后再**合并恢复**到 `backend/`，覆盖误带入的空库或错误文件。

**仍建议：** 生产用 **PostgreSQL** 或把 SQLite 放在**独立绝对路径**（见 `docs/PRODUCTION_DEPLOY.md`），并定期备份；不要用依赖仓库目录内默认 SQLite 长期扛生产。

**账户照片永久保存：** 在 ECS `backend/.env` 将 **`UPLOAD_DIR`** 设为代码目录外的绝对路径（如 `/var/lib/clothing-assistant/uploads`），并按 **`deploy/ecs/env.production.persistent.example`** 配置数据库路径；否则相对路径 `./uploads` 在发版或工作目录变化时易导致图片「刷新就没了」。

## 发布后验收

`deploy/ecs/post_deploy_verify.sh`：`/health`、`/health/ready`、根路径关键字，并调用 `scripts/full_chain_consistency_audit.sh`。
由 `deploy_full_to_ecs.ps1` 在成功后自动上传并执行（可用 `-SkipPostDeployVerify` 跳过，不推荐）。

## RELEASE_MANIFEST

见同目录 `RELEASE_MANIFEST.example`。Tar 部署会写入 `$RemoteAppRoot/RELEASE_MANIFEST`（与 `backend` 同级）。
