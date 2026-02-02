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

def change_admin_password(request):
    if request.method == 'POST':
        tool = get_object_or_404(Tool, name='jenkins')
        new_password = request.POST.get('new_password')
        if new_password:
            # Here we would normally call Jenkins API to change password
            # For now, we just update it in our config
            tool.config_data['password'] = new_password
            tool.save()
    return redirect('tool_detail', tool_name='jenkins')
