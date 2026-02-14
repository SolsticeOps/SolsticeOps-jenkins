from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from core.models import Tool
from unittest.mock import patch, MagicMock

User = get_user_model()

class JenkinsModuleTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_superuser(username='admin', password='password', email='admin@test.com')
        self.client.login(username='admin', password='password')
        self.tool = Tool.objects.create(name="jenkins", status="installed", config_data={'port': '8080', 'api_token': 'test-token'})

    @patch('jenkins.Jenkins')
    def test_jenkins_jobs_partial(self, mock_jenkins):
        mock_server = MagicMock()
        mock_server.get_jobs.return_value = [{'name': 'test-job', 'color': 'blue'}]
        mock_jenkins.return_value = mock_server
        
        # Ensure we have the necessary config for Jenkins connection
        self.tool.config_data = {'port': '8080', 'username': 'admin', 'api_token': 'test-token'}
        self.tool.save()
        
        response = self.client.get(reverse('tool_detail', kwargs={'tool_name': 'jenkins'}) + "?tab=jenkins_jobs", HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "test-job")

    def test_jenkins_update_creds(self):
        url = reverse('update_jenkins_creds')
        response = self.client.post(url, {'username': 'newadmin', 'password': 'newpassword'})
        self.assertEqual(response.status_code, 302)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.config_data['username'], 'newadmin')
        self.assertEqual(self.tool.config_data['password'], 'newpassword')
        
        # Test empty creds (should not update)
        self.client.post(url, {'username': '', 'password': ''})
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.config_data['username'], 'newadmin')

    @patch('jenkins.Jenkins')
    def test_jenkins_change_password(self, mock_jenkins):
        mock_server = MagicMock()
        mock_jenkins.return_value = mock_server
        self.tool.config_data = {'username': 'admin', 'password': 'oldpassword'}
        self.tool.save()
        
        url = reverse('change_jenkins_admin_password')
        response = self.client.post(url, {'new_password': 'verynewpassword'})
        self.assertEqual(response.status_code, 302)
        mock_server.run_script.assert_called_once()

    @patch('modules.jenkins.views.DockerCLI')
    def test_find_jenkins(self, mock_docker):
        mock_client = MagicMock()
        
        # Use a real object or a very specific mock for the container
        class MockContainer:
            def __init__(self):
                self.name = "jenkins-test"
                self.status = "running"
                self.id = "jenk123"
                self.image = MagicMock()
                self.image.tags = ["jenkins/jenkins:lts"]
                self.attrs = {'HostConfig': {'PortBindings': {'8080/tcp': [{'HostPort': '8081'}]}}}
        
        mock_container = MockContainer()
        mock_client.containers.list.return_value = [mock_container]
        mock_docker.return_value = mock_client
        
        url = reverse('find_jenkins')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'installed')
        self.assertEqual(self.tool.config_data['port'], '8081')

    @patch('modules.jenkins.module.DockerCLI')
    def test_jenkins_module_logic(self, mock_docker):
        from modules.jenkins.module import Module
        module = Module()
        
        self.assertEqual(module.module_id, "jenkins")
        self.assertEqual(module.module_name, "Jenkins")
        
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_container.status = 'running'
        mock_container.exec_run.return_value = MagicMock(exit_code=0, output=b"2.440.1")
        mock_client.containers.get.return_value = mock_container
        mock_docker.return_value = mock_client
        
        self.assertEqual(module.get_service_version(), "2.440.1")
        self.assertEqual(module.get_service_status(self.tool), "running")
        
        module.service_start(self.tool)
        mock_container.start.assert_called_once()
        
        module.service_stop(self.tool)
        mock_container.stop.assert_called_once()
        
        module.service_restart(self.tool)
        mock_container.restart.assert_called_once()
        
        self.assertEqual(module.get_logs_url(self.tool), '/docker/container/jenkins/logs/')
        self.assertEqual(module.get_install_template_name(), "core/modules/jenkins_install.html")
        
        # Test context data with jobs
        mock_server = MagicMock()
        mock_server.get_jobs.return_value = []
        with patch('jenkins.Jenkins', return_value=mock_server):
            self.tool.config_data['password'] = 'test'
            context = module.get_context_data(MagicMock(), self.tool)
            self.assertTrue(context['jenkins_connected'])

    def test_jenkins_handle_hx_request(self):
        from modules.jenkins.module import Module
        module = Module()
        request = MagicMock()
        with patch.object(Module, 'get_context_data', return_value={'tool': self.tool}):
            for target in ['jenkins_jobs', 'jenkins_nodes', 'jenkins_plugins']:
                response = module.handle_hx_request(request, self.tool, target)
                self.assertIsNotNone(response)

    @patch('modules.jenkins.module.threading.Thread')
    def test_jenkins_install(self, mock_thread):
        from modules.jenkins.module import Module
        module = Module()
        self.tool.status = 'not_installed'
        self.tool.save()
        
        # Mock POST request
        request = MagicMock()
        request.method = 'POST'
        request.POST = {'port': '8080'}
        
        module.install(request, self.tool)
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'installing')
        mock_thread.assert_called_once()

    @patch('core.docker_cli_wrapper.run_command')
    def test_jenkins_status_detection(self, mock_run):
        # Mock docker inspect
        mock_run.return_value = b'[{"Id": "jenk123", "Name": "/jenkins", "State": {"Status": "running"}}]'
        
        from core.plugin_system import plugin_registry
        module = plugin_registry.get_module("jenkins")
        status = module.get_service_status(self.tool)
        self.assertEqual(status, "running")

    @patch('modules.jenkins.module.DockerCLI')
    @patch('jenkins.Jenkins')
    @patch('modules.jenkins.module.threading.Thread')
    def test_jenkins_install_full_process(self, mock_thread, mock_jenkins, mock_docker):
        from modules.jenkins.module import Module
        module = Module()
        self.tool.status = 'not_installed'
        self.tool.save()
        
        request = MagicMock()
        request.method = 'POST'
        request.POST = {
            'port': '8081',
            'jnlp_port': '50001',
            'volume_name': 'jenkins_vol',
            'container_name': 'jenkins_cont',
            'privileged': 'on'
        }
        
        module.install(request, self.tool)
        target_func = mock_thread.call_args[1]['target']
        
        # Mock Docker components
        mock_cli = MagicMock()
        mock_docker.return_value = mock_cli
        mock_container = MagicMock()
        mock_container.id = "jenk123"
        mock_container.logs.return_value = b"Please use the following password to proceed to installation:\n1234567890abcdef1234567890abcdef\n"
        mock_cli.containers.run.return_value = mock_container
        mock_cli.networks.get.return_value = None
        
        # Mock Jenkins API
        mock_server = MagicMock()
        mock_jenkins.return_value = mock_server
        mock_server.run_script.return_value = "SOLSTICE_JENKINS_TOKEN:test-api-token"
        
        target_func()
        
        self.tool.refresh_from_db()
        self.assertEqual(self.tool.status, 'installed')
        self.assertEqual(self.tool.config_data['api_token'], 'test-api-token')
        self.assertEqual(self.tool.config_data['port'], '8081')
        self.assertEqual(self.tool.config_data['container_name'], 'jenkins_cont')

    @patch('jenkins.Jenkins')
    def test_jenkins_context_data_tabs(self, mock_jenkins):
        from modules.jenkins.module import Module
        module = Module()
        
        mock_server = MagicMock()
        mock_jenkins.return_value = mock_server
        mock_server.get_nodes.return_value = [{'name': 'master'}]
        mock_server.get_plugins_info.return_value = [{'name': 'git'}]
        
        self.tool.config_data['api_token'] = 'token'
        self.tool.save()
        
        request = MagicMock()
        
        # Test nodes tab
        request.GET = {'tab': 'jenkins_nodes'}
        context = module.get_context_data(request, self.tool)
        self.assertEqual(context['jenkins_nodes'], [{'name': 'master'}])
        
        # Test plugins tab
        request.GET = {'tab': 'jenkins_plugins'}
        context = module.get_context_data(request, self.tool)
        self.assertEqual(context['jenkins_plugins'], [{'name': 'git'}])

    @patch('jenkins.Jenkins')
    def test_jenkins_auth_errors(self, mock_jenkins):
        from modules.jenkins.module import Module
        module = Module()
        
        mock_jenkins.side_effect = Exception("401 Unauthorized")
        self.tool.config_data['api_token'] = 'wrong'
        
        context = module.get_context_data(MagicMock(), self.tool)
        self.assertTrue(context.get('jenkins_auth_error'))
        
        mock_jenkins.side_effect = Exception("Some other error")
        context = module.get_context_data(MagicMock(), self.tool)
        self.assertEqual(context.get('jenkins_error'), "Some other error")

    def test_jenkins_no_password(self):
        from modules.jenkins.module import Module
        module = Module()
        self.tool.config_data = {'port': '8080'} # No password or token
        self.tool.save()
        
        context = module.get_context_data(MagicMock(), self.tool)
        self.assertTrue(context.get('jenkins_auth_required'))
