from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User


USER_PROFILE_FIELDS = (
    'username',
    'email',
    'last_name',
    'first_name',
    'gender',
    'age',
    'weekly_reading_time',
    'annual_reading_amount',
    'profile_image',
)

USER_PROFILE_LABELS = {
    'username': '아이디',
    'email': '이메일',
    'last_name': '성',
    'first_name': '이름',
    'gender': '성별',
    'age': '나이',
    'weekly_reading_time': '주간 평균 독서 시간',
    'annual_reading_amount': '연간 독서량',
    'profile_image': '프로필 이미지',
}


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = USER_PROFILE_FIELDS
        labels = USER_PROFILE_LABELS


class CustomUserChangeForm(UserChangeForm):
    password = None

    class Meta(UserChangeForm.Meta):
        model = User
        fields = USER_PROFILE_FIELDS
        labels = USER_PROFILE_LABELS
