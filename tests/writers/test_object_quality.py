"""Object budgets verify serialized artifacts, not exporter declarations."""

import pytest
from opendoc_model.object_quality_policy import ObjectLossPolicy


@pytest.mark.parametrize("limit", [-1, True, 0.5])
def test_reject_invalid_object_budget(limit):
    with pytest.raises(ValueError):
        ObjectLossPolicy(limit)
