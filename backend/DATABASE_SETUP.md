# 数据库设置指南

本文档说明如何设置 Smart Outfit Assistant 的 PostgreSQL 数据库。

## 前置要求

- PostgreSQL 12+ 已安装并运行
- Python 3.12+ 环境
- 已安装项目依赖 (`pip install -r requirements.txt`)

## 快速开始

### 1. 创建数据库

使用 PostgreSQL 命令行或 pgAdmin 创建数据库：

```bash
# 使用 psql 命令行
psql -U postgres
CREATE DATABASE outfit_db;
CREATE USER outfit_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE outfit_db TO outfit_user;
\q
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并更新数据库连接信息：

```bash
cp .env.example .env
```

编辑 `.env` 文件中的 `DATABASE_URL`：

```
DATABASE_URL=postgresql://outfit_user:your_password@localhost:5432/outfit_db
```

### 3. 初始化数据库表

运行数据库初始化脚本：

```bash
python scripts/init_db.py
```

这将创建以下表：
- `users` - 用户账户表
- `user_profiles` - 用户画像表
- `garments` - 服饰单品表

## 数据库模式

### users 表

存储用户账户信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | UUID | 主键 |
| username | VARCHAR(50) | 用户名（唯一） |
| email | VARCHAR(255) | 邮箱（唯一） |
| password_hash | VARCHAR(255) | 密码哈希 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |
| is_active | BOOLEAN | 是否激活 |

### user_profiles 表

存储用户个性化画像信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| profile_id | UUID | 主键 |
| user_id | UUID | 外键 → users.user_id |
| height | INTEGER | 身高（厘米） |
| body_type | VARCHAR(20) | 体型（偏瘦/微胖/梨形/倒三角/沙漏/矩形） |
| skin_tone | VARCHAR(20) | 肤色（冷白/黄皮/小麦/深色） |
| style_preference | JSONB | 风格偏好列表 |
| budget_range | VARCHAR(20) | 预算范围（经济/中等/高端） |
| avoid_body_parts | JSONB | 不希望强化的身体部位列表 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### garments 表

存储用户衣橱中的服饰单品。

| 字段 | 类型 | 说明 |
|------|------|------|
| garment_id | UUID | 主键 |
| user_id | UUID | 外键 → users.user_id |
| category | VARCHAR(20) | 品类（上衣/裤子/裙子/外套/鞋/包） |
| main_color | JSONB | 主色（Color 对象） |
| secondary_colors | JSONB | 辅助色列表 |
| style_tags | JSONB | 风格标签列表 |
| fit_type | VARCHAR(20) | 版型（修身/宽松/标准/oversized） |
| image_path | VARCHAR(500) | 图片本地路径 |
| image_url | VARCHAR(500) | 图片 URL |
| feature_vector | FLOAT8[] | 1280 维特征向量 |
| notes | TEXT | 备注 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

## 索引

为提高查询性能，已创建以下索引：

- `idx_users_username` - users.username
- `idx_users_email` - users.email
- `idx_profiles_user_id` - user_profiles.user_id
- `idx_garments_user_id` - garments.user_id
- `idx_garments_category` - garments.category
- `idx_garments_user_category` - garments(user_id, category)

## 数据库迁移

本项目使用 Alembic 进行数据库迁移管理。

### 创建新迁移

```bash
alembic revision --autogenerate -m "描述你的更改"
```

### 应用迁移

```bash
alembic upgrade head
```

### 回滚迁移

```bash
alembic downgrade -1
```

## 可选：pgvector 扩展

为了优化特征向量相似度搜索，可以安装 pgvector 扩展：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE garments ADD COLUMN feature_vector_pgvector vector(1280);
CREATE INDEX idx_garments_feature_vector ON garments
    USING ivfflat (feature_vector_pgvector vector_cosine_ops);
```

## 故障排除

### 连接错误

如果遇到数据库连接错误，请检查：

1. PostgreSQL 服务是否运行
2. 数据库名称、用户名、密码是否正确
3. 主机和端口是否正确
4. 防火墙是否允许连接

### 权限错误

确保数据库用户有足够的权限：

```sql
GRANT ALL PRIVILEGES ON DATABASE outfit_db TO outfit_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO outfit_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO outfit_user;
```

### 编码问题

确保数据库使用 UTF-8 编码：

```sql
CREATE DATABASE outfit_db
    WITH ENCODING='UTF8'
    LC_COLLATE='en_US.UTF-8'
    LC_CTYPE='en_US.UTF-8'
    TEMPLATE=template0;
```

## 备份和恢复

### 备份数据库

```bash
pg_dump -U outfit_user -d outfit_db -F c -f backup.dump
```

### 恢复数据库

```bash
pg_restore -U outfit_user -d outfit_db backup.dump
```

## 参考资料

- [PostgreSQL 官方文档](https://www.postgresql.org/docs/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [Alembic 文档](https://alembic.sqlalchemy.org/)
- [pgvector 扩展](https://github.com/pgvector/pgvector)
