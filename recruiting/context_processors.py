from django.conf import settings

from .models import Notification


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_count"] = Notification.objects.filter(user=user, read_at__isnull=True).count()
    return ctx
