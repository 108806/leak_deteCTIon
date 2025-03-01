from django.contrib import admin
from .models import BreachedCredential, ScrapFile

@admin.register(BreachedCredential)
class BreachedCredentialAdmin(admin.ModelAdmin):
    list_display = ("string", "added_at", "file")
    search_fields = ("string",)
    list_filter = ("added_at", "file")

@admin.register(ScrapFile)
class ScrapFileAdmin(admin.ModelAdmin):
    list_display = ("name", "added_at", "size",  "count", "sha256",)  # Use 'count' instead of 'credential_count'
    search_fields = ("name", "size", "count", "sha256")  # Use 'count' instead of 'credential_count'
    list_filter = ("name", "added_at","size", "sha256")

    def credential_count(self, obj):
        return obj.count  # Display 'count' in admin
    credential_count.short_description = "Credentials"