"""Build an isolated, explicitly labelled Model layout consumer preview; never publish or change the project pin."""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(model_wheel: Path, expected_sha256: str, uv: str) -> Path:
    model_wheel = model_wheel.resolve(strict=True)
    digest = hashlib.sha256(model_wheel.read_bytes()).hexdigest()
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256) or digest != expected_sha256:
        raise ValueError('Model wheel SHA-256 does not match the explicitly selected artifact')
    with zipfile.ZipFile(model_wheel) as archive:
        metadata_names = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
        if len(metadata_names) != 1:
            raise ValueError('Expected one Model wheel distribution')
        metadata = email.message_from_bytes(archive.read(metadata_names[0]))
        if (str(metadata['Name']).lower().replace('_', '-') != 'opendoc-model'
                or 'opendoc_model/text_layout.py' not in archive.namelist()):
            raise ValueError('Selected artifact is not an OpenDoc Model text layout preview')
        model_version = str(metadata['Version'])
        license_names = [name for name in archive.namelist() if '/licenses/' in name and name.endswith('/LICENSE')]
        license_hashes = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in license_names}
    config_text = (ROOT/'pyproject.toml').read_text(encoding='utf-8')
    config = tomllib.loads(config_text)
    hashes = {str(path.relative_to(ROOT/'src')).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((ROOT/'src').rglob('*.py'))}
    code_digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    version = f'{config["project"]["version"]}+layoutpreview.{digest[:8]}.{code_digest[:8]}'
    parent = ROOT/'.opendoc-formats'
    parent.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='text-layout-', dir=parent))
    print(f'Preparing unpublished consumer artifacts: {output}', flush=True)
    source, dist, installed = output/'source', output/'dist', output/'installed'
    source.mkdir()
    shutil.copytree(ROOT/'src', source/'src', ignore=shutil.ignore_patterns('__pycache__', '*.egg-info'))
    shutil.copytree(ROOT/'docs', source/'docs')
    for name in ('README.md', 'MANIFEST.in'):
        shutil.copy2(ROOT/name, source/name)
    dependencies = config['project']['dependencies']
    if len(dependencies) != 1 or not dependencies[0].startswith('opendoc-model=='):
        raise ValueError('Review the consumer preview dependency override for the current project')
    preview = config_text.replace(f'version = "{config["project"]["version"]}"', f'version = "{version}"', 1)
    preview = preview.replace(json.dumps(dependencies[0]), json.dumps('opendoc-model=='+model_version))
    preview = re.sub(r'^opendoc-model = \{.*\}$', 'opendoc-model = { path = '+json.dumps(model_wheel.as_posix())+' }',
                     preview, flags=re.MULTILINE)
    parsed = tomllib.loads(preview)
    if parsed['project']['version'] != version or parsed['project']['dependencies'] != ['opendoc-model=='+model_version]:
        raise ValueError('Preview metadata override was not applied exactly')
    (source/'pyproject.toml').write_text(preview, encoding='utf-8')
    environment = dict(os.environ)
    temporary = output/'temp'
    temporary.mkdir()
    environment.update(TEMP=str(temporary), TMP=str(temporary))

    def run(arguments: list[str], name: str) -> None:
        with (output/name).open('w', encoding='utf-8') as log:
            subprocess.run(arguments, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)

    run([uv, 'build', '--wheel', str(source), '--out-dir', str(dist)], 'build.log')
    wheel, = dist.glob('*.whl')
    with zipfile.ZipFile(wheel) as archive:
        for name, expected in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f'Preview changed runtime source: {name}')
    run([uv, 'venv', str(installed)], 'venv.log')
    python = installed/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    locked = tomllib.loads((ROOT/'uv.lock').read_text(encoding='utf-8'))
    versions = {item['name']: item['version'] for item in locked['package']}
    selected = [name+'=='+versions[name] for name in ('pymupdf', 'fonttools', 'pytest')]
    run([uv, 'pip', 'install', '--python', str(python), str(model_wheel), str(wheel), *selected], 'install.log')
    run([uv, 'pip', 'check', '--python', str(python)], 'dependencies.log')
    run([str(python), '-I', '-c', (
        'from pathlib import Path; import opendoc_formats as f, opendoc_model as m; '
        'assert "site-packages" in Path(f.__file__).parts and "site-packages" in Path(m.__file__).parts; '
        'assert all(hasattr(m,n) for n in ("invalidate_text_layouts","set_text_layouts")); '
        'print(f.__version__,m.__version__)')], 'isolation.log')
    report = {
        'purpose': 'Unpublished C-TEXT-LAYOUT-01/02 consumer acceptance only',
        'production_model_dependency': dependencies[0], 'model_version': model_version, 'model_sha256': digest,
        'model_license_hashes': license_hashes, 'formats_preview_version': version,
        'formats_wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(), 'formats_source_sha256': hashes,
        'metadata_overrides': ['Formats version', 'Model dependency and dev wheel source'], 'result': 'pending',
    }
    manifest = output/'provenance.json'
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    run([str(python), '-m', 'pytest', '-q', 'tests/native/test_text_layout_consumer.py',
         'tests/test_text_layout_export.py'], 'consumer.log')
    report['result'] = 'passed'
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-wheel', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--uv', default=shutil.which('uv') or 'uv')
    args = parser.parse_args()
    output = prepare(args.model_wheel, args.sha256, args.uv)
    print(f'Consumer preview passed; logs and provenance: {output}')


if __name__ == '__main__':
    main()
