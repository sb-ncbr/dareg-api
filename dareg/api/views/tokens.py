from knox import views as knox_views

from api.authentication import GatedKnoxTokenAuthentication
from api.permissions import IsSuperuser


class SuperuserLoginView(knox_views.LoginView):
    permission_classes = [IsSuperuser]


class SuperuserLogoutAllView(knox_views.LogoutAllView):
    authentication_classes = [GatedKnoxTokenAuthentication]
    permission_classes = [IsSuperuser]
