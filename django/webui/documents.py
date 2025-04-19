from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from webui.models import BreachedCredential, ScrapFile
from datetime import datetime
from elasticsearch_dsl import Text, Date, Long, Keyword
from elasticsearch_dsl.analysis import analyzer, tokenizer

# Define custom analyzers
ngram_analyzer = analyzer(
    'ngram_analyzer',
    tokenizer=tokenizer('ngram_tokenizer', 'ngram', min_gram=3, max_gram=15),
    filter=['lowercase']
)

@registry.register_document
class BreachedCredentialDocument(Document):
    string = fields.TextField(
        fields={
            'ngram': fields.TextField(analyzer='ngram_analyzer')
        }
    )
    added_at = fields.DateField()
    file_id = fields.IntegerField()
    file_name = fields.TextField()
    file_size = fields.FloatField()
    file_uploaded_at = fields.DateField()

    class Index:
        name = 'breached_credentials'
        settings = {
            'number_of_shards': 1,
            'number_of_replicas': 0,
            'index.max_ngram_diff': 12,
            'analysis': {
                'analyzer': {
                    'ngram_analyzer': {
                        'tokenizer': 'ngram_tokenizer',
                        'filter': ['lowercase']
                    }
                },
                'tokenizer': {
                    'ngram_tokenizer': {
                        'type': 'ngram',
                        'min_gram': 3,
                        'max_gram': 15,
                        'token_chars': ['letter', 'digit', 'symbol']
                    }
                }
            }
        }

    class Django:
        model = BreachedCredential
        fields = [
            'id',
        ]
        related_models = [ScrapFile]

    def get_queryset(self):
        return self.django.model.objects.all().select_related('file')

    def prepare_id(self, instance):
        return str(instance.id)  # Ensure ID is always a string

    def prepare_file(self, instance):
        if instance.file:
            return {'name': instance.file.name}
        return None

    def prepare_indexed_at(self, instance):
        return datetime.now()

    def prepare_string(self, instance):
        return instance.string

    def get_instances_from_related(self, instance):
        if isinstance(instance, ScrapFile):
            return BreachedCredential.objects.filter(file=instance)
        return None