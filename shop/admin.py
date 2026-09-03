from django.contrib import admin

from .models import (
    ActivityLogEntry,
    Appointment,
    Customer,
    Estimate,
    EstimateLaborLine,
    EstimatePartLine,
    Inspection,
    InspectionItem,
    InventoryPart,
    Invoice,
    LaborLine,
    PartLine,
    PaymentRecord,
    ShopSettings,
    Technician,
    TimeEntry,
    WorkOrder,
)


class LaborLineInline(admin.TabularInline):
    model = LaborLine
    extra = 1


class PartLineInline(admin.TabularInline):
    model = PartLine
    extra = 1


class EstimateLaborLineInline(admin.TabularInline):
    model = EstimateLaborLine
    extra = 1


class EstimatePartLineInline(admin.TabularInline):
    model = EstimatePartLine
    extra = 1


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "email", "tax_exempt"]
    list_filter = ["tax_exempt"]
    search_fields = ["name", "phone", "email"]


@admin.register(ShopSettings)
class ShopSettingsAdmin(admin.ModelAdmin):
    list_display = ["business_name", "tax_rate_percent"]

    def has_add_permission(self, request):
        return not ShopSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "customer", "vehicle", "created_at"]
    list_filter = ["status"]
    search_fields = ["customer__name", "vehicle__vin", "complaint"]
    autocomplete_fields = ["customer", "vehicle", "repair_guides", "assigned_technician"]
    readonly_fields = ["portal_link"]
    inlines = [LaborLineInline, PartLineInline]

    @admin.display(description="Customer status link")
    def portal_link(self, obj):
        return obj.get_portal_url() if obj.pk else "(save first)"


class PaymentRecordInline(admin.TabularInline):
    model = PaymentRecord
    extra = 1


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["invoice_number", "work_order", "issued_date", "paid", "amount_paid", "balance_due"]
    list_filter = ["paid"]
    search_fields = ["invoice_number"]
    inlines = [PaymentRecordInline]


@admin.register(Estimate)
class EstimateAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "customer", "vehicle", "created_at"]
    list_filter = ["status"]
    search_fields = ["customer__name", "vehicle__vin"]
    autocomplete_fields = ["customer", "vehicle"]
    readonly_fields = ["portal_link"]
    inlines = [EstimateLaborLineInline, EstimatePartLineInline]

    @admin.display(description="Customer approval link")
    def portal_link(self, obj):
        return obj.get_portal_url() if obj.pk else "(save first)"


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["__str__", "status", "scheduled_at", "customer", "vehicle"]
    list_filter = ["status"]
    search_fields = ["customer__name", "reason"]
    autocomplete_fields = ["customer", "vehicle", "work_order"]


@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ["name", "phone", "active", "user"]
    list_filter = ["active"]
    search_fields = ["name", "phone"]


@admin.register(InventoryPart)
class InventoryPartAdmin(admin.ModelAdmin):
    list_display = ["part_number", "description", "quantity_on_hand", "reorder_point", "is_low_stock"]
    search_fields = ["part_number", "description"]

    @admin.display(boolean=True)
    def is_low_stock(self, obj):
        return obj.is_low_stock


class InspectionItemInline(admin.TabularInline):
    model = InspectionItem
    extra = 0


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "technician", "created_at"]
    autocomplete_fields = ["work_order", "technician"]
    inlines = [InspectionItemInline]


@admin.register(ActivityLogEntry)
class ActivityLogEntryAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "user", "action", "object_repr"]
    list_filter = ["action"]
    search_fields = ["action", "object_repr"]


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ["__str__", "clock_in", "clock_out", "duration_hours", "is_active"]
    list_filter = ["technician"]
    autocomplete_fields = ["work_order", "technician"]
