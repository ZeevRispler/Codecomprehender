import logging
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import defaultdict

try:
    import graphviz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

logger = logging.getLogger(__name__)

class DiagramGenerator:
    """Generate comprehensive architecture diagrams"""

    def __init__(self, config):
        self.config = config

    def generate_all(self, project_info: Dict[str, Any], output_dir: Path) -> List[Path]:
        """Generate all available diagrams"""
        if not HAS_GRAPHVIZ:
            logger.warning("Graphviz not installed - skipping diagrams")
            return []

        generated = []

        try:
            # 1. Project overview (simple)
            overview = self._generate_project_overview(project_info, output_dir)
            if overview:
                generated.append(overview)

            # 2. Package structure diagram
            package_diagram = self._generate_package_diagram(project_info, output_dir)
            if package_diagram:
                generated.append(package_diagram)

            # 3. Class diagram (UML-style)
            class_diagram = self._generate_class_diagram(project_info, output_dir)
            if class_diagram:
                generated.append(class_diagram)

            # 4. Dependency graph
            dependency_graph = self._generate_dependency_graph(project_info, output_dir)
            if dependency_graph:
                generated.append(dependency_graph)

            # 5. Inheritance hierarchy
            inheritance_diagram = self._generate_inheritance_diagram(project_info, output_dir)
            if inheritance_diagram:
                generated.append(inheritance_diagram)

            # 6. Statistics report (text-based)
            stats_report = self._generate_statistics_report(project_info, output_dir)
            if stats_report:
                generated.append(stats_report)

        except Exception as e:
            logger.warning(f"Error generating diagrams: {e}")

        logger.info(f"Generated {len(generated)} diagram files")
        return generated

    def _generate_project_overview(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate a high-level project overview"""
        dot = graphviz.Digraph(comment='Project Overview', format=self.config.diagram_format)
        dot.attr(rankdir='TB', bgcolor='white')
        dot.attr('node', fontname='Arial', fontsize='10')

        # Project root
        project_name = project_info['project_path'].name
        total_classes = project_info.get('total_classes', 0)
        total_methods = project_info.get('total_methods', 0)
        package_count = len(project_info.get('packages', []))

        dot.node('project', f"{project_name}\\n"
                           f"{total_classes} classes\\n"
                           f"{total_methods} methods\\n"
                           f"{package_count} packages",
                 shape='box', style='filled', fillcolor='lightblue')

        # Add top packages with proper formatting
        packages = project_info.get('packages', [])[:8]  # Limit for readability
        for i, package in enumerate(packages):
            # Break long package names for better display
            if len(package) > 20:
                package_display = package.replace('.', '\\n')
            else:
                package_display = package

            dot.node(f'pkg_{i}', f"📦 {package_display}",
                    shape='folder', style='filled', fillcolor='lightyellow')
            dot.edge('project', f'pkg_{i}')

        # Show if there are more packages
        if len(project_info.get('packages', [])) > 8:
            remaining = len(project_info['packages']) - 8
            dot.node('more_pkgs', f"... and {remaining} more packages",
                    shape='note', style='filled', fillcolor='lightgray')
            dot.edge('project', 'more_pkgs')

        # Render the diagram
        output_file = output_dir / 'project_overview'
        dot.render(str(output_file), cleanup=True)
        return output_file.with_suffix(f'.{self.config.diagram_format}')

    def _generate_package_diagram(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate package structure and dependencies"""
        dot = graphviz.Digraph(comment='Package Structure', format=self.config.diagram_format)
        dot.attr(rankdir='TB', bgcolor='white')
        dot.attr('node', fontname='Arial', fontsize='9')

        # Build package dependency map
        pkg_dependencies = self._analyze_package_dependencies(project_info)

        # Add package nodes
        for package in project_info.get('packages', []):
            # Count classes in this package
            class_count = sum(1 for cls in project_info.get('classes', [])
                            if hasattr(cls, 'name') and getattr(cls, 'package', '') == package)

            # Format package name for display
            display_name = package if package else 'default'
            if len(display_name) > 25:
                display_name = display_name.replace('.', '\\n')

            label = f"{display_name}\\n({class_count} classes)"
            dot.node(package or 'default', label,
                    shape='folder', style='filled', fillcolor='lightblue')

        # Add package dependencies
        for from_pkg, to_pkgs in pkg_dependencies.items():
            for to_pkg in to_pkgs:
                if from_pkg != to_pkg:  # No self-loops
                    dot.edge(from_pkg or 'default', to_pkg or 'default',
                           color='gray', arrowsize='0.7')

        output_file = output_dir / 'package_structure'
        dot.render(str(output_file), cleanup=True)
        return output_file.with_suffix(f'.{self.config.diagram_format}')

    def _generate_class_diagram(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate UML-style class diagram"""
        dot = graphviz.Digraph(comment='Class Diagram', format=self.config.diagram_format)
        dot.attr(rankdir='BT', bgcolor='white')  # Bottom-to-top for inheritance
        dot.attr('node', fontname='Arial', fontsize='8')

        # Limit classes for readability
        max_classes = getattr(self.config, 'max_classes_in_diagram', 30)
        classes = project_info.get('classes', [])[:max_classes]

        if len(project_info.get('classes', [])) > max_classes:
            logger.info(f"Showing {max_classes} of {len(project_info['classes'])} classes in diagram")

        # Add class nodes with UML-style formatting
        for cls in classes:
            if not hasattr(cls, 'name'):
                continue

            # Determine node style based on type
            cls_type = getattr(cls, 'type', 'class')
            if cls_type == 'interface':
                fillcolor = 'lightyellow'
                stereotype = '«interface»'
            elif cls_type == 'enum':
                fillcolor = 'lightgreen'
                stereotype = '«enum»'
            elif cls_type == 'abstract':
                fillcolor = 'lightcoral'
                stereotype = '«abstract»'
            else:
                fillcolor = 'lightblue'
                stereotype = ''

            # Build UML-style label
            label_parts = []

            if stereotype:
                label_parts.append(stereotype)

            label_parts.append(f"**{cls.name}**")

            # Add key fields (limit to avoid clutter)
            if hasattr(cls, 'fields') and cls.fields:
                fields_to_show = cls.fields[:5]  # Show max 5 fields
                field_lines = []
                for field in fields_to_show:
                    visibility_symbol = self._get_visibility_symbol(getattr(field, 'visibility', 'package'))
                    field_type = getattr(field, 'type', 'Object')
                    field_line = f"{visibility_symbol}{field.name}: {field_type}"
                    if getattr(field, 'is_static', False):
                        field_line = f"__{field_line}__"  # Underline static
                    field_lines.append(field_line)

                if field_lines:
                    label_parts.append("---")  # Separator
                    label_parts.extend(field_lines)

            # Add key methods
            if hasattr(cls, 'methods') and cls.methods:
                methods_to_show = cls.methods[:5]  # Show max 5 methods
                method_lines = []
                for method in methods_to_show:
                    visibility_symbol = self._get_visibility_symbol(getattr(method, 'visibility', 'package'))
                    params = getattr(method, 'parameters', [])
                    param_str = ", ".join([f"{pname}: {ptype}" for ptype, pname in params[:2]])
                    if len(params) > 2:
                        param_str += "..."
                    return_type = getattr(method, 'return_type', 'void')
                    method_line = f"{visibility_symbol}{method.name}({param_str}): {return_type}"
                    if getattr(method, 'is_static', False):
                        method_line = f"__{method_line}__"
                    method_lines.append(method_line)

                if method_lines:
                    if not any("---" in part for part in label_parts):
                        label_parts.append("---")
                    label_parts.extend(method_lines)

            label = "\\l".join(label_parts) + "\\l"  # Left-align text

            dot.node(cls.name, label, shape='record', style='filled',
                    fillcolor=fillcolor, fontsize='8')

        # Add inheritance relationships
        class_names = {cls.name for cls in classes if hasattr(cls, 'name')}
        for cls in classes:
            if not hasattr(cls, 'name'):
                continue

            # Inheritance (extends)
            if hasattr(cls, 'extends') and cls.extends and cls.extends in class_names:
                dot.edge(cls.name, cls.extends,
                        arrowhead='empty', color='blue', penwidth='2')

            # Implementation (implements)
            if hasattr(cls, 'implements'):
                for interface in cls.implements:
                    if interface in class_names:
                        dot.edge(cls.name, interface,
                               arrowhead='empty', style='dashed', color='green')

        output_file = output_dir / 'class_diagram'
        dot.render(str(output_file), cleanup=True)
        return output_file.with_suffix(f'.{self.config.diagram_format}')

    def _generate_dependency_graph(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate class dependency graph"""
        dot = graphviz.Digraph(comment='Dependency Graph', format=self.config.diagram_format)
        dot.attr(rankdir='LR', bgcolor='white')
        dot.attr('node', fontname='Arial', fontsize='9')

        # Analyze dependencies from project info
        dependencies = project_info.get('dependencies', {})

        # Find most connected classes (nodes with most dependencies)
        class_connections = defaultdict(int)
        for class_name, deps in dependencies.items():
            class_connections[class_name] += len(deps)
            for dep in deps:
                class_connections[dep] += 1

        # Show top N most connected classes
        max_nodes = 30
        important_classes = dict(sorted(class_connections.items(),
                                      key=lambda x: x[1], reverse=True)[:max_nodes])

        if not important_classes:
            # Fallback - show some classes anyway
            all_classes = [cls.name for cls in project_info.get('classes', [])
                          if hasattr(cls, 'name')][:max_nodes]
            important_classes = {name: 1 for name in all_classes}

        # Add nodes with different colors based on connection count
        for class_name, connection_count in important_classes.items():
            # Find class info for styling
            cls_info = None
            for cls in project_info.get('classes', []):
                if hasattr(cls, 'name') and cls.name == class_name:
                    cls_info = cls
                    break

            if cls_info:
                cls_type = getattr(cls_info, 'type', 'class')
                if cls_type == 'interface':
                    fillcolor = 'lightyellow'
                elif cls_type == 'enum':
                    fillcolor = 'lightgreen'
                else:
                    # Color intensity based on connections
                    if connection_count > 10:
                        fillcolor = 'red'  # Highly connected
                    elif connection_count > 5:
                        fillcolor = 'orange'
                    else:
                        fillcolor = 'lightblue'
            else:
                fillcolor = 'lightgray'

            dot.node(class_name, class_name,
                    shape='ellipse', style='filled', fillcolor=fillcolor)

        # Add dependency edges
        for class_name, deps in dependencies.items():
            if class_name in important_classes:
                for dep in deps:
                    if dep in important_classes:
                        dot.edge(class_name, dep, color='gray', arrowsize='0.7')

        output_file = output_dir / 'dependency_graph'
        dot.render(str(output_file), cleanup=True)
        return output_file.with_suffix(f'.{self.config.diagram_format}')

    def _generate_inheritance_diagram(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate inheritance hierarchy diagram"""
        dot = graphviz.Digraph(comment='Inheritance Hierarchy', format=self.config.diagram_format)
        dot.attr(rankdir='BT', bgcolor='white')
        dot.attr('node', fontname='Arial', fontsize='9')

        # Find all inheritance relationships
        inheritance_pairs = []
        classes_with_inheritance = set()

        for cls in project_info.get('classes', []):
            if not hasattr(cls, 'name'):
                continue

            if hasattr(cls, 'extends') and cls.extends:
                inheritance_pairs.append((cls.name, cls.extends))
                classes_with_inheritance.add(cls.name)
                classes_with_inheritance.add(cls.extends)

            if hasattr(cls, 'implements'):
                for interface in cls.implements:
                    inheritance_pairs.append((cls.name, interface))
                    classes_with_inheritance.add(cls.name)
                    classes_with_inheritance.add(interface)

        if not inheritance_pairs:
            logger.info("No inheritance relationships found")
            return None

        # Add nodes for classes involved in inheritance
        for class_name in classes_with_inheritance:
            # Find class info
            cls_info = None
            for cls in project_info.get('classes', []):
                if hasattr(cls, 'name') and cls.name == class_name:
                    cls_info = cls
                    break

            if cls_info:
                cls_type = getattr(cls_info, 'type', 'class')
                if cls_type == 'interface':
                    fillcolor = 'lightyellow'
                    shape = 'diamond'
                elif cls_type == 'enum':
                    fillcolor = 'lightgreen'
                    shape = 'box'
                else:
                    fillcolor = 'lightblue'
                    shape = 'box'
            else:
                # External class/interface
                fillcolor = 'lightgray'
                shape = 'box'

            dot.node(class_name, class_name,
                    shape=shape, style='filled', fillcolor=fillcolor)

        # Add inheritance edges
        for child, parent in inheritance_pairs:
            # Different styles for extends vs implements
            cls_info = None
            for cls in project_info.get('classes', []):
                if hasattr(cls, 'name') and cls.name == child:
                    cls_info = cls
                    break

            if cls_info and hasattr(cls_info, 'extends') and cls_info.extends == parent:
                # Extends relationship
                dot.edge(child, parent, arrowhead='empty', color='blue', penwidth='2')
            else:
                # Implements relationship
                dot.edge(child, parent, arrowhead='empty', style='dashed', color='green')

        output_file = output_dir / 'inheritance_hierarchy'
        dot.render(str(output_file), cleanup=True)
        return output_file.with_suffix(f'.{self.config.diagram_format}')

    def _generate_statistics_report(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate detailed statistics report"""
        import datetime

        report_lines = [
            "# Project Architecture Report",
            "",
            f"**Project:** {project_info['project_path'].name}",
            f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Overview",
            f"- **Total Java Files:** {project_info.get('total_files', 0)}",
            f"- **Successfully Parsed:** {project_info.get('parsed_files', 0)}",
            f"- **Failed to Parse:** {project_info.get('failed_files', 0)}",
            f"- **Skipped Files:** {project_info.get('skipped_files', 0)}",
            "",
            "## Code Metrics",
            f"- **Total Classes:** {project_info.get('total_classes', 0)}",
            f"- **Total Methods:** {project_info.get('total_methods', 0)}",
            f"- **Total Fields:** {project_info.get('total_fields', 0)}",
            f"- **Packages:** {len(project_info.get('packages', []))}",
            "",
        ]

        # Class type breakdown
        class_types = defaultdict(int)
        for cls in project_info.get('classes', []):
            if hasattr(cls, 'type'):
                class_types[cls.type] += 1

        if class_types:
            report_lines.extend([
                "## Class Types",
                *[f"- **{ctype.title()}s:** {count}" for ctype, count in class_types.items()],
                "",
            ])

        # Package breakdown
        packages = project_info.get('packages', [])
        if packages:
            report_lines.extend([
                "## Packages",
                *[f"- `{pkg}`" for pkg in sorted(packages)[:20]],
            ])

            if len(packages) > 20:
                report_lines.append(f"- ... and {len(packages) - 20} more packages")

            report_lines.append("")

        # Dependency analysis
        dependencies = project_info.get('dependencies', {})
        if dependencies:
            # Find most dependent classes
            most_dependent = sorted(
                [(cls, len(deps)) for cls, deps in dependencies.items()],
                key=lambda x: x[1], reverse=True
            )[:10]

            if most_dependent:
                report_lines.extend([
                    "## Most Connected Classes",
                    *[f"- **{cls}:** {count} dependencies" for cls, count in most_dependent],
                    "",
                ])

        # Save report
        report_file = output_dir / "architecture_report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))

        return report_file

    def _analyze_package_dependencies(self, project_info: Dict[str, Any]) -> Dict[str, Set[str]]:
        """Analyze dependencies between packages"""
        pkg_deps = defaultdict(set)

        for cls in project_info.get('classes', []):
            if not hasattr(cls, 'name') or not hasattr(cls, 'dependencies'):
                continue

            from_package = getattr(cls, 'package', '')

            for dep in cls.dependencies:
                # Find which package the dependency belongs to
                dep_package = self._find_class_package(dep, project_info.get('classes', []))
                if dep_package and dep_package != from_package:
                    pkg_deps[from_package].add(dep_package)

        return dict(pkg_deps)

    def _find_class_package(self, class_name: str, all_classes: List) -> str:
        """Find which package a class belongs to"""
        for cls in all_classes:
            if hasattr(cls, 'name') and cls.name == class_name:
                return getattr(cls, 'package', '')
        return ''

    def _get_visibility_symbol(self, visibility: str) -> str:
        """Get UML visibility symbol"""
        symbols = {
            'public': '+',
            'private': '-',
            'protected': '#',
            'package': '~'
        }
        return symbols.get(visibility, '~')