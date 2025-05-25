"""
Minimal configuration for CodeComprehender
"""

import os
from dataclasses import dataclass

@dataclass
class Config:
    """Minimal config - just what we actually need"""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    temperature: float = 0.3
    file_suffix: str = "_commented"
    use_javadoc: bool = True
    add_inline_comments: bool = True
    diagram_format: str = "png"

    # These are needed for the existing code
    generate_diagrams: bool = True
    skip_comments: bool = False

    def __post_init__(self):
        """Load API key from environment if not provided"""
        if not self.openai_api_key:
            self.openai_api_key = os.getenv('OPENAI_API_KEY', '')

    @classmethod
    def from_env_and_cli(cls, model: str):
        """Create config from environment and command line"""
        api_key = os.getenv('OPENAI_API_KEY', '')
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
        return cls(openai_api_key=api_key, openai_model=model)