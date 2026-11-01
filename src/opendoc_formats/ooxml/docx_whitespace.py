"""Word-observed visible w:t text; raw native snapshots keep their original strings."""

from __future__ import annotations

from typing import Any

from opendoc_formats.support.cancellation import checkpoint

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SPACE = '{http://www.w3.org/XML/1998/namespace}space'
TEXT_KEY = 'opendoc_formats.docx_text'
_TEXT_CHILDREN = {W+name for name in ('t', 'tab', 'ptab', 'br', 'cr', 'noBreakHyphen')}


def visible_text(node: Any) -> str:
    """Main-story root/direct modes follow native Word, not generic ancestor inheritance."""
    checkpoint()
    value = str(node.text or '')
    mode = node.get(SPACE)
    if mode is None:
        root = node.getroottree().getroot()
        if root.tag == W+'document':
            mode = root.get(SPACE)
        elif root.get(SPACE) is not None:
            return value  # unaccepted story-root scope; retain source projection
    if mode not in (None, 'default', 'preserve'):
        return value  # diagnostics reports the unsupported declaration
    value = value.replace('\r', ' ').replace('\n', ' ')
    return value if mode == 'preserve' else value.replace('\t', ' ').strip(' ')


def source_text_profile(element: Any, text: str) -> dict[str, Any] | None:
    """Capture the single-w:t distinction lost by the generic add_run(text) API."""
    nodes = []
    for child in element:
        checkpoint()
        if child.tag == W+'t':
            nodes.append(child)
        elif child.tag != W+'rPr':
            return None
    if len(nodes) != 1 or not text:
        return None
    node = nodes[0]
    edge = any(character.isspace() and character not in ' \t\r\n' for character in (text[0], text[-1]))
    if '\t' not in text and not edge:
        return None
    mode = node.get(SPACE)
    if mode is None:
        root = node.getroottree().getroot()
        if root.tag == W+'document':
            mode = root.get(SPACE)
        elif root.get(SPACE) is not None:
            return None
    if mode not in (None, 'default', 'preserve'):
        return None
    return {'format': TEXT_KEY, 'version': 1, 'element': 't', 'text': text, 'space': mode}


def write_text_profile(run: Any, text: str, properties: Any, report: Any, location: str) -> bool:
    """Return whether handled; an explicit text edit uses the generic writer path."""
    from docx.oxml import OxmlElement
    from opendoc_model import IssueSeverity

    checkpoint()
    state = properties.get(TEXT_KEY)
    if state is None:
        return False
    if (not isinstance(state, dict) or state.get('format') != TEXT_KEY or type(state.get('version')) is not int
            or state['version'] != 1 or state.get('element') != 't' or not isinstance(state.get('text'), str)
            or state.get('space') not in (None, 'default', 'preserve')):
        report.add(IssueSeverity.ERROR, 'docx.text-profile', 'Invalid or unsupported source text profile',
                   location+f'.properties[{TEXT_KEY}]')
        return True
    if text != state['text']:
        return False
    node = OxmlElement('w:t')
    node.text = text
    if state['space'] is not None:
        node.set(SPACE, state['space'])
    run._r.append(node)
    return True


def run_text(element: Any) -> str:
    """Project w:t; delegate other accepted control elements to their native text API."""
    parts = []
    for child in element:
        checkpoint()
        if child.tag in _TEXT_CHILDREN:
            parts.append(visible_text(child) if child.tag == W+'t' else str(child))
    return ''.join(parts)


def paragraph_text(paragraph: Any) -> str:
    """Same direct run/hyperlink scope as the legacy python-docx paragraph API."""
    parts = []
    for child in paragraph._p:
        checkpoint()
        if child.tag == W+'r':
            parts.append(run_text(child))
        elif child.tag == W+'hyperlink':
            for run in child:
                checkpoint()
                if run.tag == W+'r':
                    parts.append(run_text(run))
    return ''.join(parts)
