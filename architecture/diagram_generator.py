"""Generate architecture diagrams for Java projects"""

import graphviz
from pathlib import Path
from typing import List, Dict, Set, Tuple
from src.utils.logger import setup_logger
from src.models.project_structure import ProjectStructure, ClassInfo, Package

logger = setup_logger(__name__)


class DiagramGenerator:
    """Generates various architecture diagrams"""

    def __init__(self, config):
        self.config = config

    def generate_diagrams(self, project_structure: ProjectStructure, output_dir: Path) -> List[Path]:
        """Generate all architecture diagrams"""
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files = []

        # Build dependency graph first
        project_structure.build_dependency_graph()
        project_structure.calculate_statistics()

        # Generate package diagram
        try:
            package_diagram = self._generate_package_diagram(project_structure, output_dir)
            if package_diagram:
                generated_files.append(package_diagram)
        except Exception as e:
            logger.error(f"Error generating package diagram: {e}")

        # Generate class diagram (simplified for large projects)
        try:
            class_diagram = self._generate_class_diagram(project_structure, output_dir)
            if class_diagram:
                generated_files.append(class_diagram)
        except Exception as e:
            logger.error(f"Error generating class diagram: {e}")

        # Generate dependency graph
        try:
            dep_diagram = self._generate_dependency_diagram(project_structure, output_dir)
            if dep_diagram:
                generated_files.append(dep_diagram)
        except Exception as e:
            logger.error(f"Error generating dependency diagram: {e}")

        # Generate statistics report
        try:
            stats_file = self._generate_statistics_report(project_structure, output_dir)
            if stats_file:
                generated_files.append(stats_file)
        except Exception as e:
            logger.error(f"Error generating statistics report: {e}")

        return generated_files

    def _generate_package_diagram(self, project_structure: ProjectStructure, output_dir: Path) -> Path:
        """Generate a package-level architecture diagram"""
        dot = graphviz.Digraph(comment='Package Structure')
        dot.attr(rankdir='TB')
        dot.attr('node', shape='folder', style='filled', fillcolor='lightblue')

        # Add packages
        for package_name, package in project_structure.packages.items():
            label = f"{package_name}\n({len(package.classes)} classes)"
            dot.node(package_name or "default", label)

        # Add package relationships based on dependencies
        package_deps = self._calculate_package_dependencies(project_structure)
        for from_pkg, to_pkgs in package_deps.items():
            for to_pkg in to_pkgs:
                if from_pkg != to_pkg:  # Skip self-dependencies
                    dot.edge(from_pkg or "default", to_pkg or "default")

        # Render the diagram
        output_file = output_dir / 'package_structure'
        dot.render(output_file, format=self.config.diagram_format, cleanup=True)

        return Path(f"{output_file}.{self.config.diagram_format}")

    def _generate_class_diagram(self, project_structure: ProjectStructure, output_dir: Path) -> Path:
        """Generate a class diagram (simplified for large projects)"""
        dot = graphviz.Digraph(comment='Class Diagram')
        dot.attr(rankdir='BT')  # Bottom to top for inheritance

        # Limit the number of classes for readability
        max_classes = 50
        classes_to_show = list(project_structure.classes.values())[:max_classes]

        if len(project_structure.classes) > max_classes:
            logger.warning(f"Showing only first {max_classes} classes out of {len(project_structure.classes)}")

        # Add classes
        for class_info in classes_to_show:
            # Determine node style based on type
            if class_info.type == 'interface':
                dot.attr('node', shape='record', style='filled', fillcolor='lightyellow')
                stereotype = "«interface»\\n"
            elif class_info.type == 'enum':
                dot.attr('node', shape='record', style='filled', fillcolor='lightgreen')
                stereotype = "«enum»\\n"
            else:
                dot.attr('node', shape='record', style='filled', fillcolor='lightblue')
                stereotype = ""

            # Build label with class name and key members
            label = f"{{{stereotype}{class_info.name}"

            # Add fields if not too many
            if class_info.fields and len(class_info.fields) <= 5:
                fields_str = "\\l".join(f"+ {field}" for field in class_info.fields[:5])
                label += f"|{fields_str}\\l"

            # Add methods if not too many
            if class_info.methods and len(class_info.methods) <= 5:
                methods_str = "\\l".join(f"+ {method}()" for method in class_info.methods[:5])
                label += f"|{methods_str}\\l"

            label += "}"

            dot.node(class_info.full_name, label)

        # Add inheritance relationships
        classes_shown_set = {c.full_name for c in classes_to_show}
        for class_info in classes_to_show:
            # Extends relationship
            if class_info.extends:
                extended = self._resolve_class_name(class_info.extends, project_structure)
                if extended in classes_shown_set:
                    dot.edge(class_info.full_name, extended, arrowhead='empty')

            # Implements relationships
            for interface in class_info.implements:
                impl = self._resolve_class_name(interface, project_structure)
                if impl in classes_shown_set:
                    dot.edge(class_info.full_name, impl, arrowhead='empty', style='dashed')

        # Render the diagram
        output_file = output_dir / 'class_diagram'
        dot.render(output_file, format=self.config.diagram_format, cleanup=True)

        return Path(f"{output_file}.{self.config.diagram_format}")

    def _generate_dependency_diagram(self, project_structure: ProjectStructure, output_dir: Path) -> Path:
        """Generate a dependency diagram showing class relationships"""
        dot = graphviz.Digraph(comment='Dependency Graph')
        dot.attr(rankdir='LR')
        dot.attr('node', shape='ellipse', style='filled', fillcolor='lightgray')

        # Find the most connected classes to focus on
        dependency_counts = {}
        for class_name, deps in project_structure.dependency_graph.edges.items():
            dependency_counts[class_name] = len(deps) + len(
                project_structure.dependency_graph.get_dependents(class_name)
            )

        # Show top N most connected classes
        max_nodes = 30
        sorted_classes = sorted(dependency_counts.items(), key=lambda x: x[1], reverse=True)
        important_classes = {class_name for class_name, _ in sorted_classes[:max_nodes]}

        if not important_classes:
            # If no dependencies found, show some classes anyway
            important_classes = set(list(project_structure.classes.keys())[:max_nodes])

        # Add nodes
        for class_name in important_classes:
            if class_name in project_structure.classes:
                class_info = project_structure.classes[class_name]
                # Use different colors for different types
                if class_info.type == 'interface':
                    dot.attr('node', fillcolor='lightyellow')
                elif class_info.type == 'enum':
                    dot.attr('node', fillcolor='lightgreen')
                else:
                    dot.attr('node', fillcolor='lightblue')

                dot.node(class_name, class_info.name)

        # Add edges
        for class_name in important_classes:
            for dependency in project_structure.dependency_graph.get_dependencies(class_name):
                if dependency in important_classes:
                    dot.edge(class_name, dependency)

        # Highlight circular dependencies if any
        if project_structure.statistics.circular_dependencies:
            dot.attr('node', shape='ellipse', style='filled', fillcolor='red')
            for cycle in project_structure.statistics.circular_dependencies:
                if len(cycle) > 1:
                    for i in range(len(cycle) - 1):
                        if cycle[i] in important_classes and cycle[i + 1] in important_classes:
                            dot.edge(cycle[i], cycle[i + 1], color='red', penwidth='2')

        # Render the diagram
        output_file = output_dir / 'dependency_graph'
        dot.render(output_file, format=self.config.diagram_format, cleanup=True)

        return Path(f"{output_file}.{self.config.diagram_format}")

    def _generate_statistics_report(self, project_structure: ProjectStructure, output_dir: Path) -> Path:
        """Generate a statistics report"""
        stats = project_structure.statistics

        report = f"""# Project Statistics Report

## Overview
- **Total Packages**: {stats.package_count}
- **Total Classes**: {stats.total_classes}
- **Total Interfaces**: {stats.total_interfaces}
- **Total Enums**: {stats.total_enums}
- **Total Methods**: {stats.total_methods}

## Metrics
- **Average Methods per Class**: {stats.average_methods_per_class:.2f}
- **Max Class Dependencies**: {stats.max_class_dependencies}

## Package Summary
"""

        for package_name, package in sorted(project_structure.packages.items()):
            report += f"\n### {package_name or 'default'}\n"
            report += f"- Classes: {len(package.classes)}\n"
            report += f"- Sub-packages: {len(package.subpackages)}\n"

        # Add circular dependencies if found
        if stats.circular_dependencies:
            report += "\n## Circular Dependencies Found\n"
            for i, cycle in enumerate(stats.circular_dependencies[:10]):  # Limit to 10
                cycle_str = " -> ".join(cycle)
                report += f"{i + 1}. {cycle_str}\n"

        # Save report
        report_file = output_dir / "statistics_report.md"
        with open(report_file, 'w') as f:
            f.write(report)

        return report_file

    def _calculate_package_dependencies(self, project_structure: ProjectStructure) -> Dict[str, Set[str]]:
        """Calculate dependencies between packages"""
        package_deps = {}

        for class_info in project_structure.classes.values():
            from_package = class_info.package

            if from_package not in package_deps:
                package_deps[from_package] = set()

            for dep in project_structure.dependency_graph.get_dependencies(class_info.full_name):
                if dep in project_structure.classes:
                    to_package = project_structure.classes[dep].package
                    package_deps[from_package].add(to_package)

        return package_deps

    def _resolve_class_name(self, class_name: str, project_structure: ProjectStructure) -> str:
        """Resolve a class name to its full name if possible"""
        if class_name in project_structure.classes:
            return class_name

        # Try to find it by simple name
        for full_name, class_info in project_structure.classes.items():
            if class_info.name == class_name:
                return full_name

        return class_name