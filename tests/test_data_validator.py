import pytest
from services.data_validator import DataValidator

class TestDataValidator:
    @pytest.fixture
    def validator(self):
        return DataValidator()

    def test_validate_url_success(self, validator):
        assert validator.validate_url('https://example.com/video/123') is True

    def test_validate_url_failure(self, validator):
        assert validator.validate_url('invalid_url') is False

    def test_sanitize_episode_data(self, validator):
        input_data = [
            {'title': ' Episode 1 ', 'url': 'http://example.com?param=1', 'duration': '100'},
            {'title': 'Invalid', 'url': 'http://missing-duration.com'}
        ]
        result = validator.sanitize_episode_data(input_data)
        assert len(result) == 1
        assert result[0]['title'] == 'Episode 1'
        assert result[0]['url'] == 'http://example.com'

    def test_normalize_history_record(self, validator):
        raw_record = {'title': ' Test ', 'last_position': '100', 'timestamp': '2023-01-01T00:00:00'}
        result = validator.normalize_history_record(raw_record)
        assert result['title'] == 'Test'
        assert isinstance(result['timestamp'], datetime)