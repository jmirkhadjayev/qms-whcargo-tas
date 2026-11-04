import datetime as dt

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from cargo_queue import errors
from cargo_queue.awb import normalize_awb
from cargo_queue.models import PermitSource, PermitStatus, ReleasePermit
from cargo_queue.tests.factories import ReleasePermitFactory
from integrations.permits import (
    ManualPermitProvider,
    MockPermitProvider,
    get_permit_provider,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("17612345670", "176-12345670"),
        ("176-12345670", "176-12345670"),
        (" 176 12345670 ", None),  # inner spaces are removed, but the digit count must match
        ("1761234567", None),
        ("abc-12345670", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_awb(raw, expected):
    # " 176 12345670 " has 11 digits once spaces are stripped, so it is valid
    if raw == " 176 12345670 ":
        expected = "176-12345670"
    assert normalize_awb(raw) == expected


@pytest.mark.parametrize(
    ("awb", "ok"),
    [
        ("176-12345670", True),
        ("176-12345672", True),
        ("176-12345671", False),
        ("176-12345679", False),
    ],
)
def test_mock_even_last_digit_is_verified(awb, ok):
    result = MockPermitProvider().check(awb)
    assert result.verified is ok
    if ok:
        assert result.permit.source == PermitSource.MOCK
        assert result.permit.status == PermitStatus.VERIFIED
    else:
        assert result.permit is None and result.reason == errors.PERMIT_NOT_FOUND


def test_mock_reuses_its_permit_row():
    MockPermitProvider().check("176-12345670")
    MockPermitProvider().check("176-12345670")
    assert ReleasePermit.objects.count() == 1


def test_mock_respects_a_revoked_permit():
    MockPermitProvider().check("176-12345670")
    ReleasePermit.objects.update(status=PermitStatus.REVOKED)
    result = MockPermitProvider().check("176-12345670")
    assert not result.verified and result.reason == errors.PERMIT_REVOKED


def test_manual_provider_without_record_asks_for_confirmation():
    result = ManualPermitProvider().check("176-12345670")
    assert not result.verified and result.reason == errors.PERMIT_MANUAL_REQUIRED


def test_manual_provider_uses_verified_permit():
    permit = ReleasePermitFactory(awb_number="176-12345670")
    result = ManualPermitProvider().check("176-12345670")
    assert result.verified and result.permit == permit


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"status": PermitStatus.REVOKED}, errors.PERMIT_REVOKED),
        ({"status": PermitStatus.INVALID}, errors.PERMIT_NOT_VERIFIED),
        ({"valid_until": timezone.now() - dt.timedelta(hours=1)}, errors.PERMIT_EXPIRED),
    ],
)
def test_manual_provider_explains_unusable_permits(kwargs, reason):
    ReleasePermitFactory(awb_number="176-12345670", **kwargs)
    result = ManualPermitProvider().check("176-12345670")
    assert not result.verified and result.reason == reason


def test_manual_provider_prefers_a_usable_permit_over_a_newer_revoked_one():
    good = ReleasePermitFactory(awb_number="176-12345670")
    ReleasePermitFactory(awb_number="176-12345670", status=PermitStatus.REVOKED)
    assert ManualPermitProvider().check("176-12345670").permit == good


def test_provider_selected_from_settings(settings):
    settings.PERMIT_PROVIDER = "mock"
    assert isinstance(get_permit_provider(), MockPermitProvider)
    settings.PERMIT_PROVIDER = "manual"
    assert isinstance(get_permit_provider(), ManualPermitProvider)
    settings.PERMIT_PROVIDER = "awery"
    with pytest.raises(ImproperlyConfigured):
        get_permit_provider()
