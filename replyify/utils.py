import logging
import sys
import os
import random
import io

logger = logging.getLogger('replyify')

__all__ = ['StringIO', 'parse_qsl', 'json', 'utf8']

try:
    # When cStringIO is available
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    from urlparse import parse_qsl
except ImportError:
    # Python < 2.6
    from cgi import parse_qsl

try:
    import json
except ImportError:
    json = None

if not (json and hasattr(json, 'loads')):
    try:
        import simplejson as json
    except ImportError:
        if not json:
            raise ImportError(
                'Replyify requires a JSON library, such as simplejson. '
                'HINT: Try installing the '
                'python simplejson library via `pip install simplejson` or '
                '`easy_install simplejson`'
                'with questions.')
        else:
            raise ImportError(
                'Replyify requires a JSON library with the same interface as '
                'the Python 2.6 `json` library.  You appear to have a `json` '
                'library with a different interface.  Please install '
                'the simplejson library.  HINT: Try installing the '
                'python simplejson library via `pip install simplejson` '
                'or `easy_install simplejson`')


def convert_to_boolean(s):
    if isinstance(s, bool):
        return s
    if isinstance(s, basestring):
        if s in ('True', '1', 'true', 'T', 't'):
            return True
    if isinstance(s, int):
        if s > 0:
            return True
    return False


def utf8(value):
    if isinstance(value, unicode) and sys.version_info < (3, 0):
        return value.encode('utf-8')
    else:
        return value


def is_appengine_dev():
    return ('APPENGINE_RUNTIME' in os.environ and
            'Dev' in os.environ.get('SERVER_SOFTWARE', ''))


class MultipartDataGenerator(object):
    def __init__(self, chunk_size=1028):
        self.data = io.BytesIO()
        self.line_break = "\r\n"
        self.boundary = self._initialize_boundary()
        self.chunk_size = chunk_size

    def add_params(self, params):
        for key, value in params.iteritems():
            if value is None:
                continue

            self._write(self.param_header())
            self._write(self.line_break)
            if hasattr(value, 'read'):
                self._write("Content-Disposition: form-data; name=\"")
                self._write(key)
                self._write("\"; filename=\"")
                self._write(value.name)
                self._write("\"")
                self._write(self.line_break)
                self._write("Content-Type: application/octet-stream")
                self._write(self.line_break)
                self._write(self.line_break)

                self._write_file(value)
            else:
                self._write("Content-Disposition: form-data; name=\"")
                self._write(key)
                self._write("\"")
                self._write(self.line_break)
                self._write(self.line_break)
                self._write(value)

            self._write(self.line_break)

    def param_header(self):
        return "--%s" % self.boundary

    def get_post_data(self):
        self._write("--%s--" % (self.boundary,))
        self._write(self.line_break)
        return self.data.getvalue()

    def _write(self, value):
        if sys.version_info < (3,):
            binary_type = str
            text_type = unicode
        else:
            binary_type = bytes
            text_type = str

        if isinstance(value, binary_type):
            array = bytearray(value)
        elif isinstance(value, text_type):
            array = bytearray(value, encoding='utf-8')
        else:
            raise TypeError("unexpected type: {value_type}"
                            .format(value_type=type(value)))

        self.data.write(array)

    def _write_file(self, f):
        while True:
            file_contents = f.read(self.chunk_size)
            if not file_contents:
                break
            self._write(file_contents)

    def _initialize_boundary(self):
        return random.randint(0, 2**63)
