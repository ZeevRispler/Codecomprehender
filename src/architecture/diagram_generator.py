"""
Generate basic architecture diagrams

Creates simple class diagrams and package overviews.
Nothing fancy, just useful visualizations.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any

try:
    import graphviz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

logger = logging.getLogger(__name__)

class DiagramGenerator:
    """Generate architecture diagrams"""

    def __init__(self, config):
        self.config = config

    def generate_all(self, project_info: Dict[str, Any], output_dir: Path) -> List[Path]:
        """Generate all available diagrams"""
        if not HAS_GRAPHVIZ:
            logger.warning("Graphviz not installed - skipping diagrams")
            return []

        generated = []

        try:
            # Generate a simple project overview
            overview = self._generate_overview(project_info, output_dir)
            if overview:
                generated.append(overview)

            # TODO: Add class diagrams, dependency graphs, etc.
            # For now, just keep it simple

        except Exception as e:
            logger.warning(f"Couldn't generate diagrams: {e}")

        return generated

    def _generate_overview(self, project_info: Dict[str, Any], output_dir: Path) -> Path:
        """Generate a simple project overview diagram"""
        dot = graphviz.Digraph(comment='Project Overview')
        dot.attr(rankdir='TB')
        dot.attr('node', shape='box', style='filled', fillcolor='lightblue')

        # Add project info
        dot.node('project', f"Project\\n{project_info['total_files']} Java files\\n{project_info['total_classes']} classes")

        # Add packages
        for i, package in enumerate(project_info.get('packages', [])[:10]):  # Limit to 10
            package_name = package.replace('.', '\\n')  # Break long package names
            dot.node(f'pkg_{i}', f"Package\\n{package_name}")
            dot.edge('project', f'pkg_{i}')

        # Render
        output_file = output_dir / 'project_overview'
        dot.render(str(output_file), format='png', cleanup=True)

        return output_file.with_suffix('.png')