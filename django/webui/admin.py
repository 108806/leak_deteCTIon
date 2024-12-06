from django.contrib import admin

# Register your models here.
from .models import BreachedCredential, ScrapFile

@admin.register(BreachedCredential)
class BreachedCredentialAdmin(admin.ModelAdmin):
    list_display = ('username', 'source', 'hash', 'hash_type', 'added_at')
    search_fields = ('username', 'source', 'password')
    list_filter = ('source', 'added_at', 'file', 'hash_type')
    
@admin.register(ScrapFile)    
class ScrapFile(admin.ModelAdmin):
    list_display = ('name', 'hash', 'added_at', 'hash_type')
    search_fields = ('hash', 'name')
    list_filter = ('added_at', 'name')