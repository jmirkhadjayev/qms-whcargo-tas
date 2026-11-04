from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode as R
from cargo_queue.awb import normalize_awb
from cargo_queue.models import QueueRequest
from cargo_queue.statuses import INACTIVE_STATUSES
from config.errors import DomainError
from warehouse import errors, services
from warehouse.models import WarehouseTask
from warehouse.models import WarehouseTaskStatus as T
from warehouse.serializers import (
    ProblemSerializer,
    StartTaskSerializer,
    WarehouseTaskSerializer,
)

VIEW_ROLES = (R.WAREHOUSE, R.SUPERVISOR)
WORK_ROLES = (R.WAREHOUSE,)

ACTIVE_TASK_STATUSES = [T.NEW, T.IN_PROGRESS, T.READY, T.PROBLEM]


def _tasks():
    return WarehouseTask.objects.select_related(
        "request", "request__category", "request__dock", "assigned_to"
    )


class TaskListView(APIView):
    permission_classes = [roles_permission(*VIEW_ROLES)]

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, description="Topshiriq holatlari, vergul bilan"),
            OpenApiParameter("q", str, description="AWB yoki navbat raqami"),
        ],
        responses=WarehouseTaskSerializer(many=True),
        operation_id="warehouse_tasks_list",
        summary="Ombor topshiriqlari",
    )
    def get(self, request):
        statuses = [s for s in request.query_params.get("status", "").split(",") if s]
        queryset = _tasks().exclude(request__status__in=INACTIVE_STATUSES)
        queryset = queryset.filter(status__in=statuses or ACTIVE_TASK_STATUSES)
        term = request.query_params.get("q", "").strip()
        if term:
            condition = Q(request__awb_number__icontains=term)
            if term.isdigit():
                condition |= Q(request__queue_number=int(term))
            queryset = queryset.filter(condition)
        queryset = queryset.order_by("-request__priority", "request__sort_at", "created_at")
        return Response(WarehouseTaskSerializer(queryset[:200], many=True).data)


class TaskScanView(APIView):
    permission_classes = [roles_permission(*VIEW_ROLES)]

    @extend_schema(
        parameters=[OpenApiParameter("code", str, description="Talon QR, AWB yoki navbat raqami")],
        responses=WarehouseTaskSerializer,
        summary="Skanerlash: topshiriqni kod bo‘yicha topish",
    )
    def get(self, request):
        code = request.query_params.get("code", "").strip()
        if not code:
            raise DomainError("scan_empty", errors.SCAN_EMPTY, 400)
        requests = QueueRequest.objects.exclude(status__in=INACTIVE_STATUSES)
        found = requests.filter(qr_token=code).first()
        if found is None and normalize_awb(code):
            found = requests.filter(awb_number=normalize_awb(code)).first()
        if found is None and code.isdigit():
            found = requests.order_by("-queue_date").filter(queue_number=int(code)).first()
        task = None
        if found is not None:
            tasks = _tasks().filter(request=found).order_by("-created_at")
            # Prefer the task still in progress; fall back to the latest one.
            task = tasks.exclude(status=T.HANDED_OVER).first() or tasks.first()
        if task is None:
            raise DomainError("task_not_found", errors.TASK_NOT_FOUND, 404)
        return Response(WarehouseTaskSerializer(task).data)


class _TaskActionView(APIView):
    permission_classes = [roles_permission(*WORK_ROLES)]


class TaskStartView(_TaskActionView):
    @extend_schema(
        request=StartTaskSerializer,
        responses=WarehouseTaskSerializer,
        summary="Tayyorlashni boshlash",
    )
    def post(self, request, pk: int):
        body = StartTaskSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.start_task(pk, request.user, body.validated_data.get("storage_location"))
        return Response(WarehouseTaskSerializer(_tasks().get(pk=pk)).data)


class TaskReadyView(_TaskActionView):
    @extend_schema(request=None, responses=WarehouseTaskSerializer, summary="Yuk tayyor")
    def post(self, request, pk: int):
        services.mark_ready(pk, request.user)
        return Response(WarehouseTaskSerializer(_tasks().get(pk=pk)).data)


class TaskProblemView(_TaskActionView):
    @extend_schema(
        request=ProblemSerializer, responses=WarehouseTaskSerializer, summary="Muammoni qayd etish"
    )
    def post(self, request, pk: int):
        body = ProblemSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        services.report_problem(
            pk, request.user, data["kind"], data["description"], data["pieces_affected"]
        )
        return Response(WarehouseTaskSerializer(_tasks().get(pk=pk)).data)


class TaskHandOverView(_TaskActionView):
    @extend_schema(request=None, responses=WarehouseTaskSerializer, summary="Dokka topshirildi")
    def post(self, request, pk: int):
        services.hand_over(pk, request.user)
        return Response(WarehouseTaskSerializer(_tasks().get(pk=pk)).data)
