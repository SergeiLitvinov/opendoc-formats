"""Formula content budgets inspect real serialized output before publication."""


import pytest
from opendoc.document_codec import save_document
from opendoc.document_model import DocumentModel, Formula, FormulaFormat, Paragraph, Section, TextRun
from opendoc.formula_quality_policy import FormulaLossPolicy, formula_fingerprint

MATH = '<math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>x</mi><mn>2</mn></mfrac></math>'


def source_document(tmp_path, count=1):
    source = tmp_path / 'source.json'
    save_document(DocumentModel(sections=[Section(blocks=[
        Paragraph(content=[TextRun('Формула: '), *[Formula(MATH, FormulaFormat.MATHML) for _ in range(count)]]),
    ])]), source)
    return source


@pytest.mark.parametrize('limit', [-1, True, 0.2, '0'])
def test_invalid_formula_budget(limit):
    with pytest.raises(ValueError):
        FormulaLossPolicy(limit)










def test_xml_prefixes_and_indentation_are_ignored_but_symbols_are_not():
    namespace = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
    first = Formula(f'<m:oMath xmlns:m="{namespace}"><m:r><m:t>x</m:t></m:r></m:oMath>', FormulaFormat.OMML)
    second = Formula(f'<q:oMath xmlns:q="{namespace}">\n <q:r><q:t>x</q:t></q:r>\n</q:oMath>', FormulaFormat.OMML)
    assert formula_fingerprint(first) == formula_fingerprint(second)
    second.value = second.value.replace('>x<', '>y<')
    assert formula_fingerprint(first) != formula_fingerprint(second)
    assert formula_fingerprint(Formula('<broken', FormulaFormat.OMML)) is None
