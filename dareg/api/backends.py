import re
from urllib import response
from django.contrib.auth.models import User
from rest_framework import pagination
from django.conf import settings
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from .models import UserProfile
from rest_framework.response import Response


class DAREG_OIDCAuthenticationBackend(OIDCAuthenticationBackend):
    @staticmethod
    def is_sub(sub):
        """
        Check if sub string returned by OIDC proveder is in the appropriate form,
        e.g. '323969@muni.cz'.
        """
        pattern = r"^\d+@\w+\.\w+$"
        return bool(re.match(pattern, sub))

    def verify_username(self, sub):
        """
        Verify if username is in the appropriate form.
        """
        return self.is_sub(sub)

    def verify_claims(self, claims):
        """
        Verify if user is authorized to login according to OIDC claims.
        """
        verified = super(DAREG_OIDCAuthenticationBackend, self).verify_claims(claims)
        if not verified:
            print("login failed, OIDC claims not verified")
            return False

        return True

        # test if all OIDC claims are present
        if (
            not "eduperson_entitlement" in claims
            or not "sub" in claims
            or not "given_name" in claims
            or not "family_name" in claims
            or not "email" in claims
        ):
            print("login failed, not all OIDC claimes")
            return False

        # verify username
        if not self.verify_username(self, claims.get("sub")):
            print("login failed, not valid username (%s)" % claims.get("sub"))
            return False

        # check if access group is defined
        if settings.OIDC_ALLOWED_EDUPERSON_ENTITLEMENT.lower() == "none":
            return True
        else:
            # user has to be a member of access group
            if settings.OIDC_ALLOWED_EDUPERSON_ENTITLEMENT in claims.get(
                "eduperson_entitlement", []
            ):
                return True
            else:
                print("login failed, not allowed group (sub: %s)" % claims.get("sub"))
                return False

    def filter_users_by_claims(self, claims):
        """
        Matching Django user to identity returned by OIDC provider by OIDC claim 'sub'.
        """
        sub = claims.get("sub")
        if not sub:
            return self.UserModel.objects.none()

        try:
            user = User.objects.get(username=sub)
            return [user]

        except User.DoesNotExist:
            return self.UserModel.objects.none()

    def create_UserProfile(self, user, full_name):
        """
        Create UserProfile for a new user.
        """
        if not UserProfile.objects.filter(user=user).exists():
            user_profile = UserProfile.objects.create(user=user, full_name=full_name)
            if user_profile:
                print("login - UserProfile created (%s)" % user.username)
            else:
                print("login - UserProfile can't be created (%s)" % user.username)

    def create_user(self, claims):
        """
        Create user while her/his first login.
        """
        user = super(DAREG_OIDCAuthenticationBackend, self).create_user(claims)
        sub = claims.get("sub", "")
        user.username = sub
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.email = claims.get("email", "")
        user.save()
        self.create_UserProfile(user, claims.get("full_name", ""))
        return user

    def update_user(self, user, claims):
        """
        Update user details.
        """
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.email = claims.get("email", "")
        user.save()
        try:
            user_profile = UserProfile.objects.get(user=user)
            user_profile.full_name = claims.get("name", "")
            user_profile.save()
        except UserProfile.DoesNotExist:
            print("login - UserProfile can't be updated (%s)" % user.username)

        return user


class CustomPagination(pagination.PageNumberPagination):
    def get_paginated_response(self, data):
        return Response(
            {
                "links": {
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                },
                "count": self.page.paginator.count,
                "results": data,
            }
        )
