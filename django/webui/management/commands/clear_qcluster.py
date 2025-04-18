# webui/management/commands/clear_qcluster.py
from django.core.management.base import BaseCommand
from django_q.models import Task

class Command(BaseCommand):
    help = "Clear all tasks from the django-q queue."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Starting django-q queue cleanup..."))
        
        # Liczenie i usuwanie zadań
        task_count = Task.objects.count()
        if task_count > 0:
            Task.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"✅ Deleted {task_count} tasks from the django-q queue.")
            )
        else:
            self.stdout.write(
                self.style.WARNING("ℹ️ No tasks found in the django-q queue.")
            )
        
        self.stdout.write(self.style.SUCCESS("✅ Django-q queue cleared successfully."))