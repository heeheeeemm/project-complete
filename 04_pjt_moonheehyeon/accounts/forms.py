from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm, PasswordChangeForm, UserChangeForm, UserCreationForm,
)


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class ReadingProfileFormMixin(BootstrapFormMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['interested_genres'] = self.instance.get_genre_list()
        for name, label in [('password1', '비밀번호'), ('password2', '비밀번호 확인')]:
            if name in self.fields:
                self.fields[name].label = label

    def clean_interested_genres(self):
        # ModelForm의 모델 검증 전에 체크박스 목록을 저장용 문자열로 변환합니다.
        return ','.join(self.cleaned_data['interested_genres'])


class CustomAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    pass


class CustomUserCreationForm(ReadingProfileFormMixin, UserCreationForm):
    interested_genres = forms.MultipleChoiceField(
        label='관심 장르', choices=get_user_model().GENRE_CHOICES,
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = [
            'username', 'email', 'last_name', 'first_name', 'gender', 'age',
            'weekly_reading_hours', 'annual_reading_count', 'interested_genres',
        ]
        labels = {'username': '아이디', 'email': '이메일', 'last_name': '성', 'first_name': '이름'}


class CustomUserChangeForm(ReadingProfileFormMixin, UserChangeForm):
    password = None
    interested_genres = forms.MultipleChoiceField(
        label='관심 장르', choices=get_user_model().GENRE_CHOICES,
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta(UserChangeForm.Meta):
        model = get_user_model()
        fields = [
            'email', 'last_name', 'first_name', 'gender', 'age',
            'weekly_reading_hours', 'annual_reading_count', 'interested_genres',
        ]
        labels = {'email': '이메일', 'last_name': '성', 'first_name': '이름'}


class CustomPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    pass
