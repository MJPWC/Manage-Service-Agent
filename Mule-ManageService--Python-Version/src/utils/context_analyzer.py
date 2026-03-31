"""
Context Analyzer for MuleSoft Applications
Provides project-wide context analysis and related file impact assessment
"""

import os
import re
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
import xml.etree.ElementTree as ET

@dataclass
class FileContext:
    """Represents context information about a file"""
    file_path: str
    file_type: str
    dependencies: Set[str]
    referenced_by: Set[str]
    flow_names: List[str]
    connector_configs: List[str]
    error_handlers: bool

class MuleSoftContextAnalyzer:
    """Analyzes project context and relationships"""
    
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.file_index = self._build_file_index()
        self.dependency_graph = self._build_dependency_graph()
    
    def _build_file_index(self) -> Dict[str, FileContext]:
        """Build index of all files and their metadata"""
        file_index = {}
        
        for root, dirs, files in os.walk(self.project_root):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', 'target', 'build']]
            
            for file in files:
                if file.endswith(('.xml', '.dwl', '.java', '.properties')):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, self.project_root)
                    
                    context = self._analyze_file(file_path, relative_path)
                    file_index[relative_path] = context
        
        return file_index
    
    def _analyze_file(self, file_path: str, relative_path: str) -> FileContext:
        """Analyze individual file for context"""
        file_type = os.path.splitext(file_path)[1][1:]  # Remove dot
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return FileContext(relative_path, file_type, set(), set(), [], [], False)
        
        dependencies = set()
        referenced_by = set()
        flow_names = []
        connector_configs = []
        error_handlers = False
        
        if file_type == 'xml':
            flow_names, connector_configs, error_handlers, dependencies = self._analyze_xml_file(content)
        elif file_type == 'dwl':
            dependencies = self._analyze_dataweave_file(content)
        elif file_type == 'java':
            dependencies = self._analyze_java_file(content)
        
        return FileContext(
            file_path=relative_path,
            file_type=file_type,
            dependencies=dependencies,
            referenced_by=referenced_by,
            flow_names=flow_names,
            connector_configs=connector_configs,
            error_handlers=error_handlers
        )
    
    def _analyze_xml_file(self, content: str) -> Tuple[List[str], List[str], bool, Set[str]]:
        """Analyze XML file for flows, configs, and dependencies"""
        flow_names = []
        connector_configs = []
        error_handlers = False
        dependencies = set()
        
        try:
            root = ET.fromstring(content)
            
            # Extract flow names
            for flow in root.iter():
                if flow.tag.endswith('flow'):
                    name = flow.attrib.get('name', '')
                    if name:
                        flow_names.append(name)
                
                # Extract connector configurations
                if 'config' in flow.tag:
                    config_name = flow.attrib.get('name', '')
                    if config_name:
                        connector_configs.append(config_name)
                
                # Check for error handlers
                if flow.tag.endswith('try') or flow.tag.endswith('catch'):
                    error_handlers = True
                
                # Extract dependencies (references to other configs)
                for attr, value in flow.attrib.items():
                    if 'config-ref' in attr and value:
                        dependencies.add(value)
        
        except ET.ParseError:
            pass
        
        return flow_names, connector_configs, error_handlers, dependencies
    
    def _analyze_dataweave_file(self, content: str) -> Set[str]:
        """Analyze DataWeave file for dependencies"""
        dependencies = set()
        
        # Look for imports and references
        import_pattern = r'import\s+(\w+)'
        matches = re.findall(import_pattern, content)
        dependencies.update(matches)
        
        # Look for function calls
        function_pattern = r'(\w+)\s*\('
        matches = re.findall(function_pattern, content)
        dependencies.update(matches)
        
        return dependencies
    
    def _analyze_java_file(self, content: str) -> Set[str]:
        """Analyze Java file for dependencies"""
        dependencies = set()
        
        # Import statements
        import_pattern = r'import\s+([\w.]+);'
        matches = re.findall(import_pattern, content)
        dependencies.update(matches)
        
        return dependencies
    
    def _build_dependency_graph(self) -> Dict[str, Set[str]]:
        """Build dependency relationships between files"""
        dependency_graph = {}
        
        for file_path, context in self.file_index.items():
            dependency_graph[file_path] = set()
            
            # Find files that reference this file's configurations
            for other_file, other_context in self.file_index.items():
                if file_path != other_file:
                    # Check if other file references this file's configs
                    for config in context.connector_configs:
                        if config in other_context.dependencies:
                            dependency_graph[file_path].add(other_file)
        
        return dependency_graph
    
    def get_related_files(self, file_path: str, max_depth: int = 2) -> List[str]:
        """Get files related to the given file"""
        related = set()
        visited = set()
        
        def _traverse(current_file: str, depth: int):
            if depth >= max_depth or current_file in visited:
                return
            
            visited.add(current_file)
            
            # Add direct dependencies
            if current_file in self.file_index:
                related.update(self.file_index[current_file].dependencies)
                
                # Add files that reference this file
                related.update(self.dependency_graph.get(current_file, set()))
            
            # Recurse to related files
            for related_file in list(related):
                if related_file in self.file_index:
                    _traverse(related_file, depth + 1)
        
        if file_path in self.file_index:
            _traverse(file_path, 0)
        
        return list(related - {file_path})
    
    def get_impact_analysis(self, file_path: str, proposed_change: str) -> Dict:
        """Analyze impact of proposed changes"""
        impact = {
            "affected_files": [],
            "risk_level": "low",
            "recommendations": [],
            "breaking_changes": []
        }
        
        if file_path not in self.file_index:
            return impact
        
        related_files = self.get_related_files(file_path)
        
        # Analyze change type
        change_lower = proposed_change.lower()
        
        if "config" in change_lower or "listener" in change_lower:
            impact["risk_level"] = "high"
            impact["affected_files"] = related_files[:5]  # Top 5 related files
            impact["recommendations"].append("Test all dependent flows after configuration changes")
            impact["breaking_changes"].append("Configuration changes may affect multiple flows")
        
        elif "flow" in change_lower:
            impact["risk_level"] = "medium"
            impact["affected_files"] = [f for f in related_files if "flow" in f]
            impact["recommendations"].append("Test flow integration points")
        
        elif "dataweave" in change_lower or "dwl" in change_lower:
            impact["risk_level"] = "low"
            impact["affected_files"] = [f for f in related_files if f.endswith('.dwl')]
            impact["recommendations"].append("Validate data transformation output")
        
        return impact
    
    def get_configuration_context(self, file_path: str) -> Dict:
        """Get configuration context for a file"""
        if file_path not in self.file_index:
            return {}
        
        context = self.file_index[file_path]
        
        return {
            "file_type": context.file_type,
            "flow_names": context.flow_names,
            "connector_configs": context.connector_configs,
            "has_error_handling": context.error_handlers,
            "dependencies": list(context.dependencies),
            "referenced_by": list(context.dependency_graph.get(file_path, set()))
        }
    
    def suggest_related_fixes(self, file_path: str, error_message: str) -> List[Dict]:
        """Suggest fixes in related files based on error context"""
        suggestions = []
        
        if file_path not in self.file_index:
            return suggestions
        
        # If error is about missing configuration, suggest checking related files
        if "config" in error_message.lower():
            for related_file in self.get_related_files(file_path, 1):
                if related_file in self.file_index:
                    related_context = self.file_index[related_file]
                    if related_context.connector_configs:
                        suggestions.append({
                            "file": related_file,
                            "type": "configuration_check",
                            "description": f"Check configuration in {related_file}",
                            "configs": related_context.connector_configs
                        })
        
        # If error is about data transformation, suggest related DataWeave files
        if "dataweave" in error_message.lower() or "transformation" in error_message.lower():
            dwl_files = [f for f in self.get_related_files(file_path) if f.endswith('.dwl')]
            for dwl_file in dwl_files:
                suggestions.append({
                    "file": dwl_file,
                    "type": "transformation_check",
                    "description": f"Review data transformation in {dwl_file}"
                })
        
        return suggestions
