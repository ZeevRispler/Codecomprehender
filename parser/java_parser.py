"""Java source code parser using javalang library"""

import javalang
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from src.utils.logger import setup_logger
from src.models.code_element import CodeElement, ElementType, Visibility
from src.models.project_structure import ProjectStructure, Package, ClassInfo

logger = setup_logger(__name__)


@dataclass
class ParsedFile:
    """Represents a parsed Java file with its AST and metadata"""
    file_path: Path
    package_name: str
    imports: List[str]
    classes: List['ParsedClass']
    tree: Optional[javalang.tree.CompilationUnit] = None
    source_code: str = ""


@dataclass
class ParsedClass:
    """Represents a parsed Java class"""
    name: str
    type: str  # class, interface, enum
    visibility: str
    extends: Optional[str] = None
    implements: List[str] = field(default_factory=list)
    fields: List['ParsedField'] = field(default_factory=list)
    methods: List['ParsedMethod'] = field(default_factory=list)
    inner_classes: List['ParsedClass'] = field(default_factory=list)
    documentation: Optional[str] = None
    line_number: int = 0


@dataclass
class ParsedMethod:
    """Represents a parsed Java method"""
    name: str
    visibility: str
    return_type: str
    parameters: List[Tuple[str, str]]  # (type, name)
    throws: List[str] = field(default_factory=list)
    is_static: bool = False
    is_abstract: bool = False
    documentation: Optional[str] = None
    line_number: int = 0
    body: Optional[str] = None


@dataclass
class ParsedField:
    """Represents a parsed Java field"""
    name: str
    type: str
    visibility: str
    is_static: bool = False
    is_final: bool = False
    initial_value: Optional[str] = None
    documentation: Optional[str] = None
    line_number: int = 0


class JavaParser:
    """Parses Java source code files and extracts structure"""

    def parse_file(self, file_path: Path) -> ParsedFile:
        """Parse a single Java file and extract its structure"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            # Parse the Java source code
            tree = javalang.parse.parse(source_code)

            # Extract package name
            package_name = tree.package.name if tree.package else ""

            # Extract imports
            imports = [self._format_import(imp) for imp in tree.imports]

            # Extract classes
            classes = self._extract_classes(tree, source_code)

            return ParsedFile(
                file_path=file_path,
                package_name=package_name,
                imports=imports,
                classes=classes,
                tree=tree,
                source_code=source_code
            )

        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            raise

    def analyze_project_structure(self, project_path: Path) -> ProjectStructure:
        """Analyze the entire project structure"""
        packages: Dict[str, Package] = {}
        all_classes: Dict[str, ClassInfo] = {}

        # Find and parse all Java files
        java_files = list(project_path.rglob("*.java"))

        for java_file in java_files:
            try:
                parsed = self.parse_file(java_file)

                # Create or update package
                if parsed.package_name not in packages:
                    packages[parsed.package_name] = Package(
                        name=parsed.package_name,
                        classes=[],
                        subpackages=set()
                    )

                # Add classes to package and global registry
                for cls in parsed.classes:
                    class_info = ClassInfo(
                        name=cls.name,
                        full_name=f"{parsed.package_name}.{cls.name}" if parsed.package_name else cls.name,
                        package=parsed.package_name,
                        type=cls.type,
                        extends=cls.extends,
                        implements=cls.implements,
                        methods=[m.name for m in cls.methods],
                        fields=[f.name for f in cls.fields],
                        dependencies=self._extract_dependencies(parsed, cls)
                    )

                    packages[parsed.package_name].classes.append(class_info)
                    all_classes[class_info.full_name] = class_info

            except Exception as e:
                logger.error(f"Error analyzing {java_file}: {e}")
                continue

        # Build package hierarchy
        self._build_package_hierarchy(packages)

        return ProjectStructure(
            root_path=project_path,
            packages=packages,
            classes=all_classes
        )

    def _extract_classes(self, tree: javalang.tree.CompilationUnit, source_code: str) -> List[ParsedClass]:
        """Extract all classes from the compilation unit"""
        classes = []

        for path, node in tree.filter(javalang.tree.TypeDeclaration):
            if isinstance(node, (javalang.tree.ClassDeclaration,
                                 javalang.tree.InterfaceDeclaration,
                                 javalang.tree.EnumDeclaration)):
                parsed_class = self._parse_class(node, source_code)
                classes.append(parsed_class)

        return classes

    def _parse_class(self, node: javalang.tree.TypeDeclaration, source_code: str) -> ParsedClass:
        """Parse a single class/interface/enum declaration"""
        class_type = type(node).__name__.replace("Declaration", "").lower()

        parsed_class = ParsedClass(
            name=node.name,
            type=class_type,
            visibility=self._get_visibility(node.modifiers),
            documentation=node.documentation,
            line_number=node.position.line if node.position else 0
        )

        # Extract extends/implements
        if hasattr(node, 'extends') and node.extends:
            parsed_class.extends = node.extends.name

        if hasattr(node, 'implements') and node.implements:
            parsed_class.implements = [impl.name for impl in node.implements]

        # Extract fields
        for field_node in node.fields:
            parsed_class.fields.extend(self._parse_fields(field_node))

        # Extract methods
        for method_node in node.methods:
            parsed_class.methods.append(self._parse_method(method_node, source_code))

        # Extract inner classes
        for inner_class in node.body:
            if isinstance(inner_class, javalang.tree.TypeDeclaration):
                parsed_class.inner_classes.append(self._parse_class(inner_class, source_code))

        return parsed_class

    def _parse_fields(self, field_node: javalang.tree.FieldDeclaration) -> List[ParsedField]:
        """Parse field declarations"""
        fields = []
        visibility = self._get_visibility(field_node.modifiers)
        field_type = self._get_type_name(field_node.type)

        for declarator in field_node.declarators:
            field = ParsedField(
                name=declarator.name,
                type=field_type,
                visibility=visibility,
                is_static='static' in field_node.modifiers,
                is_final='final' in field_node.modifiers,
                documentation=field_node.documentation,
                line_number=field_node.position.line if field_node.position else 0
            )
            fields.append(field)

        return fields

    def _parse_method(self, method_node: javalang.tree.MethodDeclaration, source_code: str) -> ParsedMethod:
        """Parse a method declaration"""
        parameters = []
        for param in method_node.parameters:
            param_type = self._get_type_name(param.type)
            parameters.append((param_type, param.name))

        parsed_method = ParsedMethod(
            name=method_node.name,
            visibility=self._get_visibility(method_node.modifiers),
            return_type=self._get_type_name(method_node.return_type) if method_node.return_type else "void",
            parameters=parameters,
            throws=[t.name for t in method_node.throws] if method_node.throws else [],
            is_static='static' in method_node.modifiers,
            is_abstract='abstract' in method_node.modifiers,
            documentation=method_node.documentation,
            line_number=method_node.position.line if method_node.position else 0
        )

        # Extract method body if needed
        if method_node.body and not parsed_method.is_abstract:
            # This is simplified - in reality, you'd want to extract the actual body text
            parsed_method.body = f"// Method body at line {parsed_method.line_number}"

        return parsed_method

    def _get_visibility(self, modifiers: List[str]) -> str:
        """Extract visibility modifier from modifiers list"""
        visibility_modifiers = {'public', 'private', 'protected'}
        for modifier in modifiers:
            if modifier in visibility_modifiers:
                return modifier
        return 'package-private'

    def _get_type_name(self, type_node: Any) -> str:
        """Extract type name from type node"""
        if type_node is None:
            return "void"
        elif hasattr(type_node, 'name'):
            return type_node.name
        elif hasattr(type_node, 'type') and hasattr(type_node, 'dimensions'):
            # Array type
            base_type = self._get_type_name(type_node.type)
            return base_type + "[]" * len(type_node.dimensions)
        else:
            return str(type_node)

    def _format_import(self, import_node: javalang.tree.Import) -> str:
        """Format import statement"""
        path = import_node.path
        if import_node.static:
            path = "static " + path
        if import_node.wildcard:
            path = path + ".*"
        return path

    def _extract_dependencies(self, parsed_file: ParsedFile, parsed_class: ParsedClass) -> List[str]:
        """Extract dependencies for a class"""
        dependencies = set()

        # Add extends dependency
        if parsed_class.extends:
            dependencies.add(parsed_class.extends)

        # Add implements dependencies
        dependencies.update(parsed_class.implements)

        # Add field type dependencies
        for field in parsed_class.fields:
            # Simple extraction - could be improved
            type_name = field.type.replace("[]", "").strip()
            if type_name and not self._is_primitive(type_name):
                dependencies.add(type_name)

        # Add method parameter and return type dependencies
        for method in parsed_class.methods:
            if method.return_type and not self._is_primitive(method.return_type):
                dependencies.add(method.return_type.replace("[]", "").strip())

            for param_type, _ in method.parameters:
                type_name = param_type.replace("[]", "").strip()
                if not self._is_primitive(type_name):
                    dependencies.add(type_name)

        return list(dependencies)

    def _is_primitive(self, type_name: str) -> bool:
        """Check if a type is a Java primitive"""
        primitives = {'boolean', 'byte', 'char', 'short', 'int', 'long', 'float', 'double', 'void'}
        return type_name.lower() in primitives

    def _build_package_hierarchy(self, packages: Dict[str, Package]) -> None:
        """Build package hierarchy relationships"""
        for pkg_name, package in packages.items():
            if '.' in pkg_name:
                parent_name = pkg_name.rsplit('.', 1)[0]
                if parent_name in packages:
                    packages[parent_name].subpackages.add(pkg_name)