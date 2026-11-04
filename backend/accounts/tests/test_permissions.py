import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from accounts.permissions import roles_permission
from accounts.roles import RoleCode

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


def make_view(*codes: RoleCode):
    class View(APIView):
        permission_classes = [roles_permission(*codes)]

        def get(self, request):
            return Response({"ok": True})

    return View.as_view()


def call(view, user=None):
    request = factory.get("/x")
    if user is not None:
        from rest_framework.test import force_authenticate

        force_authenticate(request, user=user)
    return view(request)


@pytest.mark.parametrize("role", list(RoleCode))
def test_every_role_allowed_only_where_listed(role, make_user):
    user = make_user(role)
    for allowed_role in RoleCode:
        response = call(make_view(allowed_role), user)
        expected = 200 if role == allowed_role else 403
        assert response.status_code == expected, (role, allowed_role)


def test_admin_is_not_implicitly_allowed(make_user):
    admin = make_user(RoleCode.ADMIN)
    assert call(make_view(RoleCode.REG_AGENT), admin).status_code == 403


def test_multiple_roles_allowed(make_user):
    view = make_view(RoleCode.SUPERVISOR, RoleCode.MANAGER)
    assert call(view, make_user(RoleCode.MANAGER)).status_code == 200
    assert call(view, make_user(RoleCode.SUPERVISOR, username="s")).status_code == 200
    assert call(view, make_user(RoleCode.DOCK_AGENT)).status_code == 403


def test_anonymous_denied():
    assert call(make_view(RoleCode.ADMIN)).status_code in (401, 403)


def test_inactive_user_denied(make_user):
    user = make_user(RoleCode.ADMIN)
    user.is_active = False
    assert call(make_view(RoleCode.ADMIN), user).status_code == 403
