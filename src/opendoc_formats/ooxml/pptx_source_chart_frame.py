"""Prove classic chart frame ownership without rebuilding chart or workbook parts."""

from __future__ import annotations

import opendoc_model as od

from opendoc_formats.ooxml.pptx_source_geometry import A, GeometryBinding, P
from opendoc_formats.ooxml.pptx_source_xml import SourceRoots
from opendoc_formats.support.cancellation import cancellable_items

C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
CHART = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart'


def chart_frame(binding: GeometryBinding, document: od.DocumentModel, roots: SourceRoots) -> bool:
    if binding.shape.tag != P+'graphicFrame':
        return False
    data = binding.shape.find(A+'graphic/'+A+'graphicData')
    if data is None or data.get('uri') != C[1:-1] or len(data) != 1 or data[0].tag != C+'chart':
        return False
    identity = data[0].get(R+'id')
    graph = document.package
    if not identity or graph is None:
        return False
    edges = [edge for edge in cancellable_items(graph.relationships) if edge.source == binding.part and edge.id == identity]
    if len(edges) != 1 or edges[0].external or edges[0].relationship_type != CHART:
        return False
    part = graph.parts.get(edges[0].target)
    if part is None or part.media_type != 'application/vnd.openxmlformats-officedocument.drawingml.chart+xml':
        return False
    root = roots.load(graph, edges[0].target)
    charts = root.findall(C+'chart')
    return root.tag == C+'chartSpace' and len(charts) == 1 and len(charts[0].findall(C+'plotArea')) == 1
