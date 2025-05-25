import openai
import asyncio
import re
import dataclasses
import os  # For os.getpid() in debug logs
from typing import List, Optional, Dict, Any, Tuple

# Adjust relative imports based on your project structure and execution method
from ..utils.logger import setup_logger
from ..parser.java_parser import ParsedFile, ParsedClass, ParsedMethod, ParsedField
from ..utils.config import Config  # Assuming Config object is passed

logger = setup_logger(__name__)


@dataclasses.dataclass
class CommentTask:
    element_key: str
    prompt: str
    max_tokens: int
    insert_at_line: int
    indentation: str = ""
    is_inline: bool = False


class CommentGenerator:
    def __init__(self, config: Config):  # Expects a Config object or similar attribute provider
        self.config = config
        self._async_client = None  # Internal client instance, initialized in __aenter__

    async def __aenter__(self):
        """Initializes the async client when entering the context."""
        logger.debug(f"CommentGenerator context __aenter__ called (PID: {os.getpid()})")
        if not hasattr(self.config, 'openai_api_key') or not self.config.openai_api_key:
            logger.warning(
                f"OpenAI API key not configured in __aenter__ (PID: {os.getpid()}). API calls will fail if attempted.")
            return self

        client_args = {"api_key": self.config.openai_api_key}
        if hasattr(self.config, 'openai_base_url') and self.config.openai_base_url:
            client_args["base_url"] = self.config.openai_base_url

        if hasattr(self.config, 'openai_timeout') and self.config.openai_timeout:
            client_args["timeout"] = self.config.openai_timeout
        if hasattr(self.config, 'openai_max_retries') and self.config.openai_max_retries:
            client_args["max_retries"] = self.config.openai_max_retries

        self._async_client = openai.AsyncOpenAI(**client_args)

        logger.debug(
            f"AsyncOpenAI client initialized in __aenter__ (PID: {os.getpid()}). Type: {type(self._async_client)}")
        if self._async_client:
            logger.debug(
                f"Does self._async_client have 'aclose' in __aenter__? {hasattr(self._async_client, 'aclose')}")
            logger.debug(f"Does self._async_client have 'close' in __aenter__? {hasattr(self._async_client, 'close')}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes the async client when exiting the context."""
        logger.debug(f"CommentGenerator context __aexit__ called (PID: {os.getpid()})")
        if self._async_client:
            logger.debug(
                f"Attempting to close client in __aexit__. Type: {type(self._async_client)} (PID: {os.getpid()})")

            closed_successfully = False
            # Prioritize calling close() and awaiting it, as per user feedback it works.
            if hasattr(self._async_client, 'close'):
                try:
                    await self._async_client.close()
                    closed_successfully = True
                except TypeError as te:
                    logger.error(
                        f"TypeError calling await self._async_client.close() (PID: {os.getpid()}): {te}. 'close' might be synchronous.")
                    # Try synchronous call if await failed with TypeError
                    try:
                        self._async_client.close()
                        logger.info(
                            f"Synchronous self._async_client.close() called after TypeError (PID: {os.getpid()}).")
                        closed_successfully = True
                    except Exception as e_sync_close:
                        logger.error(
                            f"Error calling synchronous self._async_client.close() (PID: {os.getpid()}): {e_sync_close}")
                except RuntimeError as e_runtime:
                    if "Event loop is closed" in str(e_runtime):
                        logger.warning(
                            f"Caught 'Event loop is closed' during client.close() in __aexit__ (PID: {os.getpid()}).")
                    else:
                        logger.error(
                            f"RuntimeError calling close() on AsyncOpenAI client in __aexit__ (PID: {os.getpid()}): {e_runtime}")
                except Exception as e:
                    logger.error(f"Error calling await self._async_client.close() (PID: {os.getpid()}): {e}")

            # Fallback to aclose if close was not present or failed (less likely now)
            elif not closed_successfully and hasattr(self._async_client, 'aclose'):
                logger.warning(
                    f"Client does not have 'close' or it failed/wasn't primary. Trying 'aclose'. Calling await self._async_client.aclose() (PID: {os.getpid()}).")
                try:
                    await self._async_client.aclose()
                    logger.debug(f"AsyncOpenAI client.aclose() completed (PID: {os.getpid()}).")
                    closed_successfully = True
                except RuntimeError as e_runtime:  # Catch specific error if it persists
                    if "Event loop is closed" in str(e_runtime):
                        logger.warning(
                            f"Caught 'Event loop is closed' during client.aclose() in __aexit__ (PID: {os.getpid()}).")
                    else:  # Re-raise other RuntimeErrors or handle as needed
                        logger.error(
                            f"RuntimeError calling aclose() on client in __aexit__ (PID: {os.getpid()}): {e_runtime}")
                except Exception as e:  # Catch other exceptions during aclose
                    logger.error(f"Generic error calling aclose() on client in __aexit__ (PID: {os.getpid()}): {e}")

            if not closed_successfully:
                logger.error(
                    f"CRITICAL: self._async_client (type: {type(self._async_client)}) could not be closed properly via 'close' or 'aclose' in __aexit__ (PID: {os.getpid()}).")
        else:
            logger.debug(f"No async_client to close in __aexit__ (PID: {os.getpid()}).")
        self._async_client = None

    def _get_indentation(self, source_lines: List[str], line_number: int) -> str:
        if 0 <= line_number < len(source_lines):
            line = source_lines[line_number]
            match = re.match(r'^(\s*)', line)
            return match.group(1) if match else ''
        return ''

    async def _generate_single_comment_text_async(self, prompt: str, max_tokens: int, element_key_for_log: str) -> \
    Optional[str]:
        if not self._async_client:
            logger.error(
                f"OpenAI client not available for {element_key_for_log}. Cannot generate comment (PID: {os.getpid()}).")
            return None
        try:
            openai_model = getattr(self.config, 'openai_model', 'gpt-3.5-turbo')
            temperature = getattr(self.config, 'temperature', 0.3)
            config_max_tokens = getattr(self.config, 'max_tokens', 1000)

            response = await self._async_client.chat.completions.create(
                model=openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=min(max_tokens, config_max_tokens)
            )
            comment_text = response.choices[0].message.content.strip()

            if "JavaDoc file-level comment" in prompt:
                if not comment_text.startswith("/**"): comment_text = f"/**\n * {comment_text}\n */"
            elif "JavaDoc comment for this Java" in prompt:
                if not comment_text.startswith("/**"): comment_text = f"/**\n * {comment_text}\n */"
            elif "inline comment for this Java field" in prompt:
                if not comment_text.startswith("//"): comment_text = f"// {comment_text}"
            return comment_text
        except Exception as e:
            logger.error(
                f"Error generating single comment for {element_key_for_log} (PID: {os.getpid()}) (prompt: '{prompt[:70]}...'): {e}")
            return None

    def _has_file_comment(self, source_lines: List[str]) -> bool:
        for i, line in enumerate(source_lines):
            stripped_line = line.strip()
            if not stripped_line: continue
            if stripped_line.startswith("package ") or stripped_line.startswith("import "): return False
            if stripped_line.startswith("/**") or stripped_line.startswith("/*"): return True
            if stripped_line.startswith("//") and i < 5: continue
            if "class " in stripped_line or "interface " in stripped_line or "enum " in stripped_line: return False
            if i > 10 and stripped_line: return False
        return False

    def _build_file_prompt(self, parsed_file: ParsedFile, file_path) -> str:
        return f"""Generate a concise JavaDoc file-level comment for this Java file:
File: {file_path.name}
Package: {parsed_file.package_name or 'N/A'}
Classes: {', '.join(cls.name for cls in parsed_file.classes[:3])}{'...' if len(parsed_file.classes) > 3 else ''}
Main imports: {', '.join(parsed_file.imports[:5])}{'...' if len(parsed_file.imports) > 5 else ''}
The comment should explain the file's purpose and main functionality. Return ONLY the JavaDoc comment, no explanations."""

    def _build_class_prompt(self, parsed_class: ParsedClass, parsed_file: ParsedFile) -> str:
        return f"""Generate a concise JavaDoc comment for this Java {parsed_class.type}:
Name: {parsed_class.name}
Package: {parsed_file.package_name or 'N/A'}
Visibility: {parsed_class.visibility}
Extends: {parsed_class.extends or 'None'}
Implements: {', '.join(parsed_class.implements[:3]) if parsed_class.implements else 'None'}{'...' if parsed_class.implements and len(parsed_class.implements) > 3 else ''}
Key methods: {', '.join(m.name for m in parsed_class.methods[:3])}{'...' if len(parsed_class.methods) > 3 else ''}
Key fields: {', '.join(f.name for f in parsed_class.fields[:3])}{'...' if len(parsed_class.fields) > 3 else ''}
The comment should explain the class's purpose, responsibilities, and key features. Return ONLY the JavaDoc comment, no explanations."""

    def _build_method_prompt(self, method: ParsedMethod, parsed_class: ParsedClass) -> str:
        params_str = ", ".join(f"{ptype} {pname}" for ptype, pname in method.parameters)
        return f"""Generate a concise JavaDoc comment for this Java method:
Class: {parsed_class.name}
Method Signature: {method.visibility} {'static ' if method.is_static else ''}{method.return_type} {method.name}({params_str}){' throws ' + ', '.join(method.throws) if method.throws else ''}
Abstract: {method.is_abstract}
Method Body Snippet (max 100 chars): {method.body[:100] if method.body else "N/A"}
The comment should explain what the method does, its parameters (@param TypeName ParameterName - Description), return value (@return ReturnType - Description), and any exceptions (@throws ExceptionType - Description). Use proper JavaDoc format. Return ONLY the JavaDoc comment, no explanations."""

    def _build_field_prompt(self, field: ParsedField, parsed_class: ParsedClass) -> str:
        return f"""Generate a very brief inline comment for this Java field:
Class: {parsed_class.name}
Field Declaration: {field.visibility} {'static ' if field.is_static else ''}{'final ' if field.is_final else ''}{field.type} {field.name};
Initial Value Snippet (max 50 chars): {field.initial_value[:50] if field.initial_value else "N/A"}
Return ONLY a brief inline comment (starting with //) explaining the field's purpose. Keep it under 15 words."""

    async def generate_comments_async(self, parsed_file: ParsedFile, file_path) -> str:
        if not self._async_client:
            logger.warning(
                f"Cannot generate comments for {file_path.name}, OpenAI client not properly initialized (PID: {os.getpid()}).")
            return parsed_file.source_code

        source_lines = parsed_file.source_code.split('\n')
        comment_tasks_defs: List[CommentTask] = []

        file_comment_insert_line = 0
        found_package_or_import_or_class = False
        for idx, line_content in enumerate(source_lines):
            stripped = line_content.strip();
            if not stripped: continue
            if stripped.startswith("package "):
                file_comment_insert_line = idx + 1; found_package_or_import_or_class = True
            elif stripped.startswith("import ") or \
                    any(stripped.startswith(prefix) for prefix in
                        ["public class", "class ", "public interface", "interface ", "public enum", "enum "]):
                if not found_package_or_import_or_class: file_comment_insert_line = idx
                found_package_or_import_or_class = True;
                break
            elif stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
                if not found_package_or_import_or_class: file_comment_insert_line = idx
                found_package_or_import_or_class = True;
                break
            if idx > 20 and not found_package_or_import_or_class: break

        include_file_level_comment = getattr(self.config, 'include_class_comments', True)
        include_class_comments_flag = getattr(self.config, 'include_class_comments', True)
        include_method_comments_flag = getattr(self.config, 'include_method_comments', True)
        include_inline_comments_flag = getattr(self.config, 'include_inline_comments', True)

        if include_file_level_comment and not self._has_file_comment(source_lines):
            file_prompt = self._build_file_prompt(parsed_file, file_path)
            comment_tasks_defs.append(CommentTask(element_key="file_comment", prompt=file_prompt, max_tokens=200,
                                                  insert_at_line=file_comment_insert_line, indentation=""))

        for p_class in parsed_file.classes:
            class_insert_line = p_class.line_number - 1 if p_class.line_number > 0 else 0
            class_indent = self._get_indentation(source_lines, class_insert_line)
            if include_class_comments_flag and not p_class.documentation:
                class_prompt = self._build_class_prompt(p_class, parsed_file)
                comment_tasks_defs.append(
                    CommentTask(element_key=f"class_{p_class.name}", prompt=class_prompt, max_tokens=300,
                                insert_at_line=class_insert_line, indentation=class_indent))

            if include_method_comments_flag:
                for method in p_class.methods:
                    if not method.documentation:
                        method_insert_line = method.line_number - 1 if method.line_number > 0 else 0
                        method_indent = self._get_indentation(source_lines, method_insert_line)
                        method_prompt = self._build_method_prompt(method, p_class)
                        comment_tasks_defs.append(
                            CommentTask(element_key=f"method_{p_class.name}_{method.name}", prompt=method_prompt,
                                        max_tokens=250, insert_at_line=method_insert_line, indentation=method_indent))

            if include_inline_comments_flag:
                for field in p_class.fields:
                    if not field.documentation:
                        field_insert_line = field.line_number - 1 if field.line_number > 0 else 0
                        field_prompt = self._build_field_prompt(field, p_class)
                        comment_tasks_defs.append(
                            CommentTask(element_key=f"field_{p_class.name}_{field.name}", prompt=field_prompt,
                                        max_tokens=60, insert_at_line=field_insert_line, is_inline=True))

        if not comment_tasks_defs: return parsed_file.source_code

        async_api_tasks = [self._generate_single_comment_text_async(td.prompt, td.max_tokens, td.element_key) for td in
                           comment_tasks_defs]
        generated_texts_or_exceptions = await asyncio.gather(*async_api_tasks, return_exceptions=True)

        comments_to_insert: List[Tuple[CommentTask, str]] = []
        for i, result_or_exc in enumerate(generated_texts_or_exceptions):
            task_def = comment_tasks_defs[i]
            if isinstance(result_or_exc, Exception):
                logger.error(
                    f"Skipping comment for {task_def.element_key} due to generation error: {result_or_exc} (PID: {os.getpid()})")
            elif result_or_exc:
                comments_to_insert.append((task_def, result_or_exc))

        comments_to_insert.sort(key=lambda x: (x[0].insert_at_line, x[0].is_inline), reverse=True)
        modified_lines = list(source_lines)

        for task_def, comment_text in comments_to_insert:
            insert_line_idx = task_def.insert_at_line
            if not (0 <= insert_line_idx <= len(modified_lines)):
                logger.warning(
                    f"Invalid insert line {insert_line_idx} for {task_def.element_key} (len_lines={len(modified_lines)}, PID: {os.getpid()}). Skipping.")
                continue
            if task_def.is_inline:
                if 0 <= insert_line_idx < len(modified_lines):
                    original_line = modified_lines[insert_line_idx]
                    modified_lines[insert_line_idx] = original_line.rstrip() + f"  {comment_text.lstrip()}"
            else:
                comment_block_lines = comment_text.split('\n')
                indented_comment_block = [(task_def.indentation + line).rstrip() for line in comment_block_lines]
                modified_lines = modified_lines[:insert_line_idx] + indented_comment_block + modified_lines[
                                                                                             insert_line_idx:]

        return '\n'.join(modified_lines)