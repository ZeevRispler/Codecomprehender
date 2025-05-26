import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from functools import lru_cache
import re

import javalang

logger = logging.getLogger(__name__)

@dataclass
class ParsedField:
    """A field in a Java class"""
    name: str
    type: str
    visibility: str = "package"
    is_static: bool = False
    is_final: bool = False
    line_number: int = 0
    has_javadoc: bool = False

@dataclass
class ParsedMethod:
    """A method in a Java class"""
    name: str
    return_type: str
    visibility: str = "package"
    parameters: List[tuple] = field(default_factory=list)  # (type, name) pairs
    is_static: bool = False
    is_constructor: bool = False
    line_number: int = 0
    has_javadoc: bool = False
    throws: List[str] = field(default_factory=list)

@dataclass
class ParsedClass:
    """A Java class, interface, or enum"""
    name: str
    type: str  # "class", "interface", "enum"
    visibility: str = "package"
    extends: Optional[str] = None
    implements: List[str] = field(default_factory=list)
    fields: List[ParsedField] = field(default_factory=list)
    methods: List[ParsedMethod] = field(default_factory=list)
    line_number: int = 0
    has_javadoc: bool = False
    dependencies: Set[str] = field(default_factory=set)

@dataclass
class ParsedFile:
    """A parsed Java source file"""
    file_path: Path
    package: str = ""
    imports: List[str] = field(default_factory=list)
    classes: List[ParsedClass] = field(default_factory=list)
    source_code: str = ""
    parse_errors: List[str] = field(default_factory=list)

    @property
    def main_class(self) -> Optional[ParsedClass]:
        """Try to find the main class (usually matches filename)"""
        filename = self.file_path.stem

        # Look for exact match first
        for cls in self.classes:
            if cls.name == filename:
                return cls

        # Return first public class
        for cls in self.classes:
            if cls.visibility == "public":
                return cls

        # Just return first class if any
        return self.classes[0] if self.classes else None

    @property
    def is_parseable(self) -> bool:
        """Check if the file was parsed successfully"""
        return len(self.parse_errors) == 0

class JavaParser:
    """Efficient Java source file parser with caching"""

    def __init__(self):
        self.failed_files = []
        self.parsed_count = 0
        self.skipped_count = 0

        # Cache for repeated parsing operations
        self._type_name_cache = {}

    def parse_file(self, file_path: Path) -> ParsedFile:
        """
        Parse a single Java file efficiently.

        Returns a ParsedFile even if parsing fails - the caller can
        check is_parseable to see if it worked.
        """
        try:
            # Read the source code
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Quick pre-checks before expensive parsing
            if self._should_skip_parsing(source_code, file_path):
                self.skipped_count += 1
                return ParsedFile(
                    file_path=file_path,
                    source_code=source_code,
                    parse_errors=["Skipped - unsupported Java features"]
                )

            # Parse with javalang
            tree = javalang.parse.parse(source_code)

            parsed_file = ParsedFile(
                file_path=file_path,
                package=self._extract_package(tree),
                imports=self._extract_imports(tree),
                classes=self._extract_classes(tree, source_code),
                source_code=source_code
            )

            # Add dependency information
            self._analyze_dependencies(parsed_file)

            self.parsed_count += 1
            logger.debug(f"✓ Parsed {file_path.name}")
            return parsed_file

        except Exception as e:
            # Don't crash - return a basic parsed file
            logger.debug(f"Parse failed for {file_path.name}: {e}")
            self.failed_files.append(file_path)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()
            except:
                source_code = ""

            return ParsedFile(
                file_path=file_path,
                source_code=source_code,
                parse_errors=[str(e)]
            )

    def analyze_project(self, project_path: Path) -> Dict[str, Any]:
        """
        Analyze entire project structure efficiently.

        Returns comprehensive project information for diagram generation.
        """
        java_files = list(project_path.rglob('*.java'))

        all_classes = []
        all_packages = set()
        dependencies = {}
        failed_files = []

        logger.info(f"Analyzing {len(java_files)} Java files...")

        # Parse all files
        for java_file in java_files:
            parsed = self.parse_file(java_file)

            if parsed.is_parseable:
                all_classes.extend(parsed.classes)
                if parsed.package:
                    all_packages.add(parsed.package)

                # Collect dependencies
                for cls in parsed.classes:
                    dependencies[cls.name] = list(cls.dependencies)
            else:
                failed_files.append(java_file)

        # Build package hierarchy
        package_hierarchy = self._build_package_hierarchy(all_packages)

        # Calculate some useful metrics
        total_methods = sum(len(cls.methods) for cls in all_classes)
        total_fields = sum(len(cls.fields) for cls in all_classes)

        return {
            'project_path': project_path,
            'total_files': len(java_files),
            'parsed_files': self.parsed_count,
            'failed_files': len(failed_files),
            'skipped_files': self.skipped_count,
            'total_classes': len(all_classes),
            'total_methods': total_methods,
            'total_fields': total_fields,
            'packages': sorted(all_packages),
            'package_hierarchy': package_hierarchy,
            'dependencies': dependencies,
            'classes': all_classes,
        }

    @lru_cache(maxsize=1000)
    def _should_skip_parsing(self, source_code: str, file_path: Path) -> bool:
        """
        Quick check for Java features that will cause javalang to fail.

        This saves time by avoiding expensive parsing attempts on files
        we know we can't handle.
        """
        # Features javalang can't handle
        unsupported_features = [
            'sealed class', 'sealed interface',
            'record ', 'record(',  # Java records
            'var ', # type inference
            'switch (' + '.*->',  # Expression switches (regex)
            'yield ',  # Switch expressions
            'instanceof.*&&',  # Pattern matching
        ]

        source_lower = source_code.lower()

        # Check for obvious unsupported features
        for feature in unsupported_features:
            if feature in source_lower:
                logger.debug(f"Skipping {file_path.name} - contains '{feature}'")
                return True

        # Check for very new Java syntax patterns
        if re.search(r'switch\s*\([^)]+\)\s*\{[^}]*->', source_code):
            logger.debug(f"Skipping {file_path.name} - switch expressions")
            return True

        return False

    def _extract_package(self, tree) -> str:
        """Extract package name from AST"""
        if tree.package:
            return tree.package.name
        return ""

    def _extract_imports(self, tree) -> List[str]:
        """Extract import statements efficiently"""
        imports = []
        for imp in tree.imports:
            import_str = imp.path
            if imp.static:
                import_str = f"static {import_str}"
            if imp.wildcard:
                import_str += ".*"
            imports.append(import_str)
        return imports

    def _extract_classes(self, tree, source_code: str) -> List[ParsedClass]:
        """Extract all class declarations efficiently"""
        classes = []
        source_lines = source_code.split('\n')

        # Use javalang's filter to find all type declarations
        for path, node in tree.filter(javalang.tree.TypeDeclaration):
            try:
                parsed_class = self._parse_class_node(node, source_lines)
                if parsed_class:
                    classes.append(parsed_class)
            except Exception as e:
                logger.debug(f"Skipping class {getattr(node, 'name', 'unknown')}: {e}")
                continue

        return classes

    def _parse_class_node(self, node, source_lines: List[str]) -> Optional[ParsedClass]:
        """Parse a single class/interface/enum node efficiently"""
        if not hasattr(node, 'name'):
            return None

        # Determine class type
        class_type = type(node).__name__.lower().replace('declaration', '')

        parsed_class = ParsedClass(
            name=node.name,
            type=class_type,
            visibility=self._get_visibility(node.modifiers),
            line_number=getattr(node.position, 'line', 0) if node.position else 0,
            has_javadoc=bool(node.documentation)
        )

        # Handle inheritance efficiently
        self._parse_inheritance(node, parsed_class, class_type)

        # Extract fields
        if hasattr(node, 'fields'):
            for field_decl in node.fields:
                parsed_class.fields.extend(self._parse_field_declaration(field_decl))

        # Extract methods
        if hasattr(node, 'methods'):
            for method_decl in node.methods:
                parsed_method = self._parse_method_declaration(method_decl)
                if parsed_method:
                    parsed_class.methods.append(parsed_method)

        return parsed_class

    def _parse_inheritance(self, node, parsed_class: ParsedClass, class_type: str):
        """Parse inheritance relationships efficiently"""
        # Handle extends
        if hasattr(node, 'extends') and node.extends:
            if class_type == 'class':
                # Classes extend one class
                extends_node = node.extends[0] if isinstance(node.extends, list) else node.extends
                parsed_class.extends = getattr(extends_node, 'name', str(extends_node))
            else:
                # Interfaces can extend multiple interfaces
                if isinstance(node.extends, list):
                    parsed_class.implements = [
                        getattr(e, 'name', str(e)) for e in node.extends
                    ]
                else:
                    parsed_class.implements = [getattr(node.extends, 'name', str(node.extends))]

        # Handle implements (for classes)
        if hasattr(node, 'implements') and node.implements:
            implements_list = [getattr(i, 'name', str(i)) for i in node.implements]
            parsed_class.implements.extend(implements_list)

    def _parse_field_declaration(self, field_decl) -> List[ParsedField]:
        """Parse field declarations (can declare multiple fields)"""
        fields = []

        if not (hasattr(field_decl, 'type') and hasattr(field_decl, 'declarators')):
            return fields

        field_type = self._get_type_name(field_decl.type)
        visibility = self._get_visibility(field_decl.modifiers)
        is_static = 'static' in field_decl.modifiers
        is_final = 'final' in field_decl.modifiers
        has_javadoc = bool(field_decl.documentation)
        line_num = getattr(field_decl.position, 'line', 0) if field_decl.position else 0

        for declarator in field_decl.declarators:
            if hasattr(declarator, 'name'):
                field = ParsedField(
                    name=declarator.name,
                    type=field_type,
                    visibility=visibility,
                    is_static=is_static,
                    is_final=is_final,
                    line_number=line_num,
                    has_javadoc=has_javadoc
                )
                fields.append(field)

        return fields

    def _parse_method_declaration(self, method_decl) -> Optional[ParsedMethod]:
        """Parse a method declaration efficiently"""
        if not hasattr(method_decl, 'name'):
            return None

        # Handle constructors
        is_constructor = isinstance(method_decl, javalang.tree.ConstructorDeclaration)
        return_type = "void" if is_constructor else self._get_type_name(method_decl.return_type)

        # Parse parameters
        parameters = []
        if hasattr(method_decl, 'parameters'):
            for param in method_decl.parameters:
                if hasattr(param, 'name') and hasattr(param, 'type'):
                    param_type = self._get_type_name(param.type)
                    parameters.append((param_type, param.name))

        # Parse throws clause
        throws = []
        if hasattr(method_decl, 'throws') and method_decl.throws:
            throws = [getattr(t, 'name', str(t)) for t in method_decl.throws]

        return ParsedMethod(
            name=method_decl.name,
            return_type=return_type,
            visibility=self._get_visibility(method_decl.modifiers),
            parameters=parameters,
            is_static='static' in method_decl.modifiers,
            is_constructor=is_constructor,
            line_number=getattr(method_decl.position, 'line', 0) if method_decl.position else 0,
            has_javadoc=bool(method_decl.documentation),
            throws=throws
        )

    def _get_visibility(self, modifiers: List[str]) -> str:
        """Extract visibility from modifiers list"""
        for modifier in modifiers:
            if modifier in ('public', 'private', 'protected'):
                return modifier
        return 'package'

    def _get_type_name(self, type_node) -> str:
        """
        Extract type name from type node with caching.

        This is called a lot, so we cache results for performance.
        """
        if type_node is None:
            return "void"

        # Try cache first
        type_key = str(type_node)
        if type_key in self._type_name_cache:
            return self._type_name_cache[type_key]

        # Calculate type name
        if hasattr(type_node, 'name'):
            result = type_node.name
        elif hasattr(type_node, 'type'):
            # Handle arrays and generics
            base_type = self._get_type_name(type_node.type)
            if hasattr(type_node, 'dimensions'):
                result = base_type + "[]" * len(type_node.dimensions)
            else:
                result = base_type
        else:
            result = str(type_node)

        # Cache and return
        self._type_name_cache[type_key] = result
        return result

    def _analyze_dependencies(self, parsed_file: ParsedFile):
        """Analyze dependencies for each class"""
        for cls in parsed_file.classes:
            deps = set()

            # Add inheritance dependencies
            if cls.extends:
                deps.add(cls.extends)
            deps.update(cls.implements)

            # Add field type dependencies
            for field in cls.fields:
                deps.add(self._clean_type_name(field.type))

            # Add method parameter and return type dependencies
            for method in cls.methods:
                if method.return_type != "void":
                    deps.add(self._clean_type_name(method.return_type))

                for param_type, _ in method.parameters:
                    deps.add(self._clean_type_name(param_type))

                # Add exception dependencies
                deps.update(method.throws)

            # Filter out primitives and common types
            cls.dependencies = {
                dep for dep in deps
                if dep and not self._is_primitive_or_common(dep)
            }

    def _clean_type_name(self, type_name: str) -> str:
        """Clean up type name for dependency analysis"""
        # Remove array brackets
        cleaned = type_name.replace("[]", "")

        # Remove generics
        if '<' in cleaned:
            cleaned = cleaned.split('<')[0]

        return cleaned.strip()

    def _is_primitive_or_common(self, type_name: str) -> bool:
        """Check if type is primitive or very common (skip for dependencies)"""
        primitives = {
            'boolean', 'byte', 'char', 'short', 'int', 'long',
            'float', 'double', 'void'
        }

        common_types = {
            'String', 'Object', 'Integer', 'Long', 'Double', 'Float',
            'Boolean', 'Character', 'List', 'Map', 'Set', 'Collection'
        }

        return type_name in primitives or type_name in common_types

    def _build_package_hierarchy(self, packages: Set[str]) -> Dict[str, List[str]]:
        """Build package hierarchy for visualization"""
        hierarchy = {}

        for package in packages:
            parts = package.split('.')

            # Build hierarchy level by level
            for i in range(len(parts)):
                parent = '.'.join(parts[:i]) if i > 0 else None
                current = '.'.join(parts[:i+1])

                if parent not in hierarchy:
                    hierarchy[parent] = []

                if current not in hierarchy[parent]:
                    hierarchy[parent].append(current)

        return hierarchy