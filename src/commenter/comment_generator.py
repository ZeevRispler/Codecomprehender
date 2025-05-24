"""AI-powered comment generation using OpenAI"""

import openai
from typing import List, Optional
import re
from src.utils.logger import setup_logger
from src.parser.java_parser import ParsedFile, ParsedClass, ParsedMethod, ParsedField

logger = setup_logger(__name__)


class CommentGenerator:
    """Generates meaningful comments using OpenAI API"""

    def __init__(self, config):
        self.config = config

        # Initialize OpenAI client with optional base URL
        if config.openai_base_url:
            self.client = openai.OpenAI(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url
            )
        else:
            self.client = openai.OpenAI(api_key=config.openai_api_key)

    def generate_comments(self, parsed_file: ParsedFile, file_path) -> str:
        """Generate comments for a parsed Java file"""
        try:
            source_lines = parsed_file.source_code.split('\n')
            commented_lines = source_lines.copy()

            # Track line offsets due to inserted comments
            line_offset = 0

            # Generate file-level comment if no package documentation exists
            if not self._has_file_comment(source_lines):
                file_comment = self._generate_file_comment(parsed_file, file_path)
                if file_comment:
                    commented_lines = file_comment.split('\n') + commented_lines
                    line_offset += len(file_comment.split('\n'))

            # Process each class
            for parsed_class in parsed_file.classes:
                # Generate class comment
                if self.config.include_class_comments and not parsed_class.documentation:
                    class_comment = self._generate_class_comment(parsed_class, parsed_file)
                    if class_comment:
                        insert_line = parsed_class.line_number - 1 + line_offset
                        commented_lines = self._insert_comment(
                            commented_lines,
                            class_comment,
                            insert_line
                        )
                        line_offset += len(class_comment.split('\n'))

                # Generate method comments
                if self.config.include_method_comments:
                    for method in parsed_class.methods:
                        if not method.documentation:
                            method_comment = self._generate_method_comment(
                                method,
                                parsed_class,
                                parsed_file
                            )
                            if method_comment:
                                insert_line = method.line_number - 1 + line_offset
                                commented_lines = self._insert_comment(
                                    commented_lines,
                                    method_comment,
                                    insert_line
                                )
                                line_offset += len(method_comment.split('\n'))

                # Generate field comments if configured
                if self.config.include_inline_comments:
                    for field in parsed_class.fields:
                        if not field.documentation:
                            field_comment = self._generate_field_comment(
                                field,
                                parsed_class
                            )
                            if field_comment:
                                insert_line = field.line_number - 1 + line_offset
                                # For fields, we'll add inline comments
                                if insert_line < len(commented_lines):
                                    commented_lines[insert_line] += f"  {field_comment}"

            return '\n'.join(commented_lines)

        except Exception as e:
            logger.error(f"Error generating comments: {e}")
            # Return original code if comment generation fails
            return parsed_file.source_code

    def _generate_file_comment(self, parsed_file: ParsedFile, file_path) -> Optional[str]:
        """Generate a file-level comment"""
        prompt = f"""Generate a concise JavaDoc file-level comment for this Java file:
File: {file_path.name}
Package: {parsed_file.package_name}
Classes: {', '.join(cls.name for cls in parsed_file.classes)}
Main imports: {', '.join(parsed_file.imports[:5])}

The comment should explain the file's purpose and main functionality.
Return ONLY the JavaDoc comment, no explanations."""

        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=200
            )

            comment = response.choices[0].message.content.strip()
            return comment if comment.startswith("/**") else f"/**\n * {comment}\n */"

        except Exception as e:
            logger.error(f"Error generating file comment: {e}")
            return None

    def _generate_class_comment(self, parsed_class: ParsedClass, parsed_file: ParsedFile) -> Optional[str]:
        """Generate a class-level comment"""
        # Build context about the class
        context = f"""Generate a concise JavaDoc comment for this Java {parsed_class.type}:
Name: {parsed_class.name}
Package: {parsed_file.package_name}
Visibility: {parsed_class.visibility}
Extends: {parsed_class.extends or 'None'}
Implements: {', '.join(parsed_class.implements) if parsed_class.implements else 'None'}
Number of methods: {len(parsed_class.methods)}
Number of fields: {len(parsed_class.fields)}
Key methods: {', '.join(m.name for m in parsed_class.methods[:5])}

The comment should explain the class's purpose, responsibilities, and key features.
Return ONLY the JavaDoc comment, no explanations."""

        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": context}],
                temperature=self.config.temperature,
                max_tokens=300
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating class comment for {parsed_class.name}: {e}")
            return None

    def _generate_method_comment(self, method: ParsedMethod, parsed_class: ParsedClass,
                               parsed_file: ParsedFile) -> Optional[str]:
        """Generate a method-level comment"""
        # Build parameter string
        params_str = ", ".join(f"{ptype} {pname}" for ptype, pname in method.parameters)

        prompt = f"""Generate a concise JavaDoc comment for this Java method:
Class: {parsed_class.name}
Method: {method.visibility} {method.return_type} {method.name}({params_str})
Throws: {', '.join(method.throws) if method.throws else 'None'}
Static: {method.is_static}
Abstract: {method.is_abstract}

The comment should explain what the method does, its parameters, return value, and any exceptions.
Use proper JavaDoc format with @param, @return, @throws tags as needed.
Return ONLY the JavaDoc comment, no explanations."""

        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=250
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating method comment for {method.name}: {e}")
            return None

    def _generate_field_comment(self, field: ParsedField, parsed_class: ParsedClass) -> Optional[str]:
        """Generate a field-level comment"""
        prompt = f"""Generate a very brief inline comment for this Java field:
Class: {parsed_class.name}
Field: {field.visibility} {field.type} {field.name}
Static: {field.is_static}
Final: {field.is_final}

Return ONLY a brief inline comment (starting with //) explaining the field's purpose.
Keep it under 10 words."""

        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.temperature,
                max_tokens=50
            )

            comment = response.choices[0].message.content.strip()
            # Ensure it starts with //
            if not comment.startswith("//"):
                comment = f"// {comment}"
            return comment

        except Exception as e:
            logger.error(f"Error generating field comment for {field.name}: {e}")
            return None

    def _has_file_comment(self, source_lines: List[str]) -> bool:
        """Check if the file already has a file-level comment"""
        # Look for comments in the first few lines
        for i, line in enumerate(source_lines[:10]):
            if line.strip().startswith("/**") or line.strip().startswith("/*"):
                return True
            if line.strip() and not line.strip().startswith("package") and not line.strip().startswith("import"):
                break
        return False

    def _insert_comment(self, lines: List[str], comment: str, insert_position: int) -> List[str]:
        """Insert a comment at the specified position in the lines"""
        comment_lines = comment.split('\n')

        # Find the appropriate indentation
        if insert_position < len(lines):
            indent = self._get_indentation(lines[insert_position])
            comment_lines = [indent + line if line.strip() else line for line in comment_lines]

        # Insert the comment
        result = lines[:insert_position] + comment_lines + lines[insert_position:]
        return result

    def _get_indentation(self, line: str) -> str:
        """Extract the indentation from a line"""
        match = re.match(r'^(\s*)', line)
        return match.group(1) if match else ''