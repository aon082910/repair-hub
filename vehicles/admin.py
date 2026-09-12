from django.contrib import admin

from .models import Make, MaintenanceReminder, Vehicle, VehicleModel


@admin.register(Make)
class MakeAdmin(admin.ModelAdmin):
    search_fields = ["name"]


@admin.register(VehicleModel)
class VehicleModelAdmin(admin.ModelAdmin):
    list_display = ["name", "make"]
    list_filter = ["make"]
    search_fields = ["name", "make__name"]


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["__str__", "vin", "owner", "open_recall_count", "created_at"]
    list_filter = ["make", "year"]
    search_fields = ["vin", "make__name", "model__name", "owner__name"]
    autocomplete_fields = ["make", "model", "owner"]


@admin.register(MaintenanceReminder)
class MaintenanceReminderAdmin(admin.ModelAdmin):
    list_display = ["description", "vehicle", "due_date", "due_mileage", "completed"]
    list_filter = ["completed"]
    search_fields = ["description", "vehicle__vin"]
    autocomplete_fields = ["vehicle"]
