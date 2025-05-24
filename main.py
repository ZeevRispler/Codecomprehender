#!/usr/bin/env python3
"""
CodeComprehender - Main entry point
Analyzes Java codebases and adds meaningful comments using OpenAI
"""

import click
import sys
from pathlib import Path
import logging
from typing import Optional
import tempfile
import shutil

from src.utils.logger import setup_logger
from src.utils.config import Config
from src.utils.file_handler import FileHandler
from src.utils.github_handler import GitHubHandler
from src.parser.java_parser import JavaParser
from src.commenter.comment_generator import CommentGenerator
from src.architecture.diagram_generator import DiagramGenerator

logger = setup_logger(__name__)


class CodeComprehender:
    """Main application class for CodeComprehender"""

    def __init__(self, config: Config):
        self.config = config
        self.file_handler = FileHandler(config)
        self.github_handler = GitHubHandler()
        self.parser = JavaParser()
        self.comment_generator = CommentGenerator(config)
        self.diagram_generator = DiagramGenerator(config)
        self.temp_dir = None

    def process_repository(self, source: str, output_dir: Optional[Path] = None) -> None:
        """Process a Java repository from local path or GitHub URL"""
        try:
            # Determine if source is GitHub URL or local path
            if self._is_github_url(source):
                logger.info(f"Cloning GitHub repository: {source}")
                self.temp_dir = tempfile.mkdtemp()
                project_path = self.github_handler.clone_repository(source, self.temp_dir)
            else:
                project_path = Path(source)
                if not project_path.exists():
                    raise ValueError(f"Path does not exist: {source}")

            logger.info(f"Processing project at: {project_path}")

            # Set output directory
            if output_dir is None:
                output_dir = project_path.parent / f"{project_path.name}_comprehended"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Process the codebase
            self._analyze_and_comment(project_path, output_dir)

            # Generate architecture diagram
            if not self.config.comments_only:
                self._generate_architecture(project_path, output_dir)

            logger.info(f"Processing complete! Output saved to: {output_dir}")

        except Exception as e:
            logger.error(f"Error processing repository: {e}")
            raise
        finally:
            # Cleanup temporary directory if used
            if self.temp_dir and Path(self.temp_dir).exists():
                shutil.rmtree(self.temp_dir)

    def _is_github_url(self, source: str) -> bool:
        """Check if the source is a GitHub URL"""
        return source.startswith(('https://github.com/', 'git@github.com:'))

    def _analyze_and_comment(self, project_path: Path, output_dir: Path) -> None:
        """Analyze Java files and add comments"""
        java_files = self.file_handler.find_java_files(project_path)

        if not java_files:
            logger.warning("No Java files found in the project")
            return

        logger.info(f"Found {len(java_files)} Java files to process")

        with click.progressbar(java_files, label='Processing Java files') as files:
            for java_file in files:
                try:
                    # Parse the Java file
                    parsed_content = self.parser.parse_file(java_file)

                    # Generate comments
                    commented_content = self.comment_generator.generate_comments(
                        parsed_content,
                        java_file
                    )

                    # Save commented version
                    relative_path = java_file.relative_to(project_path)
                    output_file = output_dir / relative_path.parent / f"{java_file.stem}_commented{java_file.suffix}"

                    self.file_handler.save_commented_file(
                        original_file=java_file,
                        commented_content=commented_content,
                        output_file=output_file
                    )

                except Exception as e:
                    logger.error(f"Error processing {java_file}: {e}")
                    continue

    def _generate_architecture(self, project_path: Path, output_dir: Path) -> None:
        """Generate architecture diagrams"""
        logger.info("Generating architecture diagrams...")

        try:
            # Analyze project structure
            project_structure = self.parser.analyze_project_structure(project_path)

            # Generate diagrams
            diagram_files = self.diagram_generator.generate_diagrams(
                project_structure,
                output_dir / "architecture"
            )

            logger.info(f"Generated {len(diagram_files)} architecture diagrams")

        except Exception as e:
            logger.error(f"Error generating architecture diagrams: {e}")


@click.command()
@click.argument('source')
@click.option('--output-dir', '-o', type=click.Path(), help='Output directory for processed files')
@click.option('--api-key', help='OpenAI API key (overrides .env file)')
@click.option('--base-url', help='OpenAI base URL (overrides .env file)')
@click.option('--config', '-c', type=click.Path(exists=True), help='Configuration file path')
@click.option('--comments-only', is_flag=True, help='Generate only comments, skip architecture diagrams')
@click.option('--architecture-only', is_flag=True, help='Generate only architecture diagrams, skip comments')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(source: str, output_dir: Optional[str], api_key: Optional[str],
         base_url: Optional[str], config: Optional[str], comments_only: bool,
         architecture_only: bool, verbose: bool) -> None:
    """
    CodeComprehender - Analyze and annotate Java codebases with AI-generated comments.

    Examples:
        codecomprehender /path/to/java/project
        codecomprehender https://github.com/user/repo
        codecomprehender https://github.com/user/repo -o ./output
    """

    # Setup logging level
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load configuration
        app_config = Config(config_file=config)

        # Override with command-line arguments if provided
        if api_key:
            app_config.openai_api_key = api_key
        if base_url:
            app_config.openai_base_url = base_url

        # Validate API key
        if not app_config.openai_api_key:
            raise click.ClickException(
                "OpenAI API key not found. Please:\n"
                "1. Create a .env file with OPENAI_API_KEY=your-key\n"
                "2. Or set OPENAI_API_KEY environment variable\n"
                "3. Or provide --api-key option"
            )

        # Set processing flags
        app_config.comments_only = comments_only or architecture_only
        app_config.architecture_only = architecture_only or comments_only

        # Create and run the comprehender
        comprehender = CodeComprehender(app_config)
        comprehender.process_repository(source, Path(output_dir) if output_dir else None)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()