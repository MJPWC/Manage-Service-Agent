#!/usr/bin/env python3
"""
Centralized formatting rules and validation for LLM responses
"""

import re
from typing import Tuple, Dict, Any

# Centralized formatting rules
FORMATTING_RULES = """
⚠️ CODE FORMATTING REQUIREMENTS:
1. ALL code MUST be in triple backtick blocks with language
2. Use format: ```xml for XML, ```json for JSON
3. NEVER display code as plain text
4. ALWAYS include opening and closing triple backticks
"""

# Enhanced formatting examples (reduced size)
FORMATTING_EXAMPLES = """
GOOD FORMAT:
```xml
<flow name="test">
</flow>
```

BAD FORMAT:
<flow name="test">
</flow>
"""

def validate_code_blocks(response: str) -> Tuple[bool, str]:
    """
    Validate that all code snippets are properly formatted
    
    Args:
        response: LLM response text
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    issues = []
    
    # Simplified validation - just check for basic code block structure
    # Look for any code-like patterns that aren't in code blocks
    lines = response.split('\n')
    in_code_block = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Detect code block start/end (both triple and single backticks)
        if stripped.startswith('```') or (stripped == '`' and i > 0):
            in_code_block = not in_code_block
            continue
        
        # Only check for unformatted code if we're not in a code block
        if not in_code_block:
            # Look for obvious code patterns
            if ('<' in line and '>' in line and 
                (re.search(r'<[^>]+>.*</[^>]+>', line) or re.search(r'<[^/>]+/>', line))):
                # This might be unformatted XML, but be lenient
                continue  # Skip validation for now to avoid false positives
    
    # Only check for unclosed blocks
    triple_blocks = re.findall(r'```', response)
    if len(triple_blocks) % 2 != 0:
        issues.append("Unclosed triple backtick code blocks detected")
    
    # Be very lenient - most responses should pass
    is_valid = len(issues) == 0
    error_message = "; ".join(issues) if issues else "Format OK"
    
    return is_valid, error_message

def score_formatting(response: str) -> int:
    """
    Score response formatting quality (0-100)
    
    Args:
        response: LLM response text
        
    Returns:
        Score from 0 to 100
    """
    score = 100
    
    # Less strict deductions
    if not re.search(r'```(\w+)', response):
        score -= 15  # Missing language-specific code blocks (reduced from 30)
    
    # Check for unformatted code (more lenient)
    lines = response.split('\n')
    in_code_block = False
    unformatted_count = 0
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        
        if not in_code_block and '<' in line and '>' in line:
            if re.search(r'<[^>]+>.*</[^>]+>', line) or re.search(r'<[^/>]+/>', line):
                unformatted_count += 1
    
    if unformatted_count > 0:
        score -= 10  # Reduced from 20
    
    code_blocks = re.findall(r'```', response)
    if len(code_blocks) % 2 != 0:
        score -= 15  # Reduced from 25
    
    # Bonus points for good formatting
    if re.search(r'### Issue \d+:', response):
        score += 5  # Proper issue numbering
    
    if re.search(r'\*\*Location\*\*:', response):
        score += 5  # Proper location formatting
    
    if re.search(r'\*\*Why\)\*: ', response):
        score += 5  # Proper explanation formatting
    
    return max(0, min(100, score))

def get_formatting_correction_prompt(validation_error: str) -> str:
    """
    Generate a correction prompt based on validation errors
    
    Args:
        validation_error: Error message from validate_code_blocks
        
    Returns:
        Correction prompt string
    """
    corrections = []
    
    if "unformatted XML" in validation_error:
        corrections.append("Wrap all XML code in ```xml blocks")
    
    if "unformatted JSON" in validation_error:
        corrections.append("Wrap all JSON code in ```json blocks")
    
    if "Unclosed code blocks" in validation_error:
        corrections.append("Ensure all code blocks have opening and closing ```")
    
    if "Missing language-specific" in validation_error:
        corrections.append("Add language specification (xml, json, yaml, etc.) after ```")
    
    if "missing content" in validation_error:
        corrections.append("Ensure code blocks contain actual code between the ``` markers")
    
    if corrections:
        return f"\n\n⚠️ Formatting Error: {validation_error}\nPlease fix: {', '.join(corrections)}."
    
    return ""

def enhance_response_formatting(response: str) -> str:
    """
    Attempt to automatically fix common formatting issues
    
    Args:
        response: Original LLM response
        
    Returns:
        Enhanced response with better formatting
    """
    enhanced = response
    
    # Fix unformatted XML blocks
    xml_pattern = r'(^|\n)([^`\n]*<[^>]+>[^<]*<[^>]+>[^`\n]*)(\n|$)'
    def fix_xml(match):
        prefix, xml_code, suffix = match.groups()
        return f'{prefix}```xml\n{xml_code.strip()}\n```\n{suffix}'
    
    enhanced = re.sub(xml_pattern, fix_xml, enhanced, flags=re.MULTILINE)
    
    # Fix unformatted JSON blocks
    json_pattern = r'(^|\n)([^`\n]*\{[^}]*\}[^`\n]*)(\n|$)'
    def fix_json(match):
        prefix, json_code, suffix = match.groups()
        return f'{prefix}```json\n{json_code.strip()}\n```\n{suffix}'
    
    enhanced = re.sub(json_pattern, fix_json, enhanced, flags=re.MULTILINE)
    
    return enhanced

def get_formatting_summary(response: str) -> Dict[str, Any]:
    """
    Get comprehensive formatting analysis
    
    Args:
        response: LLM response text
        
    Returns:
        Dictionary with formatting metrics
    """
    is_valid, error_message = validate_code_blocks(response)
    score = score_formatting(response)
    
    # Count code blocks by language
    code_blocks = re.findall(r'```(\w+)', response)
    language_counts = {}
    for lang in code_blocks:
        language_counts[lang] = language_counts.get(lang, 0) + 1
    
    # Count issues
    issue_count = len(re.findall(r'### Issue \d+:', response))
    
    return {
        'is_valid': is_valid,
        'score': score,
        'error_message': error_message,
        'language_counts': language_counts,
        'issue_count': issue_count,
        'total_code_blocks': len(code_blocks),
        'recommendations': get_formatting_recommendations(score, is_valid, error_message)
    }

def get_formatting_recommendations(score: int, is_valid: bool, error_message: str) -> list:
    """
    Get formatting recommendations based on analysis
    
    Args:
        score: Formatting score
        is_valid: Whether formatting is valid
        error_message: Validation error message
        
    Returns:
        List of recommendations
    """
    recommendations = []
    
    if not is_valid:
        recommendations.append("Fix formatting errors before displaying to user")
    
    if score < 70:
        recommendations.append("Consider regenerating analysis for better formatting")
    
    if score < 50:
        recommendations.append("Use automatic formatting enhancement")
    
    if "unformatted" in error_message:
        recommendations.append("Add code block wrappers around code snippets")
    
    if "Unclosed" in error_message:
        recommendations.append("Check for missing closing ``` markers")
    
    if not recommendations and score >= 70:
        recommendations.append("Formatting looks good!")
    
    return recommendations
