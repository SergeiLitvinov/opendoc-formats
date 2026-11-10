"""Bounded static CSS cascade; unsupported syntax is never silently accepted."""

from __future__ import annotations

import re
from collections.abc import Callable
from types import ModuleType
from typing import Any

import opendoc_model as od
from opendoc_model import Length, TextStyle

from opendoc_formats.native.common import backend
from opendoc_formats.readers.css_selectors import SELECTOR, SIMPLE_SELECTOR, Selector, matches_selector, parse_selector
from opendoc_formats.readers.html_fonts import SIMPLE_QUOTED_FAMILY, FontFaces, simple_font_face
from opendoc_formats.readers.svg_color import parse_static_css_color
from opendoc_formats.support.cancellation import check_cancelled

INHERITED = {"color", "font-family", "font-size", "font-weight", "font-style", "text-align", "white-space"}
INITIAL = {"color": "#000000", "font-size": "12pt", "font-weight": "normal", "font-style": "normal", "white-space": "normal"}
_CSS_SPACE = ' \t\r\n\f'
_WHITESPACE = re.compile(r'[ \t\r\n\f]*')
_RULE_BOUNDARY = re.compile(r'/\*|}')
_DECLARATION_BOUNDARY = re.compile(r'/\*|;')
_IMPORTANT = re.compile(r'![ \t\r\n\f]*important\Z', re.ASCII | re.IGNORECASE)
_WIDE_VALUES = {'inherit', 'initial', 'unset'}
_FONT_SIZE = re.compile(r'([0-9]+(?:\.[0-9]+)?)(pt|px|em|rem|%)')
_FAMILY_IDENT = r'[A-Za-z_][A-Za-z0-9_-]*'
_FAMILY_WORDS = re.compile(rf'{_FAMILY_IDENT}(?:[ \t]+{_FAMILY_IDENT})*')
_SIMPLE_PROPERTY = re.compile(r'-?[A-Za-z_][A-Za-z0-9_-]*')
_SIMPLE_IGNORED_VALUE = re.compile(r'[A-Za-z0-9_#.%-]+(?:[ \t\r\n\f]+[A-Za-z0-9_#.%-]+)*')
_IMPORT_STRING = r"""(?:"[^"\\\r\n\f]*"|'[^'\\\r\n\f]*')"""
_IMPORT_RULE = re.compile(
    rf"""@(?P<keyword>(?ai:import))[ \t\r\n\f]*"""
    rf"""(?:{_IMPORT_STRING}|(?ai:url)\([ \t\r\n\f]*(?:{_IMPORT_STRING}|[^()"'\\\x00-\x20\x7f]+)[ \t\r\n\f]*\))"""
    r"""(?:[ \t\r\n\f]+(?ai:all|screen|print))?[ \t\r\n\f]*;"""
)
_PRINT_BLOCK = re.compile(
    r'[ \t\r\n\f]*@(?:(?P<media>media)[ \t]+print[ \t\r\n\f]*'
    r'\{(?:[A-Za-z0-9_#.%,:; \t\r\n\f-]+\{[A-Za-z0-9_#.%,:; \t\r\n\f-]*\})*[ \t\r\n\f]*\}'
    r'|(?P<page>page)[ \t]+[A-Za-z_][A-Za-z0-9_-]*[ \t\r\n\f]*'
    r'\{[A-Za-z0-9_#.%,:; \t\r\n\f-]*\})'
)
ENUMS = {
    "font-weight": {"normal", "bold", "400", "600", "700", "800", "900"},
    "font-style": {"normal", "italic", "oblique"},
    "text-align": {"left", "right", "center", "justify"},
    "white-space": {"normal", "pre", "pre-wrap"},
    "text-decoration": {"none", "underline"},
    "vertical-align": {"baseline", "super", "sub"},
    "display": {"none"},
}
_Declaration = tuple[str, str, bool]
_Problems = list[tuple[str, str]]
_Rule = tuple[Selector, tuple[int, int, int], list[_Declaration], _Problems]
_SheetAction = str | tuple[str, str, str, str]
_COLOR_PROPERTIES = {'color', 'background-color'}
_SUPPORTED_PROPERTIES = ENUMS.keys() | _COLOR_PROPERTIES | {'font-size', 'font-family'}


def _simple_family_list(value: str) -> bool:
    for item in value.split(','):
        family = item.strip(_CSS_SPACE)
        if (quoted := SIMPLE_QUOTED_FAMILY.fullmatch(family)) is not None:
            if not quoted[2].strip():
                return False
        elif not _FAMILY_WORDS.fullmatch(family) or any(word.lower() in _WIDE_VALUES for word in family.split()):
            return False
    return True


class Cascade:
    def __init__(self, soup: Any, warn: Callable[..., None], *, fonts: FontFaces,
                 cancelled: Callable[[], bool] | None = None) -> None:
        self.warn = warn
        self.cache: dict[int, dict[str, str]] = {}
        self.rules: list[_Rule] = []
        self.cancelled = cancelled
        self.fonts = fonts
        self.used_backend = False
        check_cancelled(cancelled, 'HTML CSS')
        for sheet in soup.find_all("style"):
            if sheet.get("media", "all") not in {"all", "screen", ""}:
                warn("html-css", "Условная таблица стилей не применена.")
                continue
            raw = sheet.get_text()
            simple = self._simple_stylesheet(raw)
            if simple is not None:
                rules, actions = simple
                for action in actions:
                    if isinstance(action, str):
                        warn("html-css", "Правило CSS вне первого среза: " + action)
                    else:
                        fonts.read_simple(action, sheet)
                self.rules.extend(rules)
                continue
            tinycss2 = self._backend()
            for rule in tinycss2.parse_stylesheet(raw, skip_comments=True, skip_whitespace=True):
                check_cancelled(cancelled, 'HTML CSS rule')
                if rule.type == 'at-rule' and rule.lower_at_keyword == 'font-face':
                    fonts.read(rule, sheet)
                    continue
                if rule.type != "qualified-rule":
                    warn("html-css", "Правило CSS вне первого среза: " + getattr(rule, "at_keyword", rule.type))
                    continue
                problems = []
                declarations = self.declarations(rule.content, lambda feature, message: problems.append((feature, message)))
                for selector in tinycss2.serialize(rule.prelude).split(","):
                    selector = selector.strip()
                    rule = self._rule(selector, declarations, problems, compound=SELECTOR)
                    if rule is None:
                        warn("html-css", f"Селектор не применён: {selector}")
                    else:
                        self.rules.append(rule)

    @staticmethod
    def _rule(selector: str, declarations: list[_Declaration], problems: _Problems, *,
              compound: re.Pattern[str] = SIMPLE_SELECTOR) -> _Rule | None:
        parsed = parse_selector(selector, compound=compound)
        if parsed is None:
            return None
        normalized, specificity = parsed
        return normalized, specificity, declarations, problems

    def _simple_stylesheet(self, raw: str) -> tuple[list[_Rule], list[_SheetAction]] | None:
        rules: list[_Rule] = []
        actions: list[_SheetAction] = []
        start = ordinary_size = 0
        while start < len(raw):
            check_cancelled(self.cancelled, 'HTML CSS rule')
            begin = self._skip_trivia(raw, start)
            if begin is None:
                return None
            ordinary_size += begin - start
            if ordinary_size > 16384:
                return None
            start = begin
            if start == len(raw):
                break
            limit = start + 16384 - ordinary_size
            if (external := _IMPORT_RULE.match(raw, start, limit)) is not None:
                actions.append(external['keyword'])
                ordinary_size += external.end() - start
                start = external.end()
                continue
            if (printing := _PRINT_BLOCK.match(raw, start, limit)) is not None:
                actions.append('media' if printing['media'] else 'page')
                ordinary_size += printing.end() - start
                start = printing.end()
                continue
            end = self._delimiter(raw, start, _RULE_BOUNDARY)
            if end < 0:
                return None
            block = raw[start:end]
            start = end + 1
            if (face := simple_font_face(block)) is not None:
                actions.append(face)
                continue
            ordinary_size += len(block) + 1
            if ordinary_size > 16384:
                return None
            prelude, sep, declarations = block.partition('{')
            if not sep:
                return None
            simple = self._simple_inline(declarations)
            if simple is None:
                return None
            for part in prelude.split(','):
                check_cancelled(self.cancelled, 'HTML CSS selector')
                selector = part.strip(_CSS_SPACE)
                rule = self._rule(selector, *simple)
                if rule is None:
                    return None
                rules.append(rule)
        return rules, actions

    def _skip_trivia(self, raw: str, start: int) -> int | None:
        """Skip complete comments only at rule or declaration boundaries."""
        while True:
            whitespace = _WHITESPACE.match(raw, start)
            assert whitespace is not None
            start = whitespace.end()
            if not raw.startswith('/*', start):
                return start
            check_cancelled(self.cancelled, 'HTML CSS comment')
            end = raw.find('*/', start+2)
            if end < 0:
                return None
            start = end+2

    def _delimiter(self, raw: str, start: int, boundary: re.Pattern[str]) -> int:
        while (match := boundary.search(raw, start)) is not None:
            if match[0] != '/*':
                return match.start()
            check_cancelled(self.cancelled, 'HTML CSS comment')
            end = raw.find('*/', match.end())
            if end < 0:
                break
            start = end+2
        return -1

    def _backend(self, module: str = 'tinycss2') -> ModuleType:
        loaded = backend(module, 'html')
        self.used_backend = True
        return loaded

    def _simple_inline(self, raw: str) -> tuple[list[_Declaration], _Problems] | None:
        """Parse simple declarations and report properties the model projection skips."""
        if len(raw) > 4096:
            return None
        result = []
        problems = []
        start = 0
        while start < len(raw):
            check_cancelled(self.cancelled, 'HTML inline declaration')
            begin = self._skip_trivia(raw, start)
            if begin is None:
                return None
            if begin == len(raw):
                break
            end = self._delimiter(raw, begin, _DECLARATION_BOUNDARY)
            end = len(raw) if end < 0 else end
            part = raw[begin:end]
            start = end + 1
            if not part:
                continue
            name, sep, value = part.partition(':')
            name = name.strip(_CSS_SPACE)
            if not sep or not _SIMPLE_PROPERTY.fullmatch(name):
                return None
            value_start = self._skip_trivia(value, 0)
            if value_start is None:
                return None
            value = value[value_start:].rstrip(_CSS_SPACE)
            name = name.lower()
            if name != 'font-family' and not value.isascii():
                return None
            important = _IMPORTANT.search(value)
            if important:
                value = value[:important.start()].rstrip(_CSS_SPACE)
            if name not in _SUPPORTED_PROPERTIES and _SIMPLE_IGNORED_VALUE.fullmatch(value):
                problems.append(('html-css', f'Свойство не поддержано: {name}'))
                continue
            if name == 'color' and value.lower() == 'currentcolor':
                value = 'inherit'
            elif value.lower() in _WIDE_VALUES and name in _SUPPORTED_PROPERTIES:
                value = value.lower()
            elif value.lower() in ENUMS.get(name, ()):
                value = value.lower()
            elif name in ENUMS and _SIMPLE_IGNORED_VALUE.fullmatch(value):
                problems.append(('html-css', f'Значение не поддержано: {name}: {value.lower()}'))
                continue
            elif not ((name in _COLOR_PROPERTIES
                       and (value.lower() == 'currentcolor' or parse_static_css_color(value) is not None))
                      or (name == 'font-size' and _FONT_SIZE.fullmatch(value))
                      or (name == 'font-family' and _simple_family_list(value))):
                return None
            result.append((name, value, important is not None))
        return result, problems

    def declarations(self, raw: Any, warn: Callable[..., None] | None = None) -> list[tuple[str, str, bool]]:
        if not raw:
            return []
        warn = warn or self.warn
        if isinstance(raw, str) and (simple := self._simple_inline(raw)) is not None:
            declarations, problems = simple
            for feature, message in problems:
                warn(feature, message)
            return declarations
        tinycss2 = self._backend()

        result = []
        for item in tinycss2.parse_blocks_contents(raw, skip_comments=True, skip_whitespace=True):
            check_cancelled(self.cancelled, 'HTML CSS declaration')
            if item.type != "declaration":
                warn("html-css", "Некорректное или вложенное объявление CSS пропущено.")
                continue
            name, value = item.lower_name, tinycss2.serialize(item.value).strip()
            if name == "color":
                tokens = [token for token in item.value if token.type not in {"whitespace", "comment"}]
                if len(tokens) == 1 and tokens[0].type == "ident" and tokens[0].lower_value == "currentcolor":
                    value = "inherit"
            if name in ENUMS or value.lower() in _WIDE_VALUES:
                value = value.lower()
            if name not in _SUPPORTED_PROPERTIES:
                warn("html-css", f"Свойство не поддержано: {name}")
                continue
            if name == "font-family" and re.search(r"[;{}()<>\\]", value):
                warn("html-css", "Сложное значение font-family не поддержано.")
                continue
            if name in ENUMS and value.lower() not in ENUMS[name] | _WIDE_VALUES:
                warn("html-css", f"Значение не поддержано: {name}: {value}")
                continue
            result.append((name, value, item.important))
        return result

    def style(self, node: Any) -> dict[str, str]:
        check_cancelled(self.cancelled, 'HTML CSS cascade')
        if id(node) in self.cache:
            return self.cache[id(node)]
        parent = self.style(node.parent) if getattr(node.parent, "name", None) else INITIAL
        style = {key: value for key, value in parent.items() if key in INHERITED}
        semantic = {
            "b": {"font-weight": "bold"},
            "strong": {"font-weight": "bold"},
            "th": {"font-weight": "bold"},
            "i": {"font-style": "italic"},
            "em": {"font-style": "italic"},
            "u": {"text-decoration": "underline"},
            "sup": {"vertical-align": "super"},
            "sub": {"vertical-align": "sub"},
            "pre": {"white-space": "pre"},
        }
        style.update(semantic.get(node.name, {}))
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            style.update({"font-weight": "bold", "font-size": f"{(24, 18, 14, 12, 10, 9)[int(node.name[1]) - 1]}pt"})
        winners: dict[str, tuple[tuple[int, ...], str]] = {}
        for order, (selector, specificity, declarations, problems) in enumerate(self.rules):
            check_cancelled(self.cancelled, 'HTML CSS selector')
            if self.matches(node, selector):
                self._apply(winners, declarations, (0, *specificity, order))
                for feature, message in problems:
                    self.warn(feature, message, node)
        declarations = self.declarations(node.get("style", ""), lambda feature, message: self.warn(feature, message, node))
        self._apply(winners, declarations, (1, 0, 0, 0, len(self.rules)))
        for name, (_, value) in winners.items():
            if name == "background-color" and node.name != "span":
                self.warn("html-css", "Фон вне текстового span не поддержан.", node)
                continue
            if value == "inherit" or (value == "unset" and name in INHERITED):
                value = parent.get(name, INITIAL.get(name, ""))
            elif value in {"initial", "unset"}:
                value = INITIAL.get(name, "")
            style[name] = value
        size = style.get("font-size", "12pt")
        match = _FONT_SIZE.fullmatch(size)
        if match:
            number, unit = float(match[1]), match[2]
            parent_size = float(parent.get("font-size", "12pt")[:-2])
            root_size = (
                float(self.style(node.find_parent("html")).get("font-size", "12pt")[:-2]) if node.find_parent("html") else 12
            )
            points = number * {"pt": 1, "px": 0.75, "em": parent_size, "rem": root_size, "%": parent_size / 100}[unit]
            style["font-size"] = f"{points:g}pt"
        else:
            self.warn("html-css", f"Размер шрифта не поддержан: {size}", node)
            style["font-size"] = parent.get("font-size", "12pt")
        self.cache[id(node)] = style
        if parent.get("text-decoration") == "underline":
            style["text-decoration"] = "underline"
        return style

    @staticmethod
    def _apply(
        winners: dict[str, tuple[tuple[int, ...], str]], declarations: list[tuple[str, str, bool]], specificity: tuple[int, ...]
    ) -> None:
        for index, (name, value, important) in enumerate(declarations):
            rank = (int(important), *specificity, index)
            if name not in winners or rank >= winners[name][0]:
                winners[name] = rank, value

    def matches(self, node: Any, selector: Selector) -> bool:
        return matches_selector(node, selector, self.cancelled)

    def text_style(self, css: dict[str, str], node: Any = None) -> od.TextStyle:
        def color(name: str) -> od.ColorValue | None:
            value = css.get(name)
            if not value:
                return None
            if name == "background-color" and value.lower() == "currentcolor":
                value = css.get("color", "#000000")
            if (native := parse_static_css_color(value)) is not None:
                return native
            parse_color = self._backend('tinycss2.color3').parse_color
            parsed = parse_color(value)
            if parsed == "currentColor":
                parsed = parse_color(css.get("color", "black"))
            if parsed is None or isinstance(parsed, str):
                self.warn("html-css", f"Цвет не поддержан: {name}: {value}", node)
                return None
            return od.ColorValue(space=od.ColorSpace.SRGB, components=(parsed.red, parsed.green, parsed.blue), alpha=parsed.alpha)

        style = TextStyle(
            font_family=css.get("font-family", "").split(",")[0].strip(" '\"") or None,
            font_size=Length(float(css["font-size"][:-2])),
            bold=css.get("font-weight") in {"bold", "600", "700", "800", "900"},
            italic=css.get("font-style") in {"italic", "oblique"},
            underline=css.get("text-decoration") == "underline",
            superscript=css.get("vertical-align") == "super",
            subscript=css.get("vertical-align") == "sub",
            color=color("color"),
            background=color("background-color"),
        )
        self.fonts.bind(style, node)
        return style
