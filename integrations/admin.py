from django.contrib import admin

from .models import AllDataAttachment, AllDataLink


@admin.register(AllDataLink)
class AllDataLinkAdmin(admin.ModelAdmin):
    list_display = ["label", "vehicle", "url", "created_at"]
    search_fields = ["label", "vehicle__vin"]
    autocomplete_fields = ["vehicle"]


@admin.register(AllDataAttachment)
class AllDataAttachmentAdmin(admin.ModelAdmin):
    list_display = ["__str__", "vehicle", "work_order", "uploaded_at"]
    autocomplete_fields = ["vehicle", "work_order"]
