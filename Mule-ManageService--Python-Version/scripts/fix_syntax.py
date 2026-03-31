#!/usr/bin/env python3
import re

with open('llm_manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken f-string by removing the line break and reformatting
content = re.sub(
    r'logger\.info\(f\"📤 Provider \{provi\nder\} SUCCESS - Response preview: \{preview\}\"\)',
    'logger.info(f"📤 Provider {provider} SUCCESS - Response preview: {preview}")',
    content
)

with open('llm_manager.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed syntax error in llm_manager.py")
