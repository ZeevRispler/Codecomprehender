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

    def _parse_class(self, node: javalang.tree.TypeDeclaration, source_code: str, is_problem_file: bool = False,
                     current_file_path: Path = None) -> ParsedClass:
        class_name_for_log = "UNKNOWN_CLASS"
        if hasattr(node, 'name'):
            class_name_for_log = node.name
        elif isinstance(node, str):
            if is_problem_file:
                logger.error(f"DEBUG: _parse_class received string node: {node} in {current_file_path}")
            raise TypeError(f"_parse_class expected a TypeDeclaration node, got str: {node} for {current_file_path}")
        else:  # Node is not a string but has no name
            if is_problem_file:
                logger.error(
                    f"DEBUG: _parse_class received node with no name attribute. Type: {type(node)}, Path: {current_file_path}")
            # Depending on how critical 'name' is, you might raise an error or try to assign a placeholder
            # For now, we'll rely on class_name_for_log's default "UNKNOWN_CLASS" if node.name is missing
            # but this situation indicates a potentially malformed AST node from javalang if it's a TypeDeclaration.

        if is_problem_file:
            logger.info(
                f"Parsing class details for: {class_name_for_log} (Node type: {type(node).__name__}) in {current_file_path}")

        class_type = type(node).__name__.replace("Declaration", "").lower()

        extends_value = None
        implements_list = []

        # Handle 'extends' for classes and interfaces
        if hasattr(node, 'extends') and node.extends:
            if class_type == 'class':
                extends_node_or_list = node.extends
                actual_extends_node = None

                if is_problem_file:
                    logger.info(
                        f"DEBUG: Handling 'extends' for CLASS '{class_name_for_log}'. node.extends type: {type(extends_node_or_list)}, value: {str(extends_node_or_list)}")

                if isinstance(extends_node_or_list, list):
                    if extends_node_or_list:
                        actual_extends_node = extends_node_or_list[0]
                        if len(extends_node_or_list) > 1 and is_problem_file:
                            logger.warning(
                                f"Class '{class_name_for_log}' has 'extends' as a list with multiple items. Using the first: {str(actual_extends_node)}")
                    elif is_problem_file:
                        logger.warning(f"Class '{class_name_for_log}' has 'extends' as an empty list.")
                else:
                    actual_extends_node = extends_node_or_list

                if actual_extends_node:
                    if is_problem_file:
                        logger.info(
                            f"DEBUG: actual_extends_node for CLASS '{class_name_for_log}'. type: {type(actual_extends_node)}, value: {str(actual_extends_node)}")

                    if hasattr(actual_extends_node, 'name'):
                        extends_value = actual_extends_node.name
                        if is_problem_file:
                            logger.info(
                                f"DEBUG: Successfully got extends_value='{extends_value}' for CLASS '{class_name_for_log}'")
                    elif isinstance(actual_extends_node, str):
                        if is_problem_file: logger.warning(
                            f"Class '{class_name_for_log}' has 'extends' (actual_extends_node) as a string: {actual_extends_node}")
                        extends_value = actual_extends_node
                    else:
                        if is_problem_file:
                            logger.warning(
                                f"Class '{class_name_for_log}' has 'extends' (actual_extends_node) of unexpected type (no .name attribute): {type(actual_extends_node)}. Value: {str(actual_extends_node)}. Attempting to stringify.")
                        extends_value = str(actual_extends_node)  # Fallback to string representation

            elif class_type == 'interface':
                if is_problem_file:
                    logger.info(
                        f"DEBUG: Handling 'extends' for INTERFACE '{class_name_for_log}'. node.extends type: {type(node.extends)}, value: {str(node.extends)}")

                extends_list_for_interface = node.extends
                if isinstance(extends_list_for_interface, list):
                    for item_idx, item_node in enumerate(extends_list_for_interface):
                        if hasattr(item_node, 'name'):
                            implements_list.append(
                                item_node.name)  # Interfaces "extend" other interfaces, store in implements_list for ParsedClass
                            if is_problem_file:
                                logger.info(
                                    f"DEBUG: INTERFACE '{class_name_for_log}' extends '{item_node.name}' (item #{item_idx})")
                        elif isinstance(item_node, str):
                            if is_problem_file: logger.warning(
                                f"INTERFACE '{class_name_for_log}' extends item #{item_idx} as string: {item_node}")
                            implements_list.append(item_node)
                        else:
                            if is_problem_file: logger.warning(
                                f"INTERFACE '{class_name_for_log}' extends item #{item_idx} of unexpected type: {type(item_node)}. Value: {str(item_node)}. Attempting to stringify.")
                            implements_list.append(str(item_node))  # Fallback
                # Handle if node.extends for an interface is not a list (e.g. single interface extension)
                elif hasattr(extends_list_for_interface, 'name'):  # Check if it's a single node with a name
                    implements_list.append(extends_list_for_interface.name)
                    if is_problem_file:
                        logger.info(
                            f"DEBUG: INTERFACE '{class_name_for_log}' extends single item '{extends_list_for_interface.name}'")
                elif isinstance(extends_list_for_interface, str):
                    if is_problem_file: logger.warning(
                        f"INTERFACE '{class_name_for_log}' has single 'extends' as string: {extends_list_for_interface}")
                    implements_list.append(extends_list_for_interface)
                else:  # Fallback for single, non-list, non-named item
                    if is_problem_file: logger.warning(
                        f"INTERFACE '{class_name_for_log}' has single 'extends' of unexpected type (no .name): {type(extends_list_for_interface)}. Value {str(extends_list_for_interface)}. Attempting to stringify.")
                    implements_list.append(str(extends_list_for_interface))

        # Handle 'implements' for classes
        if class_type == 'class' and hasattr(node, 'implements') and node.implements:
            if is_problem_file:
                logger.info(
                    f"DEBUG: Handling 'implements' for CLASS '{class_name_for_log}'. node.implements type: {type(node.implements)}, value: {str(node.implements)}")

            implements_node_list = node.implements
            if isinstance(implements_node_list, list):
                for item_idx, item_node in enumerate(implements_node_list):
                    if hasattr(item_node, 'name'):
                        implements_list.append(item_node.name)
                    elif isinstance(item_node, str):
                        if is_problem_file: logger.warning(
                            f"Class '{class_name_for_log}' implements item #{item_idx} as string: {item_node}")
                        implements_list.append(item_node)
                    else:
                        if is_problem_file: logger.warning(
                            f"Class '{class_name_for_log}' implements item #{item_idx} of unexpected type: {type(item_node)}. Value: {str(item_node)}. Attempting to stringify.")
                        implements_list.append(str(item_node))  # Fallback
            else:  # Should be a list according to javalang grammar for class implements
                if is_problem_file: logger.warning(
                    f"Class '{class_name_for_log}' has 'implements' attribute that is not a list: {type(implements_node_list)}. Attempting to process as single item.")
                if hasattr(implements_node_list, 'name'):
                    implements_list.append(implements_node_list.name)
                elif isinstance(implements_node_list, str):
                    implements_list.append(implements_node_list)
                else:
                    implements_list.append(str(implements_node_list))

        parsed_class = ParsedClass(
            name=class_name_for_log,
            type=class_type,
            visibility=self._get_visibility(node.modifiers),
            extends=extends_value,
            implements=implements_list,
            documentation=node.documentation,
            line_number=node.position.line if node.position and hasattr(node.position, 'line') else 0
        )

        if hasattr(node, 'fields'):
            for field_node in node.fields:
                if not isinstance(field_node, str):
                    parsed_class.fields.extend(
                        self._parse_fields(field_node, is_problem_file, class_name_for_log, current_file_path))
                elif is_problem_file:
                    logger.error(
                        f"DEBUG: Field node is a string: {field_node} in class {class_name_for_log} in {current_file_path}")

        if hasattr(node, 'methods'):
            for method_node in node.methods:
                if not isinstance(method_node, str):
                    parsed_class.methods.append(
                        self._parse_method(method_node, source_code, is_problem_file, class_name_for_log,
                                           current_file_path))
                elif is_problem_file:
                    logger.error(
                        f"DEBUG: Method node is a string: {method_node} in class {class_name_for_log} in {current_file_path}")

        if hasattr(node, 'body'):  # For inner classes
            for body_item in node.body:
                if isinstance(body_item, (
                javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration, javalang.tree.EnumDeclaration)):
                    if not isinstance(body_item, str):
                        # Pass 'is_problem_file' and 'current_file_path' for consistent debugging
                        parsed_class.inner_classes.append(
                            self._parse_class(body_item, source_code, is_problem_file, current_file_path))
                    elif is_problem_file:
                        logger.error(f"DEBUG: Inner class node is a string: {body_item} in {current_file_path}")
        return parsed_class

    def _parse_fields(self, field_node: javalang.tree.FieldDeclaration, is_problem_file: bool = False,
                      class_name_for_log: str = "UNKNOWN_CLASS", current_file_path: Path = None) -> List[ParsedField]:
        fields = []
        # Ensure field_node is not a string and has expected attributes
        if not hasattr(field_node, 'type') or not hasattr(field_node, 'declarators'):
            if is_problem_file:
                logger.error(
                    f"DEBUG: field_node missing 'type' or 'declarators'. Type: {type(field_node)} in class {class_name_for_log} in {current_file_path}")
            return fields

        field_type_name = self._get_type_name(field_node.type)
        visibility = self._get_visibility(field_node.modifiers)

        for decl_idx, declarator in enumerate(field_node.declarators):
            if not hasattr(declarator, 'name'):
                if is_problem_file:  # Or your current debug flag
                    logger.error(
                        f"DEBUG: declarator #{decl_idx} has no name. Type: {type(declarator)} in class {class_name_for_log} in {current_file_path}")
                continue

            field_name = declarator.name

            # CRITICAL LINE: Ensure 'type' and 'visibility' are correctly passed
            field = ParsedField(
                name=field_name,
                type=field_type_name,  # MUST BE PRESENT
                visibility=visibility,  # MUST BE PRESENT
                is_static='static' in field_node.modifiers,
                is_final='final' in field_node.modifiers,
                documentation=field_node.documentation,
                # This should be field_node.documentation not declarator.documentation
                line_number=field_node.position.line if field_node.position and hasattr(field_node.position,
                                                                                        'line') else 0
                # initial_value is not being parsed here, which is fine if it's optional
            )
            fields.append(field)
        return fields

    def _parse_method(self, method_node: javalang.tree.MethodDeclaration, source_code: str,
                      is_problem_file: bool = False, class_name_for_log: str = "UNKNOWN_CLASS",
                      current_file_path: Path = None) -> ParsedMethod:
        # Ensure method_node is not a string and has expected attributes
        if not hasattr(method_node, 'name') or not hasattr(method_node, 'parameters'):  # Add other essential checks
            if is_problem_file:
                logger.error(
                    f"DEBUG: method_node missing 'name' or 'parameters'. Type: {type(method_node)} in class {class_name_for_log} in {current_file_path}")
            # Return a dummy or raise, as we can't proceed
            raise TypeError(f"Malformed method node in {class_name_for_log} in {current_file_path}")

        method_name = method_node.name
        if is_problem_file:
            logger.info(
                f"Parsing method details for: {method_name} in class {class_name_for_log} in {current_file_path}")

        parameters = []
        if hasattr(method_node, 'parameters'):
            for param_idx, param in enumerate(method_node.parameters):
                if not hasattr(param, 'name') or not hasattr(param, 'type'):
                    if is_problem_file:
                        logger.error(
                            f"DEBUG: parameter #{param_idx} in method {method_name} missing 'name' or 'type'. Type: {type(param)} in {current_file_path}")
                    continue  # Skip this parameter
                param_name = param.name
                param_type_name = self._get_type_name(param.type)
                parameters.append((param_type_name, param_name))

        return_type_name = "void"
        if hasattr(method_node, 'return_type') and method_node.return_type:  # method_node.return_type can be None
            return_type_name = self._get_type_name(method_node.return_type)

        throws_list = []
        if hasattr(method_node, 'throws') and method_node.throws:
            for throw_idx, t_node in enumerate(method_node.throws):
                if hasattr(t_node, 'name'):
                    throws_list.append(t_node.name)
                elif is_problem_file:
                    logger.warning(
                        f"DEBUG: throws node #{throw_idx} in method {method_name} missing 'name'. Type: {type(t_node)} in {current_file_path}")

        # ... create ParsedMethod object ...
        parsed_method = ParsedMethod(
            name=method_name,
            visibility=self._get_visibility(method_node.modifiers),
            return_type=return_type_name,
            parameters=parameters,
            throws=throws_list,
            # ... other attributes
            line_number=method_node.position.line if method_node.position and hasattr(method_node.position,
                                                                                      'line') else 0
        )
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