from django.contrib import admin


class ReadOnlyAdmin(admin.ModelAdmin):
    """View-only admin for operational records and logs (nothing is added or edited by hand)."""

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
