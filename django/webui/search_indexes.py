from django_elasticsearch_dsl import Document
from django_elasticsearch_dsl.registries import registry
from .models import BreachedCredential

@registry.register_document
class BreachedCredentialDocument(Document):
    class Index:
        name = 'breachedcredentials'  # Index name in Elasticsearch
    class Django:
        model = BreachedCredential
        fields = ['username', 'password', 'file', 'hash', 'hash_type', 'added_at']
