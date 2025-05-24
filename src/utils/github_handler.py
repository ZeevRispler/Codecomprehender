"""GitHub repository handling utilities"""

import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class GitHubHandler:
    """Handles GitHub repository operations"""

    def clone_repository(self, repo_url: str, target_dir: str) -> Path:
        """Clone a GitHub repository to a target directory"""
        # Parse repository name from URL
        repo_name = self._get_repo_name(repo_url)
        clone_path = Path(target_dir) / repo_name

        try:
            # Clone the repository
            logger.info(f"Cloning repository to {clone_path}")
            subprocess.run(
                ["git", "clone", repo_url, str(clone_path)],
                check=True,
                capture_output=True,
                text=True
            )

            return clone_path

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e.stderr}")
            raise RuntimeError(f"Failed to clone repository: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def _get_repo_name(self, repo_url: str) -> str:
        """Extract repository name from GitHub URL"""
        # Handle both HTTPS and SSH URLs
        if repo_url.startswith("git@"):
            # SSH URL format: git@github.com:user/repo.git
            parts = repo_url.split(":")[-1]
        else:
            # HTTPS URL format: https://github.com/user/repo.git
            parsed = urlparse(repo_url)
            parts = parsed.path.strip("/")

        # Remove .git extension if present
        if parts.endswith(".git"):
            parts = parts[:-4]

        # Get just the repo name
        return parts.split("/")[-1]