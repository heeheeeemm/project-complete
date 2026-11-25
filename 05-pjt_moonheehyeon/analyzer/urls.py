from django.urls import path

from . import views

app_name = 'analyzer'
urlpatterns = [path('', views.index, name='index')]
urlpatterns += [
    path('results/latest/', views.saved_result, name='latest-result'),
    path('results/<int:pk>/', views.saved_result, name='saved-result'),
]
