from django.contrib import admin

from .models import GuideImage, GuideStep, RepairGuide, System, WiringDiagram


class GuideStepInline(admin.TabularInline):
    model = GuideStep
    extra = 1


class GuideImageInline(admin.TabularInline):
    model = GuideImage
    extra = 1


@admin.register(System)
class SystemAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(RepairGuide)
class RepairGuideAdmin(admin.ModelAdmin):
    list_display = ["title", "system", "vehicle", "make", "model", "updated_at"]
    list_filter = ["system", "make"]
    search_fields = ["title", "summary", "vehicle__vin"]
    autocomplete_fields = ["vehicle", "make", "model", "dtc_codes"]
    inlines = [GuideStepInline, GuideImageInline]


@admin.register(WiringDiagram)
class WiringDiagramAdmin(admin.ModelAdmin):
    list_display = ["title", "system", "vehicle", "make", "model", "uploaded_at"]
    list_filter = ["system", "make"]
    search_fields = ["title", "description"]
    autocomplete_fields = ["vehicle", "make", "model"]
