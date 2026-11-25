from django.db import models


class ImageAnalysis(models.Model):
    image = models.ImageField(upload_to='uploads/')
    question = models.CharField(max_length=300, default='이 책은 어떤 책이고, 비슷한 책을 추천해줘')
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ConversationMessage(models.Model):
    recommendation = models.ForeignKey(
        'Recommendation', on_delete=models.CASCADE, related_name='messages',
    )
    role = models.CharField(max_length=10, choices=[('user', '사용자'), ('assistant', '도서 도우미')])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class Speech(models.Model):
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)


class Recommendation(models.Model):
    request_text = models.TextField(max_length=300)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)

    use_tier_routing = models.BooleanField(default=False)
    route = models.CharField(max_length=50, blank=True)
    content = models.TextField(blank=True)
    model_used = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to='images/', blank=True)
    score = models.IntegerField(null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
