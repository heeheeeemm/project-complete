import base64
import uuid
from functools import wraps
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .forms import RecommendationForm, ImageAnalysisForm, SpeechForm, FollowUpForm
from .models import Recommendation, ConversationMessage

def proxy_error_page(view):
    """Proxy 연결 실패나 시간 초과도 재시도 안내 화면으로 표시합니다."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except requests.RequestException:
            return render(request, 'recommend/error.html', {
                'user_input': request.POST.get('request_text') or request.POST.get('question')
                              or request.POST.get('text', ''),
                'status_code': 503,
            }, status=503)
    return wrapped


RECOMMEND_SYSTEM_PROMPT = '''
너는 친절한 도서 추천 도우미이다. 사용자의 취향과 상황에 맞는 책을 2~3권 추천하고,
각 책마다 제목, 저자, 추천 이유를 한두 문장으로 설명한다. 한국어로 답한다.
이전 추천과 대화 내용을 기억하여 추가 질문에 자연스럽게 답한다.
추가 질문에는 필요한 부분을 중심으로 답하고, 이미 추천한 목록 전체를 매번 반복하지 않는다.
'''


def attach_conversation(request, result):
    if not request.session.session_key:
        request.session.create()
    result.session_key = request.session.session_key


def conversation_context(result, form=None, error=''):
    return {
        'title': '나의 독서 대화', 'result': result,
        'conversation': True, 'followup_form': form if form is not None else FollowUpForm(),
        'chat_messages': result.messages.all(), 'chat_error': error,
    }


@require_http_methods(['GET', 'POST'])
def conversation(request, pk):
    # 같은 브라우저 세션에서 시작한 대화만 열 수 있습니다.
    if not request.session.session_key:
        return render(request, 'recommend/conversation_missing.html', status=404)
    result = get_object_or_404(
        Recommendation, pk=pk, session_key=request.session.session_key,
    )
    form = FollowUpForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        # 첫 추천은 유지하고 최근 10번의 문답을 추가해 컨텍스트 크기를 제한합니다.
        history = list(result.messages.order_by('-id')[:20])
        messages = [
            {'role': 'developer', 'content': RECOMMEND_SYSTEM_PROMPT},
            {'role': 'user', 'content': result.request_text},
            {'role': 'assistant', 'content': result.content},
        ]
        messages.extend({'role': item.role, 'content': item.content} for item in reversed(history))
        messages.append({'role': 'user', 'content': form.cleaned_data['question']})
        try:
            response = requests.post(
                settings.PROXY_URL + '/chat/completions',
                json={'messages': messages, 'use_tier_routing': result.use_tier_routing},
                timeout=180,
            )
            if response.status_code == 403:
                error = '이 질문에는 답변하기 어려워요. 책에 관한 다른 질문을 남겨 주세요.'
                status = 403
            elif response.status_code != 200:
                error = '답변을 불러오지 못했어요. 대화는 보관되어 있으니 잠시 후 다시 보내 주세요.'
                status = 503
            else:
                data = response.json()
                if not isinstance(data.get('content'), str) or not data['content'].strip():
                    raise ValueError('empty assistant response')
                with transaction.atomic():
                    ConversationMessage.objects.create(
                        recommendation=result, role='user', content=form.cleaned_data['question'],
                    )
                    ConversationMessage.objects.create(
                        recommendation=result, role='assistant', content=data['content'],
                    )
                return redirect('recommend:conversation', pk=result.pk)
        except (requests.RequestException, ValueError):
            error = '연결이 잠시 끊겼어요. 작성한 질문은 그대로 두었으니 다시 시도해 주세요.'
            status = 503
        return render(request, 'recommend/conversation.html', conversation_context(result, form, error), status=status)
    return render(request, 'recommend/conversation.html', conversation_context(result, form))


# ---------------------------------------------------------------- F701 입력 검증
def recommend_form(request):
    """입력 검증만 확인하는 화면. 검증을 통과하면 저장하고 입력값을 그대로 보여줍니다."""
    saved = None
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            saved = form.save()
    else:
        form = RecommendationForm()
    return render(request, 'recommend/input_form.html', {
        'title': '나의 다음 책' if request.resolver_match.url_name == 'form' else '입력 검증',
        'form': form, 'saved': saved,
    })


# ---------------------------------------------------------------- F702 텍스트 추천 (제공, F709 심화 추가)
@proxy_error_page
def text_recommend(request):
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)

            # 1) Proxy 서버에 추천 생성을 요청한다
            payload = {
                'messages': [
                    {'role': 'developer', 'content': RECOMMEND_SYSTEM_PROMPT},
                    {'role': 'user', 'content': result.request_text},
                ],
                'use_tier_routing': result.use_tier_routing,     # F710
            }
            response = requests.post(settings.PROXY_URL + '/chat/completions', json=payload, timeout=180)

            # 2) 응답 코드를 확인한다 (F706)
            if response.status_code == 403:
                context = {'user_input': result.request_text}
                return render(request, 'recommend/rejected.html', context, status=403)
            if response.status_code != 200:
                context = {'user_input': result.request_text, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            # 3) 결과를 객체에 담는다
            data = response.json()
            result.content = data['content']
            result.model_used = data['model_used']               # F710 (제공)

            # F709: 채점 실패 시에도 생성된 추천을 표시한다.
            try:
                score_response = requests.post(
                    settings.PROXY_URL + '/chat/score',
                    json={'messages': payload['messages'], 'answer': result.content},
                    timeout=180,
                )
                if score_response.status_code == 200:
                    score_data = score_response.json()
                    result.score = score_data['score']
                    result.reason = score_data['reason']
                else:
                    result.reason = '추천 평가는 일시적으로 사용할 수 없습니다.'
            except requests.RequestException:
                result.reason = '추천 평가는 일시적으로 사용할 수 없습니다.'

            attach_conversation(request, result)
            result.save()
            return redirect('recommend:conversation', pk=result.pk)
    else:
        form = RecommendationForm()
    context = {
        'title': '텍스트 추천 생성',
        'form': form,
    }
    return render(request, 'recommend/input_form.html', context)


# ---------------------------------------------------------------- F704 라우트 결정 (제공)
@proxy_error_page
def decide_route(request):
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)

            payload = {'prompt': result.request_text}
            response = requests.post(settings.PROXY_URL + '/decide-route', json=payload, timeout=180)

            if response.status_code != 200:
                context = {'user_input': result.request_text, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            data = response.json()
            result.route = data['route']
            result.content = f'결정된 route: {result.route}'
            result.save()
            context = {
                'title': '라우트 결정',
                'user_input': result.request_text,
                'result': result,
            }
            return render(request, 'recommend/result_text.html', context)
    else:
        form = RecommendationForm()
    context = {
        'title': '라우트 결정',
        'form': form,
    }
    return render(request, 'recommend/input_form.html', context)


# ---------------------------------------------------------------- F705 이미지 생성 (제공, F712 심화 추가)
@proxy_error_page
def image_recommend(request):
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)

            payload = {'prompt': result.request_text}
            response = requests.post(settings.PROXY_URL + '/images/generations', json=payload, timeout=180)

            if response.status_code == 403:
                context = {'user_input': result.request_text}
                return render(request, 'recommend/rejected.html', context, status=403)
            if response.status_code != 200:
                context = {'user_input': result.request_text, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            data = response.json()
            image_base64 = data['image_base64']                  # jpeg 파일의 base64 문자열

            # F712: 고유한 파일명으로 미디어에 저장하고 URL로 제공한다.
            image_bytes = base64.b64decode(image_base64, validate=True)
            result.image.save(f'{uuid.uuid4()}.jpg', ContentFile(image_bytes), save=False)

            result.save()
            context = {
                'title': '이미지 생성',
                'result': result,
                'image_base64': image_base64,      # F705: 화면에서 data URI 로 바로 표시
            }
            return render(request, 'recommend/result_image.html', context)
    else:
        form = RecommendationForm()
    context = {
        'title': '이미지 생성',
        'form': form,
    }
    return render(request, 'recommend/input_form.html', context)


# ---------------------------------------------------------------- F707 이미지 분석 (제공)
@proxy_error_page
def image_analysis(request):
    if request.method == 'POST':
        form = ImageAnalysisForm(request.POST, request.FILES)
        if form.is_valid():
            result = form.save()                       # 업로드된 사진이 media/uploads/ 에 저장됨

            # 업로드된 파일을 base64 문자열로 바꾼다
            with result.image.open('rb') as uploaded_image:
                image_base64 = base64.b64encode(uploaded_image.read()).decode('utf-8')

            payload = {'image_base64': image_base64, 'question': result.question}
            response = requests.post(settings.PROXY_URL + '/images/analysis', json=payload, timeout=180)

            if response.status_code == 403:
                context = {'user_input': result.question}
                return render(request, 'recommend/rejected.html', context, status=403)
            if response.status_code != 200:
                context = {'user_input': result.question, 'status_code': response.status_code}
                return render(request, 'recommend/error.html', context, status=503)

            data = response.json()
            result.content = data['content']
            result.save()
            context = {
                'title': '이미지 분석',
                'user_input': result.question,
                'result': result,
                'uploaded': result.image,
            }
            return render(request, 'recommend/result_text.html', context)
    else:
        form = ImageAnalysisForm()
    context = {
        'title': '이미지 분석',
        'form': form,
    }
    return render(request, 'recommend/upload_form.html', context)


# ---------------------------------------------------------------- F708 API 흐름 제어
@proxy_error_page
def recommend_flow(request):
    """하나의 입력으로 라우트 결정 → 실행 → 결과 정리까지."""
    if request.method == 'POST':
        form = RecommendationForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)
            response = requests.post(
                settings.PROXY_URL + '/decide-route',
                json={'prompt': result.request_text}, timeout=180,
            )
            if response.status_code != 200:
                return render(request, 'recommend/error.html', {
                    'user_input': result.request_text, 'status_code': response.status_code,
                }, status=503)
            result.route = response.json()['route']
            if result.route not in ('/chat/completions', '/images/generations'):
                return render(request, 'recommend/error.html', {
                    'user_input': result.request_text, 'status_code': 503,
                }, status=503)

            image_base64 = ''
            if result.route == '/images/generations':
                payload = {'prompt': result.request_text}
            else:
                payload = {
                    'messages': [
                        {'role': 'developer', 'content': RECOMMEND_SYSTEM_PROMPT},
                        {'role': 'user', 'content': result.request_text},
                    ],
                    'use_tier_routing': result.use_tier_routing,
                }
            response = requests.post(
                settings.PROXY_URL + result.route, json=payload, timeout=180,
            )
            if response.status_code == 403:
                return render(request, 'recommend/rejected.html', {
                    'user_input': result.request_text,
                }, status=403)
            if response.status_code != 200:
                return render(request, 'recommend/error.html', {
                    'user_input': result.request_text, 'status_code': response.status_code,
                }, status=503)
            data = response.json()
            if result.route == '/images/generations':
                image_base64 = data['image_base64']
            else:
                result.content = data['content']
                result.model_used = data['model_used']
                attach_conversation(request, result)
            result.save()
            if result.route == '/chat/completions':
                return redirect('recommend:conversation', pk=result.pk)
            return render(request, 'recommend/recommend_flow.html', {
                'title': 'API 흐름 제어', 'result': result, 'image_base64': image_base64,
            })
    else:
        form = RecommendationForm()
    return render(request, 'recommend/input_form.html', {
        'title': 'API 흐름 제어', 'form': form,
    })


# ---------------------------------------------------------------- F711 TTS (심화)
# 이 항목은 FastAPI 엔드포인트(generate_speech)부터 Django 화면(result_audio.html)까지
# 기능 하나를 새로 추가하는 경험입니다. Django 쪽 뷰를 직접 작성하고, 결과 템플릿(result_audio.html)에 <audio> 태그를 넣습니다.
@proxy_error_page
def tts(request):
    if request.method == 'POST':
        form = SpeechForm(request.POST)
        if form.is_valid():
            result = form.save(commit=False)
            response = requests.post(
                settings.PROXY_URL + '/generate-speech',
                json={'text': result.text}, timeout=180,
            )
            if response.status_code != 200:
                return render(request, 'recommend/error.html', {
                    'user_input': result.text, 'status_code': response.status_code,
                }, status=503)
            audio_data = response.json()['audio_data']
            result.save()
            return render(request, 'recommend/result_audio.html', {
                'title': 'TTS 음성 변환', 'result': result, 'audio_data': audio_data,
            })
    else:
        form = SpeechForm()
    return render(request, 'recommend/input_form.html', {
        'title': 'TTS 음성 변환', 'form': form,
    })
