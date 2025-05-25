# src/__init__.py
"""
CodeComprehender - Add AI comments to Java code
"""

__version__ = "0.1.0"

# src/parser/__init__.py
from .parser.java_parser import JavaParser, ParsedFile, ParsedClass, ParsedMethod, ParsedField

__all__ = ["JavaParser", "ParsedFile", "ParsedClass", "ParsedMethod", "ParsedField"]

# src/commenter/__init__.py
from .commenter.comment_generator import CommentGenerator

__all__ = ["CommentGenerator"]

# src/utils/__init__.py
from .utils.config import Config
from .utils.github import GitHubHandler

__all__ = ["Config", "GitHubHandler"]

# src/architecture/__init__.py
from .architecture.diagram_generator import DiagramGenerator

__all__ = ["DiagramGenerator"]