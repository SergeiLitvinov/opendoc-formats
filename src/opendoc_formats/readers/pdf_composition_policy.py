"""Conservative native-dictionary audit for the finite RGB compositor profile."""

from __future__ import annotations

from typing import Any

from opendoc_model import ArtifactLimitError, DocumentLimits


def unsupported_policy(document: Any, limits: DocumentLimits) -> str | None:
    import pymupdf

    mupdf = pymupdf.mupdf
    pdf = mupdf.pdf_document_from_fz_document(document.this)
    used = 0
    blend_names = {'Normal', 'Compatible', 'Multiply', 'Screen', 'Overlay', 'Darken', 'Lighten', 'ColorDodge',
                   'ColorBurn', 'HardLight', 'SoftLight', 'Difference', 'Exclusion', 'Hue', 'Saturation', 'Color', 'Luminosity'}

    def visit(value: Any, depth: int) -> str | None:
        nonlocal used
        used += 1
        if used > limits.max_nodes or depth > limits.max_depth:
            raise ArtifactLimitError('PDF composition policy exceeds selected budget', path='$.pdf.composition-policy',
                                     quota='nodes' if used > limits.max_nodes else 'depth',
                                     maximum=limits.max_nodes if used > limits.max_nodes else limits.max_depth)
        if mupdf.pdf_is_indirect(value):
            return None  # Every indirect object is inspected once by xref below.
        if mupdf.pdf_is_dict(value):
            for index in range(mupdf.pdf_dict_len(value)):
                name = mupdf.pdf_to_name(mupdf.pdf_dict_get_key(value, index))
                child = mupdf.pdf_dict_get_val(value, index)
                if name == 'BM' and mupdf.pdf_is_name(child) and mupdf.pdf_to_name(child) not in blend_names:
                    return 'BM'
                if name == 'BM' and mupdf.pdf_is_array(child) and not any(
                    mupdf.pdf_to_name(mupdf.pdf_array_get(child, offset)) in blend_names
                    for offset in range(mupdf.pdf_array_len(child))
                ):
                    return 'BM'
                if ((name in ('AIS', 'OP', 'op') and mupdf.pdf_to_bool(child))
                        or (name == 'TK' and not mupdf.pdf_to_bool(child))
                        or name in ('DefaultRGB', 'DefaultGray', 'DefaultCMYK')):
                    return name
                problem = visit(child, depth+1)
                if problem:
                    return problem
        elif mupdf.pdf_is_array(value):
            for index in range(mupdf.pdf_array_len(value)):
                problem = visit(mupdf.pdf_array_get(value, index), depth+1)
                if problem:
                    return problem
        return None

    for xref in range(1, document.xref_length()):
        problem = visit(mupdf.pdf_load_object(pdf, xref), 1)
        if problem:
            return problem
    return None
