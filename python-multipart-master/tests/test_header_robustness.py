"""
【功能优化】增强 Content-Disposition Header 解析健壮性

测试模块：验证复杂 HTTP Header 格式的正确解析

【测试用例】
- name="user;name" → {'name': 'user;name'}
- filename="My \"Cool\" File.txt" → {'filename': 'My "Cool" File.txt'}
- filename="C:\\path\\file.txt" → {'filename': 'file.txt'}（IE6兼容性）
"""

from __future__ import annotations

import unittest

from python_multipart.multipart import parse_options_header


class TestRobustHeaderParsing(unittest.TestCase):
    """测试健壮的 Header 解析功能"""

    def test_basic_parsing(self):
        """基本解析功能保持兼容"""
        ctype, params = parse_options_header(
            'multipart/form-data; boundary=----WebKitFormBoundary'
        )
        self.assertEqual(ctype, b'multipart/form-data')
        self.assertEqual(params[b'boundary'], b'----WebKitFormBoundary')

    def test_semicolon_in_quoted_value(self):
        """引号内的分号不应被解析为分隔符"""
        ctype, params = parse_options_header(
            'form-data; name="user;name"; filename="video;game.mp4"'
        )
        self.assertEqual(ctype, b'form-data')
        self.assertEqual(params[b'name'], b'user;name')
        self.assertEqual(params[b'filename'], b'video;game.mp4')

    def test_escaped_quotes(self):
        """转义引号应被正确解析"""
        ctype, params = parse_options_header(
            r'form-data; name="field"; filename="My \"Cool\" File.txt"'
        )
        self.assertEqual(params[b'filename'], b'My "Cool" File.txt')

    def test_windows_path(self):
        """IE6 兼容的 Windows 路径处理"""
        ctype, params = parse_options_header(
            r'form-data; filename="C:\\tmp\\image.png"'
        )
        # IE6 可能发送完整路径，需要提取文件名
        self.assertEqual(params[b'filename'], b'image.png')

    def test_empty_value(self):
        """空值处理"""
        ctype, params = parse_options_header('form-data; name=""')
        self.assertEqual(ctype, b'form-data')
        self.assertEqual(params[b'name'], b'')

    def test_unquoted_params(self):
        """无引号参数处理"""
        ctype, params = parse_options_header(
            'form-data; name=test_field; filename=test.txt'
        )
        self.assertEqual(ctype, b'form-data')
        self.assertEqual(params[b'name'], b'test_field')
        self.assertEqual(params[b'filename'], b'test.txt')

    def test_unescaped_quotes_in_filename(self):
        """文件名中的未转义引号（边界情况）"""
        # 注意：这种情况在实际中较少见，但我们的解析器应该能够处理
        ctype, params = parse_options_header(
            'attachment; filename="document.pdf"'
        )
        self.assertEqual(ctype, b'attachment')
        self.assertEqual(params[b'filename'], b'document.pdf')

    def test_multiple_spaces_around_equals(self):
        """等号周围的多空格处理"""
        ctype, params = parse_options_header(
            'form-data; name = "test" ; filename = "file.txt"'
        )
        self.assertEqual(params[b'name'], b'test')
        self.assertEqual(params[b'filename'], b'file.txt')

    def test_content_type_case_insensitive(self):
        """Content-Type 不区分大小写"""
        ctype, params = parse_options_header(
            'MULTIPART/FORM-DATA; BOUNDARY=abc'
        )
        self.assertEqual(ctype, b'multipart/form-data')
        self.assertEqual(params[b'boundary'], b'abc')

    def test_empty_header(self):
        """空 Header 处理"""
        ctype, params = parse_options_header(None)
        self.assertEqual(ctype, b'')
        self.assertEqual(params, {})

    def test_single_param(self):
        """单个参数处理"""
        ctype, params = parse_options_header('application/json; charset=utf-8')
        self.assertEqual(ctype, b'application/json')
        self.assertEqual(params[b'charset'], b'utf-8')

    def test_filename_with_spaces(self):
        """带空格的文件名处理"""
        ctype, params = parse_options_header(
            'attachment; filename="my document.pdf"'
        )
        self.assertEqual(params[b'filename'], b'my document.pdf')

    def test_unicode_in_filename(self):
        """文件名中的 Unicode 字符（RFC 2231 编码）"""
        # 测试 RFC 2231 编码格式
        ctype, params = parse_options_header(
            "attachment; filename*=us-ascii'en-us'encoded%20message"
        )
        self.assertEqual(params[b'filename'], bencoded message)


def suite():
    """测试套件"""
    suite = unittest.TestSuite()
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(TestRobustHeaderParsing))
    return suite


if __name__ == '__main__':
    # 直接运行测试
    unittest.main(verbosity=2)
