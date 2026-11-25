from django import forms


class CompanySearchForm(forms.Form):
    company = forms.CharField(
        label='회사명',
        max_length=100,
        strip=True,
        widget=forms.TextInput(attrs={
            'placeholder': '예: 삼성, 카카오',
            'autocomplete': 'off',
            'autofocus': True,
        }),
    )
    include_summary = forms.BooleanField(label='댓글 요약도 생성', required=False)
