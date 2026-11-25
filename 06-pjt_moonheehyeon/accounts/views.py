from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CustomUserChangeForm, CustomUserCreationForm


@require_http_methods(['GET', 'POST'])
def login(request):
    if request.user.is_authenticated:
        return redirect('books:index')
    form = AuthenticationForm(request, data=request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        auth_login(request, form.get_user())
        return redirect('books:index')
    return render(request, 'accounts/login.html', {'form': form})


@require_POST
@login_required
def logout(request):
    auth_logout(request)
    return redirect('books:index')


@require_http_methods(['GET', 'POST'])
def signup(request):
    if request.user.is_authenticated:
        return redirect('books:index')
    form = CustomUserCreationForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
    )
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        auth_login(request, user)
        return redirect('books:index')
    return render(request, 'accounts/signup.html', {'form': form})


@require_http_methods(['GET'])
def profile(request, username):
    person = get_object_or_404(get_user_model(), username=username)
    is_following = (
        request.user.is_authenticated
        and person.followers.filter(pk=request.user.pk).exists()
    )
    return render(request, 'accounts/profile.html', {
        'person': person,
        'is_following': is_following,
    })


@require_POST
@login_required(login_url='accounts:login')
def follow(request, user_pk):
    person = get_object_or_404(get_user_model(), pk=user_pk)
    if person == request.user:
        return HttpResponseForbidden('자기 자신은 팔로우할 수 없습니다.')
    if person.followers.filter(pk=request.user.pk).exists():
        person.followers.remove(request.user)
    else:
        person.followers.add(request.user)
    return redirect('accounts:profile', username=person.username)


@require_http_methods(['GET', 'POST'])
@login_required(login_url='accounts:login')
def update(request):
    form = CustomUserChangeForm(
        request.POST if request.method == 'POST' else None,
        request.FILES if request.method == 'POST' else None,
        instance=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        return redirect('books:index')
    return render(request, 'accounts/update.html', {'form': form})


@require_POST
@login_required(login_url='accounts:login')
def delete(request):
    request.user.delete()
    auth_logout(request)
    return redirect('books:index')


@require_http_methods(['GET', 'POST'])
@login_required(login_url='accounts:login')
def change_password(request):
    form = PasswordChangeForm(
        request.user,
        data=request.POST if request.method == 'POST' else None,
    )
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        return redirect('books:index')
    return render(request, 'accounts/change_password.html', {'form': form})
