from django_q.tasks import async_task
from .processor import process_scrap_files
# Schedule the task
def schedule_scrap_processing():
    async_task(process_scrap_files)
