"""
【设计模式标注】Multipart 表单解析核心模块
==========================================

本模块实现了 HTTP multipart/form-data 和 application/x-www-form-urlencoded
格式请求体的解析功能，包含多种经典设计模式的应用。

【架构概述】
项目采用分层架构设计，从下到上依次为：
1. 数据模型层：Field、File 类表示解析后的表单数据
2. 解析器层：BaseParser、OctetStreamParser、QuerystringParser、MultipartParser
3. 协调器层：FormParser 统一调度各解析器

【设计模式应用汇总】
1. 策略模式：FormParser 根据 Content-Type 选择不同解析策略
2. 观察者模式：回调机制实现数据处理与解析的分离
3. 状态机模式：MultipartParser 和 QuerystringParser 使用状态机解析
4. 工厂模式：create_form_parser 工厂函数创建解析器
5. 模板方法模式：BaseParser 定义解析器骨架，子类实现具体逻辑
6. 装饰器模式：Base64Decoder、QuotedPrintableDecoder 包装底层对象
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from email.message import Message
from enum import IntEnum
from io import BufferedRandom, BytesIO
from numbers import Number
from typing import TYPE_CHECKING, cast

from .decoders import Base64Decoder, QuotedPrintableDecoder
from .exceptions import FileError, FormParserError, MultipartParseError, QuerystringParseError

# 【类型标注】TYPE_CHECKING 避免运行时循环依赖
if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable
    from typing import Any, Literal, Protocol, TypeAlias, TypedDict

    # 【协议定义】支持读取操作的协议
    class SupportsRead(Protocol):
        """支持读取操作的协议，用于 parse_form 函数的流式输入"""
        def read(self, __n: int) -> bytes: ...

    # 【类型定义】各解析器的回调类型定义
    class QuerystringCallbacks(TypedDict, total=False):
        """URL 编码解析器的回调类型"""
        on_field_start: Callable[[], None]
        on_field_name: Callable[[bytes, int, int], None]
        on_field_data: Callable[[bytes, int, int], None]
        on_field_end: Callable[[], None]
        on_end: Callable[[], None]

    class OctetStreamCallbacks(TypedDict, total=False):
        """八位字节流解析器的回调类型"""
        on_start: Callable[[], None]
        on_data: Callable[[bytes, int, int], None]
        on_end: Callable[[], None]

    class MultipartCallbacks(TypedDict, total=False):
        """多部分解析器的回调类型"""
        on_part_begin: Callable[[], None]
        on_part_data: Callable[[bytes, int, int], None]
        on_part_end: Callable[[], None]
        on_header_begin: Callable[[], None]
        on_header_field: Callable[[bytes, int, int], None]
        on_header_value: Callable[[bytes, int, int], None]
        on_header_end: Callable[[], None]
        on_headers_finished: Callable[[], None]
        on_end: Callable[[], None]

    # 【配置类型】表单解析器和文件上传的配置类型
    class FormParserConfig(TypedDict):
        UPLOAD_DIR: str | None
        UPLOAD_KEEP_FILENAME: bool
        UPLOAD_KEEP_EXTENSIONS: bool
        UPLOAD_ERROR_ON_BAD_CTE: bool
        MAX_MEMORY_FILE_SIZE: int
        MAX_BODY_SIZE: float

    class FileConfig(TypedDict, total=False):
        UPLOAD_DIR: str | bytes | None
        UPLOAD_DELETE_TMP: bool
        UPLOAD_KEEP_FILENAME: bool
        UPLOAD_KEEP_EXTENSIONS: bool
        MAX_MEMORY_FILE_SIZE: int

    # 【协议定义】表单解析器的协议
    class _FormProtocol(Protocol):
        """表单解析器的通用协议"""
        def write(self, data: bytes) -> int: ...
        def finalize(self) -> None: ...
        def close(self) -> None: ...

    class FieldProtocol(_FormProtocol, Protocol):
        """字段对象的协议"""
        def __init__(self, name: bytes | None) -> None: ...
        def set_none(self) -> None: ...

    class FileProtocol(_FormProtocol, Protocol):
        """文件对象的协议"""
        def __init__(self, file_name: bytes | None, field_name: bytes | None, config: FileConfig) -> None: ...

    # 【类型别名】回调名称的类型安全字符串
    OnFieldCallback = Callable[[FieldProtocol], None]
    OnFileCallback = Callable[[FileProtocol], None]

    CallbackName: TypeAlias = Literal[
        "start", "data", "end",
        "field_start", "field_name", "field_data", "field_end",
        "part_begin", "part_data", "part_end",
        "header_begin", "header_field", "header_value", "header_end",
        "headers_finished",
    ]


# =============================================================================
# 状态枚举定义
# =============================================================================

class QuerystringState(IntEnum):
    """
    【设计模式】状态机模式 - 状态枚举
    
    【状态说明】
    URL 编码表单解析的状态机，包含 3 个核心状态：
    
    BEFORE_FIELD：等待新字段开始
    - 遇到 & 或 ; 分隔符：跳过（处理连续分隔符情况）
    - 遇到其他字符：触发 field_start 回调，进入 FIELD_NAME 状态
    
    FIELD_NAME：解析字段名
    - 找到 = 号：触发 field_name 回调，进入 FIELD_DATA 状态
    - 找到分隔符：触发 field_name 和 field_end 回调，回到 BEFORE_FIELD
    - 无分隔符：将剩余数据作为字段名
    
    FIELD_DATA：解析字段值
    - 找到分隔符：触发 field_data 和 field_end 回调，回到 BEFORE_FIELD
    - 无分隔符：将剩余数据作为字段值
    """
    BEFORE_FIELD = 0
    FIELD_NAME = 1
    FIELD_DATA = 2


class MultipartState(IntEnum):
    """
    【设计模式】状态机模式 - 状态枚举
    
    【状态说明】
    Multipart/form-data 解析的状态机，包含 13 个状态。
    这是整个模块中最复杂的状态机，负责解析多部分消息的各个部分。
    
    【状态转换图】
    START → START_BOUNDARY → HEADER_FIELD_START → HEADER_FIELD → HEADER_VALUE_START → HEADER_VALUE
            → HEADER_VALUE_ALMOST_DONE → HEADERS_ALMOST_DONE → PART_DATA_START → PART_DATA → PART_DATA_END
    → END_BOUNDARY → END
    以及 PART_DATA → PART_DATA_END → HEADER_FIELD_START（多部分循环）
    """
    START = 0                      # 初始状态
    START_BOUNDARY = 1             # 解析起始边界
    HEADER_FIELD_START = 2         # 开始解析 Header 字段
    HEADER_FIELD = 3               # 解析 Header 字段名
    HEADER_VALUE_START = 4         # 开始解析 Header 值
    HEADER_VALUE = 5               # 解析 Header 值
    HEADER_VALUE_ALMOST_DONE = 6   # Header 值解析即将完成
    HEADERS_ALMOST_DONE = 7        # 所有 Header 解析即将完成
    PART_DATA_START = 8            # 开始解析 Part 数据
    PART_DATA = 9                  # 解析 Part 数据
    PART_DATA_END = 10             # Part 数据解析完成
    END_BOUNDARY = 11              # 解析结束边界
    END = 12                       # 解析完成


# =============================================================================
# 常量定义
# =============================================================================

# 【标志位】用于 MultipartParser 的状态标志
FLAG_PART_BOUNDARY = 1   # 标志：检测到部分边界（CR 字符）
FLAG_LAST_BOUNDARY = 2   # 标志：检测到结束边界（--）

# 【ASCII 常量】避免跨平台兼容性问题
CR = b"\r"[0]       # 回车符
LF = b"\n"[0]       # 换行符
COLON = b":"[0]     # 冒号
SPACE = b" "[0]     # 空格
HYPHEN = b"-"[0]    # 连字符
AMPERSAND = b"&"[0] # 与符号
SEMICOLON = b";"[0] # 分号
LOWER_A = b"a"[0]   # 小写 a
LOWER_Z = b"z"[0]   # 小写 z
NULL = b"\x00"[0]   # 空字符

# 【正则表达式替代】HTTP Token 字符集
# fmt: off
# 根据 RFC7230 3.2.6，HTTP Token 包含所有字母数字和这些特殊字符
# 使用 frozenset 提供 O(1) 的成员检查性能
TOKEN_CHARS_SET = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    b"abcdefghijklmnopqrstuvwxyz"
    b"0123456789"
    b"!#$%&'*+-.^_`|~")
# fmt: on


# =============================================================================
# 工具函数
# =============================================================================

def parse_options_header(value: str | bytes | None) -> tuple[bytes, dict[bytes, bytes]]:
    """
    【算法实现】HTTP Header 选项解析
    
    【功能说明】
    解析 Content-Type 等 HTTP Header 的值和参数。
    例如："multipart/form-data; boundary=----WebKitFormBoundary"
    将被解析为 (b"multipart/form-data", {b"boundary": b"----WebKitFormBoundary"})
    
    【算法实现】
    1. 使用 Python 标准库 email.message.Message 解析
       （遵循 PEP 594 的建议，使用 email 模块处理 legacy header 格式）
    2. 提取主类型（第一个参数）
    3. 提取所有附加参数
    4. 处理 IE6 的文件名路径提取 bug
    
    【特殊情况处理】
    - IE6 bug：IE6 可能发送完整路径 "C:\\path\\file.txt"
      需要提取出文件名部分 "file.txt"
    - RFC 2231 编码：支持非 ASCII 字符集编码的参数值
    - 转义引号：处理带转义引号的参数值
    
    【返回值】
    (content_type: bytes, options: dict) 元组
    """
    if not value:
        return (b"", {})

    if isinstance(value, bytes):  # pragma: no cover
        value = value.decode("latin-1")

    assert isinstance(value, str), "Value should be a string by now"

    if ";" not in value:
        return (value.lower().strip().encode("latin-1"), {})

    message = Message()
    message["content-type"] = value
    params = message.get_params()
    assert params, "At least the content type value should be present"
    ctype = params.pop(0)[0].encode("latin-1")
    options: dict[bytes, bytes] = {}
    for param in params:
        key, value = param
        if isinstance(value, tuple):
            value = value[-1]
        if key == "filename":
            if value[1:3] == ":\\" or value[:2] == "\\\\":
                value = value.split("\\")[-1]
        options[key.encode("latin-1")] = value.encode("latin-1")
    return ctype, options


# =============================================================================
# 数据模型类
# =============================================================================

class Field:
    """
    【数据模型】表单字段类
    
    【功能说明】
    表示解析后的表单字段，包含字段名和字段值。
    
    【设计特点】
    1. 延迟计算：使用 _missing 标记，只有在首次访问 value 时才合并数据
    2. 缓存机制：合并后的值被缓存，避免重复计算
    3. 不可变语义：finalize 后字段不再接受新数据
    
    【使用示例】
    ```python
    f = Field(b"username")
    f.write(b"admin")
    print(f.value)  # b"admin"
    f.finalize()
    ```
    """

    def __init__(self, name: bytes | None) -> None:
        self._name = name
        self._value: list[bytes] = []
        self._cache = _missing

    @classmethod
    def from_value(cls, name: bytes, value: bytes | None) -> Field:
        """
        【工厂方法】从值创建字段
        
        【快捷方法】
        创建一个字段并设置值，然后 finalize。
        适用于已知完整值的情况，无需逐块写入。
        """
        f = cls(name)
        if value is None:
            f.set_none()
        else:
            f.write(value)
        f.finalize()
        return f

    def write(self, data: bytes) -> int:
        """
        【接口方法】写入字段数据
        
        【实现】
        直接委托给 on_data 方法处理
        """
        return self.on_data(data)

    def on_data(self, data: bytes) -> int:
        """
        【回调方法】处理字段数据
        
        【实现】
        将数据追加到内部列表，并使缓存失效
        """
        self._value.append(data)
        self._cache = _missing
        return len(data)

    def on_end(self) -> None:
        """
        【生命周期方法】字段结束
        
        【实现】
        如果需要，合并所有数据块
        """
        if self._cache is _missing:
            self._cache = b"".join(self._value)

    def finalize(self) -> None:
        """
        【生命周期方法】结束字段
        
        【语义】
        调用 on_end 完成字段的最终处理
        """
        self.on_end()

    def close(self) -> None:
        """
        【资源管理】关闭字段
        
        【实现】
        释放内部数据列表
        """
        if self._cache is _missing:
            self._cache = b"".join(self._value)
        del self._value

    def set_none(self) -> None:
        """
        【特殊方法】设置字段值为 None
        
        【使用场景】
        URL 编码中 "foo&bar=" 的 bar 字段值为空字符串
        而 "foo&bar&baz" 的 bar 字段值为 None
        """
        self._cache = None

    @property
    def field_name(self) -> bytes | None:
        """
        【属性】字段名
        """
        return self._name

    @property
    def value(self) -> bytes | None:
        """
        【属性】字段值
        
        【懒加载】
        首次访问时合并所有数据块，后续访问直接返回缓存
        """
        if self._cache is _missing:
            self._cache = b"".join(self._value)
        assert isinstance(self._cache, bytes) or self._cache is None
        return self._cache

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Field):
            return self.field_name == other.field_name and self.value == other.value
        else:
            return NotImplemented

    def __repr__(self) -> str:
        if self.value is not None and len(self.value) > 97:
            v = repr(self.value[:97])[:-1] + "...'"
        else:
            v = repr(self.value)
        return f"{self.__class__.__name__}(field_name={self.field_name!r}, value={v})"


class File:
    """
    【数据模型】上传文件类
    
    【功能说明】
    表示解析后的上传文件，支持内存存储和磁盘存储两种模式。
    
    【设计模式】策略模式 + 模板方法模式
    
    【存储策略】
    1. 内存模式：数据存储在 BytesIO 中，适用于小文件
    2. 磁盘模式：数据存储在临时文件中，适用于大文件
    
    【配置选项】
    - UPLOAD_DIR：指定上传目录（默认使用系统临时目录）
    - UPLOAD_KEEP_FILENAME：是否保留原始文件名
    - UPLOAD_KEEP_EXTENSIONS：是否保留文件扩展名
    - MAX_MEMORY_FILE_SIZE：内存存储阈值（默认 1 MiB）
    
    【生命周期】
    1. 创建：初始化文件对象
    2. 写入：接收数据，可能触发内存到磁盘的转换
    3. 刷新：flush_to_disk 显式触发磁盘存储
    4. 结束：finalize 完成文件写入
    5. 清理：close 关闭底层文件对象
    """

    def __init__(self, file_name: bytes | None, field_name: bytes | None = None, config: FileConfig = {}) -> None:
        self.logger = logging.getLogger(__name__)
        self._config = config
        self._in_memory = True
        self._bytes_written = 0
        self._fileobj: BytesIO | BufferedRandom = BytesIO()

        self._field_name = field_name
        self._file_name = file_name
        self._actual_file_name: bytes | None = None

        if file_name is not None:
            base, ext = os.path.splitext(file_name)
            self._file_base = base
            self._ext = ext

    @property
    def field_name(self) -> bytes | None:
        """
        【属性】表单字段名
        """
        return self._field_name

    @property
    def file_name(self) -> bytes | None:
        """
        【属性】原始文件名
        """
        return self._file_name

    @property
    def actual_file_name(self) -> bytes | None:
        """
        【属性】实际存储的文件名
        
        【说明】
        可能与原始文件名不同，取决于配置
        """
        return self._actual_file_name

    @property
    def file_object(self) -> BytesIO | BufferedRandom:
        """
        【属性】底层文件对象
        
        【多态】
        根据存储模式返回 BytesIO 或 BufferedRandom
        """
        return self._fileobj

    @property
    def size(self) -> int:
        """
        【属性】文件大小（字节数）
        """
        return self._bytes_written

    @property
    def in_memory(self) -> bool:
        """
        【属性】是否在内存中
        """
        return self._in_memory

    def flush_to_disk(self) -> None:
        """
        【算法实现】内存到磁盘的转换
        
        【触发条件】
        当写入数据量超过 MAX_MEMORY_FILE_SIZE 时自动触发
        
        【实现步骤】
        1. 定位到文件开头
        2. 创建新的磁盘文件
        3. 使用 shutil.copyfileobj 复制数据
        4. 定位到写入位置
        5. 替换内部文件对象引用
        6. 关闭旧的文件对象
        """
        if not self._in_memory:
            self.logger.warning("Trying to flush to disk when we're not in memory")
            return

        self._fileobj.seek(0)
        new_file = self._get_disk_file()
        shutil.copyfileobj(self._fileobj, new_file)
        new_file.seek(self._bytes_written)
        old_fileobj = self._fileobj
        self._fileobj = new_file
        self._in_memory = False
        old_fileobj.close()

    def _get_disk_file(self) -> BufferedRandom:
        """
        【算法实现】创建磁盘文件
        
        【分支逻辑】
        1. 如果指定了上传目录且需要保留文件名：使用指定目录和文件名
        2. 否则：创建临时文件（使用系统临时目录）
        
        【错误处理】
        OSError 转换为 FileError，提供更明确的错误信息
        """
        self.logger.info("Opening a file on disk")

        file_dir = self._config.get("UPLOAD_DIR")
        keep_filename = self._config.get("UPLOAD_KEEP_FILENAME", False)
        keep_extensions = self._config.get("UPLOAD_KEEP_EXTENSIONS", False)
        delete_tmp = self._config.get("UPLOAD_DELETE_TMP", True)
        tmp_file: None | BufferedRandom = None

        if file_dir is not None and keep_filename:
            self.logger.info("Saving with filename in: %r", file_dir)

            fname = self._file_base + self._ext if keep_extensions else self._file_base
            path = os.path.join(file_dir, fname)  # type: ignore[arg-type]
            try:
                self.logger.info("Opening file: %r", path)
                tmp_file = open(path, "w+b")
            except OSError:
                tmp_file = None
                self.logger.exception("Error opening temporary file")
                raise FileError("Error opening temporary file: %r" % path)
        else:
            suffix = self._ext.decode(sys.getfilesystemencoding()) if keep_extensions else None

            if file_dir is None:
                dir = None
            elif isinstance(file_dir, bytes):
                dir = file_dir.decode(sys.getfilesystemencoding())
            else:
                dir = file_dir  # pragma: no cover

            self.logger.info(
                "Creating a temporary file with options: %r", {"suffix": suffix, "delete": delete_tmp, "dir": dir}
            )
            try:
                tmp_file = cast(BufferedRandom, tempfile.NamedTemporaryFile(suffix=suffix, delete=delete_tmp, dir=dir))
            except OSError:
                self.logger.exception("Error creating named temporary file")
                raise FileError("Error creating named temporary file")

            assert tmp_file is not None
            if isinstance(tmp_file.name, str):
                fname = tmp_file.name.encode(sys.getfilesystemencoding())
            else:
                fname = cast(bytes, tmp_file.name)  # pragma: no cover

        self._actual_file_name = fname
        return tmp_file

    def write(self, data: bytes) -> int:
        """
        【接口方法】写入文件数据
        """
        return self.on_data(data)

    def on_data(self, data: bytes) -> int:
        """
        【回调方法】处理文件数据
        
        【功能】
        将数据写入底层文件对象
        超过内存阈值时自动触发 flush_to_disk
        """
        bwritten = self._fileobj.write(data)
        if bwritten != len(data):
            self.logger.warning("bwritten != len(data) (%d != %d)", bwritten, len(data))
            return bwritten

        self._bytes_written += bwritten

        max_memory_file_size = self._config.get("MAX_MEMORY_FILE_SIZE")
        if self._in_memory and max_memory_file_size is not None and (self._bytes_written > max_memory_file_size):
            self.logger.info("Flushing to disk")
            self.flush_to_disk()

        return bwritten

    def on_end(self) -> None:
        """
        【生命周期方法】文件数据结束
        """
        self._fileobj.flush()

    def finalize(self) -> None:
        """
        【生命周期方法】结束文件写入
        """
        self.on_end()

    def close(self) -> None:
        """
        【资源管理】关闭文件
        """
        self._fileobj.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(file_name={self.file_name!r}, field_name={self.field_name!r})"


# =============================================================================
# 解析器基类
# =============================================================================

class BaseParser:
    """
    【设计模式】模板方法模式 - 抽象基类
    
    【功能说明】
    定义解析器的通用框架，提供回调机制的默认实现。
    
    【模板方法】
    write() 是模板方法，定义了写入数据的基本流程：
    1. 调用 _internal_write() 执行实际解析（子类实现）
    2. 更新解析进度统计
    3. 返回处理的字节数
    
    【观察者模式】
    回调机制实现了观察者模式：
    - 主题：解析器
    - 观察者：注册的回调函数
    - 通知：解析过程中的各个事件
    
    【回调类型】
    1. 通知回调：无参数，如 on_start、on_end
    2. 数据回调：带 (data, start, end) 参数，如 on_data、on_field_name
    """
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.callbacks: QuerystringCallbacks | OctetStreamCallbacks | MultipartCallbacks = {}

    def callback(
        self, name: CallbackName, data: bytes | None = None, start: int | None = None, end: int | None = None
    ) -> None:
        """
        【算法实现】回调分发
        
        【实现】
        1. 构建回调函数名（on_ + name）
        2. 从 callbacks 字典获取函数
        3. 如果函数存在，根据参数类型调用
        """
        on_name = "on_" + name
        func = self.callbacks.get(on_name)
        if func is None:
            return
        func = cast("Callable[..., Any]", func)
        if data is not None:
            if start is not None and start == end:
                return
            self.logger.debug("Calling %s with data[%d:%d]", on_name, start, end)
            func(data, start, end)
        else:
            self.logger.debug("Calling %s with no data", on_name)
            func()

    def set_callback(self, name: CallbackName, new_func: Callable[..., Any] | None) -> None:
        """
        【观察者注册】设置回调函数
        
        【参数】
        name：回调名称
        new_func：回调函数，None 表示移除回调
        """
        if new_func is None:
            self.callbacks.pop("on_" + name, None)  # type: ignore[misc]
        else:
            self.callbacks["on_" + name] = new_func  # type: ignore[literal-required]

    def close(self) -> None:
        """
        【资源管理】关闭解析器（默认空实现）
        """
        pass  # pragma: no cover

    def finalize(self) -> None:
        """
        【生命周期】结束解析（默认空实现）
        """
        pass  # pragma: no cover

    def __repr__(self) -> str:
        return "%s()" % self.__class__.__name__


# =============================================================================
# 八位字节流解析器
# =============================================================================

class OctetStreamParser(BaseParser):
    """
    【解析器实现】八位字节流解析器
    
    【功能说明】
    解析 application/octet-stream 类型的请求体。
    这是一种简单的流式解析，不进行任何格式化处理。
    
    【使用场景】
    当 Content-Type 为 application/octet-stream 时使用，
    通常用于文件上传的原始字节流。
    
    【状态管理】
    只需要一个 _started 标志来检测首次数据写入，
    以触发 on_start 回调。
    """
    def __init__(self, callbacks: OctetStreamCallbacks = {}, max_size: float = float("inf")):
        super().__init__()
        self.callbacks = callbacks
        self._started = False

        if not isinstance(max_size, Number) or max_size < 1:
            raise ValueError("max_size must be a positive number, not %r" % max_size)
        self.max_size: int | float = max_size
        self._current_size = 0

    def write(self, data: bytes) -> int:
        """
        【模板方法】写入数据
        
        【实现】
        1. 首次写入时触发 on_start 回调
        2. 检查并处理数据大小限制
        3. 触发 on_data 回调传递数据
        """
        if not self._started:
            self.callback("start")
            self._started = True

        data_len = len(data)
        if (self._current_size + data_len) > self.max_size:
            new_size = int(self.max_size - self._current_size)
            self.logger.warning(
                "Current size is %d (max %d), so truncating data length from %d to %d",
                self._current_size,
                self.max_size,
                data_len,
                new_size,
            )
            data_len = new_size

        self._current_size += data_len
        self.callback("data", data, 0, data_len)
        return data_len

    def finalize(self) -> None:
        """
        【生命周期】结束解析
        
        【触发】
        on_end 回调
        """
        self.callback("end")

    def __repr__(self) -> str:
        return "%s()" % self.__class__.__name__


# =============================================================================
# URL 编码解析器
# =============================================================================

class QuerystringParser(BaseParser):
    """
    【解析器实现】URL 编码表单解析器
    
    【功能说明】
    解析 application/x-www-form-urlencoded 类型的请求体。
    将查询字符串格式的键值对解析为字段数据。
    
    【设计模式】状态机模式
    
    【状态转换】
    BEFORE_FIELD ←→ FIELD_NAME ←→ FIELD_DATA
    
    【配置选项】
    - strict_parsing：严格解析模式
      - 普通模式：允许省略等号（foo&bar 视为 foo=None, bar=None）
      - 严格模式：省略等号视为错误
    - max_size：最大解析数据量
    """
    state: QuerystringState

    def __init__(
        self, callbacks: QuerystringCallbacks = {}, strict_parsing: bool = False, max_size: float = float("inf")
    ) -> None:
        super().__init__()
        self.state = QuerystringState.BEFORE_FIELD
        self._found_sep = False

        self.callbacks = callbacks

        if not isinstance(max_size, Number) or max_size < 1:
            raise ValueError("max_size must be a positive number, not %r" % max_size)
        self.max_size: int | float = max_size
        self._current_size = 0

        self.strict_parsing = strict_parsing

    def write(self, data: bytes) -> int:
        """
        【模板方法】写入数据
        
        【流程】
        1. 处理大小限制
        2. 调用 _internal_write 执行实际解析
        3. 更新进度统计
        """
        data_len = len(data)
        if (self._current_size + data_len) > self.max_size:
            new_size = int(self.max_size - self._current_size)
            self.logger.warning(
                "Current size is %d (max %d), so truncating data length from %d to %d",
                self._current_size,
                self.max_size,
                data_len,
                new_size,
            )
            data_len = new_size

        l = 0
        try:
            l = self._internal_write(data, data_len)
        finally:
            self._current_size += l

        return l

    def _internal_write(self, data: bytes, length: int) -> int:
        """
        【算法实现】URL 编码解析核心算法
        
        【状态机实现】
        使用 while 循环逐字节处理，根据当前状态和字节值进行状态转移。
        
        【优化技巧】
        - 使用 find() 方法快速定位分隔符位置
        - 使用局部变量缓存状态，减少属性访问开销
        - 通过 i -= 1 实现字符的重新处理
        
        【状态处理逻辑】
        BEFORE_FIELD：
        - & 或 ;：设置跳过标志（处理连续分隔符）
        - 其他字符：触发 field_start，进入 FIELD_NAME
        
        FIELD_NAME：
        - 找到 =：触发 field_name，进入 FIELD_DATA
        - 找到分隔符：触发 field_name 和 field_end，回到 BEFORE_FIELD
        - 无分隔符：整个剩余数据作为字段名
        
        FIELD_DATA：
        - 找到分隔符：触发 field_data 和 field_end，回到 BEFORE_FIELD
        - 无分隔符：整个剩余数据作为字段值
        """
        state = self.state
        strict_parsing = self.strict_parsing
        found_sep = self._found_sep

        i = 0
        while i < length:
            ch = data[i]

            if state == QuerystringState.BEFORE_FIELD:
                if ch == AMPERSAND or ch == SEMICOLON:
                    if found_sep:
                        if strict_parsing:
                            e = QuerystringParseError("Skipping duplicate ampersand/semicolon at %d" % i)
                            e.offset = i
                            raise e
                        else:
                            self.logger.debug("Skipping duplicate ampersand/semicolon at %d", i)
                    else:
                        found_sep = True
                else:
                    self.callback("field_start")
                    i -= 1
                    state = QuerystringState.FIELD_NAME
                    found_sep = False

            elif state == QuerystringState.FIELD_NAME:
                sep_pos = data.find(b"&", i)
                if sep_pos == -1:
                    sep_pos = data.find(b";", i)

                if sep_pos != -1:
                    equals_pos = data.find(b"=", i, sep_pos)
                else:
                    equals_pos = data.find(b"=", i)

                if equals_pos != -1:
                    self.callback("field_name", data, i, equals_pos)
                    i = equals_pos
                    state = QuerystringState.FIELD_DATA
                else:
                    if not strict_parsing:
                        if sep_pos != -1:
                            self.callback("field_name", data, i, sep_pos)
                            self.callback("field_end")
                            i = sep_pos - 1
                            state = QuerystringState.BEFORE_FIELD
                        else:
                            self.callback("field_name", data, i, length)
                            i = length
                    else:
                        if sep_pos != -1:
                            e = QuerystringParseError(
                                "When strict_parsing is True, we require an "
                                "equals sign in all field chunks. Did not "
                                "find one in the chunk that starts at %d" % (i,)
                            )
                            e.offset = i
                            raise e
                        self.callback("field_name", data, i, length)
                        i = length

            elif state == QuerystringState.FIELD_DATA:
                sep_pos = data.find(b"&", i)
                if sep_pos == -1:
                    sep_pos = data.find(b";", i)

                if sep_pos != -1:
                    self.callback("field_data", data, i, sep_pos)
                    self.callback("field_end")
                    i = sep_pos - 1
                    state = QuerystringState.BEFORE_FIELD
                else:
                    self.callback("field_data", data, i, length)
                    i = length

            else:  # pragma: no cover (error case)
                msg = "Reached an unknown state %d at %d" % (state, i)
                self.logger.warning(msg)
                e = QuerystringParseError(msg)
                e.offset = i
                raise e

            i += 1

        self.state = state
        self._found_sep = found_sep
        return len(data)

    def finalize(self) -> None:
        """
        【生命周期】结束解析
        
        【处理】
        如果当前在 FIELD_DATA 状态，说明有未完成的字段，
        需要触发 field_end 回调。
        """
        if self.state == QuerystringState.FIELD_DATA:
            self.callback("field_end")
        self.callback("end")

    def __repr__(self) -> str:
        return "{}(strict_parsing={!r}, max_size={!r})".format(
            self.__class__.__name__, self.strict_parsing, self.max_size
        )


# =============================================================================
# Multipart 解析器
# =============================================================================

class MultipartParser(BaseParser):
    """
    【解析器实现】Multipart 表单解析器
    
    【功能说明】
    解析 multipart/form-data 类型的请求体。
    这是最复杂的解析器，需要处理多部分的边界检测、
    Header 解析和数据块提取。
    
    【设计模式】状态机模式 + 观察者模式
    
    【边界检测算法】
    Multipart 格式使用 boundary 参数分隔各部分。
    边界格式：--<boundary> 开头，--<boundary>-- 结尾。
    
    【状态机】
    13 个状态管理整个解析流程，处理以下复杂情况：
    1. 边界的完整匹配
    2. 边界的部分匹配（跨数据块）
    3. Header 的解析（field 和 value）
    4. Part 数据的提取（边界之间的内容）
    
    【数据标记机制】
    使用 marks 字典标记各个数据块的起始位置，
    实现跨数据块的连续数据提取。
    """
    def __init__(
        self, boundary: bytes | str, callbacks: MultipartCallbacks = {}, max_size: float = float("inf")
    ) -> None:
        super().__init__()
        self.state = MultipartState.START
        self.index = self.flags = 0

        self.callbacks = callbacks

        if not isinstance(max_size, Number) or max_size < 1:
            raise ValueError("max_size must be a positive number, not %r" % max_size)
        self.max_size = max_size
        self._current_size = 0

        self.marks: dict[str, int] = {}

        if isinstance(boundary, str):  # pragma: no cover
            boundary = boundary.encode("latin-1")
        self.boundary = b"\r\n--" + boundary

    def write(self, data: bytes) -> int:
        """
        【模板方法】写入数据
        
        【流程】
        1. 处理大小限制
        2. 调用 _internal_write 执行实际解析
        3. 更新进度统计
        """
        data_len = len(data)
        if (self._current_size + data_len) > self.max_size:
            new_size = int(self.max_size - self._current_size)
            self.logger.warning(
                "Current size is %d (max %d), so truncating data length from %d to %d",
                self._current_size,
                self.max_size,
                data_len,
                new_size,
            )
            data_len = new_size

        l = 0
        try:
            l = self._internal_write(data, data_len)
        finally:
            self._current_size += l

        return l

    def _internal_write(self, data: bytes, length: int) -> int:
        """
        【算法实现】Multipart 解析核心算法
        
        【边界匹配优化】
        使用 find() 方法快速查找完整边界，
        只对边界附近的数据进行字符级比较。
        
        【look-behind 机制】
        当检测到边界部分匹配时（索引大于边界长度），
        需要从之前的边界字节中补充数据。
        这处理了边界跨越数据块的情况。
        
        【状态处理摘要】
        START：跳过前导换行，初始化边界索引
        START_BOUNDARY：验证边界格式（--boundary + CRLF）
        HEADER_FIELD_START：标记 header 字段开始
        HEADER_FIELD：解析 header 字段名（直到 :）
        HEADER_VALUE_START：跳过前导空格
        HEADER_VALUE：解析 header 值（直到 CRLF）
        HEADER_VALUE_ALMOST_DONE：验证 CRLF 中的 LF
        HEADERS_ALMOST_DONE：验证 header 结束的双 CRLF
        PART_DATA_START：标记 part 数据开始
        PART_DATA：查找边界，提取数据
        PART_DATA_END：处理边界后的 CR 字符
        END_BOUNDARY：验证结束边界（--）
        END：跳过结束后的数据
        """
        boundary = self.boundary
        state = self.state
        index = self.index
        flags = self.flags

        i = 0

        def set_mark(name: str) -> None:
            self.marks[name] = i

        def delete_mark(name: str, reset: bool = False) -> None:
            self.marks.pop(name, None)

        def data_callback(name: CallbackName, end_i: int, remaining: bool = False) -> None:
            marked_index = self.marks.get(name)
            if marked_index is None:
                return

            if end_i <= marked_index:
                pass
            elif marked_index >= 0:
                self.callback(name, data, marked_index, end_i)
            else:
                lookbehind_len = -marked_index
                if lookbehind_len <= len(boundary):
                    self.callback(name, boundary, 0, lookbehind_len)
                elif self.flags & FLAG_PART_BOUNDARY:
                    lookback = boundary + b"\r\n"
                    self.callback(name, lookback, 0, lookbehind_len)
                elif self.flags & FLAG_LAST_BOUNDARY:
                    lookback = boundary + b"--\r\n"
                    self.callback(name, lookback, 0, lookbehind_len)
                else:  # pragma: no cover (error case)
                    self.logger.warning("Look-back buffer error")

                if end_i > 0:
                    self.callback(name, data, 0, end_i)
            if remaining:
                self.marks[name] = end_i - length
            else:
                self.marks.pop(name, None)

        while i < length:
            c = data[i]

            if state == MultipartState.START:
                if c == CR or c == LF:
                    i += 1
                    continue
                index = 0
                state = MultipartState.START_BOUNDARY
                i -= 1

            elif state == MultipartState.START_BOUNDARY:
                if index == len(boundary) - 2:
                    if c == HYPHEN:
                        state = MultipartState.END_BOUNDARY
                    elif c != CR:
                        msg = "Did not find CR at end of boundary (%d)" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e
                    index += 1
                elif index == len(boundary) - 2 + 1:
                    if c != LF:
                        msg = "Did not find LF at end of boundary (%d)" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e
                    index = 0
                    self.callback("part_begin")
                    state = MultipartState.HEADER_FIELD_START
                else:
                    if c != boundary[index + 2]:
                        msg = "Expected boundary character %r, got %r at index %d" % (boundary[index + 2], c, index + 2)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e
                    index += 1

            elif state == MultipartState.HEADER_FIELD_START:
                index = 0
                set_mark("header_field")
                if c != CR:
                    self.callback("header_begin")
                state = MultipartState.HEADER_FIELD
                i -= 1

            elif state == MultipartState.HEADER_FIELD:
                if c == CR and index == 0:
                    delete_mark("header_field")
                    state = MultipartState.HEADERS_ALMOST_DONE
                    i += 1
                    continue
                index += 1
                if c == COLON:
                    if index == 1:
                        msg = "Found 0-length header at %d" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e
                    data_callback("header_field", i)
                    state = MultipartState.HEADER_VALUE_START
                elif c not in TOKEN_CHARS_SET:
                    msg = "Found invalid character %r in header at %d" % (c, i)
                    self.logger.warning(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e

            elif state == MultipartState.HEADER_VALUE_START:
                if c == SPACE:
                    i += 1
                    continue
                set_mark("header_value")
                state = MultipartState.HEADER_VALUE
                i -= 1

            elif state == MultipartState.HEADER_VALUE:
                if c == CR:
                    data_callback("header_value", i)
                    self.callback("header_end")
                    state = MultipartState.HEADER_VALUE_ALMOST_DONE

            elif state == MultipartState.HEADER_VALUE_ALMOST_DONE:
                if c != LF:
                    msg = f"Did not find LF character at end of header (found {c!r})"
                    self.logger.warning(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e
                state = MultipartState.HEADER_FIELD_START

            elif state == MultipartState.HEADERS_ALMOST_DONE:
                if c != LF:
                    msg = f"Did not find LF at end of headers (found {c!r})"
                    self.logger.warning(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e
                self.callback("headers_finished")
                state = MultipartState.PART_DATA_START

            elif state == MultipartState.PART_DATA_START:
                set_mark("part_data")
                state = MultipartState.PART_DATA
                i -= 1

            elif state == MultipartState.PART_DATA:
                prev_index = index
                boundary_length = len(boundary)
                data_length = length

                if index == 0:
                    i0 = data.find(boundary, i, data_length)
                    if i0 >= 0:
                        index = boundary_length - 1
                        i = i0 + boundary_length - 1
                    else:
                        i = max(i, data_length - boundary_length)
                        while i < data_length - 1 and data[i] != boundary[0]:
                            i += 1

                c = data[i]

                if index < boundary_length:
                    if boundary[index] == c:
                        index += 1
                    else:
                        index = 0
                elif index == boundary_length:
                    index += 1
                    if c == CR:
                        flags |= FLAG_PART_BOUNDARY
                    elif c == HYPHEN:
                        flags |= FLAG_LAST_BOUNDARY
                    else:
                        index = 0
                elif index == boundary_length + 1:
                    if flags & FLAG_PART_BOUNDARY:
                        if c == LF:
                            flags &= ~FLAG_PART_BOUNDARY
                            data_callback("part_data", i - index)
                            self.callback("part_end")
                            self.callback("part_begin")
                            index = 0
                            state = MultipartState.HEADER_FIELD_START
                            i += 1
                            continue
                        index = 0
                        flags &= ~FLAG_PART_BOUNDARY
                    elif flags & FLAG_LAST_BOUNDARY:
                        if c == HYPHEN:
                            data_callback("part_data", i - index)
                            self.callback("part_end")
                            self.callback("end")
                            state = MultipartState.END
                        else:
                            index = 0

                if index == 0 and prev_index > 0:
                    prev_index = 0
                    i -= 1

            elif state == MultipartState.END_BOUNDARY:
                if index == len(boundary) - 2 + 1:
                    if c != HYPHEN:
                        msg = "Did not find - at end of boundary (%d)" % (i,)
                        self.logger.warning(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e
                    index += 1
                    self.callback("end")
                    state = MultipartState.END

            elif state == MultipartState.END:
                if c == CR and i + 1 < length and data[i + 1] == LF:
                    i += 2
                    continue
                self.logger.warning("Skipping data after last boundary")
                i = length
                break

            else:  # pragma: no cover (error case)
                msg = "Reached an unknown state %d at %d" % (state, i)
                self.logger.warning(msg)
                e = MultipartParseError(msg)
                e.offset = i
                raise e

            i += 1

        data_callback("header_field", length, True)
        data_callback("header_value", length, True)
        data_callback("part_data", length - index, True)

        self.state = state
        self.index = index
        self.flags = flags

        return length

    def finalize(self) -> None:
        """
        【生命周期】结束解析
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(boundary={self.boundary!r})"


# =============================================================================
# 表单解析器协调器
# =============================================================================

class FormParser:
    """
    【设计模式】策略模式 - 上下文类
    
    【功能说明】
    根据 Content-Type 选择并协调相应的解析器。
    这是整个解析系统的入口点和协调器。
    
    【策略模式应用】
    - 策略接口：BaseParser 及其子类
    - 具体策略：OctetStreamParser、QuerystringParser、MultipartParser
    - 上下文：FormParser，根据 Content-Type 选择策略
    
    【工厂方法】
    create_form_parser 是工厂函数，封装了创建 FormParser 的逻辑。
    
    【初始化流程】
    1. 设置配置参数
    2. 根据 Content-Type 确定解析类型
    3. 创建对应的解析器和回调函数
    4. 设置底层 writer 处理编码转换
    """
    DEFAULT_CONFIG: FormParserConfig = {
        "MAX_BODY_SIZE": float("inf"),
        "MAX_MEMORY_FILE_SIZE": 1 * 1024 * 1024,
        "UPLOAD_DIR": None,
        "UPLOAD_KEEP_FILENAME": False,
        "UPLOAD_KEEP_EXTENSIONS": False,
        "UPLOAD_ERROR_ON_BAD_CTE": False,
    }

    def __init__(
        self,
        content_type: str,
        on_field: OnFieldCallback | None,
        on_file: OnFileCallback | None,
        on_end: Callable[[], None] | None = None,
        boundary: bytes | str | None = None,
        file_name: bytes | None = None,
        FileClass: type[FileProtocol] = File,
        FieldClass: type[FieldProtocol] = Field,
        config: dict[Any, Any] = {},
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.content_type = content_type
        self.boundary = boundary
        self.bytes_received = 0
        self.parser = None

        self.on_field = on_field
        self.on_file = on_file
        self.on_end = on_end

        self.FileClass = File
        self.FieldClass = Field

        self.config: FormParserConfig = self.DEFAULT_CONFIG.copy()
        self.config.update(config)  # type: ignore[typeddict-item]

        parser: OctetStreamParser | MultipartParser | QuerystringParser | None = None

        # application/octet-stream：创建 OctetStreamParser
        if content_type == "application/octet-stream":
            file: FileProtocol = None  # type: ignore

            def on_start() -> None:
                nonlocal file
                file = FileClass(file_name, None, config=cast("FileConfig", self.config))

            def on_data(data: bytes, start: int, end: int) -> None:
                nonlocal file
                file.write(data[start:end])

            def _on_end() -> None:
                nonlocal file
                file.finalize()
                if on_file:
                    on_file(file)
                if self.on_end is not None:
                    self.on_end()

            parser = OctetStreamParser(
                callbacks={"on_start": on_start, "on_data": on_data, "on_end": _on_end},
                max_size=self.config["MAX_BODY_SIZE"],
            )

        # application/x-www-form-urlencoded：创建 QuerystringParser
        elif content_type == "application/x-www-form-urlencoded" or content_type == "application/x-url-encoded":
            name_buffer: list[bytes] = []
            f: FieldProtocol | None = None

            def on_field_start() -> None:
                pass

            def on_field_name(data: bytes, start: int, end: int) -> None:
                name_buffer.append(data[start:end])

            def on_field_data(data: bytes, start: int, end: int) -> None:
                nonlocal f
                if f is None:
                    f = FieldClass(b"".join(name_buffer))
                    del name_buffer[:]
                f.write(data[start:end])

            def on_field_end() -> None:
                nonlocal f
                if f is None:
                    f = FieldClass(b"".join(name_buffer))
                    del name_buffer[:]
                    f.set_none()
                f.finalize()
                if on_field:
                    on_field(f)
                f = None

            def _on_end() -> None:
                if self.on_end is not None:
                    self.on_end()

            parser = QuerystringParser(
                callbacks={
                    "on_field_start": on_field_start,
                    "on_field_name": on_field_name,
                    "on_field_data": on_field_data,
                    "on_field_end": on_field_end,
                    "on_end": _on_end,
                },
                max_size=self.config["MAX_BODY_SIZE"],
            )

        # multipart/form-data：创建 MultipartParser
        elif content_type == "multipart/form-data":
            if boundary is None:
                self.logger.error("No boundary given")
                raise FormParserError("No boundary given")

            header_name: list[bytes] = []
            header_value: list[bytes] = []
            headers: dict[bytes, bytes] = {}

            f_multi: FileProtocol | FieldProtocol | None = None
            writer = None
            is_file = False

            def on_part_begin() -> None:
                nonlocal headers
                headers = {}

            def on_part_data(data: bytes, start: int, end: int) -> None:
                nonlocal writer
                assert writer is not None
                writer.write(data[start:end])

            def on_part_end() -> None:
                nonlocal f_multi, is_file
                assert f_multi is not None
                f_multi.finalize()
                if is_file:
                    if on_file:
                        on_file(f_multi)
                else:
                    if on_field:
                        on_field(cast("FieldProtocol", f_multi))

            def on_header_field(data: bytes, start: int, end: int) -> None:
                header_name.append(data[start:end])

            def on_header_value(data: bytes, start: int, end: int) -> None:
                header_value.append(data[start:end])

            def on_header_end() -> None:
                headers[b"".join(header_name)] = b"".join(header_value)
                del header_name[:]
                del header_value[:]

            def on_headers_finished() -> None:
                nonlocal is_file, f_multi, writer
                is_file = False

                content_disp = headers.get(b"Content-Disposition")
                disp, options = parse_options_header(content_disp)

                field_name = options.get(b"name")
                file_name = options.get(b"filename")

                if file_name is None:
                    f_multi = FieldClass(field_name)
                else:
                    f_multi = FileClass(file_name, field_name, config=cast("FileConfig", self.config))
                    is_file = True

                transfer_encoding = headers.get(b"Content-Transfer-Encoding", b"7bit")

                if transfer_encoding in (b"binary", b"8bit", b"7bit"):
                    writer = f_multi
                elif transfer_encoding == b"base64":
                    writer = Base64Decoder(f_multi)
                elif transfer_encoding == b"quoted-printable":
                    writer = QuotedPrintableDecoder(f_multi)
                else:
                    self.logger.warning("Unknown Content-Transfer-Encoding: %r", transfer_encoding)
                    if self.config["UPLOAD_ERROR_ON_BAD_CTE"]:
                        raise FormParserError(f'Unknown Content-Transfer-Encoding "{transfer_encoding!r}"')
                    else:
                        writer = f_multi

            def _on_end() -> None:
                nonlocal writer
                if writer is not None:
                    writer.finalize()
                if self.on_end is not None:
                    self.on_end()

            parser = MultipartParser(
                boundary,
                callbacks={
                    "on_part_begin": on_part_begin,
                    "on_part_data": on_part_data,
                    "on_part_end": on_part_end,
                    "on_header_field": on_header_field,
                    "on_header_value": on_header_value,
                    "on_header_end": on_header_end,
                    "on_headers_finished": on_headers_finished,
                    "on_end": _on_end,
                },
                max_size=self.config["MAX_BODY_SIZE"],
            )

        else:
            self.logger.warning("Unknown Content-Type: %r", content_type)
            raise FormParserError(f"Unknown Content-Type: {content_type}")

        self.parser = parser

    def write(self, data: bytes) -> int:
        """
        【接口方法】写入数据
        
        【实现】
        累计字节数，委托给底层解析器
        """
        self.bytes_received += len(data)
        assert self.parser is not None
        return self.parser.write(data)

    def finalize(self) -> None:
        """
        【生命周期】结束解析
        """
        if self.parser is not None and hasattr(self.parser, "finalize"):
            self.parser.finalize()

    def close(self) -> None:
        """
        【资源管理】关闭解析器
        """
        if self.parser is not None and hasattr(self.parser, "close"):
            self.parser.close()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(content_type={self.content_type!r}, parser={self.parser!r})"


# =============================================================================
# 工厂函数
# =============================================================================

def create_form_parser(
    headers: dict[str, bytes],
    on_field: OnFieldCallback | None,
    on_file: OnFileCallback | None,
    trust_x_headers: bool = False,
    config: dict[Any, Any] = {},
) -> FormParser:
    """
    【设计模式】工厂方法模式 - 工厂函数
    
    【功能说明】
    根据 HTTP 头部信息创建合适的 FormParser 实例。
    
    【参数】
    headers：HTTP 请求头字典（必需包含 Content-Type）
    on_field：字段解析完成回调
    on_file：文件解析完成回调
    trust_x_headers：是否信任 X-File-Name 等头部
    config：额外的配置选项
    
    【实现步骤】
    1. 从 Content-Type 头部提取主类型和参数（boundary 等）
    2. 可选地从 X-File-Name 头部提取文件名
    3. 创建并返回 FormParser 实例
    
    【使用示例】
    ```python
    headers = {"Content-Type": "multipart/form-data; boundary=----abc"}
    parser = create_form_parser(headers, on_field, on_file)
    parser.write(data)
    parser.finalize()
    ```
    """
    content_type: str | bytes | None = headers.get("Content-Type")
    if content_type is None:
        logging.getLogger(__name__).warning("No Content-Type header given")
        raise ValueError("No Content-Type header given!")

    content_type, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")

    content_type = content_type.decode("latin-1")

    file_name = headers.get("X-File-Name")

    form_parser = FormParser(content_type, on_field, on_file, boundary=boundary, file_name=file_name, config=config)

    return form_parser


def parse_form(
    headers: dict[str, bytes],
    input_stream: SupportsRead,
    on_field: OnFieldCallback | None,
    on_file: OnFileCallback | None,
    chunk_size: int = 1048576,
) -> None:
    """
    【高级接口】完整表单解析
    
    【功能说明】
    提供一站式的表单解析服务，从 HTTP 头部和输入流中解析表单数据。
    
    【参数】
    headers：HTTP 请求头字典
    input_stream：支持 read() 方法的输入流
    on_field：字段解析完成回调
    on_file：文件解析完成回调
    chunk_size：每次读取的字节数（默认 1 MiB）
    
    【实现特点】
    1. 使用 create_form_parser 创建解析器
    2. 循环读取输入流并写入解析器
    3. 支持 Content-Length 限制读取量
    
    【使用示例】
    ```python
    parse_form(
        request.headers,
        request.stream,
        lambda f: print(f.field_name, f.value),
        lambda f: save_file(f)
    )
    ```
    """
    parser = create_form_parser(headers, on_field, on_file)

    content_length: int | float | bytes | None = headers.get("Content-Length")
    if content_length is not None:
        content_length = int(content_length)
    else:
        content_length = float("inf")
    bytes_read = 0

    while True:
        max_readable = int(min(content_length - bytes_read, chunk_size))
        buff = input_stream.read(max_readable)

        parser.write(buff)
        bytes_read += len(buff)

        if len(buff) != max_readable or bytes_read == content_length:
            break

    parser.finalize()


# =============================================================================
# 模块初始化
# =============================================================================

# 【哨兵对象】用于表示未计算状态
_missing = object()
