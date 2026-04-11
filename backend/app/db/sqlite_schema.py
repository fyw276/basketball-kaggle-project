"""
SQLite 开发库轻量补丁：模型新增列后，旧表不会自动变更，此处按需 ALTER TABLE。
无性别推荐系统（修正版）：
- 新增 gender_label, neutral_score (garments)
- 新增 gender_expression, explore_cross_gender (user_profiles)
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

try:
    from loguru import logger as _loguru_logger
except Exception:  # pragma: no cover - optional dependency
    _loguru_logger = None


class _CompatLogger:
    def __init__(self):
        self._std = logging.getLogger("sqlite_schema")

    def warning(self, msg, *args):
        if _loguru_logger is not None:
            _loguru_logger.warning(msg, *args)
        else:
            self._std.warning(msg.replace("{}", "%s"), *args)

    def info(self, msg, *args):
        if _loguru_logger is not None:
            _loguru_logger.info(msg, *args)
        else:
            self._std.info(msg.replace("{}", "%s"), *args)

    def error(self, msg, *args):
        if _loguru_logger is not None:
            _loguru_logger.error(msg, *args)
        else:
            self._std.error(msg.replace("{}", "%s"), *args)


logger = _CompatLogger()

# (表名, 列名, ALTER 语句片段) — 仅当表中不存在该列时执行
_GARMENTS_SQLITE_PATCHES: list[tuple[str, str]] = [
    ("name", "ALTER TABLE garments ADD COLUMN name VARCHAR(100)"),
    ("is_favorite", "ALTER TABLE garments ADD COLUMN is_favorite CHAR(1) DEFAULT '0'"),
    ("wearing_count", "ALTER TABLE garments ADD COLUMN wearing_count VARCHAR(10) DEFAULT '0'"),
    # 无性别推荐系统新增字段
    ("gender_label", "ALTER TABLE garments ADD COLUMN gender_label VARCHAR(20) DEFAULT 'neutral'"),
    ("neutral_score", "ALTER TABLE garments ADD COLUMN neutral_score FLOAT DEFAULT 1.0"),
]

_USER_PROFILES_SQLITE_PATCHES: list[tuple[str, str]] = [
    # gender_expression 改为可空（仅对女性生效）
    ("gender_expression", "ALTER TABLE user_profiles ADD COLUMN gender_expression FLOAT"),
    # 新增 explore_cross_gender
    (
        "explore_cross_gender",
        "ALTER TABLE user_profiles ADD COLUMN explore_cross_gender CHAR(1) DEFAULT '0'",
    ),
]

_USERS_SQLITE_PATCHES: list[tuple[str, str]] = [
    (
        "phone_number",
        "ALTER TABLE users ADD COLUMN phone_number VARCHAR(32)",
    ),
]


def apply_sqlite_schema_patches(engine: Engine) -> None:
    """若为 SQLite 且表缺少 ORM 中的列，则补齐。"""
    if engine.dialect.name != "sqlite":
        return

    try:
        insp = inspect(engine)
    except Exception as e:
        logger.warning("SQLite 结构检查跳过: {}", e)
        return

    if not insp.has_table("garments"):
        return

    existing = {c["name"] for c in insp.get_columns("garments")}

    for col_name, ddl in _GARMENTS_SQLITE_PATCHES:
        if col_name in existing:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("SQLite 已执行补丁: garments 增加列 {}", col_name)
        except Exception as e:
            logger.error("SQLite 补丁失败 ({}): {}", col_name, e)
            raise

    if not insp.has_table("user_profiles"):
        return

    user_profiles_cols = {c["name"] for c in insp.get_columns("user_profiles")}

    for col_name, ddl in _USER_PROFILES_SQLITE_PATCHES:
        if col_name in user_profiles_cols:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("SQLite 已执行补丁: user_profiles 增加列 {}", col_name)
        except Exception as e:
            logger.error("SQLite 补丁失败 ({}): {}", col_name, e)
            raise

    if not insp.has_table("users"):
        return

    users_cols = {c["name"] for c in insp.get_columns("users")}

    for col_name, ddl in _USERS_SQLITE_PATCHES:
        if col_name in users_cols:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("SQLite 已执行补丁: users 增加列 {}", col_name)
        except Exception as e:
            logger.error("SQLite 补丁失败 ({}): {}", col_name, e)
            raise
