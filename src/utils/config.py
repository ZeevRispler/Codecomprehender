import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class Config:
    """Configuration for CodeComprehender with performance options"""

    # OpenAI API settings
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"  # Fast and cheap for most use cases
    openai_base_url: Optional[str] = None  # For custom endpoints
    temperature: float = 0.3  # Consistent but not robotic
    max_tokens: int = 1000  # Per request limit

    # Performance and efficiency
    max_workers: Optional[int] = None  # Auto-detect if None
    batch_size: int = 10  # How many files per batch
    max_concurrent_requests: int = 20  # Concurrent API calls per worker
    request_timeout: float = 60.0  # Seconds
    max_retries: int = 3  # For failed API calls

    # File processing
    file_suffix: str = "_commented"
    encoding: str = "utf-8"
    max_file_size_mb: float = 5.0  # Skip huge files

    # What to generate
    skip_comments: bool = False
    generate_diagrams: bool = True

    # Comment preferences
    use_javadoc: bool = True
    add_inline_comments: bool = True
    include_file_comments: bool = True
    include_method_comments: bool = True
    include_class_comments: bool = True

    # Files to skip (performance optimization)
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "*Test.java", "*Tests.java", "*TestCase.java",
        "*Generated*.java", "*generated*.java",
        "package-info.java"
    ])

    # Directories to skip
    ignore_dirs: List[str] = field(default_factory=lambda: [
        "test", "tests", "target", "build", "out",
        ".git", ".idea", ".vscode", "node_modules"
    ])

    # Diagram settings
    diagram_format: str = "png"
    max_classes_in_diagram: int = 50  # Keep diagrams readable

    def __post_init__(self):
        """Load from environment and validate settings"""
        self._load_from_env()
        self._validate_settings()

    def _load_from_env(self):
        """Load settings from environment variables"""
        # API settings
        if not self.openai_api_key:
            self.openai_api_key = os.getenv('OPENAI_API_KEY', '')

        if os.getenv('OPENAI_MODEL'):
            self.openai_model = os.getenv('OPENAI_MODEL')

        if os.getenv('OPENAI_BASE_URL'):
            self.openai_base_url = os.getenv('OPENAI_BASE_URL')

        # Performance settings from env
        if os.getenv('CODECOMPREHENDER_MAX_WORKERS'):
            try:
                self.max_workers = int(os.getenv('CODECOMPREHENDER_MAX_WORKERS'))
            except ValueError:
                pass

        if os.getenv('CODECOMPREHENDER_BATCH_SIZE'):
            try:
                self.batch_size = int(os.getenv('CODECOMPREHENDER_BATCH_SIZE'))
            except ValueError:
                pass

    def _validate_settings(self):
        """Validate and adjust settings for efficiency"""
        # Set reasonable limits
        if self.max_workers and self.max_workers > 20:
            self.max_workers = 20  # Don't go crazy with processes

        if self.batch_size > 50:
            self.batch_size = 50  # Keep batches manageable

        if self.max_concurrent_requests > 50:
            self.max_concurrent_requests = 50  # Don't overwhelm OpenAI

        # Temperature should be reasonable
        if not 0.0 <= self.temperature <= 2.0:
            self.temperature = 0.3

        # File size limit
        if self.max_file_size_mb <= 0:
            self.max_file_size_mb = 5.0

    @classmethod
    def from_file(cls, config_path: Path) -> 'Config':
        """Load configuration from YAML file"""
        config = cls()

        if not config_path.exists():
            return config

        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)

            # Update config with file values
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        except Exception as e:
            print(f"Warning: Couldn't load config file {config_path}: {e}")

        return config

    def should_skip_file(self, file_path: Path) -> bool:
        """Check if a file should be skipped for performance"""
        # Check file size
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > self.max_file_size_mb:
                return True
        except OSError:
            pass

        # Check filename patterns
        for pattern in self.ignore_patterns:
            if file_path.match(pattern):
                return True

        # Check directory names
        parts = [p.lower() for p in file_path.parts]
        for ignore_dir in self.ignore_dirs:
            if ignore_dir.lower() in parts:
                return True

        return False

    def get_worker_count(self) -> int:
        """Get optimal number of workers"""
        if self.max_workers:
            return self.max_workers

        # Auto-detect based on CPU count
        cpu_count = os.cpu_count() or 1

        # Use half the cores + 1, but at least 2 and at most 8
        workers = max(2, min(8, (cpu_count // 2) + 1))

        return workers