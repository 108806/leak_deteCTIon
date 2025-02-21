import hashlib
from django.db import models

class ScrapFile(models.Model):
    '''
    IMPORTANT : Deleting an entry of ScrapFile also removes all the connected BreachedCredentials. This is the design. Use with caution.
    '''
    name = models.CharField(max_length=256)
    sha256 = models.CharField(max_length=256, unique=True, editable=False, default='') #DEFAULT USING SHA256
    added_at = models.DateTimeField(auto_now_add=True)
    size = models.CharField(help_text="Size of the file in mb", default=0, max_length=10)

    def save(self, *args, **kwargs):
        # Automatically calculate the hash of the file content if not present:
        if not self.sha256:
            with open(self.name, "rb") as file:
                file_content = file.read()
                self.sha256 = hashlib.sha256(file_content).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"File: {self.name} (Hash: {self.sha256})"

    @property
    def credential_count(self):
        """Returns the number of BreachedCredential instances associated with this ScrapFile."""
        return self.breached_credentials.count()

class BreachedCredential(models.Model):
    '''
    Main model of the CTI. Records of the breaches are stored here.
    '''
    string = models.CharField(max_length=512)
    file = models.ForeignKey(ScrapFile, on_delete=models.CASCADE, related_name="breached_credentials", default='', null=True)
    #hash = models.CharField(max_length=256, editable=False, null=True) 
    #hash_type = models.CharField(max_length=32, default="sha256")
    added_at = models.DateTimeField(auto_now_add=True)
    #website = models.URLField(max_length=256, blank=True, null=True)

    # def save(self, *args, **kwargs):
    #     # Automatically calculate the SHA-256 hash of the password
    #     if not self.hash:
    #         self.hash = hashlib.sha256(self.password.encode()).hexdigest()
    #     super().save(*args, **kwargs)

    def __str__(self):
        return f"{ hashlib.sha256(self.string.encode('utf-8')) }"
