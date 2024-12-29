import hashlib
from django.db import models

class ScrapFile(models.Model):
    '''
    IMPORTANT : Deleting an entry of ScrapFile also removes all the connected BreachedCredentials. This is the design. Use with caution.
    '''
    name = models.CharField(max_length=255)
    hash = models.CharField(max_length=256, unique=True, editable=False, null=False)
    hash_type = models.CharField(max_length=32)
    added_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Automatically calculate the hash of the file content
        if not self.hash:
            with open(self.name, "rb") as file:
                file_content = file.read()
                self.hash = hashlib.sha256(file_content).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"File: {self.name} (Hash: {self.hash})"


class BreachedCredential(models.Model):
    '''
    Main model of the CTI. Records of the breaches are stored here.
    '''
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    source = models.CharField(max_length=128, blank=True, null=True)
    file = models.ForeignKey(ScrapFile, on_delete=models.CASCADE, related_name="breached_credentials", default='', null=True)
    hash = models.CharField(max_length=256, editable=False, null=True) 
    hash_type = models.CharField(max_length=32, default="sha256")
    added_at = models.DateTimeField(auto_now_add=True)
    website = models.URLField(max_length=256, blank=True, null=True)

    def save(self, *args, **kwargs):
        # Automatically calculate the SHA-256 hash of the password
        if not self.hash:
            self.hash = hashlib.sha256(self.password.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.hash})"
