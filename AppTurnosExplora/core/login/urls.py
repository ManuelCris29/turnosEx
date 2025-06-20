from django.urls import path
from .views import LoginFormView, LogoutUserView

urlpatterns = [
    path('', LoginFormView.as_view(), name='login'),
    path('logout/', LogoutUserView.as_view(), name='logout'),
] 