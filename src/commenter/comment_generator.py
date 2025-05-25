"""
AI-powered comment generation with async efficiency

Handles multiple OpenAI API calls concurrently to speed up processing.
Each file can have dozens of comments generated in parallel.
"""

import os
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
            max_retries=3   # Retry failed requests
        )

        logger.debug(f"OpenAI client initialized (PID: {os.getpid()})")
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

        # Print batching info to console (visible in multiprocessing)
        if comment_tasks:
            batch_size = 7
            expected_batches = (len(comment_tasks) + batch_size - 1) // batch_size
            print(f"  📦 {file_path.name}: {len(comment_tasks)} comments → {expected_batches} API call{'s' if expected_batches != 1 else ''}")

        # Insert the generated comments into the source code
        return self._insert_comments(source_lines, completed_tasks)

    def _plan_comments(self, parsed_file, source_lines: List[str], file_path: Path) -> List[CommentTask]:
        """Figure out what comments we need to generate"""
        tasks = []

        # File-level comment
        if getattr(self.config, 'include_file_comments', True) and not self._has_file_comment(source_lines):
            prompt = self._build_file_prompt(parsed_file, file_path)
            insert_line = self._find_file_comment_location(source_lines)
            tasks.append(CommentTask("file", prompt, insert_line, "", False, 150))

        # Class/interface/enum comments
        for cls in parsed_file.classes:
            if not cls.has_javadoc and self.config.use_javadoc and getattr(self.config, 'include_class_comments', True):
                prompt = self._build_class_prompt(cls, parsed_file)
                indent = self._get_line_indent(source_lines, cls.line_number - 1)
                tasks.append(CommentTask("class", prompt, cls.line_number - 1, indent, False, 200))

                # Method comments
                if getattr(self.config, 'include_method_comments', True):
                    for method in cls.methods:
                        if not method.is_constructor and not getattr(method, 'has_javadoc', False):  # Skip constructors
                            prompt = self._build_method_prompt(method, cls)
                            indent = self._get_line_indent(source_lines, method.line_number - 1)
                            tasks.append(CommentTask("method", prompt, method.line_number - 1, indent, False, 180))

                # Field comments (inline style)
                if self.config.add_inline_comments:
                    for field in cls.fields:
                        # Skip constants and obvious fields
                        if not (field.is_static and field.is_final) and not getattr(field, 'has_javadoc', False) and not self._is_obvious_field(field):
                            prompt = self._build_field_prompt(field, cls)
                            tasks.append(CommentTask("field", prompt, field.line_number, "", True, 50))

        return tasks

    async def _generate_all_comments(self, tasks: List[CommentTask]) -> List[Tuple[CommentTask, str]]:
        """
        Generate all comments using batching for efficiency.

        Instead of making individual API calls, we batch multiple comments
        together to reduce API calls and latency.
        """

        # Group tasks into batches of 6-8 for optimal API usage
        batch_size = 7  # Sweet spot for token limits and efficiency
        batches = [tasks[i:i+batch_size] for i in range(0, len(tasks), batch_size)]

        logger.info(f"🚀 BATCHING: Processing {len(tasks)} comments in {len(batches)} API calls (batch size: {batch_size})")
        logger.info(f"💰 Efficiency gain: ~{len(tasks)} individual calls → {len(batches)} batch calls ({100 - (len(batches)/len(tasks)*100):.0f}% fewer calls)")

        completed = []

        # Process each batch
        for batch_num, batch in enumerate(batches, 1):
            logger.info(f"📦 Batch {batch_num}/{len(batches)}: Processing {len(batch)} comments in 1 API call...")

            try:
                batch_results = await self._generate_batch_comments(batch)
                completed.extend(batch_results)
                logger.info(f"✅ Batch {batch_num} completed: {len(batch_results)}/{len(batch)} comments generated")
            except Exception as e:
                logger.warning(f"❌ Batch {batch_num} failed: {e}")
                logger.info(f"🔄 Falling back to individual processing for batch {batch_num}...")

                # Fallback to individual processing for this batch
                individual_success = 0
                for task in batch:
                    try:
                        individual_result = await self._generate_single_comment(task)
                        if individual_result:
                            completed.append((task, individual_result))
                            individual_success += 1
                    except Exception as individual_error:
                        logger.warning(f"Failed individual comment for {task.element_type}: {individual_error}")

                logger.info(f"🔄 Fallback completed: {individual_success}/{len(batch)} comments generated individually")

        success_rate = (len(completed) / len(tasks)) * 100
        logger.info(f"🎯 BATCHING SUMMARY: {len(completed)}/{len(tasks)} comments generated ({success_rate:.1f}% success rate)")
        return completed

    async def _generate_batch_comments(self, tasks: List[CommentTask]) -> List[Tuple[CommentTask, str]]:
        """Generate multiple comments in a single API call"""

        # Build the batch prompt
        batch_prompt = self._build_batch_prompt(tasks)

        logger.debug(f"📤 Sending batch request for {len(tasks)} comments...")

        try:
            response = await self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": batch_prompt}],
                temperature=self.config.temperature,
                max_tokens=min(4000, sum(task.max_tokens for task in tasks))  # Reasonable limit
            )

            logger.debug(f"📥 Received batch response, parsing {len(tasks)} comments...")

            # Parse the batch response
            results = self._parse_batch_response(response.choices[0].message.content, tasks)

            logger.debug(f"✨ Batch parsing successful: {len(results)} comments extracted")
            return results

        except Exception as e:
            logger.debug(f"Batch API call failed: {e}")
            raise

    def _build_batch_prompt(self, tasks: List[CommentTask]) -> str:
        """Build a prompt that requests multiple comments at once"""

        prompt_parts = [
            "Generate brief, professional comments for these Java code elements.",
            "Return ONLY the comment text for each element in the exact order given.",
            "Separate each comment with '---NEXT---' on its own line.",
            "Keep comments concise and helpful.",
            ""
        ]

        for i, task in enumerate(tasks, 1):
            element_info = self._extract_element_info_from_prompt(task.prompt)
            prompt_parts.append(f"{i}. {task.element_type.upper()}: {element_info}")

        prompt_parts.extend([
            "",
            "Format your response as:",
            "Comment for element 1",
            "---NEXT---",
            "Comment for element 2",
            "---NEXT---",
            "Comment for element 3",
            "(etc.)",
            "",
            "Generate the comments now:"
        ])

        return '\n'.join(prompt_parts)

    def _extract_element_info_from_prompt(self, prompt: str) -> str:
        """Extract key information from individual prompts for batching"""
        lines = prompt.split('\n')

        # Find the key information lines
        info_lines = []
        for line in lines:
            if any(keyword in line for keyword in ['File:', 'Class:', 'Method:', 'Field:']):
                info_lines.append(line.strip())
            elif line.startswith('Package:') or line.startswith('Static:') or line.startswith('Visibility:'):
                info_lines.append(line.strip())

        return ' | '.join(info_lines[:3])  # Limit to avoid too long prompts

    def _parse_batch_response(self, response_text: str, tasks: List[CommentTask]) -> List[Tuple[CommentTask, str]]:
        """Parse the batched response and match comments to tasks"""

        # Split response by separator
        comment_parts = response_text.split('---NEXT---')

        results = []
        for i, task in enumerate(tasks):
            if i < len(comment_parts):
                raw_comment = comment_parts[i].strip()
                if raw_comment:
                    formatted_comment = self._format_comment(task, raw_comment)
                    results.append((task, formatted_comment))
                else:
                    logger.debug(f"Empty comment received for {task.element_type}")
            else:
                logger.debug(f"No comment received for {task.element_type} (batch response too short)")

        return results

    async def _generate_single_comment(self, task: CommentTask) -> Optional[str]:
        """Generate a single comment using OpenAI API"""
        try:
            response = await self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": task.prompt}],
                temperature=self.config.temperature,
                max_tokens=task.max_tokens
            )

            # Get raw comment content and format it
            raw_comment = response.choices[0].message.content.strip()
            return self._format_comment(task, raw_comment)

        except Exception as e:
            logger.debug(f"API call failed for {task.element_type}: {e}")
            return None

    def _format_comment(self, task: CommentTask, raw_comment: str) -> str:
        """Format the comment based on its type"""

        if task.element_type == "file":
            return f"""/**
 * {raw_comment}
 * 
 * @author CodeComprehender
 */"""

        elif task.element_type == "class":
            return f"""/**
 * {raw_comment}
 * 
 * @author CodeComprehender
 */"""

        elif task.element_type == "method":
            # Basic JavaDoc format
            return f"""/**
 * {raw_comment}
 */"""

        elif task.element_type == "field":
            # Simple inline comment
            if not raw_comment.startswith('//'):
                return f"// {raw_comment}"
            return raw_comment

        else:
            # Fallback
            return f"// {raw_comment}"

    def _build_file_prompt(self, parsed_file, file_path: Path) -> str:
        """Build prompt for file-level comment"""
        classes = [cls.name for cls in parsed_file.classes[:3]]
        class_summary = ", ".join(classes)
        if len(parsed_file.classes) > 3:
            class_summary += "..."

        return f"""Write a brief description for this Java file:

File: {file_path.name}
Package: {parsed_file.package or 'default package'}
Main classes: {class_summary}
Total imports: {len(parsed_file.imports)}

Explain what this file contains and its main purpose in 1-2 sentences.
Return only the description text, no formatting."""

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

        return f"""Write a brief description for this Java {cls.type}:

{cls.type.title()}: {cls.name}{inheritance}
Package: {parsed_file.package or 'default'}
Methods: {len(cls.methods)}
Fields: {len(cls.fields)}
Visibility: {cls.visibility}

Explain the purpose and main responsibilities of this {cls.type} in 1-2 sentences.
Return only the description text, no formatting."""

    def _build_method_prompt(self, method, cls) -> str:
        """Build prompt for method comment"""
        params = ", ".join([f"{ptype} {pname}" for ptype, pname in method.parameters])
        signature = f"{method.visibility} {method.return_type} {method.name}({params})"

        return f"""Write a brief description for this Java method:

Method: {signature}
Class: {cls.name}
Static: {method.is_static}
Parameters: {len(method.parameters)}
Throws: {', '.join(getattr(method, 'throws', [])) if getattr(method, 'throws', []) else 'none'}

Explain what this method does in 1-2 sentences.
Return only the description text, no formatting."""

    def _build_field_prompt(self, field, cls) -> str:
        """Build prompt for field comment"""
        return f"""Write a very brief description for this Java field:

Field: {field.visibility} {field.type} {field.name}
Class: {cls.name}
Static: {field.is_static}, Final: {field.is_final}

Explain what this field represents in 3-5 words.
Return only the description text, no formatting."""

    def _insert_comments(self, source_lines: List[str], completed_tasks: List[Tuple[CommentTask, str]]) -> str:
        """Insert all generated comments into the source code"""

        # Sort by line number in reverse order so we don't mess up line numbers
        completed_tasks.sort(key=lambda x: x[0].insert_line, reverse=True)

        modified_lines = source_lines.copy()

        for task, formatted_comment in completed_tasks:
            if task.is_inline:
                # Inline comment - add to end of line
                line_num = task.insert_line
                if 0 <= line_num < len(modified_lines):
                    original = modified_lines[line_num].rstrip()
                    modified_lines[line_num] = f"{original}  {formatted_comment}"
            else:
                # Block comment - insert before target line
                comment_lines = formatted_comment.split('\n')
                indented_lines = [task.indent + line for line in comment_lines]

                insert_at = task.insert_line
                modified_lines[insert_at:insert_at] = indented_lines

        return '\n'.join(modified_lines)

    # Helper methods
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
            'index', 'flag', 'status', 'result', 'data', 'item'
        }
        return field.name.lower() in obvious_names