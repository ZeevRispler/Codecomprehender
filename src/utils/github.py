"""
Simple GitHub repository cloning

Just does the basic job of cloning repos.
"""

import subprocess
import logging
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class GitHubHandler:
    """Handle cloning GitHub repositories"""

    def clone(self, repo_url: str, target_dir: str) -> Path:
        """Clone a GitHub repo"""
        repo_name = self._get_repo_name(repo_url)
        clone_path = Path(target_dir) / repo_name

        try:
            # Simple git clone
            result = subprocess.run([
                'git', 'clone', '--depth', '1',  # Shallow clone for speed
                repo_url, str(clone_path)
            ], capture_output=True, text=True, check=True)

            logger.info(f"Cloned to {clone_path}")
            return clone_path

        except subprocess.CalledProcessError as e:
            if "not found" in e.stderr.lower():
                raise RuntimeError(f"Repository not found: {repo_url}")
            else:
                raise RuntimeError(f"Failed to clone {repo_url}: {e.stderr}")

        except FileNotFoundError:
            raise RuntimeError("Git not found - please install Git first")

    def _get_repo_name(self, repo_url: str) -> str:
        """Extract repository name from URL"""
        if repo_url.startswith('git@'):
            # git@github.com:user/repo.git
            name = repo_url.split(':')[-1]
        else:
            # https://github.com/user/repo.git
            parsed = urlparse(repo_url)
            name = parsed.path.strip('/')

        # Remove .git suffix
        if name.endswith('.git'):
            name = name[:-4]

        # Get just the repo name (last part)
        return name.split('/')[-1]