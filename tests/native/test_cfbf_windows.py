"""Independent Windows IStorage reads of our own compound file originals; no object activation."""

import ctypes
import sys

import pytest

from opendoc_formats.anatomy import inspect_binary
from tests.binary_fixtures import own_cfbf

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows IStorage acceptance')


def native_streams(path, expected):
    ole = ctypes.WinDLL('ole32')
    pointer = ctypes.c_void_p
    integer = ctypes.c_uint32
    ole.CoInitializeEx.argtypes = [pointer, integer]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.StgOpenStorage.argtypes = [ctypes.c_wchar_p, pointer, integer, pointer, integer, ctypes.POINTER(pointer)]
    ole.StgOpenStorage.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None

    def checked(value):
        assert value >= 0, f'Native compound storage failed: HRESULT {value & 0xffffffff:08x}'

    def method(instance, slot, *arguments):
        table = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(pointer))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, pointer, *arguments)(table[slot])

    storage = pointer()
    checked(ole.CoInitializeEx(None, 2))
    try:
        checked(ole.StgOpenStorage(str(path), None, 0x10, None, 0, ctypes.byref(storage)))  # read-only, exclusive
        try:
            for name, content in expected.items():
                stream = pointer()
                opened = method(storage, 4, ctypes.c_wchar_p, pointer, integer, integer, ctypes.POINTER(pointer))
                checked(opened(storage, name, None, 0x10, 0, ctypes.byref(stream)))
                try:
                    buffer, read = ctypes.create_string_buffer(len(content)+1), integer()
                    checked(method(stream, 3, pointer, integer, ctypes.POINTER(integer))(
                        stream, buffer, len(buffer), ctypes.byref(read)))
                    assert bytes(buffer[:read.value]) == content
                finally:
                    method(stream, 2)(stream)
        finally:
            method(storage, 2)(storage)
    finally:
        ole.CoUninitialize()


@pytest.mark.parametrize('version,high_size_bits', [(3, 0), (4, 0), (3, 0x12345678)])
def test_native_storage_confirms_original_fat_and_minifat_stream_bytes(tmp_path, version, high_size_bits):
    source, small, big = own_cfbf(version=version, high_size_bits=high_size_bits)
    path = tmp_path/'own.cfb'
    path.write_bytes(source)
    native_streams(path, {'Small': small, 'Large': big})
    inspected = inspect_binary(path, capture=True)
    assert next(item for item in inspected.items if item.locator == 'cfbf:directory=1').payload == small
    assert next(item for item in inspected.items if item.locator == 'cfbf:directory=2').payload == big
    assert path.read_bytes() == source


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('root_color', [0, 1])
def test_native_storage_reads_root_color_variants_with_unequal_black_heights(tmp_path, version, root_color):
    original, small, big = own_cfbf(version=version)
    source = bytearray(original)
    base = 1024 if version == 3 else 8192
    source[base+67] = root_color
    source[base+2*128+67] = 1  # Large is black; Folder remains red: unequal black heights.
    source = bytes(source)
    path = tmp_path/'own-colors.cfb'
    path.write_bytes(source)
    native_streams(path, {'Small': small, 'Large': big})
    details = dict(inspect_binary(path).details)
    assert details['directory_colors_assessed'] and details['directory_color_constraints_valid']
    assert path.read_bytes() == source


@pytest.mark.parametrize('version', [3, 4])
@pytest.mark.parametrize('names', [('Z', 'A', 'AA'), ('ÿ', 'Ā', 'ZZ'), ('ß', 'Z', 'SS'), ('ᾀ', 'Ω', 'ZZ'), ('𐐨', 'Z', 'AAA')])
def test_native_storage_finds_names_in_independently_authored_utf16_order(tmp_path, version, names):
    from tests.native.test_cfbf_names import original

    source = original(names, version=version)
    _, small, big = own_cfbf(version=version)
    path = tmp_path/'own-names.cfb'
    path.write_bytes(source)
    native_streams(path, {names[0]: small, names[1]: big})
    details = dict(inspect_binary(path).details)
    assert details['directory_name_order_assessed'] and details['directory_name_order_valid']
    assert path.read_bytes() == source
