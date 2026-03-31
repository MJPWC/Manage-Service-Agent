#!/usr/bin/env python3
"""
Debug script - inspect exception block parsing
"""

import os
import sys

# Add project root to path to allow importing from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.utils.log_parser import LogParser

# Simple test
SIMPLE_EXCEPTION = """2026-02-11T11:30:44.844Z ERROR [sf-agent-api] Agent-API-main - N/A
************************************************************
*            DefaultExceptionListener                       *
************************************************************
Application: sf-agent-api
Event ID: b8d0f80d-9589-4431-bfb7-0310bba71ed4
Timestamp: 2026-02-11T11:30:44.844Z
Element: Agent-API-main/processors/0 @ sf-agent-api:Agent-API.xml:17
Error type: APIKIT:METHOD_NOT_ALLOWED
Message: HTTP Method get not allowed for : /agent
************************************************************
"""

lines = SIMPLE_EXCEPTION.split('\n')

print("Checking which lines have colons:")
for i, line in enumerate(lines):
    has_colon = ':' in line
    end_idx = 11 if len(line) > 11 else len(line)
    print(f"  Line {i:2d}: {repr(line[:50])}... has_colon={has_colon}")

# Directly test parse_exception_block with detailed info
print("\nManual parse_exception_block trace at index 1:")
result = LogParser.parse_exception_block(lines, 1)
exc = result['exception']
print(f"Exception keys: {list(exc.keys())}")
print(f"Next index: {result['next_index']}")

# Print what was captured
for key in list(exc.keys())[:15]:
    if key == 'raw':
        print(f"  {key}: ({len(exc[key])} lines)")
    else:
        print(f"  {key}: {repr(str(exc[key])[:50])}")


