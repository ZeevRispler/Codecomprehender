"""File handling utilities for CodeComprehender"""

import shutil
from pathlib import Path
from typing import List, Set
import fnmatch
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class FileHandler:
    """Handles file operations for the project"""

    def __init__(self, config):
        self.config = config
        self.ignore_patterns = set(config.ignore_patterns)

    def find_java_files(self, root_path: Path) -> List[Path]:
        """Find all Java files in the project, excluding ignored patterns"""
        java_files = []

        for file_path in root_path.rglob("*.java"):
            # Check if file should be ignored
            if self._should_ignore(file_path):
                logger.debug(f"Ignoring file: {file_path}")
                continue

            java_files.append(file_path)

        return sorted(java_files)

    def _should_ignore(self, file_path: Path) -> bool:
        """Check if a file should be ignored based on patterns"""
        file_name = file_path.name

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return True

        # Also ignore common directories
        parts = file_path.parts
        ignored_dirs = {'.git', 'target', 'build', 'out', '.idea', '.vscode'}

        return any(part in ignored_dirs for part in parts)

    def save_commented_file(self, original_file: Path, commented_content: str,
                          output_file: Path) -> None:
        """Save the commented version of a file"""
        # Create output directory if it doesn't exist
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the commented content
        with open(output_file, 'w', encoding=self.config.encoding) as f:
            f.write(commented_content)

        logger.debug(f"Saved commented file: {output_file}")

    def copy_non_java_files(self, source_dir: Path, output_dir: Path) -> None:
        """Copy non-Java files to maintain project structure"""
        for file_path in source_dir.rglob("*"):
            if file_path.is_file() and not file_path.suffix == ".java":
                relative_path = file_path.relative_to(source_dir)
                output_path = output_dir / relative_path

                # Skip ignored directories
                if self._should_ignore(file_path):
                    continue

                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, output_path)
