"""Logging configuration for CodeComprehender"""

import logging
import sys
from typing import Optional


def setup_logger(name: Optional[str] = None) -> logging.Logger:
    """Setup and return a configured logger"""
    logger = logging.getLogger(name or __name__)

    # Only configure if no handlers exist
    if not logger.handlers:
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger