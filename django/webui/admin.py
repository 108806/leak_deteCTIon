from django.contrib import admin

# Register your models here.
from .models import BreachedCredential, ScrapFile


@admin.register(BreachedCredential)
class BreachedCredentialAdmin(admin.ModelAdmin):
    list_display = ("string", "added_at", "file")
    search_fields = ("string",)
    list_filter = ("added_at", "file")


@admin.register(ScrapFile)
class ScrapFile(admin.ModelAdmin):
    list_display = ("name", "sha256", "added_at", "size", "credential_count")
    search_fields = ("name", "sha256", "size")
    list_filter = ("name", "added_at", "sha256", "size")
