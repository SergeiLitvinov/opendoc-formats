"""Format-specific errors, independent of consumers."""


class FormatError(Exception):
    """Base error raised by format adapters."""


class ExtractError(FormatError):
    """Document extraction error."""


class ConvertError(FormatError):
    """Document export/conversion error."""
