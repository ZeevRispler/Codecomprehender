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
        # Dataclass fields (like self.ignore_patterns, self.openai_model, etc.)
        # are automatically initialized with their defined defaults or default_factory
        # by the dataclass decorator before this __init__ is called,
        # if you don't explicitly assign to them here first.
        # However, since we have a custom __init__, we need to ensure
        # all fields are properly initialized. The dataclass decorator does this
        # by default if no __init__ is provided, or we can re-state them.

        # Re-stating defaults to be absolutely clear, matching dataclass definitions
        self.openai_api_key: Optional[str] = None
        self.openai_base_url: Optional[str] = None
        self.openai_model: str = "gpt-4"
        self.temperature: float = 0.3
        self.max_tokens: int = 1000
        self.comment_style: str = "javadoc"
        self.include_inline_comments: bool = True
        self.include_method_comments: bool = True
        self.include_class_comments: bool = True
        self.diagram_format: str = "png"
        self.include_private_members: bool = False
        self.max_depth: int = 3
        self.file_suffix: str = "_commented"
        # Ensure ignore_patterns is initialized from its default_factory
        # The default_factory is: lambda: ["*Test.java", "*Generated.java"]
        self.ignore_patterns: List[str] = ["*Test.java", "*Generated.java"]
        self.encoding: str = "utf-8"
        self.comments_only: bool = False
        self.architecture_only: bool = False

        # Load environment variables from .env file
        load_dotenv()

        # Override with environment variables if they are set
        env_api_key = os.getenv('OPENAI_API_KEY')
        if env_api_key is not None:
            self.openai_api_key = env_api_key

        env_base_url = os.getenv('OPENAI_BASE_URL')
        if env_base_url is not None:
            self.openai_base_url = env_base_url

        # Override openai_model if set in environment (example)
        env_openai_model = os.getenv('OPENAI_MODEL')
        if env_openai_model is not None:
            self.openai_model = env_openai_model

        # Load from config file if provided, overriding current values
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
