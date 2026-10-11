"""Document format readers and writers built on the OpenDoc model."""

from importlib.metadata import version

from .api import AdapterRegistry, AdapterSpec, ImportOptions, ImportResult, default_registry, read_document
from .text_profile import TextProfile

__version__ = version("opendoc-formats")
__all__ = ["AdapterRegistry", "AdapterSpec", "ImportOptions", "ImportResult", "TextProfile", "default_registry", "read_document"]

from .export import ExporterRegistry, ExporterSpec, ExportOptions, default_exporter_registry, write_document
from .support.object_mapping import get_object_mapping
from .support.pdf_mapping_history import read_pdf_origin_mapping

__all__ += [
    "ExporterRegistry", "ExporterSpec", "ExportOptions", "default_exporter_registry", "write_document", "get_object_mapping",
    "read_pdf_origin_mapping",
]
