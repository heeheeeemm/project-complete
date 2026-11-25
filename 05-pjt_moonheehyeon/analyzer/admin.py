from django.contrib import admin

from .models import AnalysisResult


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ('actual_company', 'input_company', 'created_at')
    search_fields = ('actual_company', 'input_company', 'stock_code')
    readonly_fields = ('created_at',)
