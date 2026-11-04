"""SMS notifications (TZ 7): texts, the Celery task with retries, and the journal."""

import logging
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured

from accounts.models import SystemSetting
from cargo_queue.tests.factories import ConsigneeFactory, QueueRequestFactory
from integrations.sms import (
    ConsoleSmsGateway,
    MockSmsGateway,
    get_mock_gateway,
    get_sms_gateway,
)
from notifications import services
from notifications.models import SmsMessage, SmsStatus, SmsTemplate
from notifications.tasks import send_sms

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mock_gateway(settings):
    settings.SMS_GATEWAY = "mock"
    gateway = get_mock_gateway()
    gateway.sent.clear()
    gateway.fail_times = 0
    return gateway


_tins = iter(range(10000, 99999))


def make_request(queue_number=17, **kwargs):
    return QueueRequestFactory(
        queue_number=queue_number,
        sms_phone="+998901234567",
        consignee=ConsigneeFactory(name="Maxfiy Ismli MChJ", tin=f"98765{next(_tins)}"),
        **kwargs,
    )


def set_setting(key, value):
    SystemSetting.objects.update_or_create(key=key, defaults={"value": value})


# --- the texts ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "values", "expected"),
    [
        (SmsTemplate.REGISTERED, {}, ["№17", "ro‘yxatga olindi"]),
        (SmsTemplate.CALLED, {"dock": "D-03"}, ["№17", "D-03", "Talonni"]),
        (SmsTemplate.RECALL, {"dock": "D-03", "minutes": 10}, ["Takroriy", "№17", "D-03", "10"]),
        (SmsTemplate.STATUS, {"text": services.STATUS_REQUEUED}, ["№17", "navbat oxiriga"]),
    ],
)
def test_texts_carry_the_ticket_number_dock_and_an_instruction(template, values, expected):
    sms = services.queue_sms(make_request(), template, **values)
    for part in expected:
        assert part in sms.body
    assert sms.template == template and sms.status == SmsStatus.QUEUED


def test_texts_contain_no_personal_data():
    request = make_request(representative_name="Aliyev Vali")
    for template, values in [
        (SmsTemplate.REGISTERED, {}),
        (SmsTemplate.CALLED, {"dock": "D-01"}),
        (SmsTemplate.RECALL, {"dock": "D-01", "minutes": 10}),
    ]:
        body = services.queue_sms(request, template, **values).body
        for secret in ("Maxfiy", "Aliyev", "98765", "+998901234567", request.awb_number):
            assert secret not in body


# --- sending ----------------------------------------------------------------------------------------


def test_the_message_is_sent_after_the_transaction_commits(
    django_capture_on_commit_callbacks, mock_gateway
):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    assert mock_gateway.sent == []  # nothing before the commit
    for callback in callbacks:
        callback()
    sms.refresh_from_db()
    assert sms.status == SmsStatus.SENT and sms.attempts == 1
    assert sms.sent_at is not None and sms.provider_msg_id.startswith("mock-")
    assert mock_gateway.sent == [("+998901234567", sms.body)]


def test_a_failed_attempt_is_recorded_and_asks_for_a_retry(mock_gateway):
    mock_gateway.fail_times = 1
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    assert services.deliver_sms(sms.pk) == (False, True)
    sms.refresh_from_db()
    assert (sms.status, sms.attempts, sms.error) == (
        SmsStatus.QUEUED,
        1,
        "gateway unavailable",
    )
    assert services.deliver_sms(sms.pk) == (True, False)
    sms.refresh_from_db()
    assert (sms.status, sms.attempts, sms.error) == (SmsStatus.SENT, 2, "")


def test_after_the_last_attempt_the_message_is_marked_failed(mock_gateway):
    mock_gateway.fail_times = 99
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    results = [services.deliver_sms(sms.pk) for _ in range(3)]
    assert results == [(False, True), (False, True), (False, False)]
    sms.refresh_from_db()
    assert (sms.status, sms.attempts) == (SmsStatus.FAILED, 3)
    assert mock_gateway.sent == []


def test_the_attempt_limit_comes_from_the_settings(mock_gateway):
    set_setting("sms_max_attempts", 1)
    mock_gateway.fail_times = 99
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    assert services.deliver_sms(sms.pk) == (False, False)
    sms.refresh_from_db()
    assert sms.status == SmsStatus.FAILED


def test_a_sent_message_is_never_sent_twice(mock_gateway):
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    services.deliver_sms(sms.pk)
    assert services.deliver_sms(sms.pk) == (True, False)
    assert len(mock_gateway.sent) == 1


def test_an_unknown_message_is_ignored():
    assert services.deliver_sms(424242) == (True, False)


# --- the Celery task ---------------------------------------------------------------------------------


def test_the_task_retries_until_the_gateway_works(mock_gateway):
    mock_gateway.fail_times = 2
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    result = send_sms.apply(args=[sms.pk])
    assert result.successful() and result.result is True
    sms.refresh_from_db()
    assert (sms.status, sms.attempts) == (SmsStatus.SENT, 3)


def test_the_task_gives_up_after_the_limit(mock_gateway):
    mock_gateway.fail_times = 99
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    result = send_sms.apply(args=[sms.pk])
    assert result.result is False
    sms.refresh_from_db()
    assert (sms.status, sms.attempts) == (SmsStatus.FAILED, 3)


def test_the_retry_waits_as_long_as_the_settings_say(mock_gateway):
    set_setting("sms_retry_delay_sec", 45)
    mock_gateway.fail_times = 1
    sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    with (
        mock.patch.object(send_sms, "retry", side_effect=RuntimeError("stop")) as retry,
        pytest.raises(RuntimeError),
    ):
        send_sms.run(sms.pk)
    assert retry.call_args.kwargs["countdown"] == 45


# --- gateways --------------------------------------------------------------------------------------


def test_gateway_is_chosen_from_the_environment(settings):
    settings.SMS_GATEWAY = "console"
    assert isinstance(get_sms_gateway(), ConsoleSmsGateway)
    settings.SMS_GATEWAY = "mock"
    assert isinstance(get_sms_gateway(), MockSmsGateway)
    settings.SMS_GATEWAY = "beeline"
    with pytest.raises(ImproperlyConfigured):
        get_sms_gateway()


def test_console_gateway_writes_to_the_log(caplog):
    with caplog.at_level(logging.INFO, logger="integrations.sms"):
        result = ConsoleSmsGateway().send("+998901234567", "salom")
    assert result.ok and result.provider_msg_id.startswith("console-")
    assert "salom" in caplog.text


# --- when texts are sent ------------------------------------------------------------------------------


def test_registration_sends_a_confirmation(
    django_capture_on_commit_callbacks, mock_gateway, shifts, payload, reg_client
):
    with django_capture_on_commit_callbacks(execute=True):
        response = reg_client.post("/api/requests/", payload, format="json")
    assert response.status_code == 201
    sms = SmsMessage.objects.get()
    assert sms.template == SmsTemplate.REGISTERED and sms.status == SmsStatus.SENT
    assert f"№{response.json()['queue_number']}" in sms.body
    assert mock_gateway.sent[0][0] == "+998901234567"


# --- a broker outage must not break the request ----------------------------------------------------


def test_a_broker_outage_does_not_fail_the_request_and_the_sweep_sends_it_later(
    django_capture_on_commit_callbacks, mock_gateway
):
    with (
        mock.patch.object(send_sms, "delay", side_effect=ConnectionError("no broker")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        sms = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    sms.refresh_from_db()
    assert sms.status == SmsStatus.QUEUED and sms.attempts == 0  # nothing lost, nothing sent
    assert mock_gateway.sent == []

    assert services.send_pending(older_than_seconds=0) == 1
    sms.refresh_from_db()
    assert sms.status == SmsStatus.SENT


def test_the_sweep_leaves_fresh_and_already_tried_messages_alone(mock_gateway):
    fresh = services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    tried = services.queue_sms(make_request(queue_number=18), SmsTemplate.REGISTERED)
    SmsMessage.objects.filter(pk=tried.pk).update(attempts=1)
    assert services.send_pending(older_than_seconds=60) == 0
    assert mock_gateway.sent == []
    assert fresh.pk and tried.pk


def test_the_periodic_job_task_runs_the_sweep(mock_gateway):
    from notifications.tasks import send_pending_sms

    services.queue_sms(make_request(), SmsTemplate.REGISTERED)
    assert send_pending_sms.run() == 0  # too fresh for the default one-minute threshold
