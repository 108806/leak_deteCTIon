import hashlib
import os
from django.db import models, transaction
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import ProtectedError, QuerySet
from django.utils.functional import cached_property
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def _calculate_sha256(self) -> str:
    full_path = os.path.join(settings.BASE_DIR, self.name)
    try:
        sha256_hash = hashlib.sha256()
        with open(full_path, "rb") as file:
            while chunk := file.read(8192):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        logger.error(f"File not found: {full_path}")
        raise ValueError(f"File not found: {full_path}")


class ScrapFile(models.Model):
    """
    Represents a file containing breach or leak data in the CTI system.

    IMPORTANT: Deleting a ScrapFile instance cascades to remove all associated
    BreachedCredential instances. Use with caution in production.

    Attributes:
        name (str): The name of the file (e.g., 'breach_data.txt').
        sha256 (str): SHA-256 hash of the file content, unique identifier.
        added_at (datetime): Timestamp of file addition.
        size (Decimal): Size of the file in MB.

    Example:
        scrap = ScrapFile(name="leak.txt", size=5.5)
        scrap.save()
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

    def save(self, *args, **kwargs) -> None:
        if not self.sha256:
            self.sha256 = self._calculate_sha256()
            logger.info(f"Calculated SHA256 for {self.name}: {self.sha256}")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"File: {self.name} (Hash: {self.sha256})"

    @cached_property
    def credential_count(self) -> int:
        """Returns the number of BreachedCredential instances associated with this ScrapFile, cached for performance."""
        return self.breached_credentials.count()

    @property
    def breached_credentials(self) -> "QuerySet[BreachedCredential]":
        return self.breached_credentials.all()

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

    is_active = models.BooleanField(default=True)


@receiver(post_save, sender=ScrapFile)
def calculate_sha256(sender, instance, created, **kwargs):
    if created or not instance.sha256:
        instance.sha256 = instance._calculate_sha256()
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
        "ScrapFile",  # String literal to break circular dependency
        on_delete=models.CASCADE,
        related_name="breached_credentials",
        null=True,
    )
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Credential: {hashlib.sha256(self.string.encode('utf-8')).hexdigest()}"

    class Meta:
        indexes = [
            models.Index(fields=["string"]),  # Additional performance for searches
        ]