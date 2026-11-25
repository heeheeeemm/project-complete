from django import forms

from .models import Book


class BookForm(forms.ModelForm):
    def clean_genre(self):
        return self.cleaned_data['genre'] or self.instance.genre or 'UNCLASSIFIED'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['genre'].required = False
        genre = self.initial.get('genre', self.instance.genre)
        if self.is_bound:
            genre = self.data.get(self.add_prefix('genre')) or self.instance.genre
        self.fields['subgenre'].choices = [('', '세부 장르 선택 (선택사항)')] + Book.SUBGENRE_CHOICES.get(genre, [])
        self.subgenre_options = Book.SUBGENRE_CHOICES

    class Meta:
        model = Book
        fields = ['title', 'author', 'genre', 'subgenre', 'description', 'rating']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'genre': forms.Select(attrs={'class': 'form-select'}),
            'subgenre': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 10}),
            'author': forms.TextInput(attrs={'class': 'form-control'}),
        }
