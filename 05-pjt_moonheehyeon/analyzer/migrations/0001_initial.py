from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name='AnalysisResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('input_company', models.CharField(max_length=100, verbose_name='입력 회사명')),
                ('actual_company', models.CharField(blank=True, max_length=100, verbose_name='실제 종목명')),
                ('stock_code', models.CharField(blank=True, max_length=30, verbose_name='종목 코드')),
                ('raw_comments', models.JSONField(default=list, verbose_name='원본 댓글')),
                ('cleaned_comments', models.JSONField(default=list, verbose_name='정제 댓글')),
                ('augmented_comments', models.JSONField(default=list, verbose_name='증강 댓글')),
                ('removed_comments', models.JSONField(default=list, verbose_name='제거 댓글')),
                ('iqr_lower', models.FloatField(blank=True, null=True, verbose_name='IQR 하한')),
                ('iqr_upper', models.FloatField(blank=True, null=True, verbose_name='IQR 상한')),
                ('summary', models.TextField(blank=True, verbose_name='댓글 요약')),
                ('message', models.CharField(blank=True, max_length=300, verbose_name='상태 메시지')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='생성일시')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
