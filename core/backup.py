"""Shared list of app labels included in a business-data backup (used by
both the on-demand download and the scheduled snapshot command). Uploaded
media (photos, diagrams, attachments) is never included -- back up the
/config volume itself for that."""
BACKUP_APPS = [
    "auth.User",
    "vehicles",
    "diagnostics",
    "repairguides",
    "shop",
    "integrations",
    "core.Favorite",
]
