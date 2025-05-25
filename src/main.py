#!/usr/bin/env python3
"""
CodeComprehender - Add AI comments to Java code

Uses multiprocessing to handle large codebases efficiently.
Each worker process handles OpenAI API calls concurrently.
"""

import os
import sys
import logging
import multiprocessing
from pathlib import Path
import tempfile
import shutil
import asyncio

import click
from dotenv import load_dotenv

try:
    import tqdm

    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from .utils.config import Config
from .utils.github import GitHubHandler
from .parser.java_parser import JavaParser
from .commenter.comment_generator import CommentGenerator
from .architecture.diagram_generator import DiagramGenerator

# Load environment variables early
load_dotenv()

# Figure out how many processes to use
CPU_COUNT = os.cpu_count() or 1
# Use half the cores + 1, but at least 2 for decent parallelism
MAX_WORKERS = max(2, (CPU_COUNT // 2) + 1)


def setup_logging(verbose=False):
    """Setup logging that works well with multiprocessing"""
    level = logging.DEBUG if verbose else logging.INFO

    # Simple format for multiprocessing - include process name
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s[%(process)d] - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    return logging.getLogger(__name__)


def process_single_file(file_info):
    """
    Worker function for processing individual Java files.

    This runs in a separate process, so it needs to:
    1. Set up its own async event loop
    2. Create its own OpenAI client
    3. Handle all errors gracefully

    Args:
        file_info: tuple of (file_path_str, project_path_str, output_path_str, config_dict)
    """
    file_path_str, project_path_str, output_path_str, config_dict = file_info

    # Recreate paths and config in worker process
    java_file = Path(file_path_str)
    project_path = Path(project_path_str)
    output_path = Path(output_path_str)

    # Rebuild config object from dict
    config = Config()
    for key, value in config_dict.items():
        if hasattr(config, key):
            setattr(config, key, value)

    # Set up logging for this worker
    worker_logger = logging.getLogger(f"worker.{os.getpid()}")

    async def process_file_async():
        """The actual async work happens here"""
        parser = JavaParser()

        try:
            # Parse the Java file
            parsed_file = parser.parse_file(java_file)

            # Generate comments using async OpenAI client
            async with CommentGenerator(config) as commenter:
                commented_code = await commenter.add_comments(parsed_file, java_file)

            # Figure out where to save it
            relative_path = java_file.relative_to(project_path)
            output_file = output_path / 'src' / relative_path

            # Add suffix to filename
            stem = output_file.stem
            suffix = output_file.suffix
            output_file = output_file.parent / f"{stem}{config.file_suffix}{suffix}"

            # Make sure directory exists and save
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(commented_code)

            worker_logger.debug(f"✓ Processed {java_file.name}")
            return True

        except Exception as e:
            worker_logger.warning(f"✗ Failed {java_file.name}: {e}")
            return False

    try:
        # Each worker needs its own event loop
        return asyncio.run(process_file_async())
    except Exception as e:
        worker_logger.error(f"Worker crashed on {java_file.name}: {e}")
        return False


class CodeComprehender:
    """Main application class with efficient processing"""

    def __init__(self, config):
        self.config = config
        self.parser = JavaParser()
        self.github = GitHubHandler()
        self.temp_dir = None
        self.logger = logging.getLogger(__name__)

    def process(self, source, output_dir=None):
        """Main processing pipeline with multiprocessing"""
        try:
            # Get the source code
            if self._is_github_url(source):
                project_path = self._clone_repo(source)
            else:
                project_path = Path(source).resolve()
                if not project_path.exists():
                    self.logger.error(f"Path doesn't exist: {project_path}")
                    return False

            # Set up output directory
            if output_dir:
                output_path = Path(output_dir).resolve()
            else:
                output_path = project_path.parent / f"{project_path.name}_commented"

            output_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Processing {project_path} -> {output_path}")

            # Find Java files to process
            java_files = self._find_java_files(project_path)
            if not java_files:
                self.logger.warning("No Java files found")
                return False

            self.logger.info(f"Found {len(java_files)} Java files")

            # Process files efficiently
            if not self.config.skip_comments:
                success = self._process_files_multiprocess(java_files, project_path, output_path)
                if not success:
                    return False

            # Generate diagrams (single-threaded for now)
            if self.config.generate_diagrams:
                self._generate_diagrams(project_path, output_path)

            self.logger.info(f"✓ All done! Results in {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Processing failed: {e}")
            if self.logger.level <= logging.DEBUG:
                import traceback
                self.logger.debug(traceback.format_exc())
            return False
        finally:
            self._cleanup()

    def _is_github_url(self, source):
        """Check if source is a GitHub URL"""
        return source.startswith(('https://github.com/', 'git@github.com:'))

    def _clone_repo(self, repo_url):
        """Clone GitHub repo to temp directory"""
        self.logger.info(f"Cloning {repo_url}...")
        self.temp_dir = tempfile.mkdtemp()
        return self.github.clone(repo_url, self.temp_dir)

    def _find_java_files(self, project_path):
        """Find Java files worth processing"""
        # Skip the obvious stuff we don't want to process
        skip_patterns = [
            '*Test.java', '*Tests.java', '*TestCase.java',
            '*Generated*.java', '*generated*.java',
            'package-info.java'
        ]

        skip_dirs = {
            'test', 'tests', 'target', 'build', 'out',
            '.git', '.idea', '.vscode', 'node_modules'
        }

        java_files = []
        for file_path in project_path.rglob('*.java'):
            # Skip if in a directory we don't want
            if any(part.lower() in skip_dirs for part in file_path.parts):
                continue

            # Skip files matching our patterns
            if any(file_path.match(pattern) for pattern in skip_patterns):
                continue

            java_files.append(file_path)

        return sorted(java_files)

    def _process_files_multiprocess(self, java_files, project_path, output_path):
        """Process files using multiprocessing for efficiency"""

        # Determine number of workers
        num_workers = min(MAX_WORKERS, len(java_files))
        self.logger.info(f"Using {num_workers} worker processes")

        # Convert config to dict for passing to workers
        config_dict = {
            'openai_api_key': self.config.openai_api_key,
            'openai_model': self.config.openai_model,
            'temperature': self.config.temperature,
            'file_suffix': self.config.file_suffix,
            'use_javadoc': self.config.use_javadoc,
            'add_inline_comments': self.config.add_inline_comments,
        }

        # Prepare file info for workers
        file_infos = [
            (str(java_file), str(project_path), str(output_path), config_dict)
            for java_file in java_files
        ]

        # Process files in parallel
        successful = 0
        failed = 0

        with multiprocessing.Pool(processes=num_workers) as pool:
            if HAS_TQDM:
                # Nice progress bar if available
                results = list(tqdm.tqdm(
                    pool.imap(process_single_file, file_infos),
                    total=len(file_infos),
                    desc="Processing files"
                ))
            else:
                # Just show periodic updates
                results = []
                for i, result in enumerate(pool.imap(process_single_file, file_infos)):
                    results.append(result)
                    if (i + 1) % 10 == 0:
                        self.logger.info(f"Processed {i + 1}/{len(file_infos)} files")

        # Count results
        successful = sum(1 for r in results if r)
        failed = len(results) - successful

        self.logger.info(f"Results: {successful} successful, {failed} failed")

        if failed > successful:
            self.logger.error("More files failed than succeeded - check your API key and network")
            return False

        return True

    def _generate_diagrams(self, project_path, output_path):
        """Generate architecture diagrams"""
        self.logger.info("Generating architecture diagrams...")

        try:
            generator = DiagramGenerator(self.config)
            project_info = self.parser.analyze_project(project_path)

            diagrams_dir = output_path / 'diagrams'
            diagrams_dir.mkdir(exist_ok=True)

            diagrams = generator.generate_all(project_info, diagrams_dir)
            self.logger.info(f"Generated {len(diagrams)} diagrams")

        except Exception as e:
            self.logger.warning(f"Diagram generation failed: {e}")

    def _cleanup(self):
        """Clean up temporary files"""
        if self.temp_dir and Path(self.temp_dir).exists():
            try:
                shutil.rmtree(self.temp_dir)
                self.logger.debug(f"Cleaned up {self.temp_dir}")
            except Exception as e:
                self.logger.warning(f"Couldn't clean up temp dir: {e}")


@click.command()
@click.argument('source', required=True)
@click.option('--output', '-o', help='Output directory')
@click.option('--api-key', help='OpenAI API key')
@click.option('--model', default='gpt-4o-mini', help='OpenAI model')
@click.option('--workers', '-w', type=int, help=f'Number of worker processes (default: {MAX_WORKERS})')
@click.option('--comments-only', is_flag=True, help='Skip architecture diagrams')
@click.option('--diagrams-only', is_flag=True, help='Skip comment generation')
@click.option('--verbose', '-v', is_flag=True, help='Show debug output')
def main(source, output, api_key, model, workers, comments_only, diagrams_only, verbose):
    """
    Add AI-generated comments to Java code efficiently.

    Uses multiprocessing to handle large codebases quickly.

    SOURCE can be a local directory or GitHub repository URL.
    """

    # Set up logging
    logger = setup_logging(verbose)

    # Override worker count if specified
    global MAX_WORKERS
    if workers:
        MAX_WORKERS = max(1, workers)
        logger.info(f"Using {MAX_WORKERS} workers (overridden)")

    # Create config
    config = Config()

    # Apply command line overrides
    if api_key:
        config.openai_api_key = api_key
    config.openai_model = model
    config.skip_comments = diagrams_only
    config.generate_diagrams = not comments_only

    # Validate config
    if not config.skip_comments and not config.openai_api_key:
        logger.error("OpenAI API key required for comment generation!")
        logger.error("Set OPENAI_API_KEY environment variable or use --api-key")
        sys.exit(1)

    # Process the code
    comprehender = CodeComprehender(config)
    success = comprehender.process(source, output)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    # Required for multiprocessing on Windows
    multiprocessing.freeze_support()
    main()