from __future__ import annotations

import pytest

from extraction.registry.registry import (
    _REGISTRY,
    UnknownAttributeError,
    UnknownDocumentTypeError,
    get_attribute_specs,
    register,
)
from extraction.schemas import AttributeSpec, AttributeType


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


@pytest.fixture
def attribute_spec_fixture():
    """Creates an AttributeSpec fixture for testing."""
    return AttributeSpec(
        name='test_attribute',
        type=AttributeType.STRING,
        description='A test attribute.',
        hints=['hint1', 'hint2'],
        regex_hint=None,
        normaliser=None,
        constraints=None,
        thresholds=None,
    )


@pytest.fixture
def registry_mock():
    """Resets the registry dictionary before every test."""
    _REGISTRY.clear()


def test_register_stores_specs_correctly(attribute_spec_fixture, registry_mock):
    """Test that the register function stores AttributeSpec objects correctly."""
    register('test_doc_type', [attribute_spec_fixture])
    assert 'test_doc_type' in _REGISTRY
    assert 'test_attribute' in _REGISTRY['test_doc_type']
    assert _REGISTRY['test_doc_type']['test_attribute'] == attribute_spec_fixture


def test_register_normalizes_doc_type(attribute_spec_fixture, registry_mock):
    """Test that register function normalizes doc_type to lower case."""
    register('Test_Doc_Type', [attribute_spec_fixture])
    assert 'test_doc_type' in _REGISTRY  # Verify that doc_type is normalized


def test_register_handles_empty_spec_list(registry_mock):
    """Test that register can handle an empty list of specs."""
    register('test_doc_type', [])
    assert 'test_doc_type' in _REGISTRY
    assert _REGISTRY['test_doc_type'] == {}


def test_register_adds_to_existing_bucket(attribute_spec_fixture, registry_mock):
    """Test that register adds specs to an existing bucket without overwriting."""
    # Initial registration
    initial_spec = AttributeSpec(
        name='initial_attribute',
        type=AttributeType.INTEGER,
        description='Initial attribute.',
        hints=['initial_hint'],
    )
    register('test_doc_type', [initial_spec])

    # Add new spec
    register('test_doc_type', [attribute_spec_fixture])

    # Check if both specs exist
    assert 'test_doc_type' in _REGISTRY
    assert 'initial_attribute' in _REGISTRY['test_doc_type']
    assert 'test_attribute' in _REGISTRY['test_doc_type']
    assert _REGISTRY['test_doc_type']['initial_attribute'] == initial_spec
    assert _REGISTRY['test_doc_type']['test_attribute'] == attribute_spec_fixture
