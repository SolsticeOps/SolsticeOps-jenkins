from django.shortcuts import redirect, get_object_or_404
from core.models import Tool

def update_creds(request):
    if request.method == 'POST':
        tool = get_object_or_404(Tool, name='jenkins')
        username = request.POST.get('username')
        password = request.POST.get('password')
        if username and password:
            tool.config_data['username'] = username
            tool.config_data['password'] = password
            tool.save()
    return redirect('tool_detail', tool_name='jenkins')
