from drf_spectacular.authentication import SessionScheme
from drf_spectacular.contrib.knox_auth_token import KnoxTokenScheme
from knox.auth import TokenAuthentication
from mozilla_django_oidc.contrib.drf import OIDCAuthentication
from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication

from api.onboarding import onedata_access_allowed

# (path, allowed methods or None for any) reachable by users without a linked Onedata account
ONBOARDING_PATHS = (
    ("/api/v1/profile/", {"GET"}),
    ("/api/v1/profile/onedata-sync/", {"POST"}),
    ("/api/token/logout/", None),
    ("/api/schema/", None),
    ("/api/schema/swagger-ui/", None),
)


def is_onboarding_path(path, method):
    return any(path == p and (methods is None or method in methods) for p, methods in ONBOARDING_PATHS)


class OnedataGateMixin:
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _ = result
            if not onedata_access_allowed(user) and not is_onboarding_path(request.path, request.method):
                raise exceptions.PermissionDenied(
                    detail={"code": "onedata_not_linked",
                            "detail": "Link your Onedata account in DAREG onboarding first."})
        return result


class GatedOIDCAuthentication(OnedataGateMixin, OIDCAuthentication):
    pass


class GatedKnoxTokenAuthentication(OnedataGateMixin, TokenAuthentication):
    pass


class GatedSessionAuthentication(OnedataGateMixin, SessionAuthentication):
    pass


# drf-spectacular matches auth extensions by exact class, keep the OpenAPI security schemes
class GatedKnoxTokenScheme(KnoxTokenScheme):
    target_class = GatedKnoxTokenAuthentication


class GatedSessionScheme(SessionScheme):
    target_class = GatedSessionAuthentication
