from django import forms
from django.contrib import admin

from .models import Role, SystemSetting, User


class UserAdminForm(forms.ModelForm):
    new_password = forms.CharField(
        label="Yangi parol", required=False, widget=forms.PasswordInput, strip=False
    )

    class Meta:
        model = User
        fields = ["username", "full_name", "role", "is_active"]

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        if self.cleaned_data.get("new_password"):
            user.set_password(self.cleaned_data["new_password"])
        elif not user.pk:
            user.set_unusable_password()
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ["username", "full_name", "role", "is_active", "last_login"]
    list_filter = ["role", "is_active"]
    search_fields = ["username", "full_name"]
    fields = ["username", "full_name", "role", "is_active", "new_password"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["code", "name"]


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "updated_by", "updated_at"]
    readonly_fields = ["updated_by", "updated_at"]

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
