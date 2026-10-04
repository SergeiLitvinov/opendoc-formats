"""Document format readers and writers built on the OpenDoc model."""

from importlib.metadata import version

from .api import AdapterRegistry, AdapterSpec, ImportOptions, ImportResult, default_registry, read_document

__version__ = version("opendoc-formats")
__all__ = ["AdapterRegistry", "AdapterSpec", "ImportOptions", "ImportResult", "default_registry", "read_document"]

from .export import ExporterRegistry, ExporterSpec, ExportOptions, default_exporter_registry, write_document

__all__ += ["ExporterRegistry", "ExporterSpec", "ExportOptions", "default_exporter_registry", "write_document"]
