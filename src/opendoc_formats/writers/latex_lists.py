"""Project SDK list membership into native TeX scopes and counters."""

from opendoc_model import Anchor, DocumentLimits, DocumentModel, Paragraph, get_anchor, get_list_item, iter_list_numbers

from opendoc_formats.support.cancellation import checkpoint
from opendoc_formats.tex_lists import paragraph_marker


def list_paragraphs(document: DocumentModel, paragraphs: list[tuple[Paragraph, str]], *, limits: DocumentLimits | None) -> str:
    numbers = iter(iter_list_numbers(document, limits=limits))
    existing = {a.id for paragraph, _ in paragraphs if (a := get_anchor(paragraph, limits=limits)) is not None}
    stack: list[dict] = []
    output = []

    def emit(text: str, paragraph_break: bool = False) -> None:
        output.append(('\n\n' if paragraph_break else '\n')+text)

    def close(depth: int) -> None:
        while len(stack) > depth:
            checkpoint()
            emit('\\end{'+stack.pop()['environment']+'}')

    for index, (paragraph, text) in enumerate(paragraphs):
        checkpoint()
        anchor = get_anchor(paragraph, limits=limits)
        item = get_list_item(paragraph, limits=limits)
        if item is None:
            close(0)
            emit(paragraph_marker(anchor, None)+text, paragraph.properties.get('latex_par_after_list', True))
            continue
        occurrence = next(numbers)
        if occurrence.location.node is not paragraph:
            raise ValueError('Native list traversal does not match the paragraph stream')
        if anchor is None:
            identifier = f'tex-native-node-{index}'
            while identifier in existing:
                checkpoint()
                identifier += '-new'
            anchor = Anchor(identifier)
            existing.add(identifier)
        key = (item.list_id, item.level, item.kind, item.start, item.parent_id)
        if item.continuation_of is not None:
            owner = next((i for i, frame in enumerate(stack) if frame['item'] == item.continuation_of), None)
            if owner is None or stack[owner]['key'] != key or not text:
                raise ValueError('Continuation is not inside its current native item, or is empty')
            close(owner+1)
            emit(paragraph_marker(anchor, item)+text, paragraph.properties.get('latex_par_after_list', True))
            continue
        parent = next((i for i, frame in enumerate(stack) if frame['item'] == item.parent_id), None)
        if item.parent_id is not None and parent is None:
            raise ValueError('Parent item is not active at this native TeX position')
        depth = parent+1 if parent is not None else 0
        close(depth+1)
        if len(stack) > depth and stack[-1]['key'] != key:
            close(depth)
        if len(stack) == depth:
            environment = 'enumerate' if item.kind == 'ordered' else 'itemize'
            if len(stack) >= 6:
                raise ValueError('Native TeX list exceeds the six-level total environment profile')
            if sum(frame['environment'] == environment for frame in stack) >= 4:
                raise ValueError('Native TeX list exceeds the four-level environment profile')
            stack.append({'environment': environment, 'key': key, 'item': None})
            emit('\\begin{'+environment+'}', paragraph.properties.get('latex_list_par_before', False))
        if item.kind == 'ordered':
            number = occurrence.number
            if number is None or not 1 <= number < 2**31:
                raise ValueError('Native TeX counter cannot represent this list number')
            counter = ('enumi', 'enumii', 'enumiii', 'enumiv')[
                sum(frame['environment'] == 'enumerate' for frame in stack)-1]
            emit('\\setcounter{'+counter+'}{'+str(number-1)+'}')
        stack[-1]['item'] = anchor.id
        emit(paragraph_marker(anchor, item)+'\\item '+text)
    close(0)
    return ''.join(output).lstrip('\n')
