from .comment_generator import CommentGenerator
# Assuming comment_inserter.py and templates.py might also have classes/functions to expose:
# from .comment_inserter import CommentInserter # If CommentInserter class exists
# from . import templates # To make templates accessible, e.g., templates.CLASS_TEMPLATE

__all__ = [
    "CommentGenerator",
    # "CommentInserter",
    # "templates",
]