from django.contrib import admin

# [STEP 1-1] 관리자 페이지에 User 등록
# ※ UserAdmin : 비밀번호 변경 · 권한 설정 등 기본 회원 관리 화면을 그대로 사용
from django.contrib.auth.admin import UserAdmin

from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('독서 프로필', {'fields': (
            'gender', 'age', 'weekly_reading_hours', 'annual_reading_count', 'interested_genres',
        )}),
    )
