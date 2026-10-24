import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 获取项目根目录 (agent/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_LOG_FILE = LOGS_DIR / "agent.log"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

_loggers: dict[str, logging.Logger] = {}


def get_logger(name: str = "agent") -> logging.Logger:
    """获取或初始化一个结构化分级 Logger。
    
    特性：
    1. 控制台输出：按 INFO/DEBUG 级别输出带有时间戳与模块名的轻量日志；
    2. 文件持久化：在 logs/agent.log 中记录全量 DEBUG 细节，单文件超 10MB 自动轮转切片；
    3. 单例缓存防重：防止重复挂载 Handler 导致日志多倍打印；
    4. 编码安全：全链路指定 UTF-8，杜绝乱码风险。
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    env_level = os.getenv("LOG_LEVEL", "DEBUG").upper()
    log_level = getattr(logging, env_level, logging.DEBUG)
    logger.setLevel(log_level)

    # 避免传递给 root logger 造成重复输出
    logger.propagate = False

    if not logger.handlers:
        # 1. 控制台 Handler (默认 INFO)
        console_handler = logging.StreamHandler(sys.stdout)
        console_level_name = os.getenv("CONSOLE_LOG_LEVEL", "INFO").upper()
        console_handler.setLevel(getattr(logging, console_level_name, logging.INFO))
        console_formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # 2. 轮转文件 Handler (全量 DEBUG 落盘归档)
        file_handler = RotatingFileHandler(
            filename=str(DEFAULT_LOG_FILE),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] [%(filename)s:%(lineno)d] | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger
