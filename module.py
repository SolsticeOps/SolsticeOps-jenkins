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

    def get_install_template_name(self):
        return "core/modules/jenkins_install.html"

    def get_logs_url(self, tool):
        container_name = tool.config_data.get('container_name', 'jenkins')
        return f'/docker/container/{container_name}/logs/'

    def get_extra_actions_template_name(self):
        return "core/modules/jenkins_extra_actions.html"

    def get_extra_content_template_name(self):
        return "core/modules/jenkins_modals.html"

    def get_resource_tabs(self):
        return [
            {
                'id': 'jenkins_jobs', 
                'label': 'Jobs', 
                'hx_get': '/tool/jenkins/?tab=jenkins_jobs', 
                'hx_auto_refresh': 'load, every 10s',
                'template': 'core/modules/jenkins_loading.html'
            },
            {
                'id': 'jenkins_nodes', 
                'label': 'Nodes', 
                'hx_get': '/tool/jenkins/?tab=jenkins_nodes',
                'template': 'core/modules/jenkins_loading.html'
            },
            {
                'id': 'jenkins_plugins', 
                'label': 'Plugins', 
                'hx_get': '/tool/jenkins/?tab=jenkins_plugins',
                'template': 'core/modules/jenkins_loading.html'
            },
        ]

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
            path('jenkins/change_password/', views.change_admin_password, name='change_jenkins_admin_password'),
        ]
