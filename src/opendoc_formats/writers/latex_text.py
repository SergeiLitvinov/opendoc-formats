"""Dependency-free finite TeX text profile; other objects retain the DOCX route."""

from dataclasses import fields

from opendoc_model import (
    HEADING_PROPERTY,
    DocumentLimits,
    DocumentModel,
    PageSettings,
    Paragraph,
    PreservationState,
    TextRun,
    TextStyle,
    get_heading,
    get_integration,
)

from opendoc_formats.support.latex import PREAMBLE, escape_latex

HEADING_COMMANDS = {1: 'section', 2: 'subsection', 3: 'subsubsection', 4: 'paragraph', 5: 'subparagraph'}
HEADING_PROPERTIES = {HEADING_PROPERTY, 'latex_heading_level', 'latex_heading_command',
                      'latex_heading_starred', 'latex_heading_imported'}


def native_text(document: DocumentModel, *, limits: DocumentLimits | None) -> str | None:
    """Return TeX only when every visible object is within the text profile."""
    if len(document.sections) != 1 or document.footnotes:
        return None
    if any(key not in {f'Heading {level}' for level in HEADING_COMMANDS} or style != TextStyle()
           for key, style in document.styles.items()):
        return None
    integration = get_integration(document, limits=limits)
    if integration:
        if integration.scenes:
            return None
        original = document.resources.get('latex-original-source')
        known_preamble = next((len(prefix) for prefix in (PREAMBLE, PREAMBLE.replace('\n', '\r\n'))
                               if original and original.data and original.data.startswith(prefix.encode('utf-8'))), 0)
        for record in integration.preservation:
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
        if (not isinstance(block, Paragraph) or block.alignment or block.box or block.visual_surrogate
                or set(block.properties)-({'source_span'} | HEADING_PROPERTIES)):
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
        for run in block.content:
            if (not isinstance(run, TextRun) or run.link or run.visual_surrogate or set(run.properties)-{'source_span'}
                    or any(getattr(run.style, field.name) not in (None, {}) for field in fields(run.style)
                           if field.name not in {'bold', 'italic', 'underline'})):
                return None
            # Square brackets must remain text, never \[ display-math delimiters.
            replacements = {'[': '{[}', ']': '{]}', '^': r'\textasciicircum{}'}
            text = ''.join(replacements.get(char, escape_latex(char)) for char in run.text)
            for enabled, command in [(run.style.underline, 'underline'), (run.style.italic, 'textit'),
                                     (run.style.bold, 'textbf')]:
                if enabled:
                    text = '\\'+command+'{'+text+'}'
            parts.append(text)
        plain = block.plain_text
        # TeX collapses arbitrary whitespace; do not claim exact text preservation.
        if not plain or plain != ' '.join(plain.split()) or any(ord(char) < 32 or ord(char) == 127 for char in plain):
            return None
        text = ''.join(parts)
        if heading is not None:
            star = '*' if block.properties.get('latex_heading_starred', True) else ''
            text = '\\'+HEADING_COMMANDS[heading.level]+star+'{'+text+'}'
        body.append(text)
    return PREAMBLE+'\\begin{document}\n'+'\n\n'.join(body)+'\n\\end{document}\n'
