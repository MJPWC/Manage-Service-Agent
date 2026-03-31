#!/usr/bin/env python3
"""
Mule Application Log Parser
Specialized parser for debug and normal Mule application logs
Extracts API information, flow stack analysis, and error details
"""

import re
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum


class LogFileType(Enum):
    """Enum for log file types"""
    DEBUG_LOG = "debug_log"
    NORMAL_LOG = "normal_log"
    UNKNOWN = "unknown"


class LoggerType(Enum):
    """Enum for logger types"""
    MULESOFT_LOGGER = "mulesoft_logger"
    CUSTOM_LOGGER = "custom_logger"
    UNKNOWN = "unknown"


@dataclass
class FlowStackEntry:
    """Represents a single entry in the flow stack"""
    flow_name: str
    processor_info: str
    api_name: str
    file_name: str
    line_number: Optional[int]
    description: str
    
    def __repr__(self):
        return f"FlowStackEntry(flow={self.flow_name}, api={self.api_name}, file={self.file_name}, line={self.line_number})"


@dataclass
class ErrorLocation:
    """Error location information"""
    api_name: str
    file_name: str
    line_number: Optional[int]
    processor_location: str
    flow_name: str


@dataclass
class LogAnalysis:
    """Complete log analysis result"""
    file_type: LogFileType
    logger_type: LoggerType
    timestamp: Optional[str]
    correlation_id: Optional[str]
    error_type: Optional[str]
    error_message: Optional[str]
    error_location: Optional[ErrorLocation]
    flow_stack: List[FlowStackEntry]
    channel_id: Optional[str]
    resource: Optional[str]
    service_id: Optional[str]
    transaction_id: Optional[str]
    element: Optional[str]
    element_dsl: Optional[str]


class MuleLogDetector:
    """Detect log file and logger types"""
    
    # Patterns for Mule-specific content
    MULESOFT_PATTERNS = [
        r"DEFAULT.*CEPTION",  # DefaultExceptionListener
        r"FlowStack\s*:",
        r"Error type\s*:",
        r"Element\s*:",
        r"Element DSL\s*:",
        r"\[MuleRuntime\]",
        r"@.*\.xml:\d+",  # File references like @create-referral.xml:46
        r"at\s+\w+.*\.xml:\d+",
    ]
    
    CUSTOM_LOGGER_PATTERNS = [
        r"custom.*log",
        r"app.*log",
        r"business.*log",
    ]
    
    DEBUG_LOG_INDICATORS = [
        r"DEBUG",
        r"TRACE",
        r"correlation.?id",
        r"event.?id",
        r"\[com\.mulesoft",
        r"payload\s*=",
        r"variables\s*=",
    ]
    
    @staticmethod
    def detect_log_file_type(content: str) -> LogFileType:
        """
        Detect whether the log is a debug log or normal log file
        
        Debug logs typically contain:
        - DEBUG and TRACE level messages
        - Correlation IDs and Event IDs
        - Payload and variables information
        - Mule runtime diagnostic info
        
        Normal logs contain:
        - ERROR, WARN, INFO levels
        - Exception stack traces
        - Business-level error messages
        - DefaultExceptionListener blocks
        """
        debug_indicators = sum(
            1 for pattern in MuleLogDetector.DEBUG_LOG_INDICATORS
            if re.search(pattern, content, re.IGNORECASE)
        )
        
        # Check for normal log indicators (strong indicators)
        has_exception_block = bool(re.search(r'DefaultExceptionListener|Error type\s*:', content, re.IGNORECASE))
        has_error_level = bool(re.search(r'\sERROR\s', content))
        has_element_field = bool(re.search(r'Element\s*:|FlowStack\s*:', content, re.IGNORECASE))
        
        normal_score = sum([has_exception_block, has_error_level, has_element_field])
        
        # If we find strong normal log indicators, it's a normal log
        if normal_score >= 2:
            return LogFileType.NORMAL_LOG
        
        # If we find multiple debug indicators, it's a debug log
        if debug_indicators >= 2:
            return LogFileType.DEBUG_LOG
        
        # Check for log levels to distinguish
        if has_error_level and not debug_indicators:
            return LogFileType.NORMAL_LOG
        
        if re.search(r'\s(DEBUG|TRACE)\s', content) and not has_error_level:
            return LogFileType.DEBUG_LOG
        
        return LogFileType.UNKNOWN
    
    @staticmethod
    def detect_logger_type(content: str) -> LoggerType:
        """
        Detect whether MuleSoft logger or custom logger is being used
        
        MuleSoft logger produces:
        - Specific timestamp format (ISO 8601)
        - Component names like [MuleRuntime]
        - FlowStack information
        - DefaultExceptionListener blocks
        
        Custom logger might have:
        - Different timestamp formats
        - Custom component/tag names
        - Different message structure
        """
        mulesoft_score = sum(
            1 for pattern in MuleLogDetector.MULESOFT_PATTERNS
            if re.search(pattern, content, re.IGNORECASE)
        )
        
        custom_score = sum(
            1 for pattern in MuleLogDetector.CUSTOM_LOGGER_PATTERNS
            if re.search(pattern, content, re.IGNORECASE)
        )
        
        if mulesoft_score >= 3:
            return LoggerType.MULESOFT_LOGGER
        elif custom_score >= 2:
            return LoggerType.CUSTOM_LOGGER
        elif mulesoft_score >= 1:
            return LoggerType.MULESOFT_LOGGER
        
        return LoggerType.UNKNOWN


class FlowStackParser:
    """Parse Mule FlowStack information"""
    
    # Pattern to match flow stack entries
    # Format: at flow-name(flow-name/processors/N @ api-name:file.xml:line-number (description))
    FLOW_STACK_PATTERN = re.compile(
        r'at\s+(\w+(?:-\w+)*)\s*\('  # flow name
        r'(\w+(?:-\w+)*)/processors/(\d+)\s+@\s+'  # processor info
        r'([^:]+):([^/:]+\.xml):(\d+)\s*\('  # api-name:file.xml:line
        r'([^)]*)'  # description
        r'\)',
        re.VERBOSE
    )
    
    # Alternative pattern for api routes
    API_ROUTE_PATTERN = re.compile(
        r'at\s+([\w\\/\\:()]+):'  # route pattern
        r'(\w+):([^/:]+\.xml):(\d+)'  # api-name:type:file.xml:line
    )
    
    @staticmethod
    def parse_flow_stack(flow_stack_str: str) -> List[FlowStackEntry]:
        """
        Parse FlowStack string into structured entries
        
        Example:
        at invoke-ais-create-referral(invoke-ais-create-referral/processors/2 @ msd-sep-accint-ais-emp-sapi-v1:impl/create-referral.xml:46 (Successful else raise EXT:CANT_CREATE_REFERRAL))
        
        Returns list of FlowStackEntry objects ordered from innermost to outermost
        """
        entries = []
        
        if not flow_stack_str:
            return entries
        
        # Split by newlines to get individual stack entries
        lines = flow_stack_str.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or not line.startswith('at'):
                continue
            
            entry = FlowStackParser._parse_single_entry(line)
            if entry:
                entries.append(entry)
        
        return entries
    
    @staticmethod
    def _parse_single_entry(line: str) -> Optional[FlowStackEntry]:
        """Parse a single flow stack entry line"""
        # Remove 'at' prefix
        line = line[2:].strip()
        
        # Handle nested closing parentheses by finding balanced pairs
        # Format: flow-name(flow/processors/N @ api-name:path/file.xml:line (description))
        
        # Extract the main flow name (before first parenthesis)
        paren_idx = line.find('(')
        if paren_idx == -1:
            return None
        
        flow_name = line[:paren_idx].strip()
        
        # Find the content inside the outer parentheses
        # Count parentheses to find the matching closing paren
        paren_count = 0
        content_start = paren_idx + 1
        content_end = content_start
        
        for i in range(content_start, len(line)):
            if line[i] == '(':
                paren_count += 1
            elif line[i] == ')':
                if paren_count == 0:
                    content_end = i
                    break
                paren_count -= 1
        
        if content_end == content_start:
            return None
        
        content = line[content_start:content_end].strip()
        
        # Now parse the content: flow/processors/N @ api-name:path/file.xml:line (description)
        # Split by @ to separate processor info from api info
        at_idx = content.rfind(' @ ')
        if at_idx == -1:
            return None
        
        processor_part = content[:at_idx].strip()
        api_part = content[at_idx + 3:].strip()
        
        # Parse processor part: flow/processors/N
        processor_match = re.search(r'processors/(\d+)', processor_part)
        if not processor_match:
            return None
        
        processor_num = processor_match.group(1)
        processor_info = f"processors/{processor_num}"
        
        # Parse api part: api-name:path/file.xml:line (description)
        # Find the last colon followed by a number (line number)
        line_match = re.search(r':(\d+)\s*\(([^)]*)\)\s*$', api_part)
        if not line_match:
            return None
        
        line_number = int(line_match.group(1))
        description = line_match.group(2).strip()
        
        # Extract api-name and file.xml
        api_info = api_part[:line_match.start()].strip()
        
        # Split by colons to get api-name and file path
        # api-name:path/file.xml or api-name:impl/file.xml
        parts = api_info.split(':')
        if len(parts) < 2:
            return None
        
        api_name = parts[0].strip()
        
        # Extract file name with path from the remaining part
        remaining = ':'.join(parts[1:])
        # Find the xml file name with path (e.g., impl/create-referral.xml)
        # Look for the last path component before the line number
        # Pattern: anything ending with .xml before the :line_number
        xml_match = re.search(r'((?:[^/\\:]+[/\\])?[^/\\:]+\.xml)', remaining)
        if not xml_match:
            return None
        
        file_name = xml_match.group(1)
        
        return FlowStackEntry(
            flow_name=flow_name,
            processor_info=processor_info,
            api_name=api_name,
            file_name=file_name,
            line_number=line_number,
            description=description
        )
    
    @staticmethod
    def extract_error_location(flow_stack_entries: List[FlowStackEntry]) -> Optional[ErrorLocation]:
        """
        Extract the primary error location from flow stack
        Usually the first entry (where error occurred) or the one with actual error info
        """
        if not flow_stack_entries:
            return None
        
        # The first entry is typically where the error occurred
        first = flow_stack_entries[0]
        
        return ErrorLocation(
            api_name=first.api_name,
            file_name=first.file_name,
            line_number=first.line_number,
            processor_location=first.processor_info,
            flow_name=first.flow_name
        )


class MuleLogParser:
    """Main Mule log parser combining all analysis capabilities"""
    
    # Timestamp patterns
    TIMESTAMP_PATTERN = re.compile(
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)'
    )
    
    # Correlation and transaction IDs
    CORRELATION_ID_PATTERN = re.compile(
        r'(?:correlation.?id|event.?id|transactionId)[\s:=]+([0-9a-fA-F\-]+)',
        re.IGNORECASE
    )
    
    CHANNEL_ID_PATTERN = re.compile(
        r'channelId\s*=\s*(\S+)',
        re.IGNORECASE
    )
    
    RESOURCE_PATTERN = re.compile(
        r'resource\s*=\s*([\w:/\\()]+)',
        re.IGNORECASE
    )
    
    SERVICE_ID_PATTERN = re.compile(
        r'serviceId\s*=\s*(\S+)',
        re.IGNORECASE
    )
    
    TRANSACTION_ID_PATTERN = re.compile(
        r'transactionId\s*=\s*([0-9a-fA-F\-]+)',
        re.IGNORECASE
    )
    
    ERROR_TYPE_PATTERN = re.compile(
        r'Error\s+type\s*:\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )
    
    ERROR_MESSAGE_PATTERN = re.compile(
        r'Message\s*:\s*(.+?)(?:\n\w+\s*:|$)',
        re.IGNORECASE | re.DOTALL
    )
    
    ELEMENT_PATTERN = re.compile(
        r'Element\s*:\s*(.+?)(?:\n|$)',
        re.IGNORECASE
    )
    
    ELEMENT_DSL_PATTERN = re.compile(
        r'Element\s+DSL\s*:\s*(.+?)\n(?=\w+\s*:|error)',
        re.IGNORECASE | re.DOTALL
    )
    
    FLOW_STACK_PATTERN = re.compile(
        r'FlowStack\s*:\s*(.+?)(?:\n\s*\(set|$)',
        re.IGNORECASE | re.DOTALL
    )
    
    @staticmethod
    def analyze(content: str) -> LogAnalysis:
        """
        Comprehensive analysis of a Mule log file
        
        Returns LogAnalysis object with:
        - File type (debug or normal)
        - Logger type (MuleSoft or custom)
        - Extracted timestamps and IDs
        - Error information
        - Flow stack analysis
        """
        # Detect types
        file_type = MuleLogDetector.detect_log_file_type(content)
        logger_type = MuleLogDetector.detect_logger_type(content)
        
        # Extract basic information
        timestamp = MuleLogParser._extract_timestamp(content)
        correlation_id = MuleLogParser._extract_correlation_id(content)
        
        # Extract error information
        error_type = MuleLogParser._extract_error_type(content)
        error_message = MuleLogParser._extract_error_message(content)
        element = MuleLogParser._extract_element(content)
        element_dsl = MuleLogParser._extract_element_dsl(content)
        
        # Extract metadata
        channel_id = MuleLogParser._extract_channel_id(content)
        resource = MuleLogParser._extract_resource(content)
        service_id = MuleLogParser._extract_service_id(content)
        transaction_id = MuleLogParser._extract_transaction_id(content)
        
        # Parse FlowStack
        flow_stack_str = MuleLogParser._extract_flow_stack(content)
        flow_stack_entries = FlowStackParser.parse_flow_stack(flow_stack_str)
        error_location = FlowStackParser.extract_error_location(flow_stack_entries)
        
        return LogAnalysis(
            file_type=file_type,
            logger_type=logger_type,
            timestamp=timestamp,
            correlation_id=correlation_id,
            error_type=error_type,
            error_message=error_message,
            error_location=error_location,
            flow_stack=flow_stack_entries,
            channel_id=channel_id,
            resource=resource,
            service_id=service_id,
            transaction_id=transaction_id,
            element=element,
            element_dsl=element_dsl
        )
    
    @staticmethod
    def _extract_timestamp(content: str) -> Optional[str]:
        """Extract timestamp from log content"""
        match = MuleLogParser.TIMESTAMP_PATTERN.search(content)
        return match.group(1) if match else None
    
    @staticmethod
    def _extract_correlation_id(content: str) -> Optional[str]:
        """Extract correlation ID from log content"""
        match = MuleLogParser.CORRELATION_ID_PATTERN.search(content)
        return match.group(1) if match else None
    
    @staticmethod
    def _extract_channel_id(content: str) -> Optional[str]:
        """Extract channel ID from log content"""
        match = MuleLogParser.CHANNEL_ID_PATTERN.search(content)
        return match.group(1) if match else None
    
    @staticmethod
    def _extract_resource(content: str) -> Optional[str]:
        """Extract resource from log content"""
        match = MuleLogParser.RESOURCE_PATTERN.search(content)
        return match.group(1) if match else None
    
    @staticmethod
    def _extract_service_id(content: str) -> Optional[str]:
        """Extract service ID from log content"""
        match = MuleLogParser.SERVICE_ID_PATTERN.search(content)
        return match.group(1) if match else None
    
    @staticmethod
    def _extract_transaction_id(content: str) -> Optional[str]:
        """Extract transaction ID from log content"""
        match = MuleLogParser.TRANSACTION_ID_PATTERN.search(content)
        return match.group(1) if match else None
    
    @staticmethod
    def _extract_error_type(content: str) -> Optional[str]:
        """Extract error type from log content"""
        match = MuleLogParser.ERROR_TYPE_PATTERN.search(content)
        return match.group(1).strip() if match else None
    
    @staticmethod
    def _extract_error_message(content: str) -> Optional[str]:
        """Extract error message from log content"""
        match = MuleLogParser.ERROR_MESSAGE_PATTERN.search(content)
        if match:
            msg = match.group(1).strip()
            # Clean up multiline messages
            msg = re.sub(r'\s+', ' ', msg)
            return msg
        return None
    
    @staticmethod
    def _extract_element(content: str) -> Optional[str]:
        """Extract element from log content"""
        match = MuleLogParser.ELEMENT_PATTERN.search(content)
        return match.group(1).strip() if match else None
    
    @staticmethod
    def _extract_element_dsl(content: str) -> Optional[str]:
        """Extract element DSL from log content"""
        match = MuleLogParser.ELEMENT_DSL_PATTERN.search(content)
        return match.group(1).strip() if match else None
    
    @staticmethod
    def _extract_flow_stack(content: str) -> str:
        """Extract flow stack from log content"""
        match = MuleLogParser.FLOW_STACK_PATTERN.search(content)
        return match.group(1).strip() if match else ""


def format_analysis_report(analysis: LogAnalysis) -> str:
    """Format analysis results as a readable report"""
    report = []
    report.append("=" * 80)
    report.append("MULE LOG ANALYSIS REPORT")
    report.append("=" * 80)
    
    # File and Logger Info
    report.append("\n📋 LOG TYPE DETECTION")
    report.append(f"  File Type:   {analysis.file_type.value}")
    report.append(f"  Logger Type: {analysis.logger_type.value}")
    
    # Timestamps and IDs
    report.append("\n🕐 TIMESTAMPS AND IDENTIFIERS")
    report.append(f"  Timestamp:       {analysis.timestamp or 'N/A'}")
    report.append(f"  Correlation ID:  {analysis.correlation_id or 'N/A'}")
    report.append(f"  Channel ID:      {analysis.channel_id or 'N/A'}")
    report.append(f"  Service ID:      {analysis.service_id or 'N/A'}")
    report.append(f"  Transaction ID:  {analysis.transaction_id or 'N/A'}")
    report.append(f"  Resource:        {analysis.resource or 'N/A'}")
    
    # Error Information
    report.append("\n❌ ERROR INFORMATION")
    report.append(f"  Error Type:  {analysis.error_type or 'N/A'}")
    report.append(f"  Message:     {analysis.error_message or 'N/A'}")
    report.append(f"  Element:     {analysis.element or 'N/A'}")
    
    # Error Location
    if analysis.error_location:
        report.append("\n📍 ERROR LOCATION")
        loc = analysis.error_location
        report.append(f"  API Name:        {loc.api_name}")
        report.append(f"  File Name:       {loc.file_name}")
        report.append(f"  Line Number:     {loc.line_number}")
        report.append(f"  Processor:       {loc.processor_location}")
        report.append(f"  Flow Name:       {loc.flow_name}")
    
    # Flow Stack Analysis
    if analysis.flow_stack:
        report.append(f"\n🔄 FLOW STACK ANALYSIS ({len(analysis.flow_stack)} entries)")
        for i, entry in enumerate(analysis.flow_stack, 1):
            report.append(f"\n  Entry {i}:")
            report.append(f"    Flow Name:    {entry.flow_name}")
            report.append(f"    Processor:    {entry.processor_info}")
            report.append(f"    API Name:     {entry.api_name}")
            report.append(f"    File Name:    {entry.file_name}")
            report.append(f"    Line Number:  {entry.line_number}")
            if entry.description:
                report.append(f"    Description:  {entry.description}")
    
    report.append("\n" + "=" * 80)
    return "\n".join(report)


# Example usage and testing
if __name__ == "__main__":
    # Example log content
    example_log = """15 hours ago - 2026-03-06 02:38:46.707 GMT+5:30 - DefaultExceptionListener - 1293343f-9dcc-4f9d-a052-1b7b5af2f161
Replica 6lztv
$[MuleRuntime].uber.4614: ais-create-referral.switchOnErrorScheduler @4cbfa6e1 - 
********************************************************************************
Message               : There was a problem while trying to create referral in AIS
Element               : invoke-ais-create-referral/processors/2 @ msd-sep-accint-ais-emp-sapi-v1:impl/create-referral.xml:46 (Successful else raise EXT:CANT_CREATE_REFERRAL)
Element DSL           : <validation:is-true doc:name="Successful else raise EXT:CANT_CREATE_REFERRAL" doc:id="a980200c-c0ff-4d3f-8b26-9b23f6f20778" expression="#[vars.successful]" message="#[p('messages.createReferralBackendError')]">
<error-mapping targetType="EXT:CANT_CREATE_REFERRAL"></error-mapping>
</validation:is-true>
Error type            : EXT:CANT_CREATE_REFERRAL
FlowStack             : at invoke-ais-create-referral(invoke-ais-create-referral/processors/2 @ msd-sep-accint-ais-emp-sapi-v1:impl/create-referral.xml:46 (Successful else raise EXT:CANT_CREATE_REFERRAL))
at create-referral(create-referral/processors/2 @ msd-sep-accint-ais-emp-sapi-v1:impl/create-referral.xml:21 (Call invoke-ais-create-referral))
at post:\\clients\\(clientNumber)\\referrals:application\\json:apiConfig(post:\\clients\\(clientNumber)\\referrals:application\\json:apiConfig/processors/0 @ msd-sep-accint-ais-emp-sapi-v1:api.xml:44 (create-referral))
at api-main(api-main/processors/1 @ msd-sep-accint-ais-emp-sapi-v1:api.xml:14)

  (set debug level logging or '-Dmule.verbose.exceptions=true' for everything)
********************************************************************************
 channelId=SEP resource=POST:/api/clients/623175025/referrals serviceId=Salesforce transactionId=b-48df-ba08-42238fcabb8d
error"""
    
    # Analyze the log
    analysis = MuleLogParser.analyze(example_log)
    
    # Print the report
    print(format_analysis_report(analysis))
    
    # Print raw analysis as JSON-like format
    print("\n\n📊 RAW ANALYSIS DATA")
    print(f"File Type: {analysis.file_type.value}")
    print(f"Logger Type: {analysis.logger_type.value}")
    print(f"Error Type: {analysis.error_type}")
    if analysis.error_location:
        print(f"Error Location: API={analysis.error_location.api_name}, File={analysis.error_location.file_name}, Line={analysis.error_location.line_number}")
    else:
        print("Error Location: Not found")
    print(f"Flow Stack Entries: {len(analysis.flow_stack)}")
