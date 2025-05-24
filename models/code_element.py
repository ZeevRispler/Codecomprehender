"""Data models for code elements"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


class ElementType(Enum):
    """Types of code elements"""
    PACKAGE = "package"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    METHOD = "method"
    FIELD = "field"
    CONSTRUCTOR = "constructor"
    ANNOTATION = "annotation"


class Visibility(Enum):
    """Visibility modifiers"""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    PACKAGE_PRIVATE = "package-private"


@dataclass
class CodeElement:
    """Represents a code element with its metadata"""
    name: str
    element_type: ElementType
    visibility: Visibility
    documentation: Optional[str] = None
    line_number: int = 0
    children: List['CodeElement'] = field(default_factory=list)
    parent: Optional['CodeElement'] = None
    modifiers: List[str] = field(default_factory=list)
    annotations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_full_name(self) -> str:
        """Get the fully qualified name of the element"""
        if self.parent:
            parent_name = self.parent.get_full_name()
            return f"{parent_name}.{self.name}" if parent_name else self.name
        return self.name
    
    def add_child(self, child: 'CodeElement') -> None:
        """Add a child element"""
        child.parent = self
        self.children.append(child)
        
    def find_children_by_type(self, element_type: ElementType) -> List['CodeElement']:
        """Find all children of a specific type"""
        return [child for child in self.children if child.element_type == element_type]


