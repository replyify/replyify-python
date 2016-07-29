import calendar
import datetime
import platform
import time
import urllib
import urlparse
# import warnings

import replyify
from replyify import exceptions, http_client, version, utils
from replyify.utils import MultipartDataGenerator


def _encode_datetime(dttime):
    if dttime.tzinfo and dttime.tzinfo.utcoffset(dttime) is not None:
        utc_timestamp = calendar.timegm(dttime.utctimetuple())
    else:
        utc_timestamp = time.mktime(dttime.timetuple())

    return int(utc_timestamp)


def _encode_nested_dict(key, data, fmt='%s[%s]'):
    d = {}
    for subkey, subvalue in data.iteritems():
        d[fmt % (key, subkey)] = subvalue
    return d


def _api_encode(data):
    for key, value in data.iteritems():
        key = utils.utf8(key)
        if value is None:
            continue
        elif hasattr(value, 'replyify_guid'):
            yield (key, value.replyify_guid)
        elif isinstance(value, list) or isinstance(value, tuple):
            for sv in value:
                if isinstance(sv, dict):
                    subdict = _encode_nested_dict(key, sv, fmt='%s[][%s]')
                    for k, v in _api_encode(subdict):
                        yield (k, v)
                else:
                    yield ('%s[]' % (key,), utils.utf8(sv))
        elif isinstance(value, dict):
            subdict = _encode_nested_dict(key, value)
            for subkey, subvalue in _api_encode(subdict):
                yield (subkey, subvalue)
        elif isinstance(value, datetime.datetime):
            yield (key, _encode_datetime(value))
        else:
            yield (key, utils.utf8(value))


def _build_api_url(url, query):
    scheme, netloc, path, base_query, fragment = urlparse.urlsplit(url)

    if base_query:
        query = '%s&%s' % (base_query, query)

    return urlparse.urlunsplit((scheme, netloc, path, query, fragment))


class ReplyifApi(object):

    def __init__(self, access_token=None, client=None, api_base=None, account=None):
        self.api_base = api_base or replyify.api_base
        self.access_token = access_token

        from replyify import verify_ssl_certs as verify

        self._client = client or replyify.default_http_client or http_client.new_default_http_client(verify_ssl_certs=verify)

    def request(self, method, url, params=None, headers=None):
        rbody, rcode, rheaders, my_access_token = self.request_raw(method.lower(), url, params, headers)
        resp = self.interpret_response(rbody, rcode, rheaders)
        return resp, my_access_token

    def handle_api_error(self, rbody, rcode, resp, rheaders):
        try:
            errors = resp.get('errors')
            if not errors:
                err = resp['error']
            else:
                err = 'Error in supplied form data'
        except (KeyError, TypeError):
            raise exceptions.APIException(
                'Invalid response object from API: %r (HTTP response code '
                'was %d)' % (rbody, rcode),
                rbody, rcode, resp)

        # Rate limits were previously coded as 400's with code 'rate_limit'
        if rcode == 429:
            raise exceptions.RateLimitException(err, rbody, rcode, resp, rheaders)
        elif rcode in [400, 404]:
            raise exceptions.InvalidRequestException(err, errors, rbody, rcode, resp, rheaders)
        elif rcode == 403:
            raise exceptions.PermissionException(err, rbody, rcode, resp, rheaders)
        elif rcode == 401:
            raise exceptions.AuthenticationException(err, rbody, rcode, resp, rheaders)
        else:
            raise exceptions.APIException(err, rbody, rcode, resp, rheaders)

    def request_raw(self, method, url, params=None, supplied_headers=None):
        '''
        Mechanism for issuing an API call
        '''
        from replyify import api_version

        if self.access_token:
            my_access_token = self.access_token
        else:
            from replyify import access_token
            my_access_token = access_token

        if my_access_token is None:
            raise exceptions.AuthenticationException(
                'No ACCESS TOKEN provided. (HINT: set your ACCESS TOKEN using '
                '`replyify.access_token = <ACCESS-TOKEN>`).')

        method = method.lower()
        abs_url = '%s%s' % (self.api_base, url)
        encoded_params = urllib.urlencode(list(_api_encode(params or {})))

        if method == 'get' or method == 'delete':
            if params:
                abs_url = _build_api_url(abs_url, encoded_params)
            post_data = None
        elif method in ('post', 'put', 'patch', 'delete'):
            if supplied_headers is not None and supplied_headers.get('Content-Type') == 'multipart/form-data':
                generator = MultipartDataGenerator()
                generator.add_params(params or {})
                post_data = generator.get_post_data()
                supplied_headers['Content-Type'] = 'multipart/form-data; boundary=%s' % (generator.boundary,)
            else:
                post_data = encoded_params
        else:
            raise exceptions.APIConnectionException(
                'Unrecognized HTTP method %r.  This may indicate a bug in the '
                'Replyify bindings.  Please contact support@replyify.com for '
                'assistance.' % (method,))

        ua = {
            'bindings_version': version.VERSION,
            'lang': 'python',
            'publisher': 'replyify',
            'httplib': self._client.name,
        }
        for attr, func in [['lang_version', platform.python_version],
                           ['platform', platform.platform],
                           ['uname', lambda: ' '.join(platform.uname())]]:
            try:
                val = func()
            except Exception as e:
                val = '!! %s' % (e,)
            ua[attr] = val

        headers = {
            'X-Replyify-Client-User-Agent': utils.json.dumps(ua),
            'User-Agent': 'Replyify/v1 PythonBindings/%s' % (version.VERSION,),
            'Authorization': 'Bearer %s' % (my_access_token,)
        }

        if method == 'post':
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        # elif method in ('patch', 'put', 'delete'):
        #     headers['Content-Type'] = 'application/json'

        if api_version is not None:
            headers['Replyify-Version'] = api_version

        if supplied_headers is not None:
            for key, value in supplied_headers.items():
                headers[key] = value

        rbody, rcode, rheaders = self._client.request(method, abs_url, headers, post_data)

        utils.logger.info('%s %s %d', method.upper(), abs_url, rcode)
        utils.logger.debug(
            'API request to %s returned (response code, response body) of '
            '(%d, %r)',
            abs_url, rcode, rbody)
        return rbody, rcode, rheaders, my_access_token

    def interpret_response(self, rbody, rcode, rheaders):
        if rcode == 204:
            return
        try:
            if hasattr(rbody, 'decode'):
                rbody = rbody.decode('utf-8')
            resp = utils.json.loads(rbody)
        except Exception:
            raise exceptions.APIException(
                'Invalid response body from API: %s '
                '(HTTP response code was %d)' % (rbody[:500], rcode),
                rbody, rcode, rheaders)
        if not (200 <= rcode < 300):
            self.handle_api_error(rbody, rcode, resp, rheaders)
        return resp
