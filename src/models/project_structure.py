"""Data models for project structure"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Optional


@dataclass
class ClassInfo:
    """Information about a Java class"""
    name: str
    full_name: str
    package: str
    type: str  # class, interface, enum
    extends: Optional[str] = None
    implements: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)


@dataclass
class Package:
    """Represents a Java package"""
    name: str
    classes: List[ClassInfo] = field(default_factory=list)
    subpackages: Set[str] = field(default_factory=set)

    def get_all_classes(self) -> List[ClassInfo]:
        """Get all classes in this package"""
        return self.classes.copy()


@dataclass
class DependencyGraph:
    """Represents dependencies between classes"""
    edges: Dict[str, Set[str]] = field(default_factory=dict)
    reverse_edges: Dict[str, Set[str]] = field(default_factory=dict)

    def add_dependency(self, from_class: str, to_class: str) -> None:
        """Add a dependency edge"""
        if from_class not in self.edges:
            self.edges[from_class] = set()
        self.edges[from_class].add(to_class)

        if to_class not in self.reverse_edges:
            self.reverse_edges[to_class] = set()
        self.reverse_edges[to_class].add(from_class)

    def get_dependencies(self, class_name: str) -> Set[str]:
        """Get all dependencies of a class"""
        return self.edges.get(class_name, set())

    def get_dependents(self, class_name: str) -> Set[str]:
        """Get all classes that depend on this class"""
        return self.reverse_edges.get(class_name, set())


@dataclass
class ProjectStatistics:
    """Statistics about the project"""
    total_files: int = 0
    total_classes: int = 0
    total_interfaces: int = 0
    total_enums: int = 0
    total_methods: int = 0
    total_lines: int = 0
    package_count: int = 0
    average_methods_per_class: float = 0.0
    max_class_dependencies: int = 0
    circular_dependencies: List[List[str]] = field(default_factory=list)


@dataclass
class ProjectStructure:
    """Complete project structure"""
    root_path: Path
    packages: Dict[str, Package] = field(default_factory=dict)
    classes: Dict[str, ClassInfo] = field(default_factory=dict)
    dependency_graph: DependencyGraph = field(default_factory=DependencyGraph)
    statistics: ProjectStatistics = field(default_factory=ProjectStatistics)

    def build_dependency_graph(self) -> None:
        """Build the dependency graph from class information"""
        self.dependency_graph = DependencyGraph()

        for class_info in self.classes.values():
            for dependency in class_info.dependencies:
                # Resolve dependency to full class name if possible
                resolved_dep = self._resolve_class_name(dependency, class_info.package)
                if resolved_dep in self.classes:
                    self.dependency_graph.add_dependency(class_info.full_name, resolved_dep)

    def _resolve_class_name(self, class_name: str, current_package: str) -> str:
        """Resolve a class name to its fully qualified name"""
        # If already fully qualified
        if '.' in class_name:
            return class_name

        # Check in same package
        full_name = f"{current_package}.{class_name}" if current_package else class_name
        if full_name in self.classes:
            return full_name

        # Check in java.lang
        java_lang_name = f"java.lang.{class_name}"
        if java_lang_name in self.classes:
            return java_lang_name

        # Return as is if can't resolve
        return class_name

    def calculate_statistics(self) -> None:
        """Calculate project statistics"""
        self.statistics.package_count = len(self.packages)
        self.statistics.total_classes = sum(1 for c in self.classes.values() if c.type == 'class')
        self.statistics.total_interfaces = sum(1 for c in self.classes.values() if c.type == 'interface')
        self.statistics.total_enums = sum(1 for c in self.classes.values() if c.type == 'enum')

        total_methods = sum(len(c.methods) for c in self.classes.values())
        self.statistics.total_methods = total_methods

        if self.statistics.total_classes > 0:
            self.statistics.average_methods_per_class = total_methods / self.statistics.total_classes

        # Find max dependencies
        if self.dependency_graph.edges:
            self.statistics.max_class_dependencies = max(
                len(deps) for deps in self.dependency_graph.edges.values()
            )

    def find_circular_dependencies(self) -> List[List[str]]:
        """Find circular dependencies in the project"""
        # Simplified cycle detection - can be improved with proper algorithms
        cycles = []
        visited = set()

        def dfs(node: str, path: List[str]) -> None:
            if node in path:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for neighbor in self.dependency_graph.get_dependencies(node):
                dfs(neighbor, path.copy())

        for class_name in self.classes:
            if class_name not in visited:
                dfs(class_name, [])

        self.statistics.circular_dependencies = cycles
        return cycles