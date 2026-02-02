import jenkins
import docker
import re
import time
import threading
from django.shortcuts import render, redirect
from django.urls import path
from core.plugin_system import BaseModule

class Module(BaseModule):
    module_id = "jenkins"
    module_name = "Jenkins"
    description = "CI/CD automation server."

    def get_context_data(self, request, tool):
        context = {}
        if tool.status == 'installed':
            try:
                port = tool.config_data.get('port', '8080')
                jenkins_url = f"http://localhost:{port}"
                username = tool.config_data.get('username')
                password = tool.config_data.get('password')
                
                if username and password:
                    server = jenkins.Jenkins(jenkins_url, username=username, password=password)
                    context['jenkins_jobs'] = server.get_jobs()
                    context['jenkins_connected'] = True
                else:
                    context['jenkins_auth_required'] = True
            except Exception as e:
                context['jenkins_error'] = str(e)
        return context

    def handle_hx_request(self, request, tool, target):
        context = self.get_context_data(request, tool)
        context['tool'] = tool
        if target == 'jenkins_jobs':
            return render(request, 'core/partials/jenkins_jobs.html', context)
        return None

    def get_urls(self):
        from . import views
        return [
            path('jenkins/update_creds/', views.update_creds, name='update_jenkins_creds'),
        ]
