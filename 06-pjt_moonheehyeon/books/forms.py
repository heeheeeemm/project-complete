from django.forms import ModelForm

from .models import Book, Thread


class BookForm(ModelForm):
    class Meta:
        model = Book
        fields = ('title', 'author', 'description', 'review_score')
        labels = {
            'title': '도서 제목',
            'author': '저자',
            'description': '도서 설명',
            'review_score': '회원 리뷰 평점',
        }


class ThreadForm(ModelForm):
    class Meta:
        model = Thread
        fields = ('title', 'content', 'reading_date')
        labels = {'title': '제목', 'content': '내용', 'reading_date': '독서일'}
