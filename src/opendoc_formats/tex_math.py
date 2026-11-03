"""Finite native TeX formula syntax and inert fallback metadata; no math conversion."""

import base64
import bisect
import json
import re

from opendoc_model import ArtifactLimitError, DocumentLimits, Formula, FormulaFormat

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.readers.tex_source import TexToken, tokenize_tex
from opendoc_formats.support.cancellation import checkpoint

ARGUMENTS = {**dict.fromkeys(('frac', 'dfrac', 'tfrac', 'binom', 'dbinom', 'tbinom', 'overset', 'underset'), 2),
             **dict.fromkeys(('sqrt', 'mathrm', 'mathbf', 'mathit', 'mathsf', 'mathtt', 'mathcal', 'mathbb', 'mathfrak',
                              'text', 'operatorname', 'overline', 'underline', 'hat', 'widehat', 'bar', 'vec', 'dot',
                              'ddot', 'tilde', 'widetilde', 'overbrace', 'underbrace', 'boxed', 'phantom'), 1)}
SYMBOLS = set(('alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi '
               'rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma '
               'Upsilon Phi Psi Omega sum prod coprod int iint iiint oint lim min max sup inf sin cos tan cot sec csc '
               'arcsin arccos arctan sinh cosh tanh log ln exp det gcd Pr dim ker hom arg deg '
               'infty partial nabla ell hbar imath jmath Re Im emptyset forall exists neg '
               'in notin ni subset supset subseteq supseteq cup cap setminus land lor '
               'le leq ge geq ne neq approx sim simeq equiv cong propto pm mp times div cdot circ ast star '
               'to mapsto rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow '
               'uparrow downarrow uparrow downarrow ldots cdots vdots ddots dots '
               'langle rangle lvert rvert lVert rVert vert Vert lbrace rbrace '
               'quad qquad limits nolimits displaystyle textstyle scriptstyle scriptscriptstyle').split())
ENVIRONMENTS = {'matrix', 'pmatrix', 'bmatrix', 'Bmatrix', 'vmatrix', 'Vmatrix', 'smallmatrix', 'cases', 'aligned', 'gathered'}
PREFIX = '% opendoc-math-v1:'


def validate_math(value: str) -> None:
    """Check a bounded allowlist, groups, environments and required braced arguments."""
    if (not value.strip() or len(value) > 65_536 or '\x7f' in value or '^^' in value
            or any(ord(c) < 32 and c not in '\n\r\t' for c in value)
            or re.search(r'% opendoc-(?:math|par)-v', value)):
        raise ValueError('Formula is outside the bounded native TeX profile')
    tokens = tokenize_tex(value, max_tokens=65_536)
    groups, pairs, scopes, left = [], {}, [], []

    def following(index: int) -> int:
        while index < len(tokens) and tokens[index].kind == 'space':
            index += 1
        return index

    for index, token in enumerate(tokens):
        checkpoint()
        if token.kind == 'space':
            if re.search(r'\n[ \t\r]*\n', token.value):
                raise ValueError('Paragraph breaks are outside the formula profile')
            continue
        if token.kind == 'text' and any(ord(c) > 126 for c in token.value):
            raise ValueError('Native formula profile requires ASCII TeX notation')
        if token.kind == 'symbol':
            if token.value in '$#~' or token.value == '&' and not scopes:
                raise ValueError('Math delimiter, parameter or alignment outside its scope')
            if token.value == '{':
                groups.append(index)
                if len(groups) > 64:
                    raise ValueError('Native formula exceeds 64 group levels')
            elif token.value == '}':
                if not groups:
                    raise ValueError('Unbalanced formula group')
                pairs[groups.pop()] = index
        if token.kind != 'command':
            continue
        name = token.value
        if name in {'begin', 'end'}:
            start = following(index+1)
            if (start+2 >= len(tokens) or tokens[start].value != '{' or tokens[start+2].value != '}'
                    or tokens[start+1].value not in ENVIRONMENTS):
                raise ValueError('Unsupported formula environment')
            environment = tokens[start+1].value
            if name == 'begin':
                scopes.append((environment, len(groups)))
                if len(scopes) > 16:
                    raise ValueError('Native formula exceeds 16 environment levels')
            elif not scopes or scopes.pop() != (environment, len(groups)):
                raise ValueError('Mismatched formula environment')
        elif name in {'left', 'right'}:
            delimiter = following(index+1)
            delimiter_value = (tokens[delimiter].value if delimiter < len(tokens) else '')
            if delimiter < len(tokens) and tokens[delimiter].kind == 'text':
                delimiter_value = delimiter_value[:1]
            if delimiter_value not in {
                    '.', '(', ')', '[', ']', '|', '{', '}', 'langle', 'rangle',
                    'lvert', 'rvert', 'lVert', 'rVert', 'vert', 'Vert'}:
                raise ValueError('Unsupported scalable formula delimiter')
            scope = (len(groups), len(scopes))
            if name == 'left':
                left.append(scope)
            elif not left or left.pop() != scope:
                raise ValueError('Mismatched scalable formula delimiter')
        elif name == '\\':
            if not scopes:
                raise ValueError('Formula row break has no environment')
        elif (name not in SYMBOLS and name not in ARGUMENTS
              and name not in {',', ';', ':', '!', ' ', '{', '}', '%', '_', '&', '$', '#'}):
            raise ValueError('Unsupported native formula command: '+name)
    if groups or scopes or left:
        raise ValueError('Unclosed native formula scope')
    # A trailing comment must not swallow the writer's closing math delimiter.
    if re.search(r'(?<!\\)%[^\n]*$', value):
        raise ValueError('Formula ends in an unterminated comment')
    for index, token in enumerate(tokens):
        checkpoint()
        if token.kind != 'command' or token.value not in ARGUMENTS:
            continue
        cursor = following(index+1)
        if token.value == 'sqrt' and cursor < len(tokens) and tokens[cursor].value == '[':
            while cursor < len(tokens) and tokens[cursor].value != ']':
                cursor += 1
            cursor = following(cursor+1)
        for _ in range(ARGUMENTS[token.value]):
            if cursor not in pairs:
                raise ValueError('Native formula command requires braced arguments: '+token.value)
            cursor = following(pairs[cursor]+1)


def formula_tex(formula: Formula, *, block: bool = False) -> str:
    allowed = {'source_span', 'latex_math_delimiter'} | ({'latex_par_after_list'} if block else set())
    if (formula.format is not FormulaFormat.LATEX or formula.box or formula.visual_surrogate
            or set(formula.properties)-allowed):
        raise ValueError('Formula carries unsupported format, geometry or declarations')
    if 'latex_par_after_list' in formula.properties and type(formula.properties['latex_par_after_list']) is not bool:
        raise ValueError('Invalid native formula paragraph boundary')
    validate_math(formula.value)
    if len(formula.fallback_text) > 65_536:
        raise ValueError('Formula fallback exceeds the native profile')
    data = {'fallback_text': formula.fallback_text}
    if block:
        data['placement'] = 'block'
    marker = base64.urlsafe_b64encode(json.dumps(data,
                                               ensure_ascii=True, separators=(',', ':')).encode()).decode()
    if len(marker) > 524_288:
        raise ValueError('Formula metadata exceeds the native profile')
    delimiters = {'$': ('$', '$', False), '$$': ('$$', '$$', True),
                  '\\(': ('\\(', '\\)', False), '\\[': ('\\[', '\\]', True)}
    selected = formula.properties.get('latex_math_delimiter', '\\[' if formula.display else '\\(')
    if not isinstance(selected, str) or selected not in delimiters:
        raise ValueError('Unknown native formula delimiter')
    opening, closing, display = delimiters[selected]
    if display != formula.display:
        opening, closing = ('\\[', '\\]') if formula.display else ('\\(', '\\)')
    return PREFIX+marker+'\n'+opening+formula.value+closing


def formula_markers(text: str, tokens: list[TexToken], *, limits: DocumentLimits | None) -> list[tuple[int, dict]]:
    result = []
    starts = [token.start for token in tokens]
    for match in re.finditer(r'% opendoc-math-v[^\r\n]*', text):
        previous = bisect.bisect_right(starts, match.start())-1
        if previous >= 0 and tokens[previous].end > match.start():
            continue  # Escaped percent is text, not a metadata comment.
        if not match.group().startswith(PREFIX):
            raise InvalidDocumentError('Unsupported native formula metadata version')
        try:
            encoded = match.group()[len(PREFIX):]
            if len(encoded) > 524_288:
                raise ValueError('Formula metadata exceeds the profile')
            decoded = base64.b64decode(encoded, altchars=b'-_', validate=True)
            if not decoded.lstrip().startswith(b'{'):
                raise ValueError('Formula metadata must be an object')
            pairs = json.loads(decoded, object_pairs_hook=list)
            if not isinstance(pairs, list) or any(not isinstance(p, tuple) or len(p) != 2 for p in pairs):
                raise ValueError('Invalid formula metadata object')
            data = dict(pairs)
            if (len(data) != len(pairs) or set(data)-{'fallback_text', 'placement'}
                    or not isinstance(data.get('fallback_text'), str) or len(data['fallback_text']) > 65_536
                    or 'placement' in data and data['placement'] != 'block'):
                raise ValueError('Invalid formula fallback metadata')
        except (ValueError, TypeError, IndexError, UnicodeError, RecursionError) as error:
            raise InvalidDocumentError('Invalid inert TeX formula metadata') from error
        result.append((match.end(), data))
        maximum = (limits or DocumentLimits()).max_nodes
        if len(result) > maximum:
            raise ArtifactLimitError('Formula metadata exceeds selected budget', path='$.latex.native-formulas',
                                     quota='nodes', maximum=maximum)
    return result
