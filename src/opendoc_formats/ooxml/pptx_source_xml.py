"""Shared bounded source-slide DOMs for native PPTX projections."""

from __future__ import annotations

from typing import Any

from lxml import etree
from opendoc_model import ArtifactLimitError, DocumentLimits, PackageGraph

from opendoc_formats.anatomy import AnatomyLimits, _Budget, _xml_nodes
from opendoc_formats.native.docx_package import parse_xml


class SourceRoots(dict[str, Any]):
    def __init__(self, limits: DocumentLimits | None = None) -> None:
        super().__init__()
        self.limits = limits or DocumentLimits()
        budget = self.limits
        self.budget = _Budget(AnatomyLimits(
            max_xml_nodes=budget.max_nodes, max_xml_depth=budget.max_depth,
            max_xml_characters=max(1, budget.max_bytes), max_xml_name_chars=max(1, budget.max_bytes),
        ))

    def load(self, graph: PackageGraph, part: str) -> Any:
        if part not in self:
            data = graph.parts[part].data
            if len(data) > self.limits.max_bytes:
                raise ArtifactLimitError('PPTX source XML exceeds byte budget', path=part,
                                         quota='bytes', maximum=self.limits.max_bytes)
            _xml_nodes(data, part, self.budget, count_markup=True)
            self[part] = parse_xml(data, etree)
        return self[part]
