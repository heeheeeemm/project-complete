"""외부 모델 답변의 텍스트를 이스케이프한 뒤 제한된 강조만 표시합니다."""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def reading_text(value):
    text = str(escape(value))
    text = re.sub(r'^#{1,6}\s+(.+)$', r'<strong>\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    return mark_safe(text)
