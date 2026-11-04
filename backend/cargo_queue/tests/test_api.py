import pytest
from rest_framework.test import APIClient

from accounts.roles import RoleCode as R
from audit.models import AuditAction, AuditLog
from cargo_queue import errors
from cargo_queue.models import QueueRequest, ReleasePermit, Ticket
from cargo_queue.statuses import RequestStatus as S
from cargo_queue.tests.factories import DockFactory, QueueRequestFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def client_for(role: R) -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role_code=role, username=f"api_{role.value}"))
    return client


# --- permit check ---------------------------------------------------------------------------


def test_permit_check_verified(reg_client):
    response = reg_client.post("/api/permits/check/", {"awb_number": "17612345670"})
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is True
    assert body["awb_number"] == "176-12345670"
    assert body["permit"]["source"] == "MOCK"


def test_permit_check_rejected_has_reason_and_is_audited(reg_client):
    response = reg_client.post("/api/permits/check/", {"awb_number": "176-12345671"})
    body = response.json()
    assert (response.status_code, body["verified"], body["permit"]) == (200, False, None)
    assert body["reason"] == errors.PERMIT_NOT_FOUND
    assert AuditLog.objects.filter(action=AuditAction.PERMIT_REJECTED).count() == 1


def test_permit_check_bad_format(reg_client):
    body = reg_client.post("/api/permits/check/", {"awb_number": "12-3"}).json()
    assert body["verified"] is False and body["reason"] == errors.AWB_INVALID


def test_manual_provider_needs_supervisor_confirmation(reg_client, settings, payload, shifts):
    settings.PERMIT_PROVIDER = "manual"
    denied = reg_client.post("/api/requests/", payload, format="json")
    assert denied.status_code == 400 and denied.json()["detail"] == errors.PERMIT_MANUAL_REQUIRED

    boss = client_for(R.SUPERVISOR)
    verify = boss.post(
        "/api/permits/manual-verify/",
        {"awb_number": payload["awb_number"], "permit_number": "UZ-555"},
        format="json",
    )
    assert verify.status_code == 201
    stored = ReleasePermit.objects.get(permit_number="UZ-555")
    assert stored.source == "MANUAL" and stored.verified_by.role.code == "SUPERVISOR"
    assert AuditLog.objects.filter(entity="release_permits", entity_id=stored.pk).exists()

    assert reg_client.post("/api/requests/", payload, format="json").status_code == 201


# --- registration -----------------------------------------------------------------------------


def test_register_request_end_to_end(reg_client, payload, shifts):
    response = reg_client.post("/api/requests/", payload, format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["queue_number"] == 1
    # registration also creates the warehouse task; the system moves the request on
    assert body["status"] == S.AWAITING_PREP
    assert body["sms_phone"] == "+998901234567"
    assert body["vehicle_plate"] == "01A123BC"
    assert body["awb_number"] == "176-12345670"
    assert [h["to_status"] for h in body["history"]] == [S.REGISTERED, S.AWAITING_PREP]
    ticket = body["ticket"]
    assert ticket["queue_number"] == 1 and ticket["pieces_total"] == 12
    assert ticket["qr_token"] and ticket["is_reprint"] is False
    assert ticket["airport"]

    request = QueueRequest.objects.get(pk=body["id"])
    assert request.tickets.count() == 1
    task = request.warehouse_tasks.get()
    assert task.status == "NEW"
    assert AuditLog.objects.filter(action=AuditAction.CREATE, entity_id=request.pk).exists()
    assert request.created_by.username == "reg_agent"


def test_register_rejected_awb_creates_nothing_and_says_why(reg_client, payload, shifts):
    payload["awb_number"] = "176-12345671"
    response = reg_client.post("/api/requests/", payload, format="json")
    assert response.status_code == 400
    assert response.json() == {"detail": errors.PERMIT_NOT_FOUND, "code": "permit_rejected"}
    assert QueueRequest.objects.count() == 0


@pytest.mark.django_db(transaction=True)
@pytest.mark.postgres
def test_rejected_registration_audit_survives_the_error_response(reg_client, payload, shifts):
    payload["awb_number"] = "176-12345671"
    assert reg_client.post("/api/requests/", payload, format="json").status_code == 400
    assert AuditLog.objects.filter(action=AuditAction.PERMIT_REJECTED).count() == 1


def test_duplicate_active_awb_is_409(reg_client, payload, shifts):
    assert reg_client.post("/api/requests/", payload, format="json").status_code == 201
    again = reg_client.post("/api/requests/", payload, format="json")
    assert again.status_code == 409
    assert again.json()["detail"] == errors.DUPLICATE_ACTIVE_REQUEST


def test_validation_messages_are_uzbek(reg_client, payload, shifts):
    bad = {**payload, "sms_phone": "123", "pieces_total": 0, "category": "XXX", "weight_kg": "-1"}
    del bad["consignee_name"]
    response = reg_client.post("/api/requests/", bad, format="json")
    assert response.status_code == 400
    body = response.json()
    assert body["consignee_name"] == ["Bu maydon to‘ldirilishi shart."]
    assert body["sms_phone"] == [errors.PHONE_INVALID]
    assert body["category"] == [errors.CATEGORY_UNKNOWN]
    assert body["pieces_total"] == ["Qiymat juda kichik."]
    assert body["weight_kg"] == ["Qiymat juda kichik."]


def test_bad_awb_format_is_a_field_error(reg_client, payload, shifts):
    payload["awb_number"] = "nope"
    body = reg_client.post("/api/requests/", payload, format="json").json()
    assert body["awb_number"] == [errors.AWB_INVALID]


def test_no_shift_configured_is_reported(reg_client, payload):
    response = reg_client.post("/api/requests/", payload, format="json")
    assert response.status_code == 409 and response.json()["code"] == "no_shift"


# --- list / detail ------------------------------------------------------------------------------


def test_list_filters_and_pagination(reg_client):
    a = QueueRequestFactory(status=S.REGISTERED, queue_number=1)
    b = QueueRequestFactory(status=S.CARGO_READY, queue_number=2)
    dock = DockFactory(code="D-05")
    b.dock = dock
    b.save()
    c = QueueRequestFactory(status=S.REGISTERED, queue_number=777, queue_date="2020-01-01")

    def numbers(query: str) -> list[int]:
        response = reg_client.get(f"/api/requests/{query}")
        assert response.status_code == 200
        return sorted(r["queue_number"] for r in response.json()["results"])

    assert numbers("") == [1, 2, 777]
    assert numbers(f"?date={a.queue_date}") == [1, 2]
    assert numbers("?date=2020-01-01") == [777]
    assert numbers("?status=CARGO_READY") == [2]
    assert numbers("?status=REGISTERED,CARGO_READY") == [1, 2, 777]
    assert numbers("?dock=D-05") == [2]
    assert numbers(f"?q={a.awb_number}") == [1]
    assert numbers("?q=777") == [777]
    assert numbers(f"?category={c.category.code}") == [1, 2, 777]
    assert reg_client.get("/api/requests/?page_size=2").json()["count"] == 3
    assert len(reg_client.get("/api/requests/?page_size=2").json()["results"]) == 2


def test_list_rejects_bad_date_in_uzbek(reg_client):
    response = reg_client.get("/api/requests/?date=yesterday")
    assert response.status_code == 400
    assert response.json()["date"] == [errors.FILTER_DATE_INVALID]


def test_detail_includes_history_and_404_is_uzbek(reg_client):
    request = QueueRequestFactory()
    body = reg_client.get(f"/api/requests/{request.pk}/").json()
    assert body["awb_number"] == request.awb_number and "history" in body
    missing = reg_client.get("/api/requests/99999/")
    assert missing.status_code == 404 and missing.json()["detail"] == "Ma’lumot topilmadi."


# --- tickets -------------------------------------------------------------------------------------


def test_reprint_creates_marked_ticket_and_audit(reg_client):
    request = QueueRequestFactory()
    first = reg_client.get(f"/api/requests/{request.pk}/ticket/")
    assert first.status_code == 404  # factory request was never printed

    response = reg_client.post(f"/api/requests/{request.pk}/ticket/reprint/")
    assert response.status_code == 201 and response.json()["is_reprint"] is True
    assert Ticket.objects.filter(request=request, is_reprint=True).count() == 1
    assert AuditLog.objects.filter(action=AuditAction.REPRINT).count() == 1
    again = reg_client.get(f"/api/requests/{request.pk}/ticket/").json()
    assert again["qr_token"] == request.qr_token and again["queue_number"] == request.queue_number


# --- transitions through the API -----------------------------------------------------------------


def test_transition_endpoint_happy_path_and_errors():
    request = QueueRequestFactory(status=S.AWAITING_PREP)
    url = f"/api/requests/{request.pk}/transition/"

    ok = client_for(R.WAREHOUSE).post(url, {"to_status": "PREP_STARTED"}, format="json")
    assert ok.status_code == 200 and ok.json()["status"] == S.PREP_STARTED
    assert [h["to_status"] for h in ok.json()["history"]] == [S.PREP_STARTED]

    wrong_role = client_for(R.DOCK_AGENT).post(url, {"to_status": "CARGO_READY"}, format="json")
    assert wrong_role.status_code == 403 and wrong_role.json()["code"] == "role_forbidden"

    illegal = client_for(R.WAREHOUSE).post(url, {"to_status": "CLOSED"}, format="json")
    assert illegal.status_code == 409 and illegal.json()["code"] == "invalid_transition"

    no_reason = client_for(R.SUPERVISOR).post(url, {"to_status": "CANCELLED"}, format="json")
    assert no_reason.status_code == 400 and no_reason.json()["code"] == "reason_required"

    unknown = client_for(R.SUPERVISOR).post(url, {"to_status": "NOPE"}, format="json")
    assert unknown.status_code == 400 and "to_status" in unknown.json()


def test_lookups(reg_client, shifts, category):
    DockFactory(code="D-01")
    body = reg_client.get("/api/lookups/").json()
    assert [c["code"] for c in body["categories"]] == ["GEN"]
    assert len(body["shifts"]) == 3
    assert [d["code"] for d in body["docks"]] == ["D-01"]
