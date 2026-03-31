#!/usr/bin/env python3
"""
Correlation ID Storage Manager
Manages CSV storage of correlation IDs (event IDs) from Anypoint Platform logs
Ensures no duplicates and combines API names for same correlation IDs
"""

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class CorrelationIDStorage:
    """Manages correlation ID storage in CSV format"""

    # CSV file path relative to application root
    CSV_FILENAME = "data/correlation_ids.csv"
    CSV_HEADERS = [
        "correlationId",
        "apiName",
        "incidentSysId",
        "incidentNumber",
        "incidentStatus",
        "createdAt",
        "rca",
    ]

    def __init__(self, csv_path: Optional[str] = None):
        """Initialize the storage manager

        Args:
            csv_path: Optional custom path for CSV file. Defaults to data/correlation_ids.csv in app root
        """
        if not csv_path:
            # Get project root (2 levels up from src/services/correlation_id_storage.py)
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            self.csv_path = os.path.join(project_root, self.CSV_FILENAME)
        else:
            self.csv_path = csv_path
        self._ensure_csv_exists()

    def _ensure_csv_exists(self) -> None:
        """Create CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.csv_path):
            self._write_csv({})

    def _read_csv(self) -> Dict[str, Dict]:
        """Read CSV file and return as dictionary {correlationId: data_dict}

        Returns:
            Dictionary mapping correlation IDs to their data
        """
        data = {}

        if not os.path.exists(self.csv_path):
            return data

        try:
            with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # Accept both old CSV (without rca column) and new CSV.
                # Only reject files whose core columns are completely wrong.
                existing_fields = list(reader.fieldnames or [])
                core_fields = [
                    "correlationId",
                    "apiName",
                    "incidentSysId",
                    "incidentNumber",
                    "incidentStatus",
                    "createdAt",
                ]
                if not all(f in existing_fields for f in core_fields):
                    # Headers are unrecognisable — reinitialise
                    return data

                for row in reader:
                    if row.get("correlationId"):
                        data[row["correlationId"]] = {
                            "apiName": row.get("apiName", "").strip(),
                            "incidentSysId": row.get("incidentSysId", "").strip(),
                            "incidentNumber": row.get("incidentNumber", "").strip(),
                            "incidentStatus": row.get("incidentStatus", "").strip(),
                            "createdAt": row.get("createdAt", "").strip(),
                            # rca may be absent in old CSV files — default to ""
                            "rca": row.get("rca", "").strip(),
                        }
        except Exception as e:
            print(f"Error reading CSV file: {e}")

        return data

    def _write_csv(self, data: Dict[str, Dict]) -> None:
        """Write dictionary data to CSV file

        Args:
            data: Dictionary mapping correlationId to data dict
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)

            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=self.CSV_HEADERS, quoting=csv.QUOTE_ALL
                )
                writer.writeheader()

                for correlation_id, row_data in sorted(data.items()):
                    writer.writerow(
                        {
                            "correlationId": correlation_id,
                            "apiName": row_data.get("apiName", ""),
                            "incidentSysId": row_data.get("incidentSysId", ""),
                            "incidentNumber": row_data.get("incidentNumber", ""),
                            "incidentStatus": row_data.get("incidentStatus", ""),
                            "createdAt": row_data.get("createdAt", ""),
                            "rca": row_data.get("rca", ""),
                        }
                    )
        except Exception as e:
            print(f"Error writing CSV file: {e}")

    def add_or_update(self, correlation_id: str, api_name: str) -> bool:
        """Add a new correlation ID or update existing one with new API name

        When same correlationId is found for a different API, combines API names
        with comma separator (e.g., "process api, system api")

        Args:
            correlation_id: The correlation ID from logs (event_id)
            api_name: The API name where this correlation ID was found

        Returns:
            True if data was modified, False if no change
        """
        if not correlation_id or not api_name:
            return False

        correlation_id = str(correlation_id).strip()
        api_name = str(api_name).strip()

        if not correlation_id or not api_name:
            return False

        data = self._read_csv()

        # Check if correlation ID already exists
        if correlation_id in data:
            existing_apis = data[correlation_id]["apiName"].split(", ")

            # Check if this API is already recorded
            if api_name in existing_apis:
                return False  # No change needed

            # Add new API to the list, maintaining comma-space separator
            data[correlation_id]["apiName"] = ", ".join(existing_apis + [api_name])
        else:
            # New correlation ID
            data[correlation_id] = {
                "apiName": api_name,
                "incidentSysId": "",
                "incidentNumber": "",
                "incidentStatus": "",
                "createdAt": "",
                "rca": "",
            }

        self._write_csv(data)
        return True

    def add_batch(self, correlation_api_pairs: List[Tuple[str, str]]) -> int:
        """Add multiple correlation ID and API name pairs in a single CSV read/write.

        Args:
            correlation_api_pairs: List of tuples (correlationId, apiName)

        Returns:
            Number of entries added or modified
        """
        if not correlation_api_pairs:
            return 0

        data = self._read_csv()
        modifications_count = 0

        for correlation_id, api_name in correlation_api_pairs:
            if not correlation_id or not api_name:
                continue
            correlation_id = str(correlation_id).strip()
            api_name = str(api_name).strip()
            if not correlation_id or not api_name:
                continue

            if correlation_id in data:
                existing_apis = data[correlation_id]["apiName"].split(", ")
                if api_name not in existing_apis:
                    data[correlation_id]["apiName"] = ", ".join(
                        existing_apis + [api_name]
                    )
                    modifications_count += 1
            else:
                data[correlation_id] = {
                    "apiName": api_name,
                    "incidentSysId": "",
                    "incidentNumber": "",
                    "incidentStatus": "",
                    "createdAt": "",
                    "rca": "",
                }
                modifications_count += 1

        if modifications_count:
            self._write_csv(data)

        return modifications_count

    def get_all(self) -> Dict[str, str]:
        """Get all stored correlation IDs and their API names

        Returns:
            Dictionary mapping correlationId to apiName(s)
        """
        return self._read_csv()

    def get(self, correlation_id: str) -> Optional[Dict]:
        """Get data for a specific correlation ID

        Args:
            correlation_id: The correlation ID to look up

        Returns:
            Data dict or None if not found
        """
        data = self._read_csv()
        return data.get(str(correlation_id).strip())

    def exists(self, correlation_id: str) -> bool:
        """Check if a correlation ID exists in storage

        Args:
            correlation_id: The correlation ID to check

        Returns:
            True if correlation ID exists, False otherwise
        """
        data = self._read_csv()
        return str(correlation_id).strip() in data

    def count(self) -> int:
        """Get total number of unique correlation IDs stored

        Returns:
            Count of correlation IDs
        """
        return len(self._read_csv())

    def get_csv_path(self) -> str:
        """Get the full path to the CSV file

        Returns:
            Absolute path to CSV file
        """
        return os.path.abspath(self.csv_path)

    def export_as_list(self) -> List[Dict]:
        """Export all correlation IDs as a list of dictionaries

        Returns:
            List of dictionaries with correlation ID data
        """
        data = self._read_csv()
        return [
            {
                "correlationId": cid,
                "apiName": row_data["apiName"],
                "incidentSysId": row_data.get("incidentSysId", ""),
                "incidentNumber": row_data.get("incidentNumber", ""),
                "incidentStatus": row_data.get("incidentStatus", ""),
                "createdAt": row_data.get("createdAt", ""),
                "rca": row_data.get("rca", ""),
            }
            for cid, row_data in sorted(data.items())
        ]

    def update_incident(
        self,
        correlation_id: str,
        sys_id: str,
        incident_number: str,
        status: str,
        rca: str = "",
    ) -> bool:
        """Update incident details for a correlation ID

        Args:
            correlation_id: The correlation ID
            sys_id: ServiceNow incident sys_id
            incident_number: ServiceNow incident number
            status: Incident status
            rca: Root Cause Analysis text (optional)

        Returns:
            True if updated, False otherwise
        """
        data = self._read_csv()
        correlation_id = str(correlation_id).strip()

        if correlation_id not in data:
            return False

        data[correlation_id]["incidentSysId"] = sys_id
        data[correlation_id]["incidentNumber"] = incident_number
        data[correlation_id]["incidentStatus"] = status
        data[correlation_id]["createdAt"] = datetime.now().isoformat()
        data[correlation_id]["rca"] = str(rca).strip() if rca else ""

        self._write_csv(data)
        return True

    def get_incident(self, correlation_id: str) -> Optional[Dict]:
        """Get incident details for a correlation ID

        Args:
            correlation_id: The correlation ID

        Returns:
            Incident details dict or None
        """
        data = self._read_csv()
        row = data.get(str(correlation_id).strip())

        if not row or not row.get("incidentSysId"):
            return None

        return {
            "incidentSysId": row.get("incidentSysId"),
            "incidentNumber": row.get("incidentNumber"),
            "incidentStatus": row.get("incidentStatus"),
            "createdAt": row.get("createdAt"),
            "rca": row.get("rca", ""),
        }

    def is_incident_created(self, correlation_id: str) -> bool:
        """Check if an incident has been created for this correlation ID

        Args:
            correlation_id: The correlation ID

        Returns:
            True if incident exists, False otherwise
        """
        data = self._read_csv()
        row = data.get(str(correlation_id).strip())
        return bool(row and row.get("incidentSysId"))


# Global instance
_storage_instance: Optional[CorrelationIDStorage] = None


def get_correlation_id_storage() -> CorrelationIDStorage:
    """Get or create the global correlation ID storage instance

    Returns:
        CorrelationIDStorage instance
    """
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = CorrelationIDStorage()
    return _storage_instance


def get_correlation_ids_from_local_file():
    """Extract correlation IDs from local file session data (error logs only)

    This function is used when users log in via local file upload.
    It extracts correlation IDs only from ERROR level logs in the uploaded file.

    Returns:
        List of correlation ID dictionaries in the same format as CSV storage
    """
    try:
        # Import here to avoid circular imports
        from flask import session

        local_logs = session.get("local_logs", [])
        correlation_ids = []
        seen_ids = set()  # Avoid duplicates

        for log in local_logs:
            # Only process error logs
            if log.get("level") == "ERROR":
                event_id = log.get("event_id")
                if event_id and event_id not in seen_ids:
                    seen_ids.add(event_id)

                    # Extract timestamp and create correlation ID entry
                    timestamp = log.get("timestamp", "")
                    api_name = session.get("local_app_name", "Local File")

                    correlation_ids.append(
                        {
                            "correlationId": event_id,
                            "apiName": api_name,
                            "incidentSysId": "",
                            "incidentNumber": "",
                            "incidentStatus": "",
                            "createdAt": timestamp,
                        }
                    )

        # Sort by timestamp (newest first) if available
        correlation_ids.sort(key=lambda x: x.get("createdAt", ""), reverse=True)

        return correlation_ids

    except Exception as err:
        print(f"Error extracting correlation IDs from local file: {err}")
        return []
