#!/usr/bin/env python3
"""
Mule Application Log Parser
Port of the Node.js logParser.js functionality
"""

import re
from typing import Any, Dict, List, Optional


class LogParser:
    """Port of the Node.js logParser.js functionality"""

    START_RE_COMPAT = re.compile(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s+([A-Z]+)\s+\[([^\]]+)\]\s+(.+?)\s+-\s*(.*)$"
    )
    EVENT_ID_RE = re.compile(r"\bevent:([0-9a-fA-F-]{8,})\b")
    ASTERISK_RE = re.compile(r"^\s*\*+\s*$")
    BLANK_RE = re.compile(r"^\s*$")

    @staticmethod
    def parse_value(v: str) -> Any:
        """Coerce scalar values where obvious (null, boolean, int, float, string)"""
        v = v.strip()
        if v.lower() == "null":
            return None
        if v.lower() in ["true", "false"]:
            return v.lower() == "true"

        # Try int
        if re.match(r"^[+-]?\d+$", v):
            try:
                return int(v, 10)
            except ValueError:
                pass

        # Try float
        if re.match(r"^[+-]?\d+\.\d+$", v):
            try:
                return float(v)
            except ValueError:
                pass

        return v

    @staticmethod
    def parse_brace_payload(msg: str) -> Optional[Dict]:
        """Parse {k=v, k2=v2} into dict"""
        msg = msg.strip()
        if not msg.startswith("{") or not msg.endswith("}"):
            return None

        inner = msg[1:-1].strip()
        if not inner:
            return {}

        parts = [p.strip() for p in inner.split(",")]
        out = {}
        for p in parts:
            if "=" in p:
                k, val = p.split("=", 1)
                out[k.strip()] = LogParser.parse_value(val.strip())
            else:
                out[p] = True

        return out

    @staticmethod
    def decode_html_entities(text: str) -> str:
        """Decode HTML entities (basic implementation)"""
        entities = {
            "&lt;": "<",
            "&gt;": ">",
            "&amp;": "&",
            "&quot;": '"',
            "&#39;": "'",
            "&apos;": "'",
        }
        result = text
        for entity, char in entities.items():
            result = result.replace(entity, char)
        return result

    @staticmethod
    def is_key_line(line: str) -> bool:
        """Check if a line appears to be a key-value line (ends with key followed by colon)"""
        stripped = line.strip()
        # Check if it has a colon and the part before colon looks like a key
        # Keys typically have capital letters and no special chars except spaces and hyphens
        if ":" in stripped:
            colon_idx = stripped.find(":")
            key = stripped[:colon_idx].strip()
            # A key line has a short key (usually < 30 chars) with capital letters
            return (
                bool(key)
                and len(key) < 30
                and not any(c in key for c in ["=", "<", ">", "{", "}"])
            )
        return False

    @staticmethod
    def parse_exception_block(lines: List[str], start_index: int) -> Dict:
        """Parse Mule DefaultExceptionListener banner block"""
        exc = {"raw": []}
        i = start_index  # Start at first asterisk line

        # Skip the banner header which typically looks like:
        # ****...****
        # *   Description   *
        # ****...****
        # We need to skip these and then find the actual content

        # Simply skip the known banner structure: typically 3 lines (asterisks, text, asterisks)
        # But be safe and look for a pattern of content lines (lines with ':')
        banner_end = start_index
        while banner_end < len(lines):
            line = lines[banner_end]
            # Content lines have colons (key: value format) or are blank
            if ":" in line or LogParser.BLANK_RE.match(line):
                break
            banner_end += 1

        # Add banner lines to raw
        for j in range(start_index, banner_end):
            if j < len(lines):
                exc["raw"].append(lines[j])

        # Now parse the actual key-value pairs
        i = banner_end
        while i < len(lines):
            line = lines[i]

            # Stop at another banner or new log entry
            if LogParser.ASTERISK_RE.match(line) or LogParser.START_RE_COMPAT.match(
                line
            ):
                break

            # Skip blank lines
            if LogParser.BLANK_RE.match(line):
                i += 1
                continue

            if ":" in line:
                colon_idx = line.find(":")
                key = line[:colon_idx].strip()
                val = line[colon_idx + 1 :].strip()

                if key == "Element DSL":
                    val = LogParser.decode_html_entities(val)

                if key == "FlowStack":
                    stack_lines = [val]
                    j = i + 1
                    while j < len(lines):
                        nxt = lines[j]
                        if LogParser.ASTERISK_RE.match(nxt) or LogParser.BLANK_RE.match(
                            nxt
                        ):
                            break
                        if LogParser.START_RE_COMPAT.match(nxt):
                            break
                        stack_lines.append(nxt.strip())
                        j += 1
                    exc["FlowStack"] = "\n".join(stack_lines).strip()
                    i = j - 1
                elif key == "Message":
                    # Check if Message has unstructured content following it
                    message_lines = [val] if val else []
                    j = i + 1

                    # Collect lines until we hit another key line
                    while j < len(lines):
                        nxt = lines[j]
                        if LogParser.ASTERISK_RE.match(nxt) or LogParser.BLANK_RE.match(
                            nxt
                        ):
                            break
                        if LogParser.is_key_line(nxt):
                            # Found next key, stop here
                            break
                        if LogParser.START_RE_COMPAT.match(nxt):
                            break
                        # Add this line to the message
                        message_lines.append(nxt.strip())
                        j += 1

                    # Join all message lines and clean up
                    exc[key] = "\n".join(message_lines).strip()
                    i = j - 1
                else:
                    exc[key] = val

            exc["raw"].append(line)
            i += 1

        return {"exception": exc, "next_index": i}

    @staticmethod
    def parse_logs(text: str) -> List[Dict]:
        """Parse raw log text into structured JSON"""
        lines = text.split("\n")
        out = []
        current = None

        i = 0
        while i < len(lines):
            line = lines[i]

            m = LogParser.START_RE_COMPAT.match(line)
            if m:
                # Close previous
                if current is not None:
                    if current.get("details") and isinstance(current["details"], str):
                        current["details"] = current["details"].rstrip()
                    out.append(current)

                current = {
                    "timestamp": m[1],
                    "level": m[2],
                    "tag": m[3],
                    "component": None,
                    "context": None,
                    "message": None,
                }

                prelude = m[4].strip()
                msg = m[5]

                # component = first token; context = remainder
                parts = prelude.split()
                current["component"] = parts[0] if parts else None
                current["context"] = " ".join(parts[1:]) if len(parts) > 1 else None

                # event_id if present
                ev = LogParser.EVENT_ID_RE.search(prelude)
                if ev:
                    current["event_id"] = ev[1]

                # Message handling
                current["message"] = msg or ""

                # Parse brace payload into data
                payload = LogParser.parse_brace_payload(current["message"])
                if payload is not None:
                    current["data"] = payload

                # Detect start of an exception banner block
                # Look for asterisk lines following an ERROR log (regardless of component)
                # This handles both DefaultExceptionListener logs and other exception blocks
                next_line_idx = i + 1
                while next_line_idx < len(lines) and LogParser.BLANK_RE.match(
                    lines[next_line_idx]
                ):
                    next_line_idx += 1

                if (
                    current["level"] == "ERROR"
                    and next_line_idx < len(lines)
                    and LogParser.ASTERISK_RE.match(lines[next_line_idx])
                ):
                    result = LogParser.parse_exception_block(lines, next_line_idx)
                    current["exception"] = result["exception"]
                    i = result["next_index"]
                    continue

                i += 1
                continue

            # Non-starting line (continuation or block detail)
            if current is not None and line.strip():
                if not current.get("details"):
                    current["details"] = ""
                current["details"] += line + "\n"

            i += 1

        # Close last
        if current is not None:
            if current.get("details") and isinstance(current["details"], str):
                current["details"] = current["details"].rstrip()
            out.append(current)

        return out

    @staticmethod
    def extract_error_description(log_entry: Dict) -> str:
        """
        Extract error description from a parsed log entry.
        Handles both structured and unstructured exception formats.

        Returns:
            - From exception.Message field if it contains the error
            - Constructs description from exception fields (Error type, Element, etc.)
            - Falls back to log message if no exception
        """
        if not log_entry.get("exception"):
            return log_entry.get("message", "")

        exc = log_entry["exception"]

        # Primary source: Message field from Raw block
        if exc.get("Message"):
            msg = exc["Message"].strip()
            if msg:  # If Message is not empty
                return msg

        # Fallback: construct from structured fields
        parts = []

        # Add Error type
        if exc.get("Error type"):
            parts.append(f"Error type: {exc['Error type']}")

        # Add Element
        if exc.get("Element"):
            parts.append(f"Element: {exc['Element']}")

        # Add Element DSL if different from Element
        if exc.get("Element DSL") and exc.get("Element DSL") != exc.get("Element"):
            parts.append(f"Element DSL: {exc['Element DSL']}")

        # If we have any parts, return them
        if parts:
            return "\n".join(parts)

        # Last fallback: return the raw message or log message
        return log_entry.get("message", "")
