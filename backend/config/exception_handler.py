"""API error format: {"detail": <Uzbek text>, "code": <machine code>} (decision K26).

DRF's English default messages are replaced with Uzbek ones; field validation errors keep the
usual {"field": ["message"]} shape with translated messages.
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.exceptions import ErrorDetail
from rest_framework.response import Response
from rest_framework.views import exception_handler

from accounts import errors

from .errors import DomainError

_MESSAGES: dict[type[Exception], str] = {
    exceptions.NotAuthenticated: errors.NOT_AUTHENTICATED,
    exceptions.AuthenticationFailed: errors.NOT_AUTHENTICATED,
    exceptions.PermissionDenied: errors.PERMISSION_DENIED,
    exceptions.NotFound: errors.NOT_FOUND,
    exceptions.MethodNotAllowed: errors.METHOD_NOT_ALLOWED,
    exceptions.Throttled: errors.TOO_MANY_REQUESTS,
    exceptions.ParseError: errors.PARSE_ERROR,
}

# DRF validation error codes -> Uzbek text. Custom codes (e.g. "invalid_phone") keep their own text.
_VALIDATION_MESSAGES = {
    "required": errors.FIELD_REQUIRED,
    "blank": errors.FIELD_REQUIRED,
    "null": errors.FIELD_REQUIRED,
    "invalid": errors.FIELD_INVALID,
    "invalid_choice": errors.FIELD_INVALID_CHOICE,
    "does_not_exist": errors.FIELD_DOES_NOT_EXIST,
    "incorrect_type": errors.FIELD_INVALID,
    "max_length": errors.FIELD_TOO_LONG,
    "min_length": errors.FIELD_TOO_SHORT,
    "max_value": errors.FIELD_TOO_BIG,
    "min_value": errors.FIELD_TOO_SMALL,
    "max_digits": errors.FIELD_NUMBER_FORMAT,
    "max_decimal_places": errors.FIELD_NUMBER_FORMAT,
    "max_whole_digits": errors.FIELD_NUMBER_FORMAT,
    "max_string_length": errors.FIELD_NUMBER_FORMAT,
    "date": errors.FIELD_INVALID,
    "datetime": errors.FIELD_INVALID,
    "not_a_list": errors.FIELD_INVALID,
    "empty": errors.FIELD_REQUIRED,
}


def _translate(detail: Any) -> Any:
    if isinstance(detail, dict):
        return {key: _translate(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_translate(value) for value in detail]
    if isinstance(detail, ErrorDetail):
        return _VALIDATION_MESSAGES.get(detail.code or "", str(detail))
    return detail


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response(
            {"detail": exc.message, "code": exc.code, **exc.extra}, status=exc.status_code
        )

    response = exception_handler(exc, context)
    if response is None:
        return response

    if isinstance(exc, exceptions.ValidationError):
        response.data = _translate(response.data)
        return response

    # DRF turns Django's Http404 / PermissionDenied into API exceptions before this point.
    if isinstance(exc, Http404):
        message: str | None = errors.NOT_FOUND
    elif isinstance(exc, DjangoPermissionDenied):
        message = errors.PERMISSION_DENIED
    else:
        message = _MESSAGES.get(type(exc))
    if message is not None:
        # Keep the original code so the frontend can branch on it; only the text changes.
        code = getattr(exc, "default_code", "error")
        return Response(
            {"detail": message, "code": code},
            status=response.status_code,
            headers=dict(response.items()),
        )
    return response
