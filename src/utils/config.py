"""Configuration management for CodeComprehender"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration"""

    # OpenAI settings
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 1000

    # Comment generation settings
    comment_style: str = "javadoc"
    include_inline_comments: bool = True
    include_method_comments: bool = True
    include_class_comments: bool = True

    # Architecture settings
    diagram_format: str = "png"
    include_private_members: bool = False
    max_depth: int = 3

    # File handling settings
    file_suffix: str = "_commented"
    ignore_patterns: List[str] = field(default_factory=lambda: ["*Test.java", "*Generated.java"])
    encoding: str = "utf-8"

    # Processing flags
    comments_only: bool = False
    architecture_only: bool = False

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration from file or defaults"""
        # Load environment variables from .env file
        load_dotenv()

        # Load from environment
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.openai_base_url = os.getenv('OPENAI_BASE_URL')

        # Load from config file if provided
        if config_file:
            self._load_from_file(config_file)

    def _load_from_file(self, config_file: str) -> None:
        """Load configuration from YAML file"""
        with open(config_file, 'r') as f:
            data = yaml.safe_load(f)

        # Update configuration with file data
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
