from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    gender = models.CharField(max_length=10, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    weekly_reading_time = models.PositiveIntegerField(null=True, blank=True)
    annual_reading_amount = models.PositiveIntegerField(null=True, blank=True)
    profile_image = models.FileField(upload_to='profile_images/', blank=True)
    followings = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='followers',
        blank=True,
    )

    def __str__(self):
        return self.username
