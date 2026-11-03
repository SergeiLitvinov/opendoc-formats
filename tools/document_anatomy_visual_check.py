"""Compare the one-page independent Word fixture outside its explicitly edited label."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path


def check_fixture(root: Path, output: Path) -> dict:
    import pymupdf
    from PIL import Image, ImageChops, ImageDraw

    renderer = shutil.which('pdftoppm')
    if renderer is None:
        raise RuntimeError('This optional visual acceptance requires external Poppler pdftoppm')
    paths = [root/'source.pdf', root/'edited.pdf']
    originals = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    rectangles, pages = [], []
    for path, label in zip(paths, ['Before', 'Edited'], strict=True):
        with pymupdf.open(path) as document:
            if len(document) != 1:
                raise ValueError('This finite fixture contract requires exactly one page')
            found = document[0].search_for(label)
            if len(found) != 1:
                raise ValueError('Expected exactly one edited label per fixture')
            rectangles.append(found[0])
            pages.append(document[0].rect)
    if pages[0] != pages[1] or pages[0].get_area()*1.5**2 > 16_000_000:
        raise ValueError('Unexpected or excessive page geometry')
    mask = rectangles[0] | rectangles[1]
    mask += (-3, -3, 3, 3)
    if mask.get_area()/pages[0].get_area() >= 0.01:
        raise ValueError('Edited-label mask must cover less than one percent of the page')
    output.mkdir(parents=True, exist_ok=False)
    images = []
    for path in paths:
        stem = output/path.stem
        subprocess.run([renderer, '-r', '108', '-singlefile', '-png', str(path), str(stem)],
                       check=True, capture_output=True, timeout=45)
        with Image.open(stem.with_suffix('.png')) as png:
            image = png.convert('RGB')
            ImageDraw.Draw(image).rectangle((math.floor(mask.x0*1.5), math.floor(mask.y0*1.5),
                                             math.ceil(mask.x1*1.5), math.ceil(mask.y1*1.5)), fill='white')
            images.append(image)
    if images[0].size != images[1].size:
        raise ValueError('Poppler raster dimensions changed')
    changed = ImageChops.difference(*images).getbbox()
    if [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] != originals:
        raise ValueError('Read-only fixture PDFs changed')
    result = {'renderer': 'Poppler pdftoppm', 'dpi': 108, 'pages': 1, 'input_sha256': originals,
              'mask_points': list(mask), 'outside_edited_label_identical': changed is None, 'difference_bbox': changed}
    with (output/'result.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    if changed is not None:
        raise ValueError('Word rendering changed outside the explicitly edited label')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture_root', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New directory for independent Poppler renders')
    args = parser.parse_args()
    print(json.dumps(check_fixture(args.fixture_root, args.output)))


if __name__ == '__main__':
    main()
