"""Dependency-free finite TeX text profile; other objects retain the DOCX route."""

from dataclasses import fields

from opendoc_model import (
    ANCHOR_PROPERTY,
    HEADING_PROPERTY,
    LIST_PROPERTY,
    DocumentLimits,
    DocumentModel,
    Formula,
    PageSettings,
    Paragraph,
    PreservationState,
    TextRun,
    TextStyle,
    get_heading,
    get_integration,
    get_list_item,
)

from opendoc_formats.support.cancellation import cancellable_items, checkpoint
from opendoc_formats.support.latex import PREAMBLE, escape_latex
from opendoc_formats.tex_math import formula_tex
from opendoc_formats.writers.latex_lists import list_paragraphs

HEADING_COMMANDS = {1: 'section', 2: 'subsection', 3: 'subsubsection', 4: 'paragraph', 5: 'subparagraph'}
HEADING_PROPERTIES = {HEADING_PROPERTY, 'latex_heading_level', 'latex_heading_command',
                      'latex_heading_starred', 'latex_heading_imported'}
LIST_PROPERTIES = {LIST_PROPERTY, ANCHOR_PROPERTY, 'list_kind', 'list_level', 'latex_list_id', 'latex_list_imported',
                   'latex_list_par_before', 'latex_par_after_list'}


def native_text(document: DocumentModel, *, limits: DocumentLimits | None) -> str | None:
    """Return TeX only when every visible object is within the text profile."""
    if len(document.sections) != 1 or document.footnotes:
        return None
    if any(key not in {f'Heading {level}' for level in HEADING_COMMANDS} or style != TextStyle()
           for key, style in document.styles.items()):
        return None
    integration = get_integration(document, limits=limits)
    if integration:
        if integration.scenes or integration.formula_trees:
            return None
        original = document.resources.get('latex-original-source')
        known_preamble = next((len(prefix) for prefix in (PREAMBLE, PREAMBLE.replace('\n', '\r\n'))
                               if original and original.data and original.data.startswith(prefix.encode('utf-8'))), 0)
        for record in integration.preservation:
            checkpoint()
            if record.state is PreservationState.SEMANTIC:
                continue
            if record.issue.code == 'latex.source':
                if record.issue.reason == 'inert-original-source':
                    continue  # Original bytes are an attachment, not a visible object.
                span = record.extra.get('source_span', {})
                if (known_preamble and type(span.get('start')) is int and type(span.get('end')) is int
                        and 0 <= span['start'] < span['end'] <= known_preamble):
                    continue  # This exact prefix is emitted again, never dropped.
            return None
    if any(key != 'latex-original-source' for key in document.resources):
        return None
    section = document.sections[0]
    if (section.page != PageSettings() or section.properties or section.headers or section.footers
            or section.first_page_headers or section.first_page_footers
            or section.even_page_headers or section.even_page_footers):
        return None
    body = []
    for block in section.blocks:
        checkpoint()
        if isinstance(block, Formula):
            proxy = Paragraph(properties={'latex_par_after_list': block.properties.get('latex_par_after_list', True)})
            body.append((proxy, formula_tex(block, block=True)))
            continue
        if (not isinstance(block, Paragraph) or block.alignment or block.box or block.visual_surrogate
                or set(block.properties)-({'source_span'} | HEADING_PROPERTIES | LIST_PROPERTIES)):
            return None
        item = get_list_item(block, limits=limits)
        if any(type(block.properties[key]) is not bool for key in ('latex_list_par_before', 'latex_par_after_list')
               if key in block.properties):
            return None
        if LIST_PROPERTY in block.properties and item is None:
            return None
        if item is None and any(key in block.properties for key in ('list_kind', 'list_level', 'latex_list_id')):
            if block.properties.get('latex_list_imported') is not True:
                return None  # Legacy evidence never creates or restores a role.
        if item is not None and set(block.properties[LIST_PROPERTY])-{
                'format', 'version', 'list_id', 'level', 'kind', 'start', 'restart', 'parent_id', 'continuation_of'}:
            return None
        heading = get_heading(block, limits=limits)
        if HEADING_PROPERTY in block.properties and heading is None:
            return None  # An opaque extension is not an explicit removal.
        if heading is not None and set(block.properties[HEADING_PROPERTY])-{'format', 'version', 'level'}:
            return None
        imported = block.properties.get('latex_heading_imported') is True
        if block.style_id and (block.style_id not in document.styles or not (heading or imported)):
            return None
        if heading is not None and (heading.level not in HEADING_COMMANDS
                or block.properties.get('latex_heading_command', HEADING_COMMANDS[heading.level]) not in HEADING_COMMANDS.values()
                or type(block.properties.get('latex_heading_starred', True)) is not bool):
            return None
        parts = []
        visible = []
        for run in block.content:
            checkpoint()
            if isinstance(run, Formula):
                if heading is not None and run.display:
                    return None  # Display math is not a heading argument.
                parts.append(formula_tex(run))
                visible.append('F')  # Formula source whitespace is not paragraph whitespace.
                continue
            if (not isinstance(run, TextRun) or run.link or run.visual_surrogate or set(run.properties)-{'source_span'}
                    or any(getattr(run.style, field.name) not in (None, {}) for field in fields(run.style)
                           if field.name not in {'bold', 'italic', 'underline'})):
                return None
            # Square brackets must remain text, never \[ display-math delimiters.
            replacements = {'[': '{[}', ']': '{]}', '^': r'\textasciicircum{}'}
            text = ''.join(replacements.get(char, escape_latex(char)) for char in cancellable_items(run.text))
            for enabled, command in [(run.style.underline, 'underline'), (run.style.italic, 'textit'),
                                     (run.style.bold, 'textbf')]:
                if enabled:
                    text = '\\'+command+'{'+text+'}'
            parts.append(text)
            visible.append(run.text)
        plain = ''.join(visible)
        # TeX collapses arbitrary whitespace; do not claim exact text preservation.
        empty_item = not plain and item is not None and item.continuation_of is None and not heading
        if (not plain and not empty_item) or plain != ' '.join(plain.split()) or any(ord(c) < 32 or ord(c) == 127 for c in plain):
            return None
        text = ''.join(parts)
        if heading is not None:
            star = '*' if block.properties.get('latex_heading_starred', True) else ''
            text = '\\'+HEADING_COMMANDS[heading.level]+star+'{'+text+'}'
        body.append((block, text))
    return PREAMBLE+'\\begin{document}\n'+list_paragraphs(document, body, limits=limits)+'\n\\end{document}\n'
