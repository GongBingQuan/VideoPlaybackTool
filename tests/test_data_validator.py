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
        # 测试混合有效/无效数据
        input_data = [
            {'title': ' Episode 1 ', 'url': 'http://example.com?param=1', 'duration': '100'},
            {'title': 'Invalid', 'url': 'http://missing-duration.com'},
            'invalid_string_data',
            {'title': '负数时长', 'url': 'http://test.com', 'duration': '-50'},
            {'title': '非数字时长', 'url': 'http://test.com', 'duration': 'abc'}
        ]
        result = validator.sanitize_episode_data(input_data)
        assert len(result) == 1
        assert result[0]['title'] == 'Episode 1'
        assert result[0]['url'] == 'http://example.com'
        assert result[0]['duration'] == 100

    def test_normalize_edge_cases(self, validator):
        # 测试边界条件
        raw_record = {
            'title': ' 超长标题' * 10,
            'last_position': '-100',
            'timestamp': 'invalid_time',
            'total_duration': 'not_a_number'
        }
        result = validator.normalize_history_record(raw_record)
        assert len(result['title']) <= 255
        assert result['last_position'] == 0
        assert isinstance(result['timestamp'], datetime)
        assert result['total_duration'] == 0

    def test_invalid_data_types(self, validator):
        # 测试异常数据类型
        assert validator.validate_url(123) is False
        assert validator.sanitize_episode_data('invalid') == []
        assert validator.normalize_history_record([1,2,3]) == {}

    def test_normalize_history_record(self, validator):
        raw_record = {'title': ' Test ', 'last_position': '100', 'timestamp': '2023-01-01T00:00:00'}
        result = validator.normalize_history_record(raw_record)
        assert result['title'] == 'Test'
        assert isinstance(result['timestamp'], datetime)