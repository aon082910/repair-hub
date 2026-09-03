from .models import ActivityLogEntry


def log_activity(user, action, obj=None):
    ActivityLogEntry.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action,
        object_repr=str(obj) if obj is not None else "",
    )
