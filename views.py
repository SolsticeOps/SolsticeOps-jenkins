import docker
from django.shortcuts import redirect, get_object_or_404
from core.models import Tool
from django.contrib.auth.decorators import login_required

@login_required
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

@login_required
def change_admin_password(request):
    if request.method == 'POST':
        tool = get_object_or_404(Tool, name='jenkins')
        new_password = request.POST.get('new_password')
        if new_password:
            try:
                import jenkins as jenkins_api
                
                port = tool.config_data.get('port', '8080')
                jenkins_url = f"http://localhost:{port}"
                username = tool.config_data.get('username', 'admin')
                password = tool.config_data.get('api_token') or tool.config_data.get('password')
                
                if username and password:
                    server = jenkins_api.Jenkins(jenkins_url, username=username, password=password)
                    script = f'hudson.model.User.get("{username}").setCredentials("{new_password}")'
                    server.run_script(script)
            except Exception as e:
                print(f"Error changing Jenkins password: {e}")
            
            # We do NOT save the password in tool.config_data anymore
            tool.save()
    return redirect('tool_detail', tool_name='jenkins')

@login_required
def find_jenkins(request):
    tool = get_object_or_404(Tool, name='jenkins')
    try:
        client = docker.from_env()
        # Broaden search: check for any container with 'jenkins' in image or name
        all_containers = client.containers.list(all=True)
        found_container = None
        
        for c in all_containers:
            image_tags = c.image.tags
            if any('jenkins' in tag.lower() for tag in image_tags) or 'jenkins' in c.name.lower():
                found_container = c
                break
        
        if found_container:
            tool.status = 'installed' if found_container.status == 'running' else 'error'
            tool.version = found_container.image.tags[0] if found_container.image.tags else "Unknown"
            tool.config_data['container_id'] = found_container.id
            tool.config_data['container_name'] = found_container.name
            
            # Try to extract port from host config if available
            try:
                ports = found_container.attrs.get('HostConfig', {}).get('PortBindings', {})
                # Look for the host port mapped to Jenkins' internal 8080 port
                for container_port, host_bindings in ports.items():
                    if '8080' in container_port and host_bindings:
                        detected_port = host_bindings[0].get('HostPort')
                        if detected_port:
                            tool.config_data['port'] = detected_port
                        break
            except Exception as e:
                print(f"Error detecting port: {e}")

            tool.save()
        else:
            tool.status = 'not_installed'
            tool.config_data['error_log'] = "No Jenkins container found."
            tool.save()
    except Exception as e:
        tool.config_data['error_log'] = str(e)
        tool.save()
    return redirect('tool_detail', tool_name='jenkins')
