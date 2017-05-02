import urllib
import sys

from replyify import api, exceptions, utils, upload_api_base


def populate_headers(idempotency_key):
    if idempotency_key is not None:
        return {'Idempotency-Key': idempotency_key}
    return None


def _compute_diff(current, previous):
    if isinstance(current, dict):
        previous = previous or {}
        diff = current.copy()
        for key in set(previous.keys()) - set(diff.keys()):
            diff[key] = ''
        return diff
    return current if current is not None else ''


def _serialize_list(array, previous):
    array = array or []
    previous = previous or []
    params = {}

    for i, v in enumerate(array):
        previous_item = previous[i] if len(previous) > i else None
        if hasattr(v, 'serialize'):
            params[str(i)] = v.serialize(previous_item)
        else:
            params[str(i)] = _compute_diff(v, previous_item)

    return params


class ReplyifyObject(dict):
    def __init__(self, guid=None, access_token=None, **params):
        super(ReplyifyObject, self).__init__()

        self._unsaved_values = set()
        self._transient_values = set()

        self._retrieve_params = params
        self._previous = None

        object.__setattr__(self, 'access_token', access_token)

        if guid:
            self['guid'] = guid

    def update(self, update_dict):
        for k in update_dict:
            self._unsaved_values.add(k)

        return super(ReplyifyObject, self).update(update_dict)

    def __setattr__(self, k, v):
        if k[0] == '_' or k in self.__dict__:
            return super(ReplyifyObject, self).__setattr__(k, v)
        else:
            self[k] = v

    def __getattr__(self, k):
        if k[0] == '_':
            raise AttributeError(k)

        try:
            return self[k]
        except KeyError as err:
            raise AttributeError(*err.args)

    def __delattr__(self, k):
        if k[0] == '_' or k in self.__dict__:
            return super(ReplyifyObject, self).__delattr__(k)
        else:
            del self[k]

    def __setitem__(self, k, v):
        if v == '':
            raise ValueError(
                'You cannot set %s to an empty string. '
                'We interpret empty strings as None in requests.'
                'You may set %s.%s = None to delete the property' % (
                    k, str(self), k))

        super(ReplyifyObject, self).__setitem__(k, v)

        # Allows for unpickling in Python 3.x
        if not hasattr(self, '_unsaved_values'):
            self._unsaved_values = set()

        self._unsaved_values.add(k)

    def __getitem__(self, k):
        try:
            return super(ReplyifyObject, self).__getitem__(k)
        except KeyError as err:
            if k in self._transient_values:
                raise KeyError(
                    '%r.  HINT: The %r attribute was set in the past.'
                    'It was then wiped when refreshing the object with '
                    'the result returned by Replyify API, probably as a '
                    'result of a save().  The attributes currently '
                    'available on this object are: %s' %
                    (k, k, ', '.join(self.keys())))
            else:
                raise err

    def __delitem__(self, k):
        super(ReplyifyObject, self).__delitem__(k)

        # Allows for unpickling in Python 3.x
        if hasattr(self, '_unsaved_values'):
            self._unsaved_values.remove(k)

    @classmethod
    def construct_from(cls, values, access_token):
        instance = cls(values.get('guid'), access_token=access_token)
        instance.refresh_from(values, access_token=access_token)
        return instance

    def refresh_from(self, values, access_token=None, partial=False):
        self.access_token = access_token or getattr(values, 'access_token', None)

        # Wipe old state before setting new.  This is useful for e.g.
        # updating a customer, where there is no persistent card
        # parameter.  Mark those values which don't persist as transient
        if partial:
            self._unsaved_values = (self._unsaved_values - set(values))
        else:
            removed = set(self.keys()) - set(values)
            self._transient_values = self._transient_values | removed
            self._unsaved_values = set()
            self.clear()

        self._transient_values = self._transient_values - set(values)

        for k, v in values.iteritems():
            super(ReplyifyObject, self).__setitem__(k, convert_to_replyify_object(v, access_token))

        self._previous = values

    @classmethod
    def api_base(cls):
        return None

    def request(self, method, url, params=None, headers=None):
        if params is None:
            params = self._retrieve_params
        requestor = api.ReplyifApi(self.access_token, api_base=self.api_base())
        response, access_token = requestor.request(method, url, params, headers)

        return convert_to_replyify_object(response, access_token)

    def __repr__(self):
        ident_parts = [type(self).__name__]

        if isinstance(self.get('object'), basestring):
            ident_parts.append(self.get('object'))

        if isinstance(self.get('id'), basestring):
            ident_parts.append('id=%s' % (self.get('id'),))

        unicode_repr = '<%s at %s> JSON: %s' % (
            ' '.join(ident_parts), hex(id(self)), str(self))

        if sys.version_info[0] < 3:
            return unicode_repr.encode('utf-8')
        else:
            return unicode_repr

    def __str__(self):
        return utils.json.dumps(self, sort_keys=True, indent=2)

    def __unicode__(self):
        return self.__str__()

    @property
    def replyify_guid(self):
        return self.guid

    def serialize(self, previous):
        params = {}
        unsaved_keys = self._unsaved_values or set()
        previous = previous or self._previous or {}

        for k, v in self.items():
            if k == 'guid' or (isinstance(k, str) and k.startswith('_')):
                continue
            elif isinstance(v, APIResource):
                continue
            elif hasattr(v, 'serialize'):
                params[k] = v.serialize(previous.get(k, None))
            elif k in unsaved_keys:
                params[k] = _compute_diff(v, previous.get(k, None))
            elif k == 'additional_owners' and v is not None:
                params[k] = _serialize_list(v, previous.get(k, None))

        return params


class APIResource(ReplyifyObject):

    @classmethod
    def retrieve(cls, guid, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    def refresh(self):
        self.refresh_from(self.request('get', self.instance_url()))
        return self

    @classmethod
    def class_name(cls):
        if cls == APIResource:
            raise NotImplementedError(
                'APIResource is an abstract class.  You should perform '
                'actions on its subclasses (e.g. Charge, Customer)')
        return str(urllib.quote_plus(cls.__name__.lower()))

    @classmethod
    def class_url(cls):
        cls_name = cls.class_name()
        return '/%s/v1' % (cls_name,)

    def instance_url(self):
        guid = self.get('guid')
        if not guid:
            raise exceptions.InvalidRequestException(
                'Could not determine which URL to request: %s instance '
                'has invalid GUID: %r' % (type(self).__name__, guid), 'guid')
        guid = utils.utf8(guid)
        base = self.class_url()
        extn = urllib.quote_plus(guid)
        return '%s/%s' % (base, extn)

    @classmethod
    def _build_instance_url(cls, guid):
        base = cls.class_url()
        if not guid:
            return base
        guid = utils.utf8(guid)
        extn = urllib.quote_plus(guid)
        return '%s/%s' % (base, extn)


class ListObject(ReplyifyObject):

    def list(self, **params):
        return self.request('get', self['url'], params)

    def auto_paging_iter(self):
        page = self
        params = dict(self._retrieve_params)

        while True:
            item_guid = None
            for item in page:
                item_guid = item.get('guid', None)
                yield item

            if not getattr(page, 'has_more', False) or item_guid is None:
                return

            params['starting_after'] = item_guid
            page = self.list(**params)

    def create(self, idempotency_key=None, **params):
        headers = populate_headers(idempotency_key)
        return self.request('post', self['url'], params, headers)

    def retrieve(self, guid, **params):
        base = self.get('url')
        guid = utils.utf8(guid)
        extn = urllib.quote_plus(guid)
        url = '%s/%s' % (base, extn)

        return self.request('get', url, params)

    def __iter__(self):
        return getattr(self, 'data', []).__iter__()


class SingletonAPIResource(APIResource):

    @classmethod
    def retrieve(cls, **params):
        return super(SingletonAPIResource, cls).retrieve(None, **params)

    @classmethod
    def class_url(cls):
        cls_name = cls.class_name()
        return '/%s/v1' % (cls_name,)

    def instance_url(self):
        return self.class_url()


# Classes of API operations


class ListableAPIResource(APIResource):

    @classmethod
    def auto_paging_iter(self, *args, **params):
        return self.list(*args, **params).auto_paging_iter()

    @classmethod
    def list(cls, access_token=None, idempotency_key=None, **params):
        requestor = api.ReplyifApi(access_token, api_base=cls.api_base())
        url = cls.class_url()
        response, access_token = requestor.request('get', url, params)
        return convert_to_replyify_object(response, access_token)


class CreateableAPIResource(APIResource):

    @classmethod
    def create(cls, access_token=None, idempotency_key=None, **params):
        requestor = api.ReplyifApi(access_token)
        url = cls.class_url()
        headers = populate_headers(idempotency_key)
        response, access_token = requestor.request('post', url, params, headers)
        return convert_to_replyify_object(response, access_token)


class UpdateableAPIResource(APIResource):

    @classmethod
    def _modify(cls, url, access_token=None, idempotency_key=None, **params):
        requestor = api.ReplyifApi(access_token)
        headers = populate_headers(idempotency_key)
        response, access_token = requestor.request('patch', url, params, headers)
        return convert_to_replyify_object(response, access_token)

    @classmethod
    def modify(cls, guid, **params):
        url = '%s/%s' % (cls.class_url(), urllib.quote_plus(utils.utf8(guid)))
        return cls._modify(url, **params)

    def save(self, idempotency_key=None):
        updated_params = self.serialize(None)
        headers = populate_headers(idempotency_key)

        if updated_params:
            self.refresh_from(self.request('post', self.instance_url(), updated_params, headers))
        else:
            utils.logger.debug('Trying to save already saved object %r', self)
        return self


class DeletableAPIResource(APIResource):

    def delete(self, **params):
        self.refresh_from(self.request('delete', self.instance_url(), params))
        return self


# API objects
class Account(CreateableAPIResource, UpdateableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)

    @classmethod
    def _build_instance_url(cls, guid):
        if not guid:
            return '/account/v1'
        guid = utils.utf8(guid)
        base = cls.class_url()
        extn = urllib.quote_plus(guid)
        return '%s/%s' % (base, extn)

    def instance_url(self):
        return self._build_instance_url(self.get('guid'))


class Campaign(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class CampaignContact(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def class_url(cls):
        return '/campaign-contact/v1'

    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Contact(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class ContactField(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def class_url(cls):
        return '/contact-field/v1'

    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Note(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Reply(UpdateableAPIResource, ListableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Tag(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Template(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Timeline(CreateableAPIResource, ListableAPIResource):
    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance


class TimelineItem(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):
    @classmethod
    def class_url(cls):
        return '/timeline-item/v1'

    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class TimelineJob(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource):
    @classmethod
    def class_url(cls):
        return '/timeline-job/v1'

    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Signature(CreateableAPIResource, UpdateableAPIResource, ListableAPIResource, DeletableAPIResource):

    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance

    @classmethod
    def modify(cls, guid=None, **params):
        return cls._modify(cls._build_instance_url(guid), **params)


class Upload(CreateableAPIResource, ListableAPIResource):

    @classmethod
    def retrieve(cls, guid=None, access_token=None, **params):
        instance = cls(guid, access_token, **params)
        instance.refresh()
        return instance


def convert_to_replyify_object(resp, access_token):
    types = {
        'account': Account,
        'campaign': Campaign,
        'campaigncontact': CampaignContact,
        'contact': Contact,
        'contactfield': ContactField,
        'note': Note,
        'reply': Reply,
        'signature': Signature,
        'tag': Tag,
        'template': Template,
        'timeline': Timeline,
        'timelineitem': TimelineItem,
        'timelinejob': TimelineJob,
        'upload': Upload,
        # 'link': Link,
        # 'link_click': LinkClick,
    }

    if isinstance(resp, list):
        return [convert_to_replyify_object(i, access_token) for i in resp]
    elif isinstance(resp, dict) and not isinstance(resp, ReplyifyObject):
        resp = resp.copy()
        klass_name = resp.get('object')
        if isinstance(klass_name, basestring):
            klass = types.get(klass_name, ReplyifyObject)
        else:
            klass = ReplyifyObject
        return klass.construct_from(resp, access_token)
    else:
        return resp
