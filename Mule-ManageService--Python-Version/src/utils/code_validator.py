"""
Code Validator for MuleSoft Applications
Provides syntax validation, compilation checking, and compatibility verification
"""

import xml.etree.ElementTree as ET
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

@dataclass
class ValidationIssue:
    """Represents a validation issue"""
    line_number: int
    column: int
    severity: str  # critical, high, medium, low
    message: str
    issue_type: str

@dataclass
class ValidationResult:
    """Result of code validation"""
    is_valid: bool
    issues: List[ValidationIssue]
    warnings: List[ValidationIssue]
    suggestions: List[str]

class MuleSoftCodeValidator:
    """Validates MuleSoft code for syntax and correctness"""
    
    def __init__(self):
        self.xml_schema_cache = {}
        self.dwl_patterns = self._load_dataweave_patterns()
    
    def _load_dataweave_patterns(self) -> Dict[str, str]:
        """Load DataWeave validation patterns"""
        return {
            "function_syntax": r'^\s*func\s+\w+\s*\([^)]*\)\s*=\s*',
            "output_declaration": r'^\s*%dw\s+\d+\.\d+\s*output\s+\w+',
            "import_syntax": r'^\s*import\s+[\w.]+',
            "var_declaration": r'^\s*var\s+\w+\s*=',
            "type_declaration": r'^\s*type\s+\w+\s*=',
        }
    
    def validate_xml_file(self, content: str, file_path: str = "") -> ValidationResult:
        """Validate XML configuration file"""
        issues = []
        warnings = []
        suggestions = []
        
        # Basic XML syntax validation
        try:
            root = ET.fromstring(content)
            
            # Validate MuleSoft specific structure
            issues.extend(self._validate_mule_structure(root, content))
            warnings.extend(self._validate_best_practices(root, content))
            
        except ET.ParseError as e:
            issues.append(ValidationIssue(
                line_number=getattr(e, 'position', [1, 0])[0],
                column=getattr(e, 'position', [1, 0])[1],
                severity="critical",
                message=f"XML syntax error: {str(e)}",
                issue_type="xml_syntax"
            ))
        
        except Exception as e:
            issues.append(ValidationIssue(
                line_number=1,
                column=0,
                severity="critical",
                message=f"Validation error: {str(e)}",
                issue_type="validation_error"
            ))
        
        # Additional validation checks
        issues.extend(self._validate_xml_references(content))
        suggestions.extend(self._suggest_improvements(content))
        
        return ValidationResult(
            is_valid=len([i for i in issues if i.severity == "critical"]) == 0,
            issues=issues,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def validate_dataweave_file(self, content: str, file_path: str = "") -> ValidationResult:
        """Validate DataWeave script"""
        issues = []
        warnings = []
        suggestions = []
        
        lines = content.split('\n')
        
        # Check for required header
        if not any(re.search(self.dwl_patterns["output_declaration"], line) for line in lines[:5]):
            issues.append(ValidationIssue(
                line_number=1,
                column=0,
                severity="high",
                message="Missing DataWeave output declaration (e.g., %dw 2.0 output application/json)",
                issue_type="missing_header"
            ))
        
        # Validate each line
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            
            # Check function syntax
            if line.startswith('func'):
                if not re.search(self.dwl_patterns["function_syntax"], line):
                    issues.append(ValidationIssue(
                        line_number=line_num,
                        column=0,
                        severity="medium",
                        message="Invalid function syntax",
                        issue_type="function_syntax"
                    ))
            
            # Check variable declarations
            if line.startswith('var'):
                if not re.search(self.dwl_patterns["var_declaration"], line):
                    issues.append(ValidationIssue(
                        line_number=line_num,
                        column=0,
                        severity="medium",
                        message="Invalid variable declaration syntax",
                        issue_type="var_syntax"
                    ))
            
            # Check for common null handling issues
            if 'payload.' in line and 'default' not in line:
                warnings.append(ValidationIssue(
                    line_number=line_num,
                    column=line.find('payload.'),
                    severity="medium",
                    message="Consider adding default value for null handling",
                    issue_type="null_handling"
                ))
        
        return ValidationResult(
            is_valid=len([i for i in issues if i.severity in ["critical", "high"]]) == 0,
            issues=issues,
            warnings=warnings,
            suggestions=suggestions
        )
    
    def _validate_mule_structure(self, root: ET.Element, content: str) -> List[ValidationIssue]:
        """Validate MuleSoft specific XML structure"""
        issues = []
        
        # Check for required Mule namespace
        if not any('mule' in ns for ns in root.attrib.values() if isinstance(ns, str)):
            issues.append(ValidationIssue(
                line_number=1,
                column=0,
                severity="high",
                message="Missing Mule namespace declaration",
                issue_type="missing_namespace"
            ))
        
        # Validate flow elements
        for flow in root.iter():
            if flow.tag.endswith('flow'):
                if 'name' not in flow.attrib:
                    issues.append(ValidationIssue(
                        line_number=self._get_line_number(content, flow),
                        column=0,
                        severity="high",
                        message="Flow element missing required 'name' attribute",
                        issue_type="missing_flow_name"
                    ))
        
        return issues
    
    def _validate_best_practices(self, root: ET.Element, content: str) -> List[ValidationIssue]:
        """Validate against MuleSoft best practices"""
        warnings = []
        
        # Check for unhandled exceptions
        for element in root.iter():
            if element.tag.endswith('try'):
                has_catch = False
                for sibling in element.itersiblings():
                    if sibling.tag.endswith('catch') or sibling.tag.endswith('error-handler'):
                        has_catch = True
                        break
                
                if not has_catch:
                    warnings.append(ValidationIssue(
                        line_number=self._get_line_number(content, element),
                        column=0,
                        severity="medium",
                        message="Try block without corresponding exception handler",
                        issue_type="unhandled_exception"
                    ))
        
        return warnings
    
    def _validate_xml_references(self, content: str) -> List[ValidationIssue]:
        """Validate XML references and dependencies"""
        issues = []
        
        # Find all config-ref attributes
        config_refs = re.findall(r'config-ref="([^"]+)"', content)
        
        # Check if referenced configs exist
        for ref in config_refs:
            config_pattern = f'name="{ref}"'
            if config_pattern not in content:
                issues.append(ValidationIssue(
                    line_number=content.find(f'config-ref="{ref}"') // len(content) + 1,
                    column=0,
                    severity="high",
                    message=f"Referenced configuration '{ref}' not found",
                    issue_type="missing_config_reference"
                ))
        
        return issues
    
    def _suggest_improvements(self, content: str) -> List[str]:
        """Suggest code improvements"""
        suggestions = []
        
        # Check for documentation
        if 'doc:name=' not in content:
            suggestions.append("Consider adding doc:name attributes for better documentation")
        
        # Check for logging
        if '<logger' not in content:
            suggestions.append("Consider adding logging for better debugging")
        
        # Check for error handling
        if '<catch' not in content and '<error-handler' not in content:
            suggestions.append("Consider adding error handling for robustness")
        
        return suggestions
    
    def _get_line_number(self, content: str, element: ET.Element) -> int:
        """Get line number of XML element (simplified)"""
        element_str = ET.tostring(element, encoding='unicode').split('\n')[0]
        return content.find(element_str) // len(content) + 1
    
    def validate_generated_code(self, original_content: str, generated_content: str, 
                               file_type: str) -> Tuple[bool, List[str]]:
        """Validate generated code against original"""
        validation_result = ValidationResult(True, [], [], [])
        
        if file_type == 'xml':
            validation_result = self.validate_xml_file(generated_content)
        elif file_type == 'dwl':
            validation_result = self.validate_dataweave_file(generated_content)
        
        # Additional comparison checks
        comparison_issues = self._compare_code_changes(original_content, generated_content)
        
        is_valid = validation_result.is_valid and len(comparison_issues) == 0
        all_issues = [f"{i.message} (line {i.line_number})" for i in validation_result.issues] + comparison_issues
        
        return is_valid, all_issues
    
    def _compare_code_changes(self, original: str, generated: str) -> List[str]:
        """Compare original and generated code for potential issues"""
        issues = []
        
        # Check for excessive changes
        original_lines = set(original.split('\n'))
        generated_lines = set(generated.split('\n'))
        
        unchanged_lines = original_lines & generated_lines
        total_lines = len(generated_lines)
        
        if total_lines > 0:
            change_ratio = 1 - (len(unchanged_lines) / total_lines)
            if change_ratio > 0.8:  # More than 80% changed
                issues.append("Warning: Large percentage of code changed. Review for unintended modifications.")
        
        # Check for indentation consistency
        original_indent = self._detect_indentation(original)
        generated_indent = self._detect_indentation(generated)
        
        if original_indent != generated_indent:
            issues.append(f"Indentation style changed from {original_indent} to {generated_indent}")
        
        return issues
    
    def _detect_indentation(self, content: str) -> str:
        """Detect indentation style (spaces or tabs)"""
        lines = [line for line in content.split('\n') if line.strip()]
        
        if not lines:
            return "unknown"
        
        # Check first few indented lines
        for line in lines[:10]:
            if line.startswith('\t'):
                return "tabs"
            elif line.startswith('  '):
                return "spaces"
        
        return "mixed_or_none"
    
    def get_fix_suggestions(self, validation_result: ValidationResult) -> List[Dict]:
        """Get fix suggestions based on validation results"""
        suggestions = []
        
        for issue in validation_result.issues:
            if issue.issue_type == "xml_syntax":
                suggestions.append({
                    "type": "syntax_fix",
                    "description": f"Fix XML syntax: {issue.message}",
                    "line": issue.line_number,
                    "auto_fixable": False
                })
            elif issue.issue_type == "missing_config_reference":
                suggestions.append({
                    "type": "config_fix",
                    "description": f"Add missing configuration: {issue.message}",
                    "line": issue.line_number,
                    "auto_fixable": True
                })
            elif issue.issue_type == "missing_flow_name":
                suggestions.append({
                    "type": "naming_fix",
                    "description": "Add flow name attribute",
                    "line": issue.line_number,
                    "auto_fixable": True
                })
        
        return suggestions
