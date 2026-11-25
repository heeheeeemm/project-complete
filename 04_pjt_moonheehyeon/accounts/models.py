from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models


class User(AbstractUser):
    GENDER_CHOICES = [('F', '여성'), ('M', '남성'), ('OTHER', '기타'), ('UNDISCLOSED', '응답하지 않음')]
    GENRE_CHOICES = [
        ('NOVEL', '소설'), ('POETRY', '시'), ('ESSAY', '에세이'),
        ('HUMANITIES', '인문'), ('SCIENCE', '과학'), ('HISTORY', '역사'),
        ('ECONOMY', '경제·경영'), ('SELF_HELP', '자기계발'), ('ART', '예술'),
    ]

    gender = models.CharField('성별', max_length=12, choices=GENDER_CHOICES, blank=True)
    age = models.PositiveIntegerField('나이', null=True, blank=True, validators=[MinValueValidator(1)])
    weekly_reading_hours = models.PositiveIntegerField(
        '주간 평균 독서 시간', null=True, blank=True, validators=[MinValueValidator(1)],
    )
    annual_reading_count = models.PositiveIntegerField(
        '연간 독서량', null=True, blank=True, validators=[MinValueValidator(1)],
    )
    interested_genres = models.CharField('관심 장르', max_length=600, blank=True)

    def get_genre_list(self):
        return self.interested_genres.split(',') if self.interested_genres else []

    def get_interested_genres_display(self):
        labels = dict(self.GENRE_CHOICES)
        return ', '.join(labels.get(code, code) for code in self.get_genre_list())
