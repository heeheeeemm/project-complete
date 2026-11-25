from django.shortcuts import get_object_or_404, render

from .forms import CompanySearchForm
from .models import AnalysisResult
from .services import analyze_company


def result_to_context(saved):
    """DB에 저장된 분석 결과를 화면에서 다시 볼 수 있는 형태로 바꾼다."""
    cleaned = saved.cleaned_comments
    augmented = saved.augmented_comments
    records = [{'text': text, 'source': 'original'} for text in cleaned]
    records.extend(
        {'text': text, 'source': 'augmented', 'origin_index': index}
        for index, text in enumerate(augmented)
    )
    return {
        'saved_id': saved.pk,
        'company': saved.input_company,
        'actual_company': saved.actual_company or saved.input_company,
        'stock_code': saved.stock_code,
        'message': saved.message,
        'raw_comments': saved.raw_comments,
        'cleaned_comments': cleaned,
        'augmented_comments': augmented,
        'removed': saved.removed_comments,
        'summary': saved.summary,
        'iqr': {'lower': saved.iqr_lower, 'upper': saved.iqr_upper},
        'counts': {
            'collected': len(saved.raw_comments),
            'filtered': len(saved.raw_comments) - len(saved.removed_comments),
            'cleaned': len(cleaned),
            'augmented': len(augmented),
        },
        'records': records,
    }


def index(request):
    form = CompanySearchForm(request.POST or None)
    result = None

    if request.method == 'POST' and form.is_valid():
        company = form.cleaned_data['company']
        print(f'[사용자 입력] {company}')
        try:
            result = analyze_company(company, form.cleaned_data['include_summary'])
        except Exception as error:
            print(f'[처리 오류] {type(error).__name__}: {error}')
            result = {
                'company': company,
                'actual_company': '',
                'message': '데이터 수집 중 페이지가 변경되었거나 연결이 지연되었습니다. 잠시 후 다시 검색해주세요.',
                'counts': {},
                'raw_comments': [], 'cleaned_comments': [],
                'augmented_comments': [], 'removed': [],
            }

        iqr = result.get('iqr', {})
        saved = AnalysisResult.objects.create(
            input_company=company,
            actual_company=result.get('actual_company', ''),
            stock_code=result.get('stock_code', ''),
            raw_comments=result.get('raw_comments', []),
            cleaned_comments=result.get('cleaned_comments', []),
            augmented_comments=result.get('augmented_comments', []),
            removed_comments=result.get('removed', []),
            iqr_lower=iqr.get('lower'),
            iqr_upper=iqr.get('upper'),
            summary=result.get('summary', ''),
            message=result.get('message', ''),
        )
        result['saved_id'] = saved.pk

    return render(request, 'analyzer/index.html', {'form': form, 'result': result})


def saved_result(request, pk=None):
    """저장된 결과를 재실행 없이 조회한다. 캡처와 결과 검토에도 사용한다."""
    if pk is None:
        saved = AnalysisResult.objects.first()
        if saved is None:
            return index(request)
    else:
        saved = get_object_or_404(AnalysisResult, pk=pk)
    form = CompanySearchForm(initial={'company': saved.input_company})
    return render(
        request,
        'analyzer/index.html',
        {'form': form, 'result': result_to_context(saved)},
    )
