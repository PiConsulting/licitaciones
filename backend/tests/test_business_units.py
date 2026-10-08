from infra.business_units import BUSINESS_UNITS, is_valid_business_unit, normalize_business_unit


def test_catalog_has_no_duplicates():
    assert len(set(BUSINESS_UNITS)) == len(BUSINESS_UNITS)


def test_normalize_is_case_insensitive_and_returns_canonical_name():
    for unit in BUSINESS_UNITS:
        assert normalize_business_unit(f"  {unit.upper()} ") == unit
        assert normalize_business_unit(unit.lower()) == unit


def test_normalize_rejects_unknown_empty_and_none():
    assert normalize_business_unit("desconocida") is None
    assert normalize_business_unit("   ") is None
    assert normalize_business_unit(None) is None
    assert not is_valid_business_unit("desconocida")
