from django.contrib import admin

# Register your models here.
from .models import BreachedCredential, ScrapFile

@admin.register(BreachedCredential)
class BreachedCredentialAdmin(admin.ModelAdmin):
    list_display = ('username', 'source', 'website', 'hash_type', 'added_at')
    search_fields = ('username', 'source', 'password', 'website')
    list_filter = ('source', 'added_at', 'file', 'hash_type', 'website')
    
@admin.register(ScrapFile)    
class ScrapFile(admin.ModelAdmin):
    list_display = ('name', 'hash', 'added_at', 'hash_type')
    search_fields = ('hash', 'name')
    list_filter = ('added_at', 'name')