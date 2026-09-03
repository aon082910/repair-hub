from django.contrib import admin

from .models import DTCCode


@admin.register(DTCCode)
class DTCCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "description", "system", "origin", "make"]
    list_filter = ["system", "origin", "make"]
    search_fields = ["code", "description"]
