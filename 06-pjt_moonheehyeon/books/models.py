from django.conf import settings
from django.db import models


class Book(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='books',
    )
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    review_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class Thread(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='threads',
    )
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='threads',
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    reading_date = models.DateField()
    like_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='like_threads',
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
