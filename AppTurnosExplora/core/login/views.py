from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect


# Create your views here.
class LoginFormView(LoginView):
    template_name = 'login.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs) 
        context['title']= 'Iniciar sesión'    
        return context

class LogoutUserView(LogoutView):
    http_method_names = ['post', 'options', 'get']
    
    next_page = 'login'

    def get(self, request, *args, **kwargs):
        logout(request)
        return redirect(self.next_page)
        