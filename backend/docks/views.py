from __future__ import annotations

from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode as R
from accounts.settings_store import get_setting
from cargo_queue.awb import normalize_awb
from cargo_queue.models import QueueRequest
from cargo_queue.services import closing, state_machine
from cargo_queue.statuses import INACTIVE_STATUSES
from cargo_queue.statuses import RequestStatus as S
from config.errors import DomainError
from docks import agent, calls, display, services
from docks import errors as dock_errors
from docks.models import Dock, ScreenKind
from docks.serializers import (
    AgentScreenSerializer,
    CheckInSerializer,
    DockCardSerializer,
    DockStateSerializer,
    HallSerializer,
    LedSerializer,
    OverviewSerializer,
    QueueRowSerializer,
    ScanResultSerializer,
)
from exceptions_app.models import ExceptionKind, ExceptionRecord
from warehouse.models import WarehouseTask

SCREEN_ROLES = (R.SUPERVISOR, R.ADMIN)  # the dispatcher screen; ADMIN reads only
CONTROL_ROLES = (R.SUPERVISOR,)

PREPARATION = [S.REGISTERED, S.AWAITING_PREP, S.PREP_STARTED]
WAITING_FOR_DOCK = [S.CARGO_READY, S.AWAITING_DOCK]
AT_DOCK = [S.DOCK_ASSIGNED, S.CALLED, S.ARRIVED, S.RELEASE_STARTED]
DONE = [S.EXIT_CONFIRMED, S.CLOSED]


def _minutes_since(moment) -> int:
    return max(0, int((timezone.now() - moment).total_seconds() // 60))


def _dock_card(dock: Dock) -> dict:
    current = services.occupying_request(dock)
    return {
        "id": dock.pk,
        "code": dock.code,
        "name": dock.name,
        "state": dock.state,
        "is_active": dock.is_active,
        "categories": [dc.category.code for dc in dock.dock_categories.all()],
        "agent": dock.current_agent.full_name if dock.current_agent else None,
        "agent_ready": dock.current_agent_id is not None and dock.agent_ready_at is not None,
        "request": (
            {
                "id": current.pk,
                "queue_number": current.queue_number,
                "status": current.status,
                "vehicle_plate": current.vehicle_plate,
                "category": current.category.code,
            }
            if current
            else None
        ),
    }


class OverviewView(APIView):
    permission_classes = [roles_permission(*SCREEN_ROLES)]

    @extend_schema(responses=OverviewSerializer, summary="KPI va dok kartalari")
    def get(self, request):
        today = timezone.localdate()
        by_status = dict(
            QueueRequest.objects.exclude(status__in=INACTIVE_STATUSES)
            .values_list("status")
            .annotate(n=Count("id"))
        )

        def count(statuses) -> int:
            return sum(by_status.get(s, 0) for s in statuses)

        waiting = QueueRequest.objects.filter(status__in=[*PREPARATION, *WAITING_FOR_DOCK])
        ages = [_minutes_since(r.registered_at) for r in waiting.only("registered_at")]
        kpi = {
            "registered_today": QueueRequest.objects.filter(queue_date=today).count(),
            "in_preparation": count(PREPARATION),
            "waiting_dock": count(WAITING_FOR_DOCK),
            "at_dock": count(AT_DOCK),
            "completed_today": QueueRequest.objects.filter(
                queue_date=today, status__in=DONE
            ).count(),
            # "did not come" records are expected traffic, not problems to resolve
            "open_exceptions": ExceptionRecord.objects.filter(resolved_at__isnull=True)
            .exclude(kind=ExceptionKind.NO_SHOW)
            .count(),
            "avg_wait_minutes": round(sum(ages) / len(ages)) if ages else None,
        }

        docks = [
            _dock_card(dock)
            for dock in Dock.objects.filter(is_active=True).prefetch_related(
                "dock_categories__category"
            )
        ]
        return Response(OverviewSerializer({"kpi": kpi, "docks": docks}).data)


class QueueView(APIView):
    permission_classes = [roles_permission(*SCREEN_ROLES)]

    @extend_schema(
        responses=QueueRowSerializer(many=True),
        operation_id="dispatcher_queue",
        summary="Faol navbat: ustuvorlik va kutish tartibida",
    )
    def get(self, request):
        rows = (
            QueueRequest.objects.exclude(status__in=INACTIVE_STATUSES)
            .select_related("consignee", "category", "dock", "dock__current_agent")
            .order_by("-priority", "sort_at")[:300]
        )
        latest_task = {}
        for task in WarehouseTask.objects.filter(request__in=[r.pk for r in rows]).order_by("id"):
            latest_task[task.request_id] = task.status
        free_cache: dict[int, list[str]] = {}
        result = []
        for r in rows:
            free: list[str] = []
            if r.status == S.AWAITING_DOCK:
                if r.category_id not in free_cache:
                    free_cache[r.category_id] = services.free_docks_for_category(r.category_id)
                free = free_cache[r.category_id]
            result.append(
                {
                    "id": r.pk,
                    "queue_number": r.queue_number,
                    "awb_number": r.awb_number,
                    "consignee_name": r.consignee.name,
                    "category": r.category.code,
                    "special_handling": r.category.special_handling,
                    "status": r.status,
                    "priority": r.priority,
                    "dock": r.dock.code if r.dock else None,
                    "pieces_total": r.pieces_total,
                    "vehicle_plate": r.vehicle_plate,
                    "wait_minutes": _minutes_since(r.registered_at),
                    "task_status": latest_task.get(r.pk),
                    "free_docks": free,
                    "attempts": calls.recalls_used(r) + 1 if r.status == S.CALLED else 0,
                    "recalls_left": (
                        max(0, int(get_setting("max_recalls")) - calls.recalls_used(r))
                        if r.status == S.CALLED
                        else 0
                    ),
                    "call_blockers": calls.call_blockers(r) if r.status == S.DOCK_ASSIGNED else [],
                    "remaining_pieces": closing.remaining_pieces(r),
                    "suspended_from": (
                        state_machine.suspended_from(r) if r.status == S.SUSPENDED else None
                    ),
                }
            )
        return Response(QueueRowSerializer(result, many=True).data)


class DockMaintenanceView(APIView):
    permission_classes = [roles_permission(*CONTROL_ROLES)]

    @extend_schema(
        request=DockStateSerializer,
        responses=DockCardSerializer,
        summary="Dokni ta’mirga qo‘yish yoki qaytarish",
    )
    def post(self, request, code: str):
        body = DockStateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        dock = services.set_maintenance(code, body.validated_data["maintenance"], request.user)
        return Response(DockCardSerializer(_dock_card(dock)).data)


# --- dock agent (screen 3) ---------------------------------------------------------------------

AGENT_ROLES = (R.DOCK_AGENT,)


class AgentScreenView(APIView):
    permission_classes = [roles_permission(*AGENT_ROLES)]

    @extend_schema(responses=AgentScreenSerializer, summary="Dok agenti ekrani")
    def get(self, request):
        return Response(AgentScreenSerializer(agent.me_payload(request.user)).data)


class CheckInView(APIView):
    permission_classes = [roles_permission(*AGENT_ROLES)]

    @extend_schema(
        request=CheckInSerializer,
        responses=AgentScreenSerializer,
        summary="Dokda ishga tayyorligini bildirish",
    )
    def post(self, request):
        body = CheckInSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        calls.check_in(request.user, body.validated_data["dock"])
        return Response(AgentScreenSerializer(agent.me_payload(request.user)).data)


class CheckOutView(APIView):
    permission_classes = [roles_permission(*AGENT_ROLES)]

    @extend_schema(request=None, responses=AgentScreenSerializer, summary="Dokdan chiqish")
    def post(self, request):
        calls.check_out(request.user)
        return Response(AgentScreenSerializer(agent.me_payload(request.user)).data)


class AgentScanView(APIView):
    permission_classes = [roles_permission(*AGENT_ROLES)]

    @extend_schema(
        parameters=[OpenApiParameter("code", str, description="Talon QR, AWB yoki navbat raqami")],
        responses=ScanResultSerializer,
        summary="Talonni skanerlash: o‘z dokingizdagi arizani topish",
    )
    def get(self, request):
        code = request.query_params.get("code", "").strip()
        if not code:
            raise DomainError("scan_empty", dock_errors.SCAN_EMPTY, 400)
        dock = calls.agent_dock(request.user)
        if dock is None:
            raise DomainError("agent_not_at_dock", dock_errors.AGENT_NOT_AT_DOCK, 409)
        queue = QueueRequest.objects.filter(dock=dock, status__in=agent.CURRENT_STATUSES)
        found = queue.filter(qr_token=code).first()
        if found is None and normalize_awb(code):
            found = queue.filter(awb_number=normalize_awb(code)).first()
        if found is None and code.isdigit():
            found = queue.filter(queue_number=int(code)).first()
        if found is None:
            raise DomainError("scan_not_found", dock_errors.SCAN_NOT_FOUND, 404)
        return Response(
            ScanResultSerializer(
                {"id": found.pk, "queue_number": found.queue_number, "status": found.status}
            ).data
        )


# --- public screens: no login, see docks/display.py for the access rules ---------------------


class _DisplayView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    kind = ScreenKind.HALL

    def _check(self, request, dock_code: str | None = None) -> None:
        token = request.query_params.get("token")
        if not display.authorize(request.META.get("REMOTE_ADDR"), token, self.kind, dock_code):
            raise PermissionDenied()


class DisplayHallView(_DisplayView):
    kind = ScreenKind.HALL

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "token", str, description="Ekran tokeni (ruxsat etilgan tarmoqdan tashqarida)"
            )
        ],
        responses=HallSerializer,
        summary="Zal ekrani (login talab qilinmaydi)",
    )
    def get(self, request):
        self._check(request)
        return Response(HallSerializer(display.hall_payload()).data)


class DisplayLedView(_DisplayView):
    kind = ScreenKind.DOCK_LED

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "token", str, description="Ekran tokeni (ruxsat etilgan tarmoqdan tashqarida)"
            )
        ],
        responses=LedSerializer,
        summary="Dok LED ekrani (login talab qilinmaydi)",
    )
    def get(self, request, code: str):
        code = code.upper()
        self._check(request, code)
        dock = Dock.objects.filter(code=code).first()
        if dock is None:
            raise NotFound()
        return Response(LedSerializer(display.led_payload(dock)).data)
