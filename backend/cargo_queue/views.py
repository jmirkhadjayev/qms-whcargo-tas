from __future__ import annotations

import datetime as dt

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode as R
from audit import services as audit
from audit.models import AuditAction
from cargo_queue import errors
from cargo_queue.awb import normalize_awb
from cargo_queue.models import CargoCategory, QueueRequest, Shift, Ticket
from cargo_queue.serializers import (
    AssignDockSerializer,
    LookupsSerializer,
    ManualVerifySerializer,
    PaginatedQueueRequestSerializer,
    PermitCheckResultSerializer,
    PermitCheckSerializer,
    PrioritySerializer,
    QueueRequestDetailSerializer,
    QueueRequestSerializer,
    ReasonSerializer,
    RegisterRequestSerializer,
    RegistrationResponseSerializer,
    TicketDataSerializer,
    TransitionSerializer,
    ticket_data,
)
from cargo_queue.services import permits, priority, registration, state_machine
from cargo_queue.statuses import RequestStatus as S
from config.errors import DomainError
from docks import calls
from docks.models import Dock

# Who may call what. ADMIN is listed explicitly wherever it is allowed (decision K23).
OPERATIONAL_READ = (R.REG_AGENT, R.WAREHOUSE, R.DOCK_AGENT, R.SUPERVISOR, R.CHECKPOINT, R.ADMIN)
PERMIT_CHECK_ROLES = (R.REG_AGENT, R.SUPERVISOR)
MANUAL_VERIFY_ROLES = (R.SUPERVISOR, R.ADMIN)
REGISTER_ROLES = (R.REG_AGENT,)
TRANSITION_ROLES = (R.WAREHOUSE, R.DOCK_AGENT, R.SUPERVISOR, R.CHECKPOINT, R.ADMIN)
TICKET_ROLES = (R.REG_AGENT, R.SUPERVISOR)


def _ip(request) -> str | None:
    return audit.client_ip(request)


class RequestPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class PermitCheckView(APIView):
    permission_classes = [roles_permission(*PERMIT_CHECK_ROLES)]

    @extend_schema(
        request=PermitCheckSerializer,
        responses=PermitCheckResultSerializer,
        summary="Ruxsatnomani tekshirish",
    )
    def post(self, request):
        serializer = PermitCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw = serializer.validated_data["awb_number"]
        result = permits.check_permit(raw, request.user, _ip(request))
        permit = result.permit
        return Response(
            {
                "verified": result.verified,
                "awb_number": normalize_awb(raw),
                "reason": result.reason,
                "permit": (
                    {
                        "id": permit.pk,
                        "permit_number": permit.permit_number,
                        "source": permit.source,
                        "valid_until": permit.valid_until,
                    }
                    if permit
                    else None
                ),
            }
        )


class ManualVerifyView(APIView):
    permission_classes = [roles_permission(*MANUAL_VERIFY_ROLES)]

    @extend_schema(
        request=ManualVerifySerializer,
        responses=PermitCheckResultSerializer,
        summary="Ruxsatnomani qo‘lda tasdiqlash",
    )
    def post(self, request):
        serializer = ManualVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        permit = permits.manual_verify(
            data["awb_number"],
            data["permit_number"],
            data.get("valid_until"),
            request.user,
            _ip(request),
        )
        return Response(
            {
                "verified": True,
                "awb_number": permit.awb_number,
                "reason": "",
                "permit": {
                    "id": permit.pk,
                    "permit_number": permit.permit_number,
                    "source": permit.source,
                    "valid_until": permit.valid_until,
                },
            },
            status=status.HTTP_201_CREATED,
        )


def _parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({"date": [errors.FILTER_DATE_INVALID]}, code="invalid_date") from None


class QueueRequestListCreateView(APIView):
    def get_permissions(self):
        roles = REGISTER_ROLES if self.request.method == "POST" else OPERATIONAL_READ
        return [roles_permission(*roles)()]

    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.DATE, description="Navbat sanasi (YYYY-MM-DD)"),
            OpenApiParameter("status", str, description="Holat kodlari, vergul bilan"),
            OpenApiParameter("dock", str, description="Dok kodi (D-01)"),
            OpenApiParameter("category", str, description="Toifa kodi (GEN)"),
            OpenApiParameter("shift", int, description="Smena ID"),
            OpenApiParameter("q", str, description="AWB yoki navbat raqami"),
        ],
        responses=PaginatedQueueRequestSerializer,
        operation_id="requests_list",
        summary="Arizalar ro‘yxati",
    )
    def get(self, request):
        queryset = QueueRequest.objects.select_related("consignee", "category", "shift", "dock")
        params = request.query_params
        if params.get("date"):
            queryset = queryset.filter(queue_date=_parse_date(params["date"]))
        if params.get("status"):
            queryset = queryset.filter(status__in=[s for s in params["status"].split(",") if s])
        if params.get("dock"):
            queryset = queryset.filter(dock__code=params["dock"])
        if params.get("category"):
            queryset = queryset.filter(category__code=params["category"])
        if params.get("shift"):
            queryset = queryset.filter(shift_id=params["shift"])
        if params.get("q"):
            term = params["q"].strip()
            condition = Q(awb_number__icontains=term)
            if term.isdigit():
                condition |= Q(queue_number=int(term))
            queryset = queryset.filter(condition)
        paginator = RequestPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(QueueRequestSerializer(page, many=True).data)

    @extend_schema(
        request=RegisterRequestSerializer,
        responses={201: RegistrationResponseSerializer},
        summary="Ariza yaratish va talon berish",
    )
    def post(self, request):
        serializer = RegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queue_request = registration.register_request(
            registration.RegistrationData(
                awb_number=data["awb_number"],
                consignee_name=data["consignee_name"].strip(),
                consignee_tin=data.get("consignee_tin"),
                representative_name=data.get("representative_name", "").strip(),
                sms_phone=data["sms_phone"],
                pieces_total=data["pieces_total"],
                weight_kg=data["weight_kg"],
                category=data["category"],
                vehicle_plate=data.get("vehicle_plate", ""),
                notes=data.get("notes", ""),
            ),
            request.user,
            ip=_ip(request),
        )
        ticket = queue_request.tickets.order_by("-id").first()
        assert ticket is not None  # created in the same transaction
        payload = QueueRequestDetailSerializer(queue_request).data
        payload["ticket"] = ticket_data(queue_request, ticket)
        return Response(payload, status=status.HTTP_201_CREATED)


def _get_request(pk: int) -> QueueRequest:
    return get_object_or_404(
        QueueRequest.objects.select_related("consignee", "category", "shift", "dock", "permit"),
        pk=pk,
    )


class QueueRequestDetailView(APIView):
    permission_classes = [roles_permission(*OPERATIONAL_READ)]

    @extend_schema(responses=QueueRequestDetailSerializer, summary="Ariza va uning tarixi")
    def get(self, request, pk: int):
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class TransitionView(APIView):
    permission_classes = [roles_permission(*TRANSITION_ROLES)]

    @extend_schema(
        request=TransitionSerializer,
        responses=QueueRequestDetailSerializer,
        summary="Ariza holatini o‘zgartirish",
    )
    def post(self, request, pk: int):
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queue_request = _get_request(pk)
        state_machine.transition(
            queue_request,
            serializer.validated_data["to_status"],
            request.user,
            serializer.validated_data.get("reason"),
        )
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class AssignDockView(APIView):
    permission_classes = [roles_permission(R.SUPERVISOR)]

    @extend_schema(
        request=AssignDockSerializer,
        responses=QueueRequestDetailSerializer,
        summary="Dok belgilash (AWAITING_DOCK -> DOCK_ASSIGNED)",
    )
    def post(self, request, pk: int):
        body = AssignDockSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        state_machine.transition(
            _get_request(pk),
            S.DOCK_ASSIGNED,
            request.user,
            extra={"dock": body.validated_data["dock"].strip().upper()},
        )
        # The system calls the customer at once if cargo, dock and staff are ready (TZ 3.4);
        # otherwise the request waits and is called as soon as they are.
        calls.try_call(_get_request(pk))
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class ResumeView(APIView):
    permission_classes = [roles_permission(R.SUPERVISOR)]

    @extend_schema(
        request=ReasonSerializer,
        responses=QueueRequestDetailSerializer,
        summary="To‘xtatilgan arizani oldingi holatiga qaytarish",
    )
    def post(self, request, pk: int):
        body = ReasonSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        queue_request = _get_request(pk)
        target = state_machine.suspended_from(queue_request)
        if queue_request.status != S.SUSPENDED or target is None:
            raise DomainError("not_suspended", errors.NOT_SUSPENDED, 409)
        state_machine.transition(queue_request, target, request.user, body.validated_data["reason"])
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class CallView(APIView):
    permission_classes = [roles_permission(R.SUPERVISOR)]

    @extend_schema(
        request=None, responses=QueueRequestDetailSerializer, summary="Mijozni chaqirish"
    )
    def post(self, request, pk: int):
        calls.call(pk, request.user)
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class RecallView(APIView):
    permission_classes = [roles_permission(R.DOCK_AGENT, R.SUPERVISOR)]

    @extend_schema(
        request=None, responses=QueueRequestDetailSerializer, summary="Takroriy chaqiruv"
    )
    def post(self, request, pk: int):
        calls.recall(pk, request.user)
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class ArriveView(APIView):
    permission_classes = [roles_permission(R.DOCK_AGENT)]

    @extend_schema(
        request=None, responses=QueueRequestDetailSerializer, summary="Mijoz yetib keldi"
    )
    def post(self, request, pk: int):
        calls.arrive(pk, request.user)
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class PriorityView(APIView):
    permission_classes = [roles_permission(R.SUPERVISOR)]

    @extend_schema(
        request=PrioritySerializer,
        responses=QueueRequestDetailSerializer,
        summary="Ustuvorlikni belgilash",
    )
    def post(self, request, pk: int):
        body = PrioritySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        get_object_or_404(QueueRequest, pk=pk)
        priority.set_priority(
            pk,
            body.validated_data["priority"],
            request.user,
            body.validated_data.get("reason", ""),
        )
        return Response(QueueRequestDetailSerializer(_get_request(pk)).data)


class TicketView(APIView):
    permission_classes = [roles_permission(*TICKET_ROLES)]

    @extend_schema(responses=TicketDataSerializer, summary="Talon ma’lumotlari (chop etish uchun)")
    def get(self, request, pk: int):
        queue_request = _get_request(pk)
        ticket = queue_request.tickets.order_by("-id").first()
        if ticket is None:
            raise DomainError("ticket_missing", errors.REQUEST_NOT_FOUND, 404)
        return Response(ticket_data(queue_request, ticket))


class TicketReprintView(APIView):
    permission_classes = [roles_permission(*TICKET_ROLES)]

    @extend_schema(
        request=None, responses={201: TicketDataSerializer}, summary="Talonni qayta chop etish"
    )
    def post(self, request, pk: int):
        queue_request = _get_request(pk)
        ticket = Ticket.objects.create(
            request=queue_request, printed_by=request.user, is_reprint=True
        )
        audit.log(
            AuditAction.REPRINT,
            "tickets",
            ticket.pk,
            user=request.user,
            new_value={"request_id": queue_request.pk},
            ip=_ip(request),
        )
        return Response(ticket_data(queue_request, ticket), status=status.HTTP_201_CREATED)


class LookupsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LookupsSerializer, summary="Ma’lumotnomalar: toifa, smena, dok")
    def get(self, request):
        return Response(
            LookupsSerializer(
                {
                    "categories": CargoCategory.objects.all(),
                    "shifts": Shift.objects.all(),
                    "docks": Dock.objects.filter(is_active=True),
                }
            ).data
        )
