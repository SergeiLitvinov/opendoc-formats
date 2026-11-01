"""Isolated C-PAGE-DEFAULTS-01 consumer; never adopt the draft into production imports."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

import opendoc_model as od

FIELDS = ('width', 'height', 'margin_top', 'margin_right', 'margin_bottom', 'margin_left')
KEY = 'opendoc.page-settings-state'


def snapshot(section):
    return copy.deepcopy((section.page, dict(section.properties)))


def refuses(section, action, exception=ValueError):
    before = snapshot(section)
    try:
        action()
    except exception as error:
        assert snapshot(section) == before
        return str(error)
    raise AssertionError('Expected an atomic refusal')


def cycles(document):
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
    return document


def api_checks():
    checks = []
    section = od.Section()
    before = snapshot(section)
    assert od.get_page_settings_state(section) is None and snapshot(section) == before
    assert od.get_page_settings_state(cycles(od.DocumentModel(sections=[section])).sections[0]) is None
    checks.append('legacy getter and two official JSON cycles do not add tracking')

    state = od.PageSettingsState(width=od.PageSettingValue('source', od.Length(612)),
                                margin_left=od.PageSettingValue('source', od.Length(0)),
                                margin_top=od.PageSettingValue('computed', od.Length(36), 'consumer estimate v1'))
    old_height = section.page.height
    od.set_page_settings_state(section, state)
    assert section.page.width.pt == 612 and section.page.margin_left.pt == 0 and section.page.height == old_height
    section = cycles(od.DocumentModel(sections=[section])).sections[0]
    assert od.get_page_settings_state(section) == state
    checks.append('partial source, zero, unknown and based computed values survive two official cycles')

    section = od.Section()
    od.set_page_settings_state(section, od.PageSettingsState())
    old_width = section.page.width
    section.page.width = od.Length(old_width.pt)
    assert od.get_page_settings_state(section).width.state == 'unknown'
    od.accept_page_settings(section, ['width'])
    assert section.page.width == old_width
    assert od.get_page_settings_state(section).width == od.PageSettingValue('explicit', old_width)
    checks.append('same-number assignment stays unknown; explicit same-number acceptance changes certainty')

    section.page.width, section.page.height = od.Length(620), od.Length(800)
    before = snapshot(section)
    effective = od.get_page_settings_state(section)
    assert effective.width.freshness == effective.height.freshness == 'stale' and snapshot(section) == before
    document = od.DocumentModel(sections=[section])
    assert document.validate()
    refuses(section, lambda: od.document_to_json(document))
    refuses(section, lambda: od.accept_page_settings(section, ['width']))
    refuses(section, lambda: od.invalidate_page_settings(section, ['height']))
    od.accept_page_settings(section, ['width', 'height'])
    assert not document.validate()
    assert od.get_page_settings_state(cycles(document).sections[0]).height == od.PageSettingValue('explicit', od.Length(800))
    checks.append('direct edits detach effective stale states; serialization and partial batches refuse atomically')

    state = od.get_page_settings_state(section)
    od.set_page_settings_state(section, replace(state, margin_top=od.PageSettingValue('computed', od.Length(18), 'own basis')))
    section.page.margin_top = od.Length(20)
    od.invalidate_page_settings(section, ['margin_top'])
    state = od.get_page_settings_state(cycles(document).sections[0])
    assert state.margin_top == od.PageSettingValue('computed', od.Length(18), 'own basis', 'stale')
    od.set_page_settings_state(section, replace(state, margin_top=od.PageSettingValue('unknown')))
    assert section.page.margin_top.pt == 20 and od.get_page_settings_state(section).margin_top.value is None
    refuses(section, lambda: od.set_page_settings_state(section, None))
    od.accept_page_settings(section)
    od.set_page_settings_state(section, None)
    assert od.get_page_settings_state(section) is None and section.page.margin_top.pt == 20
    checks.append('stale history, deleting estimate and explicitly resolving before removal remain distinct')

    section = od.Section()
    state = od.PageSettingsState(width=od.PageSettingValue('source', od.Length(612), extra={'field_future': [1]}),
                                extra={'state_future': {'nested': [2]}})
    od.set_page_settings_state(section, state)
    section.properties[KEY]['wrapper_future'] = {'nested': [3]}
    section.properties[KEY]['projection']['projection_future'] = [4]
    od.accept_page_settings(section, ['width'])
    detached = od.get_page_settings_state(section)
    detached.width.extra['field_future'].append(999)
    detached.extra['state_future']['nested'].append(999)
    raw = detached.to_dict()
    raw['state_future']['nested'].append(888)
    section = cycles(od.DocumentModel(sections=[section])).sections[0]
    retained = od.get_page_settings_state(section)
    assert retained.width.extra['field_future'] == [1] and retained.extra['state_future'] == {'nested': [2]}
    assert section.properties[KEY]['wrapper_future'] == {'nested': [3]}
    assert section.properties[KEY]['projection']['projection_future'] == [4]
    assert od.PageSettingsState.from_dict(retained.to_dict()) == retained
    checks.append('DTO, field, envelope and projection unknown fields survive without getter/codec aliases')

    for field in ('width', 'height', 'margin_top', 'margin_right', 'margin_bottom', 'margin_left'):
        bad = od.Section()
        od.set_page_settings_state(bad, od.PageSettingsState())
        del bad.properties[KEY]['projection'][field]
        assert 'projection.'+field in refuses(bad, lambda: od.get_page_settings_state(bad))
    bad = od.Section()
    od.set_page_settings_state(bad, od.PageSettingsState())
    bad.properties[KEY]['version'] = 2
    assert 'version' in refuses(bad, lambda: od.get_page_settings_state(bad))
    refuses(bad, lambda: od.set_page_settings_state(bad, od.PageSettingsState()))
    for opaque in (None, 'native', {'format': 'future.vendor', 'values': [1]}):
        bad = od.Section(properties={KEY: opaque})
        assert od.get_page_settings_state(bad) is None
        refuses(bad, lambda: od.set_page_settings_state(bad, od.PageSettingsState()))
        refuses(bad, lambda: od.accept_page_settings(bad))
    checks.append('all six missing snapshots, unknown version and opaque carriers refuse without repairs')

    for damage in ('snapshot-conflict', 'invalid-size', 'missing-state'):
        bad = od.Section()
        od.set_page_settings_state(bad, od.PageSettingsState(width=od.PageSettingValue('source', od.Length(612))))
        if damage == 'snapshot-conflict':
            bad.properties[KEY]['projection']['width']['pt'] = 613
        elif damage == 'invalid-size':
            bad.properties[KEY]['projection']['height']['pt'] = 0
        else:
            del bad.properties[KEY]['state']
        refuses(bad, lambda: od.get_page_settings_state(bad))
    checks.append('contradictory projections and incomplete envelopes refuse without inferring defaults')

    invalid = [lambda: od.PageSettingValue('unknown', od.Length(1)),
               lambda: od.PageSettingValue('computed', od.Length(1)),
               lambda: od.PageSettingValue('source', od.Length(float('nan'))),
               lambda: od.PageSettingValue('explicit', od.Length(float('inf'))),
               lambda: od.PageSettingValue('source', od.Length(True)),
               lambda: od.PageSettingValue('source', od.Length(-1)),
               lambda: od.PageSettingsState(width=od.PageSettingValue('source', od.Length(0))),
               lambda: od.PageSettingsState(width=od.PageSettingValue('source', od.Length(100)),
                                           margin_left=od.PageSettingValue('source', od.Length(60)),
                                           margin_right=od.PageSettingValue('source', od.Length(40)))]
    for factory in invalid:
        try:
            factory()
        except (ValueError, TypeError):
            pass
        else:
            raise AssertionError('Invalid geometry was accepted')
    checks.append('invalid certainty/value/basis, bool/nonfinite/negative/zero sizes and consuming margins refuse')

    section = od.Section()
    od.set_page_settings_state(section, od.PageSettingsState())
    for selection in ('width', ['width', 'width'], ['unknown-field'], [True]):
        refuses(section, lambda: od.accept_page_settings(section, selection))
    nested = 'leaf'
    for _ in range(40):
        nested = {'next': nested}
    for budget, extra in ((od.DocumentLimits(max_nodes=1500), {'future': [None]*2000}),
                          (od.DocumentLimits(max_bytes=3000), {'future': 'x'*10000}),
                          (od.DocumentLimits(max_depth=20), {'future': nested})):
        state = od.PageSettingsState(extra=extra)
        refuses(section, lambda: od.set_page_settings_state(section, state, limits=budget), od.ArtifactLimitError)
        try:
            od.PageSettingsState.from_dict(state.to_dict(), limits=budget)
        except od.ArtifactLimitError as error:
            assert error.path and error.quota in {'nodes', 'bytes', 'depth'}
        else:
            raise AssertionError('Unknown fields evaded codec quota')
    for action in (lambda: od.get_page_settings_state(section, limits=od.DocumentLimits(max_nodes=1)),
                   lambda: od.accept_page_settings(section, limits=od.DocumentLimits(max_nodes=1)),
                   lambda: od.invalidate_page_settings(section, limits=od.DocumentLimits(max_nodes=1))):
        refuses(section, action, od.ArtifactLimitError)
    checks.append('selection and node/byte/depth quotas cover getter/setter/accept/invalidate/codec atomically')
    return checks


def source_prototype(inputs, native):
    from opendoc_formats import read_document

    observed = {row['name']: row for row in json.loads(native.read_text(encoding='utf-8'))['observations']}
    manifest = json.loads((inputs/'manifest.json').read_text(encoding='utf-8'))
    results = []
    for entry in manifest:
        assert Path(entry['file']).name == entry['file']
        path = inputs/entry['file']
        row = observed[entry['name']]
        assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == row['sha256']
        imported = read_document(path)
        assert imported.success, imported.issues
        document = imported.document
        counts = {'source': 0, 'unknown': 0}
        for index, section in enumerate(document.sections):
            private = section.properties['opendoc_formats.docx_page']
            states = {}
            for field in FIELDS:
                kind = 'unknown' if field in private['unresolved'] else 'source'
                counts[kind] += 1
                value = getattr(section.page, field) if kind == 'source' else None
                states[field] = od.PageSettingValue(kind, value)
                if kind == 'source':
                    measure = row['page_geometry'][index][field.removeprefix('margin_')]
                    assert abs(value.pt-measure) < 0.026
            before = copy.deepcopy(private)
            od.set_page_settings_state(section, od.PageSettingsState(**states))
            assert section.properties['opendoc_formats.docx_page'] == before
        reloaded = cycles(document)
        assert od.document_to_json(document) == od.document_to_json(reloaded)
        computed = od.document_from_json(od.document_to_json(document))
        for index, section in enumerate(computed.sections):
            state = od.get_page_settings_state(section)
            changes = {}
            for field in FIELDS:
                if getattr(state, field).state == 'unknown':
                    measured = row['page_geometry'][index][field.removeprefix('margin_')]
                    changes[field] = od.PageSettingValue('computed', od.Length(measured), 'Independent native QA '+row['sha256'])
            od.set_page_settings_state(section, replace(state, **changes))
        computed = cycles(computed)
        assert not computed.validate()
        results.append({'name': entry['name'], 'source_sha256': row['sha256'], 'states': counts,
                        'source_and_unknown_json_cycles': 2, 'native_measured_computed_json_cycles': 2,
                        'native_omission_binding_unchanged': True})
        assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == row['sha256']
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'native', 'manifest', 'candidate-wheel', 'formats-wheel', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    package = Path(od.__file__).resolve().parent.parent
    assert 'site-packages' in package.parts
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    actual = {name: hashlib.sha256((package/name).read_bytes()).hexdigest() for name in manifest['files']}
    assert actual == manifest['files']
    actual_hash = hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert actual_hash == manifest['source_tree_sha256']
    report = {'scope': 'Isolated unpublished C-PAGE-DEFAULTS-01 API/codec and finite DOCX source-mapping prototype',
              'model_candidate': {'version': version('opendoc-model'), 'source_tree_sha256': actual_hash,
                                  'files': len(actual),
                                  'wheel_sha256': hashlib.sha256(args.candidate_wheel.read_bytes()).hexdigest(),
                                  'published': False},
              'formats_wheel_sha256': hashlib.sha256(args.formats_wheel.read_bytes()).hexdigest(),
              'api_checks': api_checks(), 'source_prototype': source_prototype(args.inputs, args.native),
              'production_pin_changed': False, 'production_api_adopted': False,
              'not_proven': ['production renderer/writer adoption', 'same-number acceptance materialization in DOCX',
                             'external environment freshness', 'arbitrary format compatibility']}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Candidate source parity:', len(actual), actual_hash)
    print('Consumer groups:', len(report['api_checks']), 'independent native source prototypes:', len(report['source_prototype']))


if __name__ == '__main__':
    main()
