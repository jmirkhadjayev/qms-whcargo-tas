from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit import services as audit
from audit.models import AuditAction

from . import errors
from .serializers import LoginSerializer, UserSerializer


class CsrfView(APIView):
    """Sets the CSRF cookie so the SPA can send X-CSRFToken on the following requests."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        responses=inline_serializer("CsrfResponse", {"csrf_token": serializers.CharField()})
    )
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


# Login is CSRF-protected even for anonymous callers (DRF only enforces CSRF when authenticated).
@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={200: UserSerializer, 400: OpenApiResponse(description="Login yoki parol xato")},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            audit.log(
                AuditAction.LOGIN_FAILED,
                "users",
                new_value={"username": serializer.validated_data["username"][:150]},
                ip=audit.client_ip(request),
            )
            return Response(
                {"detail": errors.INVALID_CREDENTIALS, "code": "invalid_credentials"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        audit.log(AuditAction.LOGIN, "users", user.pk, user=user, ip=audit.client_ip(request))
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)
