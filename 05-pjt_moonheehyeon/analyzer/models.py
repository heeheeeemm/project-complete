from django.db import models


class AnalysisResult(models.Model):
    input_company = models.CharField('입력 회사명', max_length=100)
    actual_company = models.CharField('실제 종목명', max_length=100, blank=True)
    stock_code = models.CharField('종목 코드', max_length=30, blank=True)
    raw_comments = models.JSONField('원본 댓글', default=list)
    cleaned_comments = models.JSONField('정제 댓글', default=list)
    augmented_comments = models.JSONField('증강 댓글', default=list)
    removed_comments = models.JSONField('제거 댓글', default=list)
    iqr_lower = models.FloatField('IQR 하한', null=True, blank=True)
    iqr_upper = models.FloatField('IQR 상한', null=True, blank=True)
    summary = models.TextField('댓글 요약', blank=True)
    message = models.CharField('상태 메시지', max_length=300, blank=True)
    created_at = models.DateTimeField('생성일시', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.actual_company or self.input_company} - {self.created_at:%Y-%m-%d %H:%M}'
