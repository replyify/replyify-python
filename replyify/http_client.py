import os
import sys
import textwrap
import warnings
import email

from replyify import error, util


# - Requests is the preferred HTTP library
# - Google App Engine has urlfetch
# - Use Pycurl if it's there (at least it verifies SSL certs)
# - Fall back to urllib2 with a warning if needed
try:
    import urllib2
except ImportError:
    pass

try:
    import pycurl
except ImportError:
    pycurl = None

try:
    import requests
except ImportError:
    requests = None
else:
    try:
        # Require version 0.8.8, but don't want to depend on distutils
        version = requests.__version__
        major, minor, patch = [int(i) for i in version.split('.')]
    except Exception:
        # Probably some new-fangled version, so it should support verify
        pass
    else:
        if (major, minor, patch) < (0, 8, 8):
            sys.stderr.write(
                'Warning: the Replyify library requires that your Python '
                '"requests" library be newer than version 0.8.8, but your '
                '"requests" library is version %s. Replyify will fall back to '
                'an alternate HTTP library so everything should work. We '
                'recommend upgrading your "requests" library. (HINT: running '
                '"pip install -U requests" should upgrade your requests '
                'library to the latest version.)' % (version,))
            requests = None

try:
    from google.appengine.api import urlfetch
except ImportError:
    urlfetch = None


def new_default_http_client(*args, **kwargs):
    if urlfetch:
        impl = UrlFetchClient
    elif requests:
        impl = RequestsClient
    elif pycurl:
        impl = PycurlClient
    else:
        impl = Urllib2Client
        warnings.warn(
            "Warning: the Replyify library is falling back to urllib2/urllib "
            "because neither requests nor pycurl are installed. "
            "urllib2's SSL implementation doesn't verify server "
            "certificates. For improved security, we suggest installing "
            "requests.")

    return impl(*args, **kwargs)


class HTTPClient(object):

    def __init__(self, verify_ssl_certs=True):
        self._verify_ssl_certs = verify_ssl_certs

    def request(self, method, url, headers, post_data=None):
        raise NotImplementedError(
            'HTTPClient subclasses must implement `request`')


class RequestsClient(HTTPClient):
    name = 'requests'

    def request(self, method, url, headers, post_data=None):
        kwargs = {}

        if self._verify_ssl_certs:
            kwargs['verify'] = os.path.join(
                os.path.dirname(__file__), 'data/ca-certificates.crt')
        else:
            kwargs['verify'] = False

        try:
            try:
                result = requests.request(method,
                                          url,
                                          headers=headers,
                                          data=post_data,
                                          timeout=80,
                                          **kwargs)
            except TypeError as e:
                raise TypeError(
                    'Warning: It looks like your installed version of the '
                    '"requests" library is not compatible with Replyify\'s '
                    'usage thereof. (HINT: The most likely cause is that '
                    'your "requests" library is out of date. You can fix '
                    'that by running "pip install -U requests".) The '
                    'underlying error was: %s' % (e,))

            # This causes the content to actually be read, which could cause
            # e.g. a socket timeout. TODO: The other fetch methods probably
            # are susceptible to the same and should be updated.
            content = result.content
            status_code = result.status_code
        except Exception as e:
            # Would catch just requests.exceptions.RequestException, but can
            # also raise ValueError, RuntimeError, etc.
            self._handle_request_error(e)
        return content, status_code, result.headers

    def _handle_request_error(self, e):
        if isinstance(e, requests.exceptions.RequestException):
            msg = ("Unexpected error communicating with Replyify.  "
                   "If this problem persists, let us know at "
                   "support@replyify.com.")
            err = "%s: %s" % (type(e).__name__, str(e))
        else:
            msg = ("Unexpected error communicating with Replyify. "
                   "It looks like there's probably a configuration "
                   "issue locally.  If this problem persists, let us "
                   "know at support@replyify.com.")
            err = "A %s was raised" % (type(e).__name__,)
            if str(e):
                err += " with error message %s" % (str(e),)
            else:
                err += " with no error message"
        msg = textwrap.fill(msg) + "\n\n(Network error: %s)" % (err,)
        raise error.APIConnectionError(msg)


class UrlFetchClient(HTTPClient):
    name = 'urlfetch'

    def __init__(self, verify_ssl_certs=True, deadline=55):
        self._verify_ssl_certs = verify_ssl_certs
        # GAE requests time out after 60 seconds, so make sure to default
        # to 55 seconds to allow for a slow Replyify
        self._deadline = deadline

    def request(self, method, url, headers, post_data=None):
        try:
            result = urlfetch.fetch(
                url=url,
                method=method,
                headers=headers,
                # Google App Engine doesn't let us specify our own cert bundle.
                # However, that's ok because the CA bundle they use recognizes
                # api.replyify.com.
                validate_certificate=self._verify_ssl_certs,
                deadline=self._deadline,
                payload=post_data
            )
        except urlfetch.Error as e:
            self._handle_request_error(e, url)

        return result.content, result.status_code, result.headers

    def _handle_request_error(self, e, url):
        if isinstance(e, urlfetch.InvalidURLError):
            msg = ("The Replyify library attempted to fetch an "
                   "invalid URL (%r). This is likely due to a bug "
                   "in the Replyify Python bindings. Please let us know "
                   "at support@replyify.com." % (url,))
        elif isinstance(e, urlfetch.DownloadError):
            msg = "There was a problem retrieving data from Replyify."
        elif isinstance(e, urlfetch.ResponseTooLargeError):
            msg = ("There was a problem receiving all of your data from "
                   "Replyify.  This is likely due to a bug in Replyify. "
                   "Please let us know at support@replyify.com.")
        else:
            msg = ("Unexpected error communicating with Replyify. If this "
                   "problem persists, let us know at support@replyify.com.")

        msg = textwrap.fill(msg) + "\n\n(Network error: " + str(e) + ")"
        raise error.APIConnectionError(msg)


class PycurlClient(HTTPClient):
    name = 'pycurl'

    def parse_headers(self, data):
        if '\r\n' not in data:
            return {}
        raw_headers = data.split('\r\n', 1)[1]
        headers = email.message_from_string(raw_headers)
        return dict((k.lower(), v) for k, v in dict(headers).iteritems())

    def request(self, method, url, headers, post_data=None):
        s = util.StringIO.StringIO()
        rheaders = util.StringIO.StringIO()
        curl = pycurl.Curl()

        if method == 'get':
            curl.setopt(pycurl.HTTPGET, 1)
        elif method == 'post':
            curl.setopt(pycurl.POST, 1)
            curl.setopt(pycurl.POSTFIELDS, post_data)
        else:
            curl.setopt(pycurl.CUSTOMREQUEST, method.upper())

        # pycurl doesn't like unicode URLs
        curl.setopt(pycurl.URL, util.utf8(url))

        curl.setopt(pycurl.WRITEFUNCTION, s.write)
        curl.setopt(pycurl.HEADERFUNCTION, rheaders.write)
        curl.setopt(pycurl.NOSIGNAL, 1)
        curl.setopt(pycurl.CONNECTTIMEOUT, 30)
        curl.setopt(pycurl.TIMEOUT, 80)
        curl.setopt(pycurl.HTTPHEADER, ['%s: %s' % (k, v)
                    for k, v in headers.iteritems()])
        if self._verify_ssl_certs:
            curl.setopt(pycurl.CAINFO, os.path.join(
                os.path.dirname(__file__), 'data/ca-certificates.crt'))
        else:
            curl.setopt(pycurl.SSL_VERIFYHOST, False)

        try:
            curl.perform()
        except pycurl.error as e:
            self._handle_request_error(e)
        rbody = s.getvalue()
        rcode = curl.getinfo(pycurl.RESPONSE_CODE)

        return rbody, rcode, self.parse_headers(rheaders.getvalue())

    def _handle_request_error(self, e):
        if e[0] in [pycurl.E_COULDNT_CONNECT,
                    pycurl.E_COULDNT_RESOLVE_HOST,
                    pycurl.E_OPERATION_TIMEOUTED]:
            msg = ("Could not connect to Replyify.  Please check your "
                   "internet connection and try again.  If this problem "
                   "persists, you should check Replyify's service status at "
                   "https://twitter.com/replyifystatus, or let us know at "
                   "support@replyify.com.")
        elif (e[0] in [pycurl.E_SSL_CACERT,
                       pycurl.E_SSL_PEER_CERTIFICATE]):
            msg = ("Could not verify Replyify's SSL certificate.  Please make "
                   "sure that your network is not intercepting certificates.  "
                   "If this problem persists, let us know at "
                   "support@replyify.com.")
        else:
            msg = ("Unexpected error communicating with Replyify. If this "
                   "problem persists, let us know at support@replyify.com.")

        msg = textwrap.fill(msg) + "\n\n(Network error: " + e[1] + ")"
        raise error.APIConnectionError(msg)


class Urllib2Client(HTTPClient):
    if sys.version_info >= (3, 0):
        name = 'urllib.request'
    else:
        name = 'urllib2'

    def request(self, method, url, headers, post_data=None):
        if sys.version_info >= (3, 0) and isinstance(post_data, basestring):
            post_data = post_data.encode('utf-8')

        req = urllib2.Request(url, post_data, headers)

        if method not in ('get', 'post'):
            req.get_method = lambda: method.upper()

        try:
            response = urllib2.urlopen(req)
            rbody = response.read()
            rcode = response.code
            headers = dict(response.info())
        except urllib2.HTTPError as e:
            rcode = e.code
            rbody = e.read()
            headers = dict(e.info())
        except (urllib2.URLError, ValueError) as e:
            self._handle_request_error(e)
        lh = dict((k.lower(), v) for k, v in dict(headers).iteritems())
        return rbody, rcode, lh

    def _handle_request_error(self, e):
        msg = ("Unexpected error communicating with Replyify. "
               "If this problem persists, let us know at support@replyify.com.")
        msg = textwrap.fill(msg) + "\n\n(Network error: " + str(e) + ")"
        raise error.APIConnectionError(msg)
