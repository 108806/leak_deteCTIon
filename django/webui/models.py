import hashlib
from django.db import models, transaction
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import ProtectedError, QuerySet
from django.utils.functional import cached_property
from typing import Optional
from minio import Minio
from core.settings import AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME
import logging

logger = logging.getLogger(__name__)

class ScrapFile(models.Model):
    """
    Represents a file containing breach or leak data in the CTI system.

    IMPORTANT: Deleting a ScrapFile instance cascades to remove all associated
    BreachedCredential instances. Use with caution in production.

    Attributes:
        name (str): The MinIO object key (path) of the file (e.g., '1501020529/1192_Hungary_Combolistfresh.txt').
        sha256 (str): SHA-256 hash of the file content, unique identifier.
        added_at (datetime): Timestamp of file addition.
        size (Decimal): Size of the file in MB.
    """

    name = models.CharField(max_length=256, db_index=True)
    sha256 = models.CharField(max_length=64, unique=True, editable=False, default="")
    added_at = models.DateTimeField(auto_now_add=True)
    size = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Size of the file in MB",
        default=0.0,
        validators=[MinValueValidator(0.0)],
    )
    count = models.IntegerField(default=0, help_text="Number of associated BreachedCredentials")
    is_active = models.BooleanField(default=True)

    def _calculate_sha256(self) -> str:
        """Calculate the SHA-256 hash of the file content by streaming from MinIO."""
        client = Minio(
            AWS_S3_ENDPOINT_URL,
            access_key=AWS_ACCESS_KEY_ID,
            secret_key=AWS_SECRET_ACCESS_KEY,
            secure=False,  # Use True if SSL/TLS enabled; adjust based on AWS_S3_ENDPOINT_URL
        )
        try:
            response = client.get_object(AWS_STORAGE_BUCKET_NAME, self.name)
            sha256_hash = hashlib.sha256()
            for chunk in response.stream(8192):  # Read in chunks of 8KB
                sha256_hash.update(chunk)
            hash_value = sha256_hash.hexdigest()
            response.close()
            return hash_value
        except Exception as e:
            logger.error(f"Error calculating SHA-256 for {self.name} from MinIO: {e}")
            raise ValueError(f"Failed to calculate SHA-256 for {self.name}: {e}")

    @transaction.atomic
    def save(self, *args, **kwargs) -> None:
        if not self.sha256:
            self.sha256 = self._calculate_sha256()
            logger.info(f"Calculated SHA256 for {self.name}: {self.sha256}")
        super().save(*args, **kwargs)
        # Update count after saving, accessing credential_count as a property
        self.count = self.credential_count
        super().save(update_fields=['count'])

    def update_breached_credential_count(self) -> None:
        """Calculate and update the count of BreachedCredential instances."""
        self.refresh_from_db()
        new_count = BreachedCredential.objects.filter(file=self).count()
        logger.debug(f"Count before update for {self.name}: {new_count} (current: {self.count})")
        self.count = new_count
        try:
            self.save(update_fields=['count'])  # Attempt field-specific save
            logger.info(f"Updated count for {self.name}: {self.count}")
        except Exception as e:
            logger.error(f"Failed to save count for {self.name}: {e}")
            # Fallback: direct DB update
            ScrapFile.objects.filter(id=self.id).update(count=new_count)
            self.refresh_from_db()
            logger.info(f"Forced count update for {self.name}: {self.count}")
        if self.count != new_count:
            logger.error(f"Count mismatch for {self.name}: expected {new_count}, got {self.count}")

    @cached_property
    def credential_count(self) -> int:
        """Cached count for performance, not used in update."""
        return BreachedCredential.objects.filter(file=self).count()

    def delete(self, *args, **kwargs):
        try:
            self.breached_credentials.all().delete()
            super().delete(*args, **kwargs)
        except ProtectedError:
            raise ProtectedError(
                "Cannot delete ScrapFile with associated BreachedCredentials. Use soft_delete or clear relations first.",
                self.breached_credentials.all(),
            )

    def soft_delete(self):
        self.is_active = False
        self.save()

@receiver(post_save, sender=ScrapFile)
def calculate_sha256(sender, instance, created, **kwargs):
    if created and not instance.sha256:
        try:
            instance.sha256 = instance._calculate_sha256()
            instance.save(update_fields=["sha256"])
            logger.info(f"Calculated SHA256 for {instance.name}: {instance.sha256}")
        except ValueError as e:
            logger.error(f"Failed to calculate SHA256 for {instance.name}: {e}")
            instance.sha256 = "hash_calculation_failed"  # Placeholder
            instance.save(update_fields=["sha256"])

class BreachedCredential(models.Model):
    """
    Main model of the CTI. Records of the breaches are stored here.

    Attributes:
        string (str): The credential string (e.g., username:password or email).
        file (ScrapFile): Foreign key to the associated ScrapFile.
        added_at (datetime): Timestamp of addition.

    Example:
        cred = BreachedCredential(string="user:pass123", file=scrap_file)
        cred.save()
    """

    string = models.CharField(max_length=1024, db_index=True)
    file = models.ForeignKey(
        "ScrapFile",
        on_delete=models.CASCADE,
        related_name="breached_credentials",
        null=True,
    )
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Credential: {hashlib.sha256(self.string.encode('utf-8')).hexdigest()}"

    class Meta:
        indexes = [
            models.Index(fields=["string"]),
        ]