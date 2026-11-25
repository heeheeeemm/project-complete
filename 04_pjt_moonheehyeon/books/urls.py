from django.urls import path

from . import views

app_name = 'books'
urlpatterns = [
    path('', views.index, name='index'),
    path('create/', views.create, name='create'),
    path('cover/', views.cover_lookup, name='cover_lookup'),
    path('covers/<str:filename>/', views.cover_image, name='cover_image'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/update/', views.update, name='update'),
    path('<int:pk>/delete/', views.delete, name='delete'),
    path('<int:pk>/author-info/', views.author_info, name='author_info'),
]
