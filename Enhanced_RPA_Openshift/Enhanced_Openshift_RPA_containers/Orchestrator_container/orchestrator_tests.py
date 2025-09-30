"""
Unit tests for enhanced orchestrator services
"""
import pytest
import os
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Import services to test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.config_manager import ConfigManager
from services.totp_manager import TOTPManager


class TestConfigManager:
    """Tests for ConfigManager"""
    
    def test_get_from_environment(self):
        """Test getting config from environment variables"""
        os.environ['TEST_CONFIG_KEY'] = 'test_value'
        
        config = ConfigManager()
        value = config.get('TEST_CONFIG_KEY')
        
        assert value == 'test_value'
        
        # Cleanup
        del os.environ['TEST_CONFIG_KEY']
    
    def test_get_with_default(self):
        """Test getting config with default value"""
        config = ConfigManager()
        value = config.get('NON_EXISTENT_KEY', 'default_value')
        
        assert value == 'default_value'
    
    def test_get_int(self):
        """Test getting integer config"""
        os.environ['TEST_INT'] = '42'
        
        config = ConfigManager()
        value = config.get_int('TEST_INT')
        
        assert value == 42
        assert isinstance(value, int)
        
        del os.environ['TEST_INT']
    
    def test_get_int_with_invalid(self):
        """Test getting int with invalid value returns default"""
        os.environ['TEST_INVALID_INT'] = 'not_a_number'
        
        config = ConfigManager()
        value = config.get_int('TEST_INVALID_INT', default=10)
        
        assert value == 10
        
        del os.environ['TEST_INVALID_INT']
    
    def test_get_bool(self):
        """Test getting boolean config"""
        test_cases = [
            ('true', True),
            ('True', True),
            ('yes', True),
            ('1', True),
            ('false', False),
            ('False', False),
            ('no', False),
            ('0', False),
        ]
        
        config = ConfigManager()
        
        for str_value, expected_bool in test_cases:
            os.environ['TEST_BOOL'] = str_value
            value = config.get_bool('TEST_BOOL')
            assert value == expected_bool, f"Failed for {str_value}"
            del os.environ['TEST_BOOL']
    
    def test_get_list(self):
        """Test getting list config"""
        os.environ['TEST_LIST'] = 'item1,item2,item3'
        
        config = ConfigManager()
        value = config.get_list('TEST_LIST')
        
        assert value == ['item1', 'item2', 'item3']
        assert isinstance(value, list)
        
        del os.environ['TEST_LIST']
    
    def test_get_list_json(self):
        """Test getting list from JSON"""
        os.environ['TEST_JSON_LIST'] = '["item1", "item2", "item3"]'
        
        config = ConfigManager()
        value = config.get_list('TEST_JSON_LIST')
        
        assert value == ['item1', 'item2', 'item3']
        
        del os.environ['TEST_JSON_LIST']
    
    def test_get_dict(self):
        """Test getting dict config"""
        os.environ['TEST_DICT'] = '{"key1": "value1", "key2": "value2"}'
        
        config = ConfigManager()
        value = config.get_dict('TEST_DICT')
        
        assert value == {"key1": "value1", "key2": "value2"}
        assert isinstance(value, dict)
        
        del os.environ['TEST_DICT']
    
    def test_get_secret_required(self):
        """Test getting required secret raises error if missing"""
        config = ConfigManager()
        
        with pytest.raises(ValueError, match="Required secret"):
            config.get_secret('NON_EXISTENT_SECRET', required=True)
    
    def test_validate_required_config(self):
        """Test validating required config keys"""
        os.environ['REQUIRED_KEY_1'] = 'value1'
        os.environ['REQUIRED_KEY_2'] = 'value2'
        
        config = ConfigManager()
        result = config.validate_required_config(['REQUIRED_KEY_1', 'REQUIRED_KEY_2'])
        
        assert result is True
        
        # Test with missing key
        result = config.validate_required_config(['REQUIRED_KEY_1', 'MISSING_KEY'])
        
        assert result is False
        
        del os.environ['REQUIRED_KEY_1']
        del os.environ['REQUIRED_KEY_2']
    
    def test_get_provider_credentials(self):
        """Test getting provider credentials"""
        os.environ['METROFIBER_URL'] = 'https://portal.metrofiber.co.za'
        os.environ['METROFIBER_EMAIL'] = 'test@example.com'
        os.environ['METROFIBER_PASSWORD'] = 'testpass'
        
        config = ConfigManager()
        creds = config.get_provider_credentials('metrofiber')
        
        assert 'url' in creds
        assert creds['url'] == 'https://portal.metrofiber.co.za'
        assert creds['email'] == 'test@example.com'
        assert creds['password'] == 'testpass'
        
        # Cleanup
        del os.environ['METROFIBER_URL']
        del os.environ['METROFIBER_EMAIL']
        del os.environ['METROFIBER_PASSWORD']


class TestTOTPManager:
    """Tests for TOTPManager"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create mock config manager"""
        config = Mock(spec=ConfigManager)
        config.get.side_effect = lambda key, default=None: {
            'VALKEY_HOST': 'localhost',
            'VALKEY_PORT': '6379',
            'VALKEY_PASSWORD': 'testpass',
            'OCTOTEL_TOTP_SECRET': 'JBSWY3DPEHPK3PXP'
        }.get(key, default)
        return config
    
    @pytest.fixture
    def mock_valkey_client(self):
        """Create mock Valkey client"""
        client = MagicMock()
        client.ping.return_value = True
        client.exists.return_value = 0
        client.set.return_value = True
        client.get.return_value = None
        client.incr.return_value = 1
        client.zadd.return_value = 1
        client.zrevrange.return_value = []
        return client
    
    def test_provider_requires_totp(self, mock_config_manager):
        """Test checking if provider requires TOTP"""
        totp_manager = TOTPManager(mock_config_manager)
        
        assert totp_manager.provider_requires_totp('octotel') is True
        assert totp_manager.provider_requires_totp('Octotel') is True
        assert totp_manager.provider_requires_totp('metrofiber') is False
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_initialize_success(self, mock_valkey_class, mock_config_manager):
        """Test successful initialization"""
        mock_valkey_class.return_value.ping.return_value = True
        
        totp_manager = TOTPManager(mock_config_manager)
        result = totp_manager.initialize()
        
        assert result is True
        assert totp_manager.valkey_client is not None
        assert 'octotel' in totp_manager.totp_secrets
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_initialize_failure(self, mock_valkey_class, mock_config_manager):
        """Test initialization failure"""
        mock_valkey_class.side_effect = Exception("Connection failed")
        
        totp_manager = TOTPManager(mock_config_manager)
        result = totp_manager.initialize()
        
        assert result is False
    
    @patch('services.totp_manager.valkey.Valkey')
    @patch('services.totp_manager.pyotp.TOTP')
    def test_get_fresh_totp_code_success(self, mock_totp_class, mock_valkey_class, 
                                         mock_config_manager, mock_valkey_client):
        """Test generating fresh TOTP code"""
        mock_valkey_class.return_value = mock_valkey_client
        mock_totp_instance = MagicMock()
        mock_totp_instance.now.return_value = '123456'
        mock_totp_class.return_value = mock_totp_instance
        
        totp_manager = TOTPManager(mock_config_manager)
        totp_manager.initialize()
        
        code = totp_manager.get_fresh_totp_code('octotel', job_id=1)
        
        assert code == '123456'
        mock_valkey_client.set.assert_called()
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_is_code_used(self, mock_valkey_class, mock_config_manager, mock_valkey_client):
        """Test checking if code is used"""
        mock_valkey_class.return_value = mock_valkey_client
        
        totp_manager = TOTPManager(mock_config_manager)
        totp_manager.initialize()
        
        # Code not used
        mock_valkey_client.exists.return_value = 0
        assert totp_manager._is_code_used('octotel', '123456') is False
        
        # Code used
        mock_valkey_client.exists.return_value = 1
        assert totp_manager._is_code_used('octotel', '123456') is True
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_reserve_code(self, mock_valkey_class, mock_config_manager, mock_valkey_client):
        """Test reserving a TOTP code"""
        mock_valkey_class.return_value = mock_valkey_client
        mock_valkey_client.set.return_value = True
        
        totp_manager = TOTPManager(mock_config_manager)
        totp_manager.initialize()
        
        result = totp_manager._reserve_code('octotel', '123456', job_id=1)
        
        assert result is True
        mock_valkey_client.set.assert_called()
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_mark_totp_consumed(self, mock_valkey_class, mock_config_manager, mock_valkey_client):
        """Test marking TOTP as consumed"""
        mock_valkey_class.return_value = mock_valkey_client
        
        totp_manager = TOTPManager(mock_config_manager)
        totp_manager.initialize()
        
        totp_manager.mark_totp_consumed('octotel', job_id=1, success=True)
        
        # Verify metrics were updated
        mock_valkey_client.set.assert_called()
        mock_valkey_client.incr.assert_called()
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_get_totp_metrics(self, mock_valkey_class, mock_config_manager, mock_valkey_client):
        """Test getting TOTP metrics"""
        mock_valkey_class.return_value = mock_valkey_client
        mock_valkey_client.get.side_effect = lambda key: {
            'totp:generated:octotel': '10',
            'totp:metrics:octotel:success': '8',
            'totp:metrics:octotel:failure': '2'
        }.get(key, '0')
        
        totp_manager = TOTPManager(mock_config_manager)
        totp_manager.initialize()
        
        metrics = totp_manager.get_totp_metrics('octotel')
        
        assert metrics['provider'] == 'octotel'
        assert metrics['generated'] == 10
        assert metrics['successes'] == 8
        assert metrics['failures'] == 2
        assert metrics['success_rate'] == 80.0
    
    @patch('services.totp_manager.valkey.Valkey')
    def test_health_check(self, mock_valkey_class, mock_config_manager, mock_valkey_client):
        """Test health check"""
        mock_valkey_class.return_value = mock_valkey_client
        
        totp_manager = TOTPManager(mock_config_manager)
        totp_manager.initialize()
        
        # Healthy
        mock_valkey_client.ping.return_value = True
        assert totp_manager.health_check() is True
        
        # Unhealthy
        mock_valkey_client.ping.side_effect = Exception("Connection failed")
        assert totp_manager.health_check() is False


class TestBrowserServiceManager:
    """Tests for BrowserServiceManager - Basic tests without full k8s mock"""
    
    @pytest.fixture
    def mock_config_manager(self):
        """Create mock config manager"""
        config = Mock(spec=ConfigManager)
        config.get.side_effect = lambda key, default=None: {
            'NAMESPACE': 'rpa-system',
            'BROWSER_SERVICE_IMAGE': 'rpa-browser:v2.0-enhanced',
            'BROWSER_CPU_REQUEST': '500m',
            'BROWSER_CPU_LIMIT': '2',
            'BROWSER_MEMORY_REQUEST': '1Gi',
            'BROWSER_MEMORY_LIMIT': '4Gi',
            'LOG_LEVEL': 'INFO'
        }.get(key, default)
        return config
    
    def test_get_service_info(self, mock_config_manager):
        """Test getting service info"""
        # This is a basic test without full k8s mocking
        # Full integration tests would require a more complex setup
        from services.browser_service_manager import BrowserServiceManager
        
        # We can't fully test without k8s, but we can test the data structure
        with patch('services.browser_service_manager.config.load_incluster_config'):
            with patch('services.browser_service_manager.client.AppsV1Api'):
                with patch('services.browser_service_manager.client.CoreV1Api'):
                    manager = BrowserServiceManager(mock_config_manager)
                    
                    # Add mock service
                    manager.active_services['test-service'] = {
                        'service_id': 'test-service',
                        'service_url': 'http://test-service:8080',
                        'status': 'active'
                    }
                    
                    info = manager.get_service_info('test-service')
                    
                    assert info is not None
                    assert info['service_id'] == 'test-service'
                    assert info['status'] == 'active'
    
    def test_get_active_services(self, mock_config_manager):
        """Test getting list of active services"""
        from services.browser_service_manager import BrowserServiceManager
        
        with patch('services.browser_service_manager.config.load_incluster_config'):
            with patch('services.browser_service_manager.client.AppsV1Api'):
                with patch('services.browser_service_manager.client.CoreV1Api'):
                    manager = BrowserServiceManager(mock_config_manager)
                    
                    # Initially empty
                    assert len(manager.get_active_services()) == 0
                    
                    # Add services
                    manager.active_services['service1'] = {'service_id': 'service1'}
                    manager.active_services['service2'] = {'service_id': 'service2'}
                    
                    services = manager.get_active_services()
                    assert len(services) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
