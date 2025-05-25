import click
import sys
from pathlib import Path
import logging
from typing import Optional, Dict, Any
import tempfile
import shutil
import asyncio
import os
import multiprocessing
from functools import partial

# Assuming src is in PYTHONPATH or running as part of a package
from .utils.logger import setup_logger
from .utils.config import Config
from .utils.file_handler import FileHandler
from .utils.github_handler import GitHubHandler
from .parser.java_parser import JavaParser
from .commenter.comment_generator import CommentGenerator
from .architecture.diagram_generator import DiagramGenerator

# This logger is for the main process.
main_process_logger = setup_logger(__name__)

CPU_COUNT = os.cpu_count() or 1
MAX_PROCESSES = max(1, (CPU_COUNT // 2) + (CPU_COUNT % 2) if CPU_COUNT else 2)


def process_single_file_wrapper(java_file_path_str: str, config_dict: dict, project_path_str: str,
                                output_dir_str: str) -> bool:
    """
    Wrapper function to process a single Java file in a separate process.
    Manages the asyncio event loop and CommentGenerator lifecycle for each file.
    """
    worker_log_level_name = config_dict.get('log_level_name', 'INFO')
    worker_log_level = logging.getLevelName(worker_log_level_name)

    _worker_logger = logging.getLogger(f"worker.{os.getpid()}")
    if not _worker_logger.handlers:
        _handler = logging.StreamHandler(sys.stdout)
        # Include process ID in worker logs for clarity
        _formatter = logging.Formatter('%(asctime)s - %(name)s:%(process)d - %(levelname)s - %(message)s')
        _handler.setFormatter(_formatter)
        _worker_logger.addHandler(_handler)
    _worker_logger.setLevel(worker_log_level)

    java_file = Path(java_file_path_str)
    project_path = Path(project_path_str)
    output_dir = Path(output_dir_str)

    class SimpleConfig:  # Helper to pass config values to workers
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            # Ensure all essential config attributes are present with defaults
            self.file_suffix = kwargs.get('file_suffix', '_commented')
            self.encoding = kwargs.get('encoding', 'utf-8')
            self.openai_api_key = kwargs.get('openai_api_key')
            self.openai_base_url = kwargs.get('openai_base_url')
            self.openai_model = kwargs.get('openai_model', 'gpt-3.5-turbo')
            self.temperature = kwargs.get('temperature', 0.3)
            self.max_tokens = kwargs.get('max_tokens', 1000)  # Used by CommentGenerator internally
            self.include_class_comments = kwargs.get('include_class_comments', True)
            self.include_method_comments = kwargs.get('include_method_comments', True)
            self.include_inline_comments = kwargs.get('include_inline_comments', True)
            # Add other fields CommentGenerator might expect from self.config

    process_config = SimpleConfig(**config_dict)
    parser = JavaParser()
    file_handler = FileHandler(process_config)

    async def _perform_file_processing_async():
        # CommentGenerator is used as an async context manager
        # This ensures its __aenter__ (client init) and __aexit__ (client aclose) are called
        async with CommentGenerator(process_config) as comment_generator:
            _worker_logger.debug(f"Parsing: {java_file}")
            parsed_content = parser.parse_file(java_file)

            _worker_logger.debug(f"Generating comments for: {java_file}")
            commented_content_str = await comment_generator.generate_comments_async(parsed_content, java_file)

            relative_path = java_file.relative_to(project_path)
            commented_file_output_dir = output_dir / "src"
            output_file_path = commented_file_output_dir / relative_path.parent / f"{java_file.stem}{process_config.file_suffix}{java_file.suffix}"

            file_handler.save_commented_file(
                original_file=java_file,
                commented_content=commented_content_str,
                output_file=output_file_path
            )
            _worker_logger.info(f"Successfully processed and saved: {java_file} to {output_file_path}")
            # No explicit return needed from here if no error occurs

    try:
        _worker_logger.info(f"Process {os.getpid()}: Starting to process file: {java_file}")
        asyncio.run(_perform_file_processing_async())
        return True  # Success if asyncio.run completes without raising an exception
    except Exception as e:
        _worker_logger.error(f"Process {os.getpid()}: Error processing {java_file}: {e}")
        import traceback
        _worker_logger.debug(f"Process {os.getpid()}: Traceback for {java_file}:\n{traceback.format_exc()}")
        return False


class CodeComprehender:
    def __init__(self, config: Config):
        self.config = config
        self.file_handler = FileHandler(config)
        self.github_handler = GitHubHandler()
        self.parser = JavaParser()
        self.diagram_generator = DiagramGenerator(config)
        self.temp_dir = None

    def _analyze_and_comment_multiprocess(self, project_path: Path, output_dir: Path) -> None:
        java_files = self.file_handler.find_java_files(project_path)

        if not java_files:
            main_process_logger.warning("No Java files found in the project")
            return

        num_processes_to_use = min(MAX_PROCESSES, len(java_files))
        main_process_logger.info(
            f"Found {len(java_files)} Java files to process using up to {num_processes_to_use} parallel processes.")

        config_dict = {attr: getattr(self.config, attr) for attr in dir(self.config)
                       if not callable(getattr(self.config, attr)) and not attr.startswith("__")}

        # Pass the string name of the log level for the worker to use for its own logger
        current_main_log_level = main_process_logger.getEffectiveLevel()  # Use the specific logger for main process
        config_dict['log_level_name'] = logging.getLevelName(current_main_log_level)

        task_processor = partial(process_single_file_wrapper,
                                 config_dict=config_dict,
                                 project_path_str=str(project_path),
                                 output_dir_str=str(output_dir))

        java_file_paths_str = [str(jf) for jf in java_files]
        results = []

        with multiprocessing.Pool(processes=num_processes_to_use) as pool:
            main_process_logger.info(f"Starting multiprocessing pool with {num_processes_to_use} workers.")
            try:
                import tqdm
                main_process_logger.info("Using tqdm for progress indication.")
                for result in tqdm.tqdm(pool.imap_unordered(task_processor, java_file_paths_str),
                                        total=len(java_file_paths_str),
                                        desc="Processing Java files (multiprocess)"):
                    results.append(result)
            except ImportError:
                main_process_logger.info(
                    "tqdm not found. Processing without detailed progress bar for multiprocessing.")
                results = list(pool.map(task_processor, java_file_paths_str))

        successful_files = sum(1 for r in results if r is True)
        failed_files = len(results) - successful_files
        main_process_logger.info(
            f"Comment generation complete. Successfully processed {successful_files} files. Failed to process {failed_files} files.")

    def process_repository(self, source: str, output_dir_cli: Optional[Path] = None) -> None:
        actual_output_dir: Path
        project_root_for_processing: Path

        try:
            if self._is_github_url(source):
                main_process_logger.info(f"Cloning GitHub repository: {source}")
                self.temp_dir = tempfile.mkdtemp()
                project_root_for_processing = self.github_handler.clone_repository(source, self.temp_dir)
                if output_dir_cli is None:
                    default_output_base = Path.cwd()
                    actual_output_dir = default_output_base / f"{project_root_for_processing.name}_comprehended"
                    main_process_logger.info(f"--output-dir not specified for URL, defaulting to: {actual_output_dir}")
                else:
                    actual_output_dir = output_dir_cli.resolve()
            else:
                project_root_for_processing = Path(source).resolve()
                if not project_root_for_processing.exists():
                    raise ValueError(f"Local path does not exist: {project_root_for_processing}")
                if not project_root_for_processing.is_dir():
                    raise ValueError(f"Local path is not a directory: {project_root_for_processing}")
                if output_dir_cli is None:
                    actual_output_dir = project_root_for_processing.parent / f"{project_root_for_processing.name}_comprehended"
                    main_process_logger.info(
                        f"--output-dir not specified for local path, defaulting to: {actual_output_dir}")
                else:
                    actual_output_dir = output_dir_cli.resolve()

            actual_output_dir.mkdir(parents=True, exist_ok=True)
            # Create src and architecture subdirs in the output directory
            (actual_output_dir / "src").mkdir(parents=True, exist_ok=True)
            (actual_output_dir / "architecture").mkdir(parents=True, exist_ok=True)

            main_process_logger.info(f"Processing project at: {project_root_for_processing}")
            main_process_logger.info(f"Output will be saved to: {actual_output_dir}")

            if not self.config.architecture_only:
                self._analyze_and_comment_multiprocess(project_root_for_processing, actual_output_dir)
            else:
                main_process_logger.info("Skipping comment generation (--architecture-only).")

            if not self.config.comments_only:
                self._generate_architecture(project_root_for_processing, actual_output_dir)
            else:
                main_process_logger.info("Skipping architecture diagram generation (--comments-only).")

            main_process_logger.info(f"Processing complete! Output saved to: {actual_output_dir.resolve()}")

        except Exception as e:
            main_process_logger.error(f"Error in process_repository: {e}")
            if main_process_logger.getEffectiveLevel() <= logging.DEBUG:
                import traceback
                main_process_logger.debug(traceback.format_exc())
        finally:
            if self.temp_dir and Path(self.temp_dir).exists():
                # shutil.rmtree(self.temp_dir) # Keep commented for debugging
                # main_process_logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
                main_process_logger.info(f"Temporary directory NOT cleaned up (for debugging): {self.temp_dir}")

    def _is_github_url(self, source: str) -> bool:
        return source.startswith(('https://github.com/', 'git@github.com:'))

    def _generate_architecture(self, project_path: Path, output_dir: Path) -> None:
        main_process_logger.info("Generating architecture diagrams...")
        try:
            architecture_output_path = output_dir / "architecture"  # Ensure this path is used
            project_structure = self.parser.analyze_project_structure(project_path)
            diagram_files = self.diagram_generator.generate_diagrams(
                project_structure,
                architecture_output_path
            )
            main_process_logger.info(
                f"Generated {len(diagram_files)} architecture diagrams in {architecture_output_path.resolve()}")
        except Exception as e:
            main_process_logger.error(f"Error generating architecture diagrams: {e}")
            if main_process_logger.getEffectiveLevel() <= logging.DEBUG:
                import traceback
                main_process_logger.debug(traceback.format_exc())


@click.command()
@click.argument('source')
@click.option('--output-dir', '-o', "output_dir_cli_arg", type=click.Path(),
              help='Output directory for processed files.')
@click.option('--api-key', help='OpenAI API key (overrides .env file or environment variable)')
@click.option('--base-url', help='OpenAI base URL (overrides .env file or environment variable)')
@click.option('--config', '-c', "config_path_cli", type=click.Path(exists=True, dir_okay=False),
              help='Configuration file path.')
@click.option('--comments-only', is_flag=True, default=False,
              help='Generate only comments, skip architecture diagrams.')
@click.option('--architecture-only', is_flag=True, default=False,
              help='Generate only architecture diagrams, skip comments.')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose DEBUG logging.')
def main(source: str, output_dir_cli_arg: Optional[str], api_key: Optional[str],
         base_url: Optional[str], config_path_cli: Optional[str], comments_only: bool,
         architecture_only: bool, verbose: bool) -> None:
    """
    CodeComprehender - Analyze and annotate Java codebases with AI-generated comments.
    """
    log_level = logging.DEBUG if verbose else logging.INFO

    # Ensure main_process_logger (which is setup_logger(__name__)) level is set
    # setup_logger might already configure a handler. If basicConfig runs, it adds another.
    # For simplicity, let basicConfig set the root and our specific logger inherit.
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(processName)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True  # Override any existing root logger configuration
    )
    # Explicitly set level for the main process logger after basicConfig
    main_process_logger.setLevel(log_level)

    main_process_logger.info(
        f"CodeComprehender started. Effective log level for main: {logging.getLevelName(main_process_logger.getEffectiveLevel())}")
    if verbose:
        main_process_logger.debug("Verbose logging enabled.")

    try:
        app_config = Config(config_file=config_path_cli)

        if api_key:
            app_config.openai_api_key = api_key
        if base_url:
            app_config.openai_base_url = base_url

        # Check for API key if comments are needed
        generate_comments_flag = not architecture_only
        if generate_comments_flag and not app_config.openai_api_key:
            # If comments_only is True, it implies generate_comments_flag is True
            # If neither comments_only nor architecture_only is set, default is to do both.
            main_process_logger.warning(
                "OpenAI API key not found. Comment generation will be skipped or fail. "
                "Set API key or use --architecture-only."
            )
            # Decide if this should be a fatal error or if CommentGenerator should just skip API calls
            # For now, CommentGenerator is designed to check for self.async_client.

        app_config.comments_only = comments_only
        app_config.architecture_only = architecture_only

        output_dir_path_obj: Optional[Path] = Path(output_dir_cli_arg).resolve() if output_dir_cli_arg else None

        comprehender = CodeComprehender(app_config)
        comprehender.process_repository(source, output_dir_path_obj)

    except Exception as e:
        main_process_logger.error(f"Fatal error in main: {e}", exc_info=(log_level == logging.DEBUG))
        sys.exit(1)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()