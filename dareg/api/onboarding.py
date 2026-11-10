from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def validate_onedata_settings(config=settings):
    if config.ONEDATA_REQUIRED and not config.ONEDATA_AUTO_LINK_ENABLED:
        raise ImproperlyConfigured("ONEDATA_REQUIRED needs ONEDATA_AUTO_LINK_ENABLED")


def onedata_access_allowed(user) -> bool:
    if not settings.ONEDATA_REQUIRED:
        return True
    if not user or not user.is_authenticated:
        return True  # anonymous handling is left to the views' permission classes
    if user.is_superuser or hasattr(user, "instrument"):
        return True
    profile = getattr(user, "userprofile", None)
    return bool(profile and profile.onedata_user_id)
