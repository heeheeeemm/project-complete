from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import BookForm, ThreadForm
from .models import Book, Thread


@require_http_methods(['GET'])
def index(request):
    books = Book.objects.select_related('user').order_by('-pk')
    return render(request, 'books/index.html', {'books': books})


@require_http_methods(['GET', 'POST'])
@login_required(login_url='accounts:login')
def create(request):
    form = BookForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        book = form.save(commit=False)
        book.user = request.user
        book.save()
        return redirect('books:detail', book_pk=book.pk)
    return render(request, 'books/create.html', {'form': form})


@require_http_methods(['GET'])
def detail(request, book_pk):
    book = get_object_or_404(Book.objects.select_related('user'), pk=book_pk)
    return render(request, 'books/detail.html', {'book': book})


@require_http_methods(['GET', 'POST'])
@login_required(login_url='accounts:login')
def update(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)
    if book.user != request.user:
        return HttpResponseForbidden('도서를 등록한 사용자만 수정할 수 있습니다.')
    form = BookForm(request.POST if request.method == 'POST' else None, instance=book)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('books:detail', book_pk=book.pk)
    return render(request, 'books/update.html', {'book': book, 'form': form})


@require_POST
@login_required(login_url='accounts:login')
def delete(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)
    if book.user != request.user:
        return HttpResponseForbidden('도서를 등록한 사용자만 삭제할 수 있습니다.')
    book.delete()
    return redirect('books:index')


@require_http_methods(['GET', 'POST'])
@login_required(login_url='accounts:login')
def thread_create(request, book_pk):
    book = get_object_or_404(Book, pk=book_pk)
    form = ThreadForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        thread = form.save(commit=False)
        thread.user = request.user
        thread.book = book
        thread.save()
        return redirect('books:thread_detail', thread_pk=thread.pk)
    return render(request, 'books/thread_create.html', {'book': book, 'form': form})


@require_http_methods(['GET'])
def thread_detail(request, thread_pk):
    thread = get_object_or_404(Thread.objects.select_related('user', 'book'), pk=thread_pk)
    is_liked = (
        request.user.is_authenticated
        and thread.like_users.filter(pk=request.user.pk).exists()
    )
    return render(request, 'books/thread_detail.html', {
        'thread': thread,
        'is_liked': is_liked,
    })


@require_http_methods(['GET', 'POST'])
@login_required(login_url='accounts:login')
def thread_update(request, thread_pk):
    thread = get_object_or_404(Thread, pk=thread_pk)
    if thread.user != request.user:
        return HttpResponseForbidden('쓰레드를 작성한 사용자만 수정할 수 있습니다.')
    form = ThreadForm(request.POST if request.method == 'POST' else None, instance=thread)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('books:thread_detail', thread_pk=thread.pk)
    return render(request, 'books/thread_update.html', {'thread': thread, 'form': form})


@require_POST
@login_required(login_url='accounts:login')
def thread_delete(request, thread_pk):
    thread = get_object_or_404(Thread, pk=thread_pk)
    if thread.user != request.user:
        return HttpResponseForbidden('쓰레드를 작성한 사용자만 삭제할 수 있습니다.')
    book_pk = thread.book_id
    thread.delete()
    return redirect('books:detail', book_pk=book_pk)


@require_POST
@login_required(login_url='accounts:login')
def like(request, thread_pk):
    thread = get_object_or_404(Thread, pk=thread_pk)
    if thread.like_users.filter(pk=request.user.pk).exists():
        thread.like_users.remove(request.user)
    else:
        thread.like_users.add(request.user)
    return redirect('books:thread_detail', thread_pk=thread.pk)
