"""Local URI parsing parity and absence of process-wide URL-cache retention."""

import random
from urllib.parse import urlsplit

import pytest

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.native.opc import _internal_uri_path, resolve_target


def assert_parser_parity(value):
    try:
        parsed = urlsplit(value)
    except ValueError:
        rejected = True
    else:
        rejected = bool(parsed.scheme or parsed.netloc or parsed.query)
    if rejected:
        with pytest.raises(ValueError):
            _internal_uri_path(value)
    else:
        assert _internal_uri_path(value) == parsed.path


@pytest.mark.parametrize('value', [
    '', ' ', ' media/own.png', 'media/own.png ', '#own?part', 'media/own.png#x?y',
    'media/own.png?', 'media/own.png?#x', '?', '?x', 'media/own.png?x#y',
    '//', '///own.bin', '////own.bin', '//example.invalid/own', '//[broken',
    'urn:own', 'HTTP://example.invalid/own', 'c:/own', '1c:own', 'own/path:tail',
    '../media/own.png', '%2e%2e/own', 'own%2Fpart', 'own%FF', 'own%25', '文字/own',
    'urn%3Aown', 'é:own', 'a+b.c:own', 'own/[literal]', '///[literal]',
])
def test_local_path_component_matches_previous_parser(value):
    assert_parser_parity(value)


def test_bounded_generated_references_match_previous_component_parser():
    random_source = random.Random(54321)
    alphabet = 'abcXYZ019:/?#[]@%. +-é文字'
    for _ in range(6000):
        value = ''.join(random_source.choice(alphabet) for _ in range(random_source.randrange(40)))
        assert_parser_parity(value)


def test_large_resolved_targets_do_not_enter_or_clear_shared_urlsplit_cache():
    if not hasattr(urlsplit, 'cache_info'):
        pytest.skip('This Python implementation does not cache urlsplit')
    marker = urlsplit('https://unrelated.invalid/keep-shared-state')
    before = urlsplit.cache_info()
    for number in range(3):
        value = 'media/'+'a'*64000+str(number)+'.bin#fragment'
        assert resolve_target('/word/document.xml', value) == '/word/'+value.partition('#')[0]
    assert urlsplit.cache_info() == before
    assert urlsplit('https://unrelated.invalid/keep-shared-state') == marker
    assert urlsplit.cache_info().hits == before.hits+1


@pytest.mark.parametrize('value', ['own\npath', '\town', '\x00own', 'own\x7f', 'https://example.invalid/own',
                                 '//example.invalid/own', '../%2e%2e/own', 'media%2Fown.png'])
def test_existing_unsafe_target_refusals_are_preserved(value):
    with pytest.raises(InvalidDocumentError):
        resolve_target('/word/document.xml', value)


@pytest.mark.parametrize('value,target', [('#fragment', '/word/document.xml'), ('?', '/word/document.xml'),
                                       ('///own.bin', '/own.bin'), ('media/own.png?', '/word/media/own.png'),
                                       ('../media/own.png#part', '/media/own.png')])
def test_owner_and_path_resolution_preserve_existing_finite_profile(value, target):
    assert resolve_target('/word/document.xml', value) == target
