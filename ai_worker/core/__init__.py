import logging

from ai_worker.core.config import Config
from ai_worker.core.logger import setup_logger


def get_config() -> Config:
    return Config()


def get_logger() -> logging.Logger:
    return setup_logger()


config = get_config()
default_logger = get_logger()
