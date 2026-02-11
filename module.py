import jenkins as python_jenkins
import re
import time
import threading
from django.shortcuts import render, redirect
from django.urls import path
from core.plugin_system import BaseModule
from .cli_wrapper import DockerCLI

class Module(BaseModule):
    @property
    def module_id(self):
        return "jenkins"

    @property
    def module_name(self):
        return "Jenkins"

    description = "CI/CD automation server."
    version = "1.0.0"

    def get_service_version(self):
        try:
            # Try to get version from the running container if possible
            # Jenkins version is usually in the footer or available via API
            # But we can also check the image tag or run a command in container
            import docker
                    client = DockerCLI()
            container = client.containers.get('jenkins')
            if container.status == 'running':
                # Run 'java -jar /usr/share/jenkins/jenkins.war --version'
                res = container.exec_run("java -jar /usr/share/jenkins/jenkins.war --version")
                if res.exit_code == 0:
                    return res.output.decode().strip()
        except Exception:
            pass
        return None

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
                username = tool.config_data.get('username', 'admin')
                password = tool.config_data.get('api_token') or tool.config_data.get('password')
                
                if password:
                    server = python_jenkins.Jenkins(jenkins_url, username=username, password=password)
                    
                    target = request.GET.get('tab')
                    if target == 'jenkins_nodes':
                        context['jenkins_nodes'] = server.get_nodes()
                    elif target == 'jenkins_plugins':
                        context['jenkins_plugins'] = server.get_plugins_info()
                    else:
                        context['jenkins_jobs'] = server.get_jobs()
                    
                    context['jenkins_connected'] = True
                else:
                    context['jenkins_auth_required'] = True
            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "Unauthorized" in error_msg:
                    context['jenkins_auth_error'] = True
                context['jenkins_error'] = error_msg.split('\n')[0] # Only show the first line of the error
        return context

    def handle_hx_request(self, request, tool, target):
        context = self.get_context_data(request, tool)
        context['tool'] = tool
        if target == 'jenkins_jobs':
            return render(request, 'core/partials/jenkins_jobs.html', context)
        elif target == 'jenkins_nodes':
            return render(request, 'core/partials/jenkins_nodes.html', context)
        elif target == 'jenkins_plugins':
            return render(request, 'core/partials/jenkins_plugins.html', context)
        return None

    def install(self, request, tool):
        if tool.status not in ['not_installed', 'error'] and request.method != 'POST':
            return

        if request.method == 'POST':
            port = request.POST.get('port', '8080')
            jnlp_port = request.POST.get('jnlp_port', '50000')
            volume_name = request.POST.get('volume_name', 'jenkins_home')
            container_name = request.POST.get('container_name', 'jenkins')
            privileged = request.POST.get('privileged') == 'on'

            tool.status = 'installing'
            tool.save()

            def run_jenkins_install():
                try:
                    client = DockerCLI()
                    tool.current_stage = "Checking for Docker..."
                    tool.save()
                    
                    # Ensure volume exists
                    tool.current_stage = f"Creating volume {volume_name}..."
                    tool.save()
                    client.volumes.create(name=volume_name)

                    # Ensure network exists
                    tool.current_stage = "Creating network jenkins_network..."
                    tool.save()
                    try:
                        client.networks.get("jenkins_network")
                    except docker.errors.NotFound:
                        client.networks.create("jenkins_network", driver="bridge")

                    # Pull image
                    tool.current_stage = "Pulling Jenkins image (jenkins/jenkins:lts)..."
                    tool.save()
                    client.images.pull("jenkins/jenkins", tag="lts")

                    # Run container
                    tool.current_stage = "Starting Jenkins container..."
                    tool.save()
                    
                    ports = {
                        '8080/tcp': port,
                        '50000/tcp': jnlp_port
                    }
                    
                    volumes = {
                        volume_name: {'bind': '/var/jenkins_home', 'mode': 'rw'}
                    }

                    container = client.containers.run(
                        "jenkins/jenkins:lts",
                        name=container_name,
                        ports=ports,
                        volumes=volumes,
                        detach=True,
                        privileged=privileged,
                        network="jenkins_network",
                        restart_policy={"Name": "always"}
                    )

                    tool.status = 'installing'
                    tool.current_stage = "Waiting for initial password..."
                    tool.config_data['port'] = port
                    tool.config_data['container_id'] = container.id
                    tool.config_data['container_name'] = container_name
                    tool.save()

                    # Wait for initial password in logs
                    initial_password = None
                    for _ in range(30):
                        logs = container.logs().decode('utf-8')
                        match = re.search(r'Please use the following password to proceed to installation:.*?([a-f0-9]{32})', logs, re.DOTALL)
                        if match:
                            initial_password = match.group(1)
                            break
                        time.sleep(5)
                    
                    if initial_password:
                        tool.current_stage = "Configuring Jenkins (setting admin/admin)..."
                        tool.save()
                        
                        # Wait for Jenkins to be ready
                        jenkins_url = f"http://localhost:{port}"
                        server = None
                        for _ in range(20):
                            try:
                                server = python_jenkins.Jenkins(jenkins_url, username='admin', password=initial_password)
                                server.get_version()
                                break
                            except:
                                time.sleep(5)
                        
                        if server:
                            setup_script = """
                            import jenkins.model.*
                            import hudson.security.*
                            import jenkins.install.*

                            def instance = Jenkins.getInstance()

                            // Set admin password
                            def hudsonRealm = new HudsonPrivateSecurityRealm(false)
                            hudsonRealm.createAccount("admin", "admin")
                            instance.setSecurityRealm(hudsonRealm)

                            def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
                            strategy.setAllowAnonymousRead(false)
                            instance.setAuthorizationStrategy(strategy)

                            // Disable setup wizard
                            instance.setInstallState(InstallState.INITIAL_SETUP_COMPLETED)

                            // Set Jenkins URL
                            def location = jenkins.model.JenkinsLocationConfiguration.get()
                            location.setUrl("http://127.0.0.1:{{PORT}}/")
                            location.save()

                            // Generate API Token for admin
                            def user = hudson.model.User.get("admin")
                            def prop = user.getProperty(jenkins.security.ApiTokenProperty.class)
                            def token = prop.tokenStore.generateNewToken("SolsticeOps").plainValue
                            user.save()
                            
                            // We will print the token so it can be captured by the installer
                            println("SOLSTICE_JENKINS_TOKEN:" + token)

                            // Install recommended plugins
                            def pluginManager = instance.getPluginManager()
                            def updateCenter = instance.getUpdateCenter()
                            def plugins = [
                                "workflow-aggregator", "git", "pipeline-stage-view", 
                                "ssh-slaves", "matrix-auth", "pam-auth", "ldap", 
                                "email-ext", "mailer", "dark-theme"
                            ]
                            
                            def installed = false
                            plugins.each { 
                                if (!pluginManager.getPlugin(it)) {
                                    def plugin = updateCenter.getById("default").getPlugin(it)
                                    if (plugin) {
                                        plugin.deploy()
                                        installed = true
                                    }
                                }
                            }
                            if (installed) {
                                instance.save()
                                instance.restart()
                            }

                            instance.save()
                            """.replace('{{PORT}}', port)
                            # Get token from script output
                            script_output = server.run_script(setup_script)
                            token_match = re.search(r'SOLSTICE_JENKINS_TOKEN:([a-zA-Z0-9-]+)', script_output)
                            if token_match:
                                tool.config_data['api_token'] = token_match.group(1)
                                tool.config_data['username'] = 'admin'
                                # Remove password after getting token
                                if 'password' in tool.config_data:
                                    del tool.config_data['password']

                            tool.status = 'installed'
                            tool.current_stage = "Jenkins installed, configured and plugins requested"
                        else:
                            tool.status = 'error'
                            tool.current_stage = "Jenkins started, but auto-config failed (timeout)"
                    else:
                        tool.status = 'error'
                        tool.current_stage = "Jenkins started, but initial password not found in logs"

                    tool.version = "LTS"
                    tool.save()
                except Exception as e:
                    tool.status = 'error'
                    tool.config_data['error_log'] = str(e)
                    tool.save()

            threading.Thread(target=run_jenkins_install).start()

    def get_urls(self):
        from . import views
        return [
            path('jenkins/update_creds/', views.update_creds, name='update_jenkins_creds'),
            path('jenkins/change_password/', views.change_admin_password, name='change_jenkins_admin_password'),
            path('jenkins/find/', views.find_jenkins, name='find_jenkins'),
        ]
