from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode as R
from exceptions_app import services
from exceptions_app.models import ExceptionKind, ExceptionRecord
from exceptions_app.serializers import ExceptionSerializer, ResolveSerializer

READ_ROLES = (R.SUPERVISOR, R.ADMIN)
DECIDE_ROLES = (R.SUPERVISOR,)


class ExceptionListView(APIView):
    permission_classes = [roles_permission(*READ_ROLES)]

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, description="open (standart), resolved yoki all"),
            OpenApiParameter("kind", str, description="Istisno turi"),
        ],
        responses=ExceptionSerializer(many=True),
        operation_id="exceptions_list",
        summary="Istisnolar ro‘yxati",
    )
    def get(self, request):
        queryset = ExceptionRecord.objects.select_related(
            "request", "reported_by", "resolved_by"
        ).order_by("-reported_at")
        state = request.query_params.get("status", "open")
        if state == "open":
            queryset = queryset.filter(resolved_at__isnull=True)
        elif state == "resolved":
            queryset = queryset.filter(resolved_at__isnull=False)
        kind = request.query_params.get("kind")
        if kind:
            queryset = queryset.filter(kind=kind)
        else:
            # "Did not come" records are bookkeeping, not problems to decide on.
            queryset = queryset.exclude(kind=ExceptionKind.NO_SHOW)
        return Response(ExceptionSerializer(queryset[:200], many=True).data)


class ExceptionResolveView(APIView):
    permission_classes = [roles_permission(*DECIDE_ROLES)]

    @extend_schema(
        request=ResolveSerializer,
        responses=ExceptionSerializer,
        summary="Istisnoni hal qilish (hujjatlashtirilgan qaror)",
    )
    def post(self, request, pk: int):
        body = ResolveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        record = services.resolve(pk, body.validated_data["resolution"], request.user)
        record = ExceptionRecord.objects.select_related(
            "request", "reported_by", "resolved_by"
        ).get(pk=record.pk)
        return Response(ExceptionSerializer(record).data)
