from __future__ import with_statement, absolute_import, print_function

from .six import (
    binary_type,
    text_type,
    PY3,
)

from .decoders import *
from .exceptions import *

try:
    from urlparse import parse_qs
except ImportError:
    from urllib.parse import parse_qs

import os
import re
import sys
import shutil
import logging
import tempfile
from io import BytesIO
from numbers import Number

# Unique missing object.
_missing = object()

# Get logger for this module.
logger = logging.getLogger(__name__)

# States for the querystring parser.
STATE_BEFORE_FIELD = 0
STATE_FIELD_NAME   = 1
STATE_FIELD_DATA   = 2

# States for the multipart parser
STATE_START                     = 0
STATE_START_BOUNDARY            = 1
STATE_HEADER_FIELD_START        = 2
STATE_HEADER_FIELD              = 3
STATE_HEADER_VALUE_START        = 4
STATE_HEADER_VALUE              = 5
STATE_HEADER_VALUE_ALMOST_DONE  = 6
STATE_HEADERS_ALMOST_DONE       = 7
STATE_PART_DATA_START           = 8
STATE_PART_DATA                 = 9
STATE_PART_DATA_END             = 10
STATE_END                       = 11

# Flags for the multipart parser.
FLAG_PART_BOUNDARY              = 1
FLAG_LAST_BOUNDARY              = 2

# Get constants.  Since iterating over a str on Python 2 gives you a 1-length
# string, but iterating over a bytes object on Python 3 gives you an integer,
# we need to save these constants.
CR = b'\r'[0]
LF = b'\n'[0]
COLON = b':'[0]
SPACE = b' '[0]
HYPHEN = b'-'[0]
AMPERSAND = b'&'[0]
SEMICOLON = b';'[0]
LOWER_A = b'a'[0]
LOWER_Z = b'z'[0]
NULL = b'\x00'[0]

# Lower-casing a character is different, because of the difference between
# str on Py2, and bytes on Py3.  Same with getting the ordinal value of a byte,
# and joining a list of bytes together.
# These functions abstract that.
if PY3:                         # pragma: no cover
    lower_char = lambda c: c | 0x20
    ord_char = lambda c: c
    join_bytes = lambda b: bytes(list(b))
else:                           # pragma: no cover
    lower_char = lambda c: c.lower()
    ord_char = lambda c: ord(c)
    join_bytes = lambda b: b''.join(list(b))

# These are regexes for parsing header values.
SPECIAL_CHARS = re.escape(b'()<>@,;:\\"/[]?={} \t')
QUOTED_STR = br'"(?:\\.|[^"])*"'
VALUE_STR = br'(?:[^' + SPECIAL_CHARS + br']+|' + QUOTED_STR + br')'
OPTION_RE_STR = (
    br'(?:;|^)\s*([^' + SPECIAL_CHARS + br']+)\s*=\s*(' + VALUE_STR + br')'
)
OPTION_RE = re.compile(OPTION_RE_STR)
QUOTE = b'"'[0]


def parse_options_header(value):
    """
    Parses a Content-Type header into a value in the following format:
        (content_type, {parameters})
    """
    if not value:
        return (b'', {})

    # If we have no options, return the string as-is.
    if b';' not in value:
        return (value.lower().strip(), {})

    # Split at the first semicolon, to get our value and then options.
    ctype, rest = value.split(b';', 1)
    options = {}

    # Parse the options.
    for match in OPTION_RE.finditer(rest):
        key = match.group(1).lower()
        value = match.group(2)
        if value[0] == QUOTE and value[-1] == QUOTE:
            # Unquote the value.
            value = value[1:-1]
            value = value.replace(b'\\\\', b'\\').replace(b'\\"', b'"')

        # If the value is a filename, we need to fix a bug on IE6 that sends
        # the full file path instead of the filename.
        if key == b'filename':
            if value[1:3] == b':\\' or value[:2] == b'\\\\':
                value = value.split(b'\\')[-1]

        options[key] = value

    return ctype, options


class Field(object):
    """
    Object that represents a form field.  You can subclass this to handle the
    written data in an alternate method.
    """
    def __init__(self, name):
        self._name = name
        self._value = []

        # We cache the joined version of _value for speed.
        self._cache = _missing

    @classmethod
    def from_value(klass, name, value):
        f = klass(name)
        if value is None:
            f.set_none()
        else:
            f.write(value)
        f.finalize()
        return f

    def write(self, data):
        return self.on_data(data)

    def on_data(self, data):
        self._value.append(data)
        self._cache = _missing
        return len(data)

    def on_end(self):
        if self._cache is _missing:
            self._cache = b''.join(self._value)

    def finalize(self):
        self.on_end()

    def close(self):
        # Free our value array.
        if self._cache is _missing:
            self._cache = b''.join(self._value)

        del self._value

    def set_none(self):
        """
        Some fields in a querystring can possibly have a value of None - for
        example, the string "foo&bar=&baz=asdf" will have a field with the
        name "foo" and value None, one with name "bar" and value "", and one
        with name "baz" and value "asdf".  Since the write() interface doesn't
        support writing None, this function will set the field value to None.
        """
        self._cache = None

    @property
    def field_name(self):
        return self._name

    @property
    def value(self):
        if self._cache is _missing:
            self._cache = b''.join(self._value)

        return self._cache

    def __eq__(self, other):
        if isinstance(other, Field):
            return (
                self.field_name == other.field_name and
                self.value == other.value
            )
        else:
            return NotImplemented

    def __repr__(self):
        if len(self.value) > 97:
            # We get the repr, and then insert three dots before the final
            # quote.
            v = repr(self.value[:97])[:-1] + "...'"
        else:
            v = repr(self.value)

        return "%s(field_name=%r, value=%s)" % (
            self.__class__.__name__,
            self.field_name,
            v
        )


class File(object):
    """
    This class represents an uploaded file.  It handles writing file data to
    either an in-memory file or a temporary file on-disk, if the optional
    threshold is passed.
    """
    def __init__(self, file_name, field_name=None, config={}):
        # Save configuration, set other variables default.
        self._config = config
        self._in_memory = True
        self._bytes_written = 0
        self._fileobj = BytesIO()

        # Save the provided field/file name.
        self._field_name = field_name
        self._file_name = file_name

        # Our actual file name is None by default, since, depending on our
        # config, we may not actually use the provided name.
        self._actual_file_name = None

        # Split the extension from the filename.
        if file_name is not None:
            base, ext = os.path.splitext(file_name)
            self._file_base = base
            self._ext = ext

    @property
    def field_name(self):
        """
        The form field associated with this file.  May be None if there isn't
        one, for example when we have an application/octet-stream upload.
        """
        return self._field_name

    @property
    def file_name(self):
        """
        The file name given in the upload request.
        """
        return self._file_name

    @property
    def actual_file_name(self):
        """
        The file name that this file is saved as.  Will return None if it's not
        currently saved on disk.
        """
        return self._actual_file_name

    @property
    def file_object(self):
        """
        The file object that we're currently writing to.
        """
        return self._fileobj

    @property
    def in_memory(self):
        """
        Whether or not this file object is currently stored in-memory or on-
        disk.
        """
        return self._in_memory

    def flush_to_disk(self):
        """
        If the file is already on-disk, do nothing.  Otherwise, copy from the
        in-memory buffer to a disk file, and then reassign our internal file
        object to this new disk file.
        """
        if not self._in_memory:
            logger.warn("Trying to flush to disk when we're not in memory")
            return

        # Go back to the start of our file.
        self._fileobj.seek(0)

        # Open a new file.
        new_file = self.get_disk_file()

        # Copy the file objects.
        shutil.copyfileobj(self._fileobj, new_file)

        # Seek to the new position in our new file.
        new_file.seek(self._bytes_written)

        # Reassign the fileobject.
        old_fileobj = self._fileobj
        self._fileobj = new_file

        # We're no longer in memory.
        self._in_memory = False

        # Close the old file object.
        old_fileobj.close()

    def get_disk_file(self):
        """
        This function is responsible for getting a file object on-disk for us.
        """
        logger.info("Opening a file on disk")

        file_dir = self._config.get('UPLOAD_DIR')
        keep_filename = self._config.get('UPLOAD_KEEP_FILENAME', False)
        keep_extensions = self._config.get('UPLOAD_KEEP_EXTENSIONS', False)

        # If we have a directory and are to keep the filename...
        if file_dir is not None and keep_filename:
            logger.info("Saving with filename in: %r", file_dir)

            # Build our filename.
            # TODO: what happens if we don't have a filename?
            fname = self._file_base
            if keep_extensions:
                fname = fname + self._ext

            path = os.path.join(file_dir, fname)
            try:
                logger.info("Opening file: %r", path)
                tmp_file = open(path, 'w+b')
            except (IOError, OSError) as e:
                tmp_file = None

                logger.exception("Error opening temporary file")
                raise FileError("Error opening temporary file: %r" % path)
        else:
            # Build options array.
            # Note that on Python 3, tempfile doesn't support byte names.  We
            # encode our paths using the default filesystem encoding.
            options = {}
            if keep_extensions:
                ext = self._ext
                if isinstance(ext, binary_type):
                    ext = ext.decode(sys.getfilesystemencoding())

                options['suffix'] = ext
            if file_dir is not None:
                d = file_dir
                if isinstance(d, binary_type):
                    d = d.decode(sys.getfilesystemencoding())

                options['dir'] = d

            # Create a temporary (named) file with the appropriate settings.
            logger.info("Creating a temporary file with options: %r", options)
            try:
                tmp_file = tempfile.NamedTemporaryFile(**options)
            except (IOError, OSError):
                logger.exception("Error creating named temporary file")
                raise FileError("Error creating named temporary file")

            fname = tmp_file.name

            # Encode filename as bytes.
            if isinstance(fname, text_type):
                fname = fname.encode(sys.getfilesystemencoding())

        self._actual_file_name = fname
        return tmp_file

    def write(self, data):
        return self.on_data(data)

    def on_data(self, data):
        bwritten = self._fileobj.write(data)

        # If the bytes written isn't the same as the length, just return.
        if bwritten != len(data):
            logger.warn("bwritten != len(data) (%d != %d)", bwritten,
                        len(data))
            return bwritten

        # Keep track of how many bytes we've written.
        self._bytes_written += bwritten

        # If we're in-memory and are over our limit, we create a file.
        if (self._in_memory and
                self._config.get('MAX_MEMORY_FILE_SIZE') is not None and
                (self._bytes_written >
                 self._config.get('MAX_MEMORY_FILE_SIZE'))):
            logger.info("Flushing to disk")
            self.flush_to_disk()

        # Return the number of bytes written.
        return bwritten

    def on_end(self):
        pass

    def finalize(self):
        self.on_end()

    def close(self):
        self._fileobj.close()

    def __repr__(self):
        return "%s(file_name=%r, field_name=%r)" % (
            self.__class__.__name__,
            self.file_name,
            self.field_name
        )


class BaseParser(object):
    """
    This class implements some helpful methods for parsers.  Currently, it
    just implements the callback logic in a central location.
    """
    def callback(self, name, data=None, start=None, end=None):
        """
        This function calls a provided callback with some data.
        """
        name = "on_" + name
        func = self.callbacks.get(name)
        if func is None:
            return

        # Depending on whether we're given a buffer...
        if data is not None:
            # Don't do anything if we have start == end.
            if start is not None and start == end:
                return

            logger.debug("Calling %s with data[%d:%d]", name, start, end)
            func(data, start, end)
        else:
            logger.debug("Calling %s with no data", name)
            func()

    def set_callback(self, name, new_func):
        """
        Update the function for a callback.  Removes from the callbacks dict
        if new_func is None.
        """
        if new_func is None:
            self.callbacks.pop('on_' + name, None)
        else:
            self.callbacks['on_' + name] = new_func

    def close(self):
        pass                # pragma: no cover

    def finalize(self):
        pass                # pragma: no cover

    def __repr__(self):
        return "%s()" % self.__class__.__name__


class OctetStreamParser(BaseParser):
    """
    This parser parses an octet-stream request body and calls callbacks when
    incoming data is received.  Callbacks are:
        - on_start
        - on_data       (with data parameters)
        - on_end
    """
    def __init__(self, callbacks={}, max_size=float('inf')):
        self.callbacks = callbacks
        self._started = False

        if not isinstance(max_size, Number) or max_size < 1:
            raise ValueError("max_size must be a positive number, not %r" %
                             max_size)
        self.max_size = max_size
        self._current_size = 0

    def write(self, data):
        if not self._started:
            self.callback('start')
            self._started = True

        # Truncate data length.
        data_len = len(data)
        if self._current_size + data_len > self.max_size:
            # We truncate the length of data that we are to process.
            new_size = int(self.max_size - self._current_size)
            logging.warn("Current size is %d (max %d), so truncating data "
                         "length from %d to %d", self._current_size,
                         self.max_size, data_len, new_size)
            data_len = new_size

        # Increment size, then callback, in case there's an exception.
        self._current_size += data_len
        self.callback('data', data, 0, data_len)
        return data_len

    def finalize(self):
        self.callback('end')

    def __repr__(self):
        return "%s()" % self.__class__.__name__


class QuerystringParser(BaseParser):
    """
    This is a streaming querystring parser.  It will consume data, and call
    the callbacks given when it has enough data.

    Valid callbacks (* means with data):
        - on_field_start
        - on_field_name         *
        - on_field_data         *
        - on_field_end
        - on_end

    Some details on how the strict_parsing deals with values:
        - If a field has a value with an equal sign (e.g. "foo=bar", or
          "foo="), it is always included.
        - If a field has no equals sign (e.g. "...&name&..."), it will be
          treated as an error if 'strict_parsing' is True, otherwise included.
    """
    SPLIT_RE = re.compile(b'[&;]')

    def __init__(self, callbacks={}, strict_parsing=False,
                 max_size=float('inf')):
        self.state = STATE_BEFORE_FIELD
        self._found_sep = False

        self.callbacks = callbacks

        # Max-size stuff
        if not isinstance(max_size, Number) or max_size < 1:
            raise ValueError("max_size must be a positive number, not %r" %
                             max_size)
        self.max_size = max_size
        self._current_size = 0

        # Should parsing be strict?
        self.strict_parsing = strict_parsing

    def write(self, data):
        # Handle sizing.
        data_len = len(data)
        if self._current_size + data_len > self.max_size:
            # We truncate the length of data that we are to process.
            new_size = int(self.max_size - self._current_size)
            logging.warn("Current size is %d (max %d), so truncating data "
                         "length from %d to %d", self._current_size,
                         self.max_size, data_len, new_size)
            data_len = new_size

        l = 0
        try:
            l = self._internal_write(data, data_len)
        finally:
            self._current_size += l

        return l

    def _internal_write(self, data, length):
        state = self.state
        strict_parsing = self.strict_parsing
        found_sep = self._found_sep

        i = 0
        while i < length:
            ch = data[i]

            # Depending on our state...
            if state == STATE_BEFORE_FIELD:
                # If the 'found_sep' flag is set, we've already encountered
                # and skipped a single seperator.  If so, we check our strict
                # parsing flag and decide what to do.  Otherwise, we haven't
                # yet reached a seperator, and thus, if we do, we need to skip
                # it as it will be the boundary between fields that's supposed
                # to be there.
                if ch == AMPERSAND or ch == SEMICOLON:
                    if found_sep:
                        # If we're parsing strictly, we disallow blank chunks.
                        if strict_parsing:
                            e = QuerystringParseError(
                                "Skipping duplicate ampersand/semicolon at "
                                "%d" % i
                            )
                            e.offset = i
                            raise e
                        else:
                            logger.debug("Skipping duplicate ampersand/"
                                         "semicolon at %d", i)
                    else:
                        # This case is when we're skipping the (first)
                        # seperator between fields, so we just set our flag
                        # and continue on.
                        found_sep = True
                else:
                    # Emit a field-start event, and go to that state.  Also,
                    # reset the "found_sep" flag, for the next time we get to
                    # this state.
                    self.callback('field_start')
                    i -= 1
                    state = STATE_FIELD_NAME
                    found_sep = False

            elif state == STATE_FIELD_NAME:
                # Try and find a seperator - we ensure that, if we do, we only
                # look for the equal sign before it.
                sep_pos = data.find(b'&', i)
                if sep_pos == -1:
                    sep_pos = data.find(b';', i)

                # See if we can find an equals sign in the remaining data.  If
                # so, we can immedately emit the field name and jump to the
                # data state.
                if sep_pos != -1:
                    equals_pos = data.find(b'=', i, sep_pos)
                else:
                    equals_pos = data.find(b'=', i)

                if equals_pos != -1:
                    # Emit this name.
                    self.callback('field_name', data, i, equals_pos)

                    # Jump i to this position.  Note that it will then have 1
                    # added to it below, which means the next iteration of this
                    # loop will inspect the character after the equals sign.
                    i = equals_pos
                    state = STATE_FIELD_DATA
                else:
                    # No equals sign found.
                    if not strict_parsing:
                        # See also comments in the STATE_FIELD_DATA case below.
                        # If we found the seperator, we emit the name and just
                        # end - there's no data callback at all (not even with
                        # a blank value).
                        if sep_pos != -1:
                            self.callback('field_name', data, i, sep_pos)
                            self.callback('field_end')

                            i = sep_pos - 1
                            state = STATE_BEFORE_FIELD
                        else:
                            # Otherwise, no seperator in this block, so the
                            # rest of this chunk must be a name.
                            self.callback('field_name', data, i, length)
                            i = length

                    else:
                        # We're parsing strictly.  If we find a seperator,
                        # this is an error - we require an equals sign.
                        if sep_pos != -1:
                            e =  QuerystringParseError(
                                "When strict_parsing is True, we require an "
                                "equals sign in all field chunks. Did not "
                                "find one in the chunk that starts at %d" %
                                (i,)
                            )
                            e.offset = i
                            raise e

                        # No seperator in the rest of this chunk, so it's just
                        # a field name.
                        self.callback('field_name', data, i, length)
                        i = length

            elif state == STATE_FIELD_DATA:
                # Try finding either an ampersand or a semicolon after this
                # position.
                sep_pos = data.find(b'&', i)
                if sep_pos == -1:
                    sep_pos = data.find(b';', i)

                # If we found it, callback this bit as data and then go back
                # to expecting to find a field.
                if sep_pos != -1:
                    self.callback('field_data', data, i, sep_pos)
                    self.callback('field_end')

                    # Note that we go to the seperator, which brings us to the
                    # "before field" state.  This allows us to properly emit
                    # "field_start" events only when we actually have data for
                    # a field of some sort.
                    i = sep_pos - 1
                    state = STATE_BEFORE_FIELD

                # Otherwise, emit the rest as data and finish.
                else:
                    self.callback('field_data', data, i, length)
                    i = length

            else:                   # pragma: no cover (error case)
                msg = "Reached an unknown state %d at %d" % (state, i)
                logger.warn(msg)
                e = QuerystringParseError(msg)
                e.offset = i
                raise e

            i += 1

        self.state = state
        self._found_sep = found_sep
        return len(data)

    def finalize(self):
        # If we're currently in the middle of a field, we finish it.
        if self.state == STATE_FIELD_DATA:
            self.callback('field_end')
        self.callback('end')

    def __repr__(self):
        return "%s(keep_blank_values=%r, strict_parsing=%r, max_size=%r)" % (
            self.__class__.__name__,
            self.keep_blank_values, self.strict_parsing, self.max_size
        )


class MultipartParser(BaseParser):
    """
    This class implements a state machine that parses a multipart/form-data
    message.

    Valid callbacks (* indicates given data):
        - on_part_begin
        - on_part_data              *
        - on_part_end
        - on_header_begin
        - on_header_field           *
        - on_header_value           *
        - on_header_end
        - on_headers_finished
        - on_end
    """

    def __init__(self, boundary, callbacks={}, max_size=float('inf')):
        # Initialize parser state.
        self.state = STATE_START
        self.index = self.flags = 0

        self.callbacks = callbacks

        if not isinstance(max_size, Number) or max_size < 1:
            raise ValueError("max_size must be a positive number, not %r" %
                             max_size)
        self.max_size = max_size
        self._current_size = 0

        # Setup marks.  These are used to track the state of data recieved.
        self.marks = {}

        # TODO: Actually use this rather than the dumb version we currently use
        # # Precompute the skip table for the Boyer-Moore-Horspool algorithm.
        # skip = [len(boundary) for x in range(256)]
        # for i in range(len(boundary) - 1):
        #     skip[ord_char(boundary[i])] = len(boundary) - i - 1
        #
        # # We use a tuple since it's a constant, and marginally faster.
        # self.skip = tuple(skip)

        # Save our boundary.
        self.boundary = b'\r\n--' + boundary

        # Get a set of characters that belong to our boundary.
        self.boundary_chars = frozenset(self.boundary)

        # We also create a lookbehind list.
        # Note: the +8 is since we can have, at maximum, "\r\n--" + boundary +
        # "--\r\n" at the final boundary, and the length of '\r\n--' and
        # '--\r\n' is 8 bytes.
        self.lookbehind = [NULL for x in range(len(boundary) + 8)]

    def write(self, data):
        # Handle sizing.
        data_len = len(data)
        if self._current_size + data_len > self.max_size:
            # We truncate the length of data that we are to process.
            new_size = int(self.max_size - self._current_size)
            logging.warn("Current size is %d (max %d), so truncating data "
                         "length from %d to %d", self._current_size,
                         self.max_size, data_len, new_size)
            data_len = new_size

        l = 0
        try:
            l = self._internal_write(data, data_len)
        finally:
            self._current_size += l

        return l

    def _internal_write(self, data, length):
        # Get values from locals.
        boundary = self.boundary

        # Get our state, flags and index.  These are persisted between calls to
        # this function.
        state = self.state
        index = self.index
        flags = self.flags

        # Our index defaults to 0.
        i = 0

        # Set a mark.
        def set_mark(name):
            self.marks[name] = i

        # Remove a mark.
        def delete_mark(name, reset=False):
            self.marks.pop(name, None)

        # Helper function that makes calling a callback with data easier. The
        # 'remaining' parameter will callback from the marked value until the
        # end of the buffer, and reset the mark, instead of deleting it.  This
        # is used at the end of the function to call our callbacks with any
        # remaining data in this chunk.
        def data_callback(name, remaining=False):
            marked_index = self.marks.get(name)
            if marked_index is None:
                return

            # If we're getting remaining data, we ignore the current i value
            # and just call with the remaining data.
            if remaining:
                self.callback(name, data, marked_index, length)
                self.marks[name] = 0

            # Otherwise, we call it from the mark to the current byte we're
            # processing.
            else:
                self.callback(name, data, marked_index, i)
                self.marks.pop(name, None)

        # For each byte...
        while i < length:
            c = data[i]

            if state == STATE_START:
                # Skip leading newlines
                if c == CR or c == LF:
                    i += 1
                    logger.debug("Skipping leading CR/LF at %d", i)
                    continue

                # index is used as in index into our boundary.  Set to 0.
                index = 0

                # Move to the next state, but decrement i so that we re-process
                # this character.
                state = STATE_START_BOUNDARY
                i -= 1

            elif state == STATE_START_BOUNDARY:
                # Check to ensure that the last 2 characters in our boundary
                # are CRLF.
                if index == len(boundary) - 2:
                    if c != CR:
                        # Error!
                        msg = "Did not find CR at end of boundary (%d)" % (i,)
                        logger.warn(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    index += 1

                elif index == len(boundary) - 2 + 1:
                    if c != LF:
                        msg = "Did not find LF at end of boundary (%d)" % (i,)
                        logger.warn(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    # The index is now used for indexing into our boundary.
                    index = 0

                    # Callback for the start of a part.
                    self.callback('part_begin')

                    # Move to the next character and state.
                    state = STATE_HEADER_FIELD_START

                else:
                    # Check to ensure our boundary matches
                    if c != boundary[index + 2]:
                        # print('start_boundary: expected %r, found %r' % (c,
                        #        boundary[index + 2]))
                        msg = "Did not find boundary character %r at index " \
                              "%d" % (c, index + 2)
                        logger.warn(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    # Increment index into boundary and continue.
                    index += 1

            elif state == STATE_HEADER_FIELD_START:
                # Mark the start of a header field here, reset the index, and
                # continue parsing our header field.
                index = 0

                # Set a mark of our header field.
                set_mark('header_field')

                # Move to parsing header fields.
                state = STATE_HEADER_FIELD
                i -= 1

            elif state == STATE_HEADER_FIELD:
                # If we've reached a CR at the beginning of a header, it means
                # that we've reached the second of 2 newlines, and so there are
                # no more headers to parse.
                if c == CR:
                    delete_mark('header_field')
                    state = STATE_HEADERS_ALMOST_DONE
                    i += 1
                    continue

                # Increment our index in the header.
                index += 1

                # Do nothing if we encounter a hyphen.
                if c == HYPHEN:
                    pass

                # If we've reached a colon, we're done with this header.
                elif c == COLON:
                    # A 0-length header is an error.
                    if index == 1:
                        msg = "Found 0-length header at %d" % (i,)
                        logger.warn(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

                    # Call our callback with the header field.
                    data_callback('header_field')

                    # Move to parsing the header value.
                    state = STATE_HEADER_VALUE_START

                else:
                    # Lower-case this character, and ensure that it is in fact
                    # a valid letter.  If not, it's an error.
                    cl = lower_char(c)
                    if cl < LOWER_A or cl > LOWER_Z:
                        msg = "Found non-alphanumeric character %r in " \
                              "header at %d" % (c, i)
                        logger.warn(msg)
                        e = MultipartParseError(msg)
                        e.offset = i
                        raise e

            elif state == STATE_HEADER_VALUE_START:
                # Skip leading spaces.
                if c == SPACE:
                    i += 1
                    continue

                # Mark the start of the header value.
                set_mark('header_value')

                # Move to the header-value state, reprocessing this character.
                state = STATE_HEADER_VALUE
                i -= 1

            elif state == STATE_HEADER_VALUE:
                # If we've got a CR, we're nearly done our headers.  Otherwise,
                # we do nothing and just move past this character.
                if c == CR:
                    data_callback('header_value')
                    self.callback('header_end')
                    state = STATE_HEADER_VALUE_ALMOST_DONE

            elif state == STATE_HEADER_VALUE_ALMOST_DONE:
                # The last character should be a LF.  If not, it's an error.
                if c != LF:
                    msg = "Did not find LF character at end of header " \
                          "(found %r)" % (c,)
                    logger.warn(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e

                # Move back to the start of another header.  Note that if that
                # state detects ANOTHER newline, it'll trigger the end of our
                # headers.
                state = STATE_HEADER_FIELD_START

            elif state == STATE_HEADERS_ALMOST_DONE:
                # We're almost done our headers.  This is reached when we parse
                # a CR at the beginning of a header, so our next character
                # should be a LF, or it's an error.
                if c != LF:
                    msg = "Did not find LF at end of headers (found %r)" % (c,)
                    logger.warn(msg)
                    e = MultipartParseError(msg)
                    e.offset = i
                    raise e

                self.callback('headers_finished')
                state = STATE_PART_DATA_START

            elif state == STATE_PART_DATA_START:
                # Mark the start of our part data.
                set_mark('part_data')

                # Start processing part data, including this character.
                state = STATE_PART_DATA
                i -= 1

            elif state == STATE_PART_DATA:
                # We're processing our part data right now.  During this, we
                # need to efficiently search for our boundary, since any data
                # on any number of lines can be a part of the current data.
                # We use the Boyer-Moore-Horspool algorithm to efficiently
                # search through the remainder of the buffer looking for our
                # boundary.

                # Save the current value of our index.  We use this in case we
                # find part of a boundary, but it doesn't match fully.
                prev_index = index

                # Set up variables.
                boundary_length = len(boundary)
                boundary_end = boundary_length - 1
                data_length = length
                boundary_chars = self.boundary_chars

                # If our index is 0, we're starting a new part, so start our
                # search.
                if index == 0:
                    # Search forward until we either hit the end of our buffer,
                    # or reach a character that's in our boundary.
                    i += boundary_end
                    while i < data_length and data[i] not in boundary_chars:
                        i += boundary_length

                    # Reset i back the length of our boundary, which is the
                    # earliest possible location that could be our match (i.e.
                    # if we've just broken out of our loop since we saw the
                    # last character in our boundary)
                    i -= boundary_end
                    c = data[i]

                # Now, we have a couple of cases here.  If our index is before
                # the end of the boundary...
                if index < boundary_length:
                    # If the character matches...
                    if boundary[index] == c:
                        # If we found a match for our boundary, we send the
                        # existing data.
                        if index == 0:
                            data_callback('part_data')

                        # The current character matches, so continue!
                        index += 1
                    else:
                        index = 0

                # Our index is equal to the length of our boundary!
                elif index == boundary_length:
                    # First we increment it.
                    index += 1

                    # Now, if we've reached a newline, we need to set this as
                    # the potential end of our boundary.
                    if c == CR:
                        flags |= FLAG_PART_BOUNDARY

                    # Otherwise, if this is a hyphen, we might be at the last
                    # of all boundaries.
                    elif c == HYPHEN:
                        flags |= FLAG_LAST_BOUNDARY

                    # Otherwise, we reset our index, since this isn't either a
                    # newline or a hyphen.
                    else:
                        index = 0

                # Our index is right after the part boundary, which should be
                # a LF.
                elif index == boundary_length + 1:
                    # If we're at a part boundary (i.e. we've seen a CR
                    # character already)...
                    if flags & FLAG_PART_BOUNDARY:
                        # We need a LF character next.
                        if c == LF:
                            # Unset the part boundary flag.
                            flags &= (~FLAG_PART_BOUNDARY)

                            # Callback indicating that we've reached the end of
                            # a part, and are starting a new one.
                            self.callback('part_end')
                            self.callback('part_begin')

                            # Move to parsing new headers.
                            index = 0
                            state = STATE_HEADER_FIELD_START
                            i += 1
                            continue

                        # We didn't find an LF character, so no match.  Reset
                        # our index and clear our flag.
                        index = 0
                        flags &= (~FLAG_PART_BOUNDARY)

                    # Otherwise, if we're at the last boundary (i.e. we've
                    # seen a hyphen already)...
                    elif flags & FLAG_LAST_BOUNDARY:
                        # We need a second hyphen here.
                        if c == HYPHEN:
                            # Callback to end the current part, and then the
                            # message.
                            self.callback('part_end')
                            self.callback('end')
                            state = STATE_END
                        else:
                            # No match, so reset index.
                            index = 0

                # If we have an index, we need to keep this byte for later, in
                # case we can't match the full boundary.
                if index > 0:
                    self.lookbehind[index - 1] = c

                # Otherwise, our index is 0.  If the previous index is not, it
                # means we reset something, and we need to take the data we
                # thought was part of our boundary and send it along as actual
                # data.
                elif prev_index > 0:
                    # Callback to write the saved data.
                    lb_data = join_bytes(self.lookbehind)
                    self.callback('part_data', lb_data, 0, prev_index)

                    # Overwrite our previous index.
                    prev_index = 0

                    # Re-set our mark for part data.
                    set_mark('part_data')

                    # Re-consider the current character, since this could be
                    # the start of the boundary itself.
                    i -= 1

            elif state == STATE_END:
                # Do nothing and just consume a byte in the end state.
                logger.warn("Consuming a byte in the end state")
                pass

            else:                   # pragma: no cover (error case)
                # We got into a strange state somehow!  Just stop processing.
                msg = "Reached an unknown state %d at %d" % (state, i)
                logger.warn(msg)
                e = MultipartParseError(msg)
                e.offset = i
                raise e

            # Move to the next byte.
            i += 1

        # We call our callbacks with any remaining data.  Note that we pass
        # the 'remaining' flag, which sets the mark back to 0 instead of
        # deleting it, if it's found.  This is because, if the mark is found
        # at this point, we assume that there's data for one of these things
        # that has been parsed, but not yet emitted.  And, as such, it implies
        # that we haven't yet reached the end of this 'thing'.  So, by setting
        # the mark to 0, we cause any data callbacks that take place in future
        # calls to this function to start from the beginning of that buffer.
        data_callback('header_field', True)
        data_callback('header_value', True)
        data_callback('part_data', True)

        # Save values to locals.
        self.state = state
        self.index = index
        self.flags = flags

        # Return our data length to indicate no errors, and that we processed
        # all of it.
        return length

    def finalize(self):
        # TODO: verify that we're in the state STATE_END, otherwise throw an
        # error or otherwise state that we're not finished parsing.
        pass

    def __repr__(self):
        return "%s(boundary=%r)" % (self.__class__.__name__, self.boundary)


class FormParser(object):
    # This is the default configuration for our form parser.
    # Note: all file sizes should be in bytes.
    DEFAULT_CONFIG = {
        'MAX_BODY_SIZE': 1024,
        'MAX_MEMORY_FILE_SIZE': 1 * 1024 * 1024,
        'UPLOAD_DIR': None,
        'UPLOAD_KEEP_FILENAME': False,
        'UPLOAD_KEEP_EXTENSIONS': False,

        # Error on invalid Content-Transfer-Encoding?
        'UPLOAD_ERROR_ON_BAD_CTE': False,
    }

    def __init__(self, content_type, on_field, on_file, on_end=None,
                 boundary=None, content_length=-1, file_name=None,
                 FileClass=File, FieldClass=Field, config={}):

        # Save variables.
        self.content_length = content_length
        self.content_type = content_type
        self.boundary = boundary
        self.bytes_received = 0
        self.parser = None

        # Save callbacks.
        self.on_field = on_field
        self.on_file = on_file
        self.on_end = on_end

        # Save classes.
        self.FileClass = File
        self.FieldClass = Field

        # Set configuration options.
        self.config = self.DEFAULT_CONFIG.copy()
        self.config.update(config)

        # Depending on the Content-Type, we instantiate the correct parser.
        if content_type == b'application/octet-stream':
            # Work around the lack of 'nonlocal' in Py2
            class vars(object):
                f = None

            def on_start():
                vars.f = FileClass(file_name, None)

            def on_data(data, start, end):
                vars.f.write(data[start:end])

            def on_end():
                # Finalize the file itself.
                vars.f.finalize()

                # Call our callback.
                on_file(vars.f)

                # Call the on-end callback.
                if self.on_end is not None:
                    self.on_end()

            callbacks = {
                'on_start': on_start,
                'on_data': on_data,
                'on_end': on_end,
            }

            # Instantiate an octet-stream parser
            parser = OctetStreamParser(callbacks,
                                       max_size=self.config['MAX_BODY_SIZE'])

        elif (content_type == b'application/x-www-form-urlencoded' or
              content_type == b'application/x-url-encoded'):

            name_buffer = []

            class vars(object):
                f = None

            def on_field_start():
                pass

            def on_field_name(data, start, end):
                name_buffer.append(data[start:end])

            def on_field_data(data, start, end):
                if vars.f is None:
                    vars.f = FieldClass(b''.join(name_buffer))
                    del name_buffer[:]
                vars.f.write(data[start:end])

            def on_field_end():
                # Finalize and call callback.
                if vars.f is None:
                    # If we get here, it's because there was no field data.
                    # We create a field, set it to None, and then continue.
                    vars.f = FieldClass(b''.join(name_buffer))
                    del name_buffer[:]
                    vars.f.set_none()

                vars.f.finalize()
                on_field(vars.f)
                vars.f = None

            def on_end():
                if self.on_end is not None:
                    self.on_end()

            # Setup callbacks.
            callbacks = {
                'on_field_start': on_field_start,
                'on_field_name': on_field_name,
                'on_field_data': on_field_data,
                'on_field_end': on_field_end,
                'on_end': on_end,
            }

            # Instantiate parser.
            parser = QuerystringParser(
                callbacks=callbacks,
                max_size=self.config['MAX_BODY_SIZE']
            )

        elif content_type == b'multipart/form-data':
            if boundary is None:
                logger.error("No boundary given")
                raise FormParserError("No boundary given")

            header_name = []
            header_value = []
            headers = {}

            # No 'nonlocal' on Python 2 :-(
            class vars(object):
                f = None
                writer = None
                is_file = False

            def on_part_begin():
                pass

            def on_part_data(data, start, end):
                bytes_processed = vars.writer.write(data[start:end])
                # TODO: check for error here.
                return bytes_processed

            def on_part_end():
                vars.f.finalize()
                if vars.is_file:
                    on_file(vars.f)
                else:
                    on_field(vars.f)

            def on_header_field(data, start, end):
                header_name.append(data[start:end])

            def on_header_value(data, start, end):
                header_value.append(data[start:end])

            def on_header_end():
                headers[b''.join(header_name)] = b''.join(header_value)
                del header_name[:]
                del header_value[:]

            def on_headers_finished():
                # Reset the 'is file' flag.
                vars.is_file = False

                # Parse the content-disposition header.
                # TODO: handle mixed case
                content_disp = headers.get(b'Content-Disposition')
                disp, options = parse_options_header(content_disp)

                # Get the field and filename.
                field_name = options.get(b'name')
                file_name = options.get(b'filename')
                # TODO: check for errors

                # Create the proper class.
                if file_name is None:
                    vars.f = FieldClass(field_name)
                else:
                    vars.f = FileClass(file_name, field_name)
                    vars.is_file = True

                # Parse the given Content-Transfer-Encoding to determine what
                # we need to do with the incoming data.
                # TODO: check that we properly handle 8bit / 7bit encoding.
                transfer_encoding = headers.get(b'Content-Transfer-Encoding',
                                                b'7bit')

                if (transfer_encoding == b'binary' or
                        transfer_encoding == b'8bit' or
                        transfer_encoding == b'7bit'):
                    vars.writer = vars.f

                elif transfer_encoding == b'base64':
                    vars.writer = Base64Decoder(vars.f)

                elif transfer_encoding == b'quoted-printable':
                    vars.writer = QuotedPrintableDecoder(vars.f)

                else:
                    logger.warn("Unknown Content-Transfer-Encoding: %r",
                                transfer_encoding)
                    if self.config['UPLOAD_ERROR_ON_BAD_CTE']:
                        raise FormParserError(
                            'Unknown Content-Transfer-Encoding "{0}"'.format(
                                transfer_encoding
                            )
                        )
                    else:
                        # If we aren't erroring, then we just treat this as an
                        # unencoded Content-Transfer-Encoding.
                        vars.writer = vars.f

            def on_end():
                vars.writer.finalize()
                if self.on_end is not None:
                    self.on_end()

            # These are our callbacks for the parser.
            callbacks = {
                'on_part_begin': on_part_begin,
                'on_part_data': on_part_data,
                'on_part_end': on_part_end,
                'on_header_field': on_header_field,
                'on_header_value': on_header_value,
                'on_header_end': on_header_end,
                'on_headers_finished': on_headers_finished,
                'on_end': on_end,
            }

            # Instantiate a multipart parser.
            parser = MultipartParser(boundary, callbacks,
                                     max_size=self.config['MAX_BODY_SIZE'])

        else:
            logger.warn("Unknown Content-Type: %r", content_type)
            raise FormParserError("Unknown Content-Type: {0}".format(
                content_type
            ))

        self.parser = parser

    def write(self, data):
        self.bytes_received += len(data)
        # TODO: check the parser's return value for errors?
        return self.parser.write(data)

    def finalize(self):
        if self.parser is not None and hasattr(self.parser, 'finalize'):
            self.parser.finalize()

    def close(self):
        if self.parser is not None and hasattr(self.parser, 'close'):
            self.parser.close()

    def __repr__(self):
        return "%s(content_type=%r, content_length=%r, parser=%r)" % (
            self.__class__.__name__,
            self.content_type,
            self.content_length,
            self.parser,
        )
