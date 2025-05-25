"""
AI-powered comment generation with async efficiency

Handles multiple OpenAI API calls concurrently to speed up processing.
Each file can have dozens of comments generated in parallel.
"""

import logging
import re
import asyncio
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from dataclasses import dataclass

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class CommentTask:
    """Represents a single comment generation task"""
    element_type: str  # "file", "class", "method", "field"
    prompt: str
    insert_line: int
    indent: str = ""
    is_inline: bool = False
    max_tokens: int = 150


class CommentGenerator:
    """Generate comments efficiently using async OpenAI calls"""

    def __init__(self, config):
        self.config = config
        self.client = None

    async def __aenter__(self):
        """Set up the async OpenAI client"""
        if not self.config.openai_api_key:
            logger.warning("No OpenAI API key - skipping comment generation")
            return self

        self.client = AsyncOpenAI(
            api_key=self.config.openai_api_key,
            timeout=60.0,  # Longer timeout for reliability
            max_retries=3  # Retry failed requests
        )

        logger.debug(f"OpenAI client initialized (PID: {os.getpid() if 'os' in globals() else 'unknown'})")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up the client properly"""
        if self.client:
            try:
                await self.client.close()
                logger.debug("OpenAI client closed")
            except Exception as e:
                logger.warning(f"Error closing OpenAI client: {e}")
            finally:
                self.client = None

    async def add_comments(self, parsed_file, file_path: Path) -> str:
        """
        Add comments to a parsed Java file.

        This is the main entry point - it:
        1. Analyzes what comments are needed
        2. Generates all comments concurrently 
        3. Inserts them into the source code
        """
        if not self.client:
            logger.debug(f"No OpenAI client - returning original code for {file_path.name}")
            return parsed_file.source_code

        source_lines = parsed_file.source_code.split('\n')

        # Build list of all comments we want to generate
        comment_tasks = self._plan_comments(parsed_file, source_lines, file_path)

        if not comment_tasks:
            logger.debug(f"No comments needed for {file_path.name}")
            return parsed_file.source_code

        # Generate all comments concurrently - this is the key efficiency gain
        logger.debug(f"Generating {len(comment_tasks)} comments for {file_path.name}")
        completed_tasks = await self._generate_all_comments(comment_tasks)

        # Insert the generated comments into the source code
        return self._insert_comments(source_lines, completed_tasks)

    def _plan_comments(self, parsed_file, source_lines: List[str], file_path: Path) -> List[CommentTask]:
        """Figure out what comments we need to generate"""
        tasks = []

        # File-level comment
        if not self._has_file_comment(source_lines):
            prompt = self._build_file_prompt(parsed_file, file_path)
            insert_line = self._find_file_comment_location(source_lines)
            tasks.append(CommentTask("file", prompt, insert_line, "", False, 150))

        # Class/interface/enum comments
        for cls in parsed_file.classes:
            if not cls.has_javadoc and self.config.use_javadoc:
                prompt = self._build_class_prompt(cls, parsed_file)
                indent = self._get_line_indent(source_lines, cls.line_number - 1)
                tasks.append(CommentTask("class", prompt, cls.line_number - 1, indent, False, 200))

                # Method comments
                for method in cls.methods:
                    if not method.is_constructor:  # Skip constructors for now
                        prompt = self._build_method_prompt(method, cls)
                        indent = self._get_line_indent(source_lines, method.line_number - 1)
                        tasks.append(CommentTask("method", prompt, method.line_number - 1, indent, False, 180))

                # Field comments (inline style)
                if self.config.add_inline_comments:
                    for field in cls.fields:
                        # Skip constants and obvious fields
                        if not (field.is_static and field.is_final) and not self._is_obvious_field(field):
                            prompt = self._build_field_prompt(field, cls)
                            tasks.append(CommentTask("field", prompt, field.line_number, "", True, 50))

        return tasks

    async def _generate_all_comments(self, tasks: List[CommentTask]) -> List[Tuple[CommentTask, str]]:
        """
        Generate all comments concurrently.

        This is where the async magic happens - instead of waiting for each
        API call sequentially, we fire them all off at once.
        """

        # Create async tasks for all comment generation
        async_tasks = [
            self._generate_single_comment(task)
            for task in tasks
        ]

        # Wait for all to complete, but don't fail if some do
        results = await asyncio.gather(*async_tasks, return_exceptions=True)

        # Filter out failed results
        completed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to generate {tasks[i].element_type} comment: {result}")
            elif result:
                completed.append((tasks[i], result))

        logger.debug(f"Successfully generated {len(completed)}/{len(tasks)} comments")
        return completed

    async def _generate_single_comment(self, task: CommentTask) -> Optional[str]:
        """Generate a single comment using OpenAI API"""
        try:
            response = await self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": task.prompt}],
                temperature=self.config.temperature,
                max_tokens=task.max_tokens
            )

            comment = response.choices[0].message.content.strip()

            # Basic formatting fixes
            if task.is_inline:
                if not comment.startswith('//'):
                    comment = f"// {comment}"
            else:
                if not comment.startswith('/**'):
                    comment = f"/**\n * {comment}\n */"

            return comment

        except Exception as e:
            logger.debug(f"API call failed for {task.element_type}: {e}")
            return None

    def _build_file_prompt(self, parsed_file, file_path: Path) -> str:
        """Build prompt for file-level comment"""
        classes = [cls.name for cls in parsed_file.classes[:3]]
        class_summary = ", ".join(classes)
        if len(parsed_file.classes) > 3:
            class_summary += "..."

        return f"""Write a brief JavaDoc comment for this Java file:

File: {file_path.name}
Package: {parsed_file.package or 'default package'}
Main classes: {class_summary}
Total imports: {len(parsed_file.imports)}

Explain what this file contains and its main purpose.
Keep it concise and helpful.
Return only the JavaDoc comment."""

    def _build_class_prompt(self, cls, parsed_file) -> str:
        """Build prompt for class comment"""
        inheritance = ""
        if cls.extends:
            inheritance += f" extends {cls.extends}"
        if cls.implements:
            impl_list = ", ".join(cls.implements[:2])
            if len(cls.implements) > 2:
                impl_list += "..."
            inheritance += f" implements {impl_list}"

        return f"""Write a concise JavaDoc comment for this Java {cls.type}:

{cls.type.title()}: {cls.name}{inheritance}
Package: {parsed_file.package or 'default'}
Methods: {len(cls.methods)}
Fields: {len(cls.fields)}
Visibility: {cls.visibility}

Explain the purpose and main responsibilities of this {cls.type}.
Return only the JavaDoc comment."""

    def _build_method_prompt(self, method, cls) -> str:
        """Build prompt for method comment"""
        params = ", ".join([f"{ptype} {pname}" for ptype, pname in method.parameters])
        signature = f"{method.visibility} {method.return_type} {method.name}({params})"

        return f"""Write a JavaDoc comment for this Java method:

Method: {signature}
Class: {cls.name}
Static: {method.is_static}

Explain what this method does, include @param and @return if appropriate.
Be practical and helpful.
Return only the JavaDoc comment."""

    def _build_field_prompt(self, field, cls) -> str:
        """Build prompt for field comment"""
        return f"""Write a brief inline comment for this Java field:

Field: {field.visibility} {field.type} {field.name}
Class: {cls.name}
Static: {field.is_static}, Final: {field.is_final}

Just explain what this field represents in a few words.
Return only a single-line comment starting with //"""

    def _has_file_comment(self, source_lines: List[str]) -> bool:
        """Check if file already has a comment at the top"""
        for line in source_lines[:10]:
            stripped = line.strip()
            if stripped.startswith(('/**', '/*')):
                return True
            elif stripped and not stripped.startswith('//'):
                break
        return False

    def _find_file_comment_location(self, source_lines: List[str]) -> int:
        """Find the best place to insert file comment"""
        for i, line in enumerate(source_lines):
            stripped = line.strip()
            if stripped.startswith('package '):
                return i + 1  # After package declaration
            elif stripped and not stripped.startswith('//'):
                return i  # Before first real code
        return 0

    def _get_line_indent(self, source_lines: List[str], line_num: int) -> str:
        """Get indentation of a specific line"""
        if 0 <= line_num < len(source_lines):
            match = re.match(r'^(\s*)', source_lines[line_num])
            return match.group(1) if match else ""
        return ""

    def _is_obvious_field(self, field) -> bool:
        """Skip fields that don't need comments"""
        obvious_names = {
            'id', 'name', 'value', 'count', 'size', 'length',
            'index', 'flag', 'status', 'result'
        }
        return field.name.lower() in obvious_names

    def _insert_comments(self, source_lines: List[str], completed_tasks: List[Tuple[CommentTask, str]]) -> str:
        """Insert all generated comments into the source code"""

        # Sort by line number in reverse order so we don't mess up line numbers
        completed_tasks.sort(key=lambda x: x[0].insert_line, reverse=True)

        modified_lines = source_lines.copy()

        for task, comment in completed_tasks:
            if task.is_inline:
                # Inline comment - add to end of line
                line_num = task.insert_line
                if 0 <= line_num < len(modified_lines):
                    original = modified_lines[line_num].rstrip()
                    modified_lines[line_num] = f"{original}  {comment}"
            else:
                # Block comment - insert before target line
                comment_lines = comment.split('\n')
                indented_lines = [task.indent + line for line in comment_lines]

                insert_at = task.insert_line
                modified_lines[insert_at:insert_at] = indented_lines

        return '\n'.join(modified_lines)


# Add os import at the top if it's missing
import os