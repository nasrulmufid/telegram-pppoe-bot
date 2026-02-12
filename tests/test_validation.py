import pytest

from app.security.validation import validate_page, validate_plan_query, validate_username


def test_validate_username_ok():
    assert validate_username("user_1") == "user_1"


@pytest.mark.parametrize("value", ["", " ", "a", "user name", "x" * 100, "u*"])
def test_validate_username_bad(value: str):
    with pytest.raises(ValueError):
        validate_username(value)


def test_validate_plan_query_ok():
    assert validate_plan_query("Paket 10 Mbps") == "Paket 10 Mbps"


def test_validate_page_ok():
    assert validate_page("1") == 1


@pytest.mark.parametrize("value", ["0", "-1", "abc", "100000"])
def test_validate_page_bad(value: str):
    with pytest.raises(ValueError):
        validate_page(value)
