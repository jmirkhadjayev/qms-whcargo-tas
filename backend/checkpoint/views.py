from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode as R
from cargo_queue.models import QueueRequest
from cargo_queue.services.closing import released_pieces
from cargo_queue.statuses import RequestStatus as S
from checkpoint import errors, services
from checkpoint.models import CheckpointPass
from checkpoint.serializers import (
    CheckpointOverviewSerializer,
    CheckSummarySerializer,
    ConfirmSerializer,
    HoldSerializer,
)
from config.errors import DomainError

OFFICER = (R.CHECKPOINT,)
RECENT_LIMIT = 15


class OverviewView(APIView):
    permission_classes = [roles_permission(*OFFICER)]

    @extend_schema(
        responses=CheckpointOverviewSerializer, summary="NO‘P: kutayotganlar va bugungi o‘tishlar"
    )
    def get(self, request):
        waiting = QueueRequest.objects.filter(status=S.AWAITING_CHECKPOINT).order_by("sort_at")
        rows = []
        for r in waiting:
            released = released_pieces(r)
            rows.append(
                {
                    "id": r.pk,
                    "queue_number": r.queue_number,
                    "vehicle_plate": r.vehicle_plate,
                    "pieces_released": released,
                    "pieces_total": r.pieces_total,
                    "is_partial": released < r.pieces_total,
                }
            )
        today = timezone.localdate()
        recent = (
            CheckpointPass.objects.filter(scanned_at__date=today)
            .select_related("request", "officer")
            .order_by("-scanned_at")[:RECENT_LIMIT]
        )
        return Response(
            CheckpointOverviewSerializer(
                {
                    "waiting": rows,
                    "recent": [
                        {
                            "queue_number": p.request.queue_number,
                            "result": p.result,
                            "scanned_at": p.scanned_at,
                            "officer": p.officer.full_name,
                        }
                        for p in recent
                    ],
                }
            ).data
        )


class ScanView(APIView):
    permission_classes = [roles_permission(*OFFICER)]

    @extend_schema(
        parameters=[OpenApiParameter("code", str, description="Talon QR, AWB yoki navbat raqami")],
        responses=CheckSummarySerializer,
        summary="Talonni skanerlash",
    )
    def get(self, request):
        found = services.find_request(request.query_params.get("code", ""))
        if found is None:
            raise DomainError("request_not_found", errors.NOT_FOUND, 404)
        return Response(CheckSummarySerializer(services.summary(found)).data)


class ConfirmView(APIView):
    permission_classes = [roles_permission(*OFFICER)]

    @extend_schema(
        request=ConfirmSerializer,
        responses=CheckSummarySerializer,
        summary="Chiqishni tasdiqlash",
    )
    def post(self, request, pk: int):
        body = ConfirmSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.confirm_exit(pk, request.user, body.validated_data.get("plate_observed", ""))
        found = QueueRequest.objects.select_related("consignee", "category", "dock").get(pk=pk)
        return Response(CheckSummarySerializer(services.summary(found)).data)


class HoldView(APIView):
    permission_classes = [roles_permission(*OFFICER)]

    @extend_schema(
        request=HoldSerializer,
        responses=CheckSummarySerializer,
        summary="Tafovut bor: chiqishni to‘xtatish",
    )
    def post(self, request, pk: int):
        body = HoldSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.hold(
            pk,
            request.user,
            body.validated_data["description"],
            body.validated_data.get("plate_observed", ""),
        )
        found = QueueRequest.objects.select_related("consignee", "category", "dock").get(pk=pk)
        return Response(CheckSummarySerializer(services.summary(found)).data)
