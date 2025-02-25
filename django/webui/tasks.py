from django_q.tasks import schedule
from datetime import timedelta


def setup_scrap_schedule():
    # Schedule the process_scrap_files function to run every 3 minutes
    schedule(
        "webui.processor.process_scrap_files",  # The full path to your actual function
        name="Process Scrap Files",
        schedule_type="M",  # Schedule by minutes
        minutes=3,  # Run every 3 minutes
        catch_up=False,  # Don't backfill missed runs
    )
