"""PowerPoint full-page acceptance for HSL luminance and its ordered compositions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED = {'lum-mod': '#102030', 'lum-off': '#4080BF', 'mod-off': '#336699', 'off-mod': '#2E5C8A',
            'mod-double': '#4080C0', 'off-negative': '#102030', 'shade-lum': '#326CA7', 'lum-shade': '#2D5C8C',
            'clip-return': '#7F7F7F', 'negative-return': '#7F7F7F', 'grey-double': '#FFFFFF', 'grey-shade': '#5C5C5C'}


def main() -> None:
    from tools.pptx_background_acceptance import compare
    from tools.pptx_color_acceptance import controls, prepare

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'check'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        from tests.readers.test_pptx_luminance import CASES

        prepare(args.root, CASES)
    elif args.output:
        source_controls = controls(args.root, EXPECTED)
        compare(args.root, args.output,
                scope='DrawingML HSL luminance on text, shapes and series fill; signed percentages and order',
                limitations=['Finite sRGB luminance profile; not all color models or transforms',
                             'Not full chart/theme/shaping compatibility'])
        evidence = json.loads(args.output.read_text(encoding='utf-8'))
        evidence['source_color_controls'] = source_controls
        args.output.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    else:
        parser.error('check requires --output')


if __name__ == '__main__':
    main()
