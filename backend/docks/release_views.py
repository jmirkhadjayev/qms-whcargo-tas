"""Release actions at the dock (screen 3): start, count, finish, partial, problem."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode as R
from cargo_queue.models import QueueRequest
from cargo_queue.serializers import QueueRequestDetailSerializer
from config.errors import DomainError
from docks import release
from docks.errors import PARTIAL_REASONS
from exceptions_app import services as exception_services
from exceptions_app.serializers import ExceptionSerializer, ReportSerializer

AGENT = (R.DOCK_AGENT,)


class ProgressSerializer(serializers.Serializer):
    pieces_released = serializers.IntegerField(min_value=0)


class FinishSerializer(serializers.Serializer):
    weight_released_kg = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False
    )


class PartialSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=list(PARTIAL_REASONS))
    comment = serializers.CharField(max_length=2000)


def _detail(pk: int) -> dict:
    request = QueueRequest.objects.select_related(
        "consignee", "category", "shift", "dock", "permit"
    ).get(pk=pk)
    return QueueRequestDetailSerializer(request).data


class StartView(APIView):
    permission_classes = [roles_permission(*AGENT)]

    @extend_schema(
        request=None, responses=QueueRequestDetailSerializer, summary="Berishni boshlash"
    )
    def post(self, request, pk: int):
        release.start(pk, request.user)
        return Response(_detail(pk))


class ProgressView(APIView):
    permission_classes = [roles_permission(*AGENT)]

    @extend_schema(
        request=ProgressSerializer,
        responses=QueueRequestDetailSerializer,
        summary="Berilgan o‘rinlar sonini belgilash",
    )
    def post(self, request, pk: int):
        body = ProgressSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        release.set_progress(pk, request.user, body.validated_data["pieces_released"])
        return Response(_detail(pk))


class FinishView(APIView):
    permission_classes = [roles_permission(*AGENT)]

    @extend_schema(
        request=FinishSerializer,
        responses=QueueRequestDetailSerializer,
        summary="Yakunlash: hamma o‘rinlar berildi",
    )
    def post(self, request, pk: int):
        body = FinishSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        release.finish_full(pk, request.user, body.validated_data.get("weight_released_kg"))
        return Response(_detail(pk))


class PartialView(APIView):
    permission_classes = [roles_permission(*AGENT)]

    @extend_schema(
        request=PartialSerializer,
        responses=QueueRequestDetailSerializer,
        summary="Qisman berish (sabab va izoh majburiy)",
    )
    def post(self, request, pk: int):
        body = PartialSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        release.finish_partial(
            pk, request.user, body.validated_data["reason"], body.validated_data["comment"]
        )
        return Response(_detail(pk))


class ProblemView(APIView):
    """Dock agent (own dock) or supervisor reports a problem with a request."""

    permission_classes = [roles_permission(R.DOCK_AGENT, R.SUPERVISOR)]

    @extend_schema(
        request=ReportSerializer,
        responses={201: ExceptionSerializer},
        summary="Muammoni qayd etish",
    )
    def post(self, request, pk: int):
        body = ReportSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if request.user.role.code == R.DOCK_AGENT:
            record = release.report_problem(
                pk, request.user, data["kind"], data["description"], data["pieces_affected"]
            )
        else:
            target = QueueRequest.objects.filter(pk=pk).first()
            if target is None:
                raise DomainError("request_not_found", "Ariza topilmadi.", 404)
            record = exception_services.report(
                target, data["kind"], data["description"], request.user, data["pieces_affected"]
            )
        return Response(ExceptionSerializer(record).data, status=201)
