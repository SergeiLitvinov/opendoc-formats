"""Verify the pinned Model wheel through its public API in an isolated environment."""

import argparse
import hashlib
import json
import runpy
from importlib.metadata import distributions, version
from pathlib import Path
from zipfile import ZipFile

import opendoc_model as od


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert version('opendoc-model') == '0.1.0'
    assert hashlib.sha256(args.wheel.read_bytes()).hexdigest() == args.sha256
    assert sorted(item.metadata['Name'] for item in distributions()) == ['opendoc-model']
    installed = Path(od.__file__).parent.parent
    assert 'site-packages' in installed.parts
    files = {}
    with ZipFile(args.wheel) as archive:
        for name in archive.namelist():
            if name.startswith('opendoc_model/') and (name.endswith('.py') or name.endswith('/py.typed')):
                digest = hashlib.sha256(archive.read(name)).hexdigest()
                assert hashlib.sha256((installed/name).read_bytes()).hexdigest() == digest
                files[name] = digest
    public = ('ImageSourceRect', 'get_image_source_rect', 'set_image_source_rect',
              'PageSettingsState', 'get_page_settings_state', 'set_page_settings_state',
              'BlockGroup', 'OutlineLabel', 'BackgroundPaint', 'GradientPaint')
    assert all(hasattr(od, name) and name in od.__all__ for name in public)
    checks = {}
    for filename, function in (
        ('page_model_consumer.py', 'api_checks'),
        ('block_group_consumer.py', 'checks'),
        ('outline_label_consumer.py', 'checks'),
        ('background_gradient_consumer.py', 'checks'),
    ):
        namespace = runpy.run_path(str(Path(__file__).with_name(filename)), run_name='formats_model_consumer')
        checks[filename] = namespace[function]()
    image = od.Image('own', box=od.Box(0, 0, 10, 10))
    document = od.DocumentModel(sections=[od.Section(blocks=[od.Paragraph([image])])], resources={
        'own': od.Resource('own', od.ResourceKind.VECTOR_IMAGE, 'image/svg+xml',
                           data=b'<svg xmlns="http://www.w3.org/2000/svg"/>')})
    rectangle = od.ImageSourceRect(-.25, .1, 1.5, .9, extra={'own': [1, 2]})
    od.set_image_source_rect(image, rectangle)
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
        image = document.sections[0].blocks[0].content[0]
        assert od.get_image_source_rect(image) == rectangle and image.crop is None
        assert image.box == od.Box(0, 0, 10, 10)
    checks['image_source_rect'] = 'signed/outside coordinates and extra survive two JSON cycles without changing Box/crop'
    args.output.write_text(json.dumps({
        'sdk_version': version('opendoc-model'), 'wheel_sha256': args.sha256,
        'source_files': files, 'checks': checks,
        'scope': 'Public Model API and transport only; native format projection remains subject to its own gates.',
    }, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Pinned Model public API, source integrity, JSON, quotas and atomic refusals passed')


if __name__ == '__main__':
    main()
