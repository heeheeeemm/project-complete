from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models


class Book(models.Model):
    GENRE_CHOICES = [
        ('UNCLASSIFIED', '미분류'), ('NOVEL', '소설'), ('POETRY', '시'),
        ('ESSAY', '에세이'), ('HUMANITIES', '인문'), ('SCIENCE', '과학'),
        ('HISTORY', '역사'), ('ECONOMY', '경제·경영'),
        ('SELF_HELP', '자기계발'), ('ART', '예술'), ('OTHER', '기타'),
    ]
    SUBGENRE_CHOICES = {
        'NOVEL': [
            ('NOVEL_LITERARY', '문학·일반'), ('NOVEL_FANTASY', '판타지'),
            ('NOVEL_MYSTERY', '추리·미스터리'), ('NOVEL_ROMANCE', '로맨스'),
            ('NOVEL_SF', 'SF'), ('NOVEL_THRILLER', '스릴러·공포'),
            ('NOVEL_HISTORY', '역사소설'), ('NOVEL_MARTIAL', '무협'),
        ],
        'POETRY': [
            ('POETRY_MODERN', '현대시'), ('POETRY_CLASSIC', '고전시'),
            ('POETRY_PROSE', '산문시'), ('POETRY_FOREIGN', '해외시'),
            ('POETRY_CHILDREN', '동시'),
        ],
        'ESSAY': [
            ('ESSAY_DAILY', '일상·감성'), ('ESSAY_TRAVEL', '여행'),
            ('ESSAY_NATURE', '자연·환경'), ('ESSAY_SOCIAL', '사회·문화'),
            ('ESSAY_MEMOIR', '자전·회고'),
        ],
        'HUMANITIES': [
            ('HUMANITIES_PHILOSOPHY', '철학'), ('HUMANITIES_PSYCHOLOGY', '심리학'),
            ('HUMANITIES_SOCIOLOGY', '사회학'), ('HUMANITIES_LINGUISTICS', '언어학'),
            ('HUMANITIES_RELIGION', '종교'), ('HUMANITIES_LITERATURE', '문학이론·비평'),
        ],
        'SCIENCE': [
            ('SCIENCE_PHYSICS', '물리·천문'), ('SCIENCE_CHEMISTRY', '화학'),
            ('SCIENCE_BIOLOGY', '생물·생명'), ('SCIENCE_MATH', '수학'),
            ('SCIENCE_EARTH', '지구·환경'), ('SCIENCE_TECH', '컴퓨터·기술'),
            ('SCIENCE_MEDICINE', '의학·건강'),
        ],
        'HISTORY': [
            ('HISTORY_KOREA', '한국사'), ('HISTORY_WORLD', '세계사'),
            ('HISTORY_EAST', '동양사'), ('HISTORY_WEST', '서양사'),
            ('HISTORY_PERSON', '인물·평전'), ('HISTORY_CULTURE', '문화사'),
        ],
        'ECONOMY': [
            ('ECONOMY_GENERAL', '경제학'), ('ECONOMY_MANAGEMENT', '경영'),
            ('ECONOMY_INVESTMENT', '투자·재테크'), ('ECONOMY_MARKETING', '마케팅'),
            ('ECONOMY_STARTUP', '창업·비즈니스'),
        ],
        'SELF_HELP': [
            ('SELF_HELP_HABITS', '습관·시간관리'), ('SELF_HELP_CAREER', '직장·커리어'),
            ('SELF_HELP_RELATIONS', '인간관계·소통'), ('SELF_HELP_MINDSET', '마음·동기부여'),
            ('SELF_HELP_LEARNING', '공부·학습법'),
        ],
        'ART': [
            ('ART_PAINTING', '미술·디자인'), ('ART_MUSIC', '음악'),
            ('ART_CINEMA', '영화·공연'), ('ART_PHOTO', '사진'), ('ART_ARCHITECTURE', '건축'),
        ],
        'OTHER': [
            ('OTHER_COOKING', '요리'), ('OTHER_HOBBY', '취미·실용'),
            ('OTHER_CHILDREN', '아동·청소년'), ('OTHER_COMICS', '만화·그래픽노블'),
            ('OTHER_GENERAL', '기타 일반'),
        ],
    }

    title = models.CharField(max_length=100, verbose_name='제목')
    genre = models.CharField('장르', max_length=12, choices=GENRE_CHOICES, default='UNCLASSIFIED')
    subgenre = models.CharField(
        '세부 장르', max_length=24, blank=True,
        choices=[choice for group in SUBGENRE_CHOICES.values() for choice in group],
        help_text='선택한 장르 안에서 세부 장르 하나를 고를 수 있어요.',
    )
    description = models.TextField(verbose_name='설명')
    # 기존 DB의 보조 열은 데이터 호환을 위해 유지하며 도서 폼에는 노출하지 않습니다.
    completed = models.BooleanField(default=False, verbose_name='완료 여부')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    STATUS_CHOICES = [
        ('TODO', '할 일'),
        ('DOING', '진행 중'),
        ('DONE', '완료'),
    ]
    status = models.CharField(
        max_length=5,
        choices=STATUS_CHOICES,
        default='TODO',
        help_text='현재 작업 상태를 선택해주세요.',
        verbose_name='상태',
    )

    rating = models.PositiveIntegerField(
        default=2, verbose_name='회원 리뷰 평점',
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text='0부터 10까지의 정수를 입력하세요.',
    )
    author = models.CharField(max_length=100, verbose_name='저자')
    author_info = models.TextField('작가 정보', blank=True)
    author_works = models.JSONField('작가 대표작', default=list, blank=True)
    author_image = models.URLField('작가 프로필 사진', max_length=1000, blank=True)
    author_source = models.URLField('작가 정보 출처', max_length=1000, blank=True)

    class Meta:
        verbose_name = '도서'
        verbose_name_plural = '도서'

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.subgenre and self.subgenre not in dict(self.SUBGENRE_CHOICES.get(self.genre, [])):
            raise ValidationError({'subgenre': '선택한 장르에 속하는 세부 장르를 골라 주세요.'})
