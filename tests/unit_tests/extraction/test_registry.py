from __future__ import annotations

import pytest

from extraction.registry import (
    UnknownAttributeError,
    UnknownDocumentTypeError,
    get_attribute_specs,
)


def test_get_attribute_specs_returns_all_for_doc_type() -> None:
    specs = get_attribute_specs('annual_report')
    names = {spec.name for spec in specs}
    assert 'company_name' in names
    assert 'isin' in names
    assert all(spec.thresholds is not None for spec in specs), 'every attribute should have thresholds'


def test_get_attribute_specs_subset() -> None:
    specs = get_attribute_specs('annual_report', ['isin', 'company_name'])
    assert [spec.name for spec in specs] == ['isin', 'company_name']


def test_get_attribute_specs_unknown_doc_type() -> None:
    with pytest.raises(UnknownDocumentTypeError):
        get_attribute_specs('mystery_doc')


def test_get_attribute_specs_unknown_attribute() -> None:
    with pytest.raises(UnknownAttributeError):
        get_attribute_specs('annual_report', ['does_not_exist'])
