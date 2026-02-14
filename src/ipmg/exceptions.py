"""
Custom exceptions for IPMG.

All application-specific errors should inherit from IPMGError.
"""


class IPMGError(Exception):
    """Base exception for all IPMG-related errors."""


class ConfigurationError(IPMGError):
    """Raised when configuration or CLI arguments are invalid."""


class DiscoveryError(IPMGError):
    """Raised when IP discovery fails."""


class PingError(IPMGError):
    """Raised when ping execution fails unexpectedly."""


class FileIOError(IPMGError):
    """Raised when input/output file operations fail."""


class ReportError(IPMGError):
    """Raised when report generation or export fails."""
