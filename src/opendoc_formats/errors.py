"""Format-specific errors, independent of consumers."""


class FormatError(Exception):
    """Base error raised by format adapters."""


class ExtractError(FormatError):
    """Document extraction error."""


class ConvertError(FormatError):
    """Document export/conversion error."""


class NativeAccessError(FormatError):
    """Backend-independent error from native access; code is stable and machine-readable."""

    code = "native-access"


class BackendUnavailableError(NativeAccessError, ImportError):
    """An optional engine or executable is unavailable."""

    code = "backend-unavailable"


class InvalidDocumentError(NativeAccessError, ValueError):
    """The input or staged output is corrupt or has an unexpected format."""

    code = "invalid-document"


class EncryptedDocumentError(InvalidDocumentError):
    """Encrypted documents are not accepted by this API."""

    code = "encrypted-document"


class UnsupportedDocumentError(NativeAccessError, ValueError):
    """A feature requires an explicit policy or cannot safely be edited."""

    code = "unsupported-document"


class ResourceLimitError(NativeAccessError, ValueError):
    """An input, output or operation exceeds an explicit resource limit."""

    code = "resource-limit"


class OperationCancelledError(NativeAccessError):
    """A cooperative checkpoint observed cancellation."""

    code = "cancelled"


class DocumentClosedError(NativeAccessError):
    """The document context has already been closed."""

    code = "document-closed"


class PageIndexError(NativeAccessError, IndexError):
    """The zero-based PDF page index is outside the document."""

    code = "page-index"


class PatchConflictError(NativeAccessError, ValueError):
    """A patch is stale, overlaps another patch or is ambiguous."""

    code = "patch-conflict"


class OfficeTimeoutError(NativeAccessError, TimeoutError):
    """The managed office conversion exceeded its timeout."""

    code = "office-timeout"
