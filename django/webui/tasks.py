from django_q.tasks import schedule
from datetime import timedelta
from .processor import process_scrap_files
# Schedule the task
schedule(
    "webui.tasks.process_scrap_files",
    name="Process Scrap Files",
    schedule_type="H",  # Hourly schedule
    next_run=timedelta(hours=1),  # Run every hour
)
