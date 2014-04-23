"""
Library for helping you write nice clients for RESTful APIs.
"""
from __future__ import division
import abc
import logging
import math
import pprint
import re
import threading
import httplib
import urllib
import urlparse

import requests

__version__ = '0.23'

__all__ = [
    'Config',
    'Error',
    'Redirection',
    'Client',
    'NoResultFound',
    'MultipleResultsFound',
    'URIGen',
    'ResourceRegistry',
    'Resource',
]

logger = logging.getLogger(__name__)


# utilities

# http://stackoverflow.com/a/5191224/1339571
class _ClassPropertyDescriptor(object):

    def __init__(self, fget, fset=None):
        self.fget = fget
        self.fset = fset

    def __get__(self, obj, klass=None):
        if klass is None:
            klass = type(obj)
        return self.fget.__get__(obj, klass)()

    def __set__(self, obj, value):
        if not self.fset:
            raise AttributeError("can't set attribute")
        type_ = type(obj)
        return self.fset.__get__(obj, type_)(value)

    def setter(self, func):
        if not isinstance(func, (classmethod, staticmethod)):
            func = classmethod(func)
        self.fset = func
        return self


# http://stackoverflow.com/a/5191224/1339571
def classproperty(func):
    if not isinstance(func, (classmethod, staticmethod)):
        func = classmethod(func)
    return _ClassPropertyDescriptor(func)


# client

class Config(object):
    """
    Contains all configuration settings. These are attached to `Client` as
    `config`. You typically provide a global default instance and a `configure`
    function to help users configure your client::

        default_config = wac.Config(None)


        def configure(root_url, **kwargs):
            default = kwargs.pop('default', True)
            kwargs['client_agent'] = 'example-client/' + __version__
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers']['Accept-Type'] = 'application/json'
            if default:
                default_config.reset(root_url, **kwargs)
            else:
                Client.config = wac.Config(root_url, **kwargs)

    `root_url`
        The scheme://authority to use when constructing urls (e.g.
        https://api.example.com). This is required.

    `client_agent`
        The name/version of the client (e.g. 'example-client/1.2'). Defaults
        to None.

    `user_agent`
        The user agent for the person using your client ('consumer/3.3'). It
        is up to users of your client to configure this. Defaults to None.

    `auth`
        Credentials as a user-name, password tuple (e.g. ('me', 'p@$$w0rd')) to
        use for authentication. Defaults to None (i.e. no authentication).

    `headers`
        Dictionary of headers to include in each request. Defaults to {}.

    `echo`
        Flag indicating whether request and response information should be
        echoed to stdout. This can be used for debugging. Defaults to False.

    `allow_redirects`
        Flag indicating whether client should follow server redirects (e.g.
        Location header for a 301). Defaults to False.

    `error_cls`
        Callable used to convert ``requests.HTTPError`` exceptions with the
        following signature:

            def convert_error(ex)
                ...

        where ``ex`` is an instance of ``requests.HTTPError``.

    `before_request`
        A list of callables to invoke each time before a request is made with
        the following signature:

            def before_request(method, url, kwargs)
                ...

        Where `method` is the HTTP method verb as a string, `url` is the path
        to the resource targeted by the request and kwargs are all other
        parameters to a request (e.g. headers). Not that you can modify
        `kwargs` (e.g. injecting per-request headers).

    `after_request`
        A list of callables to invoke each time after a request is made with
        the following signature:

            def after_request(response)
                    ...

        Where `response` is the requests.Response object returned by the
         Note that `after_request` callables are always called if we have a
        `response` object. So e.g. if the server returned a 503 they will still
        be called. On the other hand if the requests fails for connection
        reasons (e.g. timeout) `after_request` callables are not called since
        we don't have a response.

    `keep_alive`
        Deprecated, keep_alive is set by default in urllib3

    `timeout`
        Connection timeout in seconds. Defaults to None, which means no
        timeout.
    """

    def __init__(self,
                 root_url,
                 client_agent=None,
                 user_agent=None,
                 auth=None,
                 headers=None,
                 echo=False,
                 allow_redirects=False,
                 error_cls=None,
                 keep_alive=False,
                 timeout=None,
                 ):
        self.reset(
            root_url,
            client_agent=client_agent,
            user_agent=user_agent,
            auth=auth,
            headers=headers,
            echo=echo,
            allow_redirects=allow_redirects,
            error_cls=error_cls,
            keep_alive=keep_alive,
            timeout=timeout,
            )

    def reset(self,
              root_url,
              client_agent=None,
              user_agent=None,
              auth=None,
              headers=None,
              echo=False,
              allow_redirects=False,
              error_cls=None,
              keep_alive=False,
              timeout=None,
              ):
        headers = headers or {}
        self.root_url = root_url.rstrip('/') if root_url else None
        user_agent = ' '.join(p for p in [client_agent, user_agent] if p)
        if user_agent:
            headers['User-Agent'] = user_agent
        self.auth = auth
        self.headers = headers
        self.allow_redirects = allow_redirects
        self.error_cls = error_cls or Error
        self.before_request = []
        self.after_request = []
        self.keep_alive = keep_alive
        self.timeout = timeout
        if echo:
            self.before_request.append(Config._echo_request)
            self.after_request.append(Config._echo_response)

    @staticmethod
    def _echo_request(method, url, **kwargs):
        pprint.pprint(kwargs)

    @staticmethod
    def _echo_response(response):
        pprint.pprint(response.content)

    def copy(self):
        c = Config(self.root_url)
        c.auth = self.auth
        c.headers = self.headers.copy()
        c.allow_redirects = self.allow_redirects
        c.error_cls = self.error_cls
        c.before_request = self.before_request[:]
        c.after_request = self.after_request[:]
        c.keep_alive = self.keep_alive
        c.timeout = self.timeout
        return c


class _ObjectifyMixin(object):

    @classmethod
    def _load(cls, resource_cls, value):
        if isinstance(value, dict) and '_type' in value:
            _type = value['_type']
            try:
                _type_cls = resource_cls.registry.match(_type)
            except LookupError:
                logger.warning(
                    "Unable to determine class for '%s'. Defaulting to "
                    "dictionary", _type)
            else:
                if (issubclass(cls, Resource) and
                    issubclass(_type_cls, Page)):
                    page = _type_cls(resource_cls, **value)
                    value = resource_cls.collection_cls(
                        resource_cls,
                        page.uri,
                        page)
                elif issubclass(_type_cls, Resource):
                    value = _type_cls(**value)
                else:
                    value = _type_cls(resource_cls, **value)
        if isinstance(value, dict):
            value = dict(
                (k, cls._load(resource_cls, v))
                for k, v in value.iteritems()
            )
        elif isinstance(value, (list, tuple)):
            value = [cls._load(resource_cls, v) for v in value]
        return value

    def _lazy_load(self, resource_cls, property_cls, uri_key, property_key):
        cls = self.__class__

        def _getter(self):
            cached_key = '_' + property_key
            if hasattr(self, cached_key):
                return getattr(self, cached_key)
            uri = getattr(self, uri_key)
            if uri is None:
                value = None
            else:
                if issubclass(property_cls, resource_cls.page_cls):
                    value = resource_cls.collection_cls(resource_cls, uri)
                else:
                    resp = resource_cls.client.get(uri)
                    value = property_cls(**resp.data)
            setattr(self, cached_key, value)
            return value

        def _setter(self, value):
            cached_key = '_' + property_key
            setattr(self, cached_key, value)

        if not hasattr(cls, property_key):
            setattr(cls, property_key, property(_getter,  _setter))

    def _objectify(self, resource_cls, **fields):
        cls = type(self)
        if cls.type and '_type' in fields and fields['_type'] != cls.type:
            raise ValueError('{0} type "{1}" does not match "{2}"'
                             .format(cls.__name__, cls.type, fields['_type'])
            )
        for key, value in fields.iteritems():
            if '_uris' in fields and key in fields['_uris']:
                _uri = fields['_uris'][key]
                try:
                    property_cls = resource_cls.registry.match(_uri['_type'])
                except LookupError:
                    logger.warning(
                        "Unable to determine resource for '%s' with type "
                        "'%s'. Not attaching lazy load property.",
                        key, _uri['_type'])
                else:
                    self._lazy_load(
                        resource_cls, property_cls, key, _uri['key']
                    )
            elif not key.startswith('_'):
                value = cls._load(resource_cls, value)
            setattr(self, key, value)

    def __repr__(self):
        attrs = ', '.join([
            '{0}={1}'.format(k, repr(v))
            for k, v in self.__dict__.iteritems()
        ])
        return '{0}({1})'.format(self.__class__.__name__, attrs)


class Error(requests.HTTPError):
    """
    Represents HTTP errors detected by `Client` as specialization of
    `requests.HTTPError`.

    `message`
        String message formatted by `format_message`. For different formatting
         derived from `Error`, change `format_message` and pass that as the
         `error_cls` when configuring your `Client`.
    `status_code`
        The HTTP status code associated with the response. This will always be
        present.

    If the response has a payload that deserializes to  a dict then each key
    in that dict is attached as an attribute to the exception with the
    corresponding value.
    """
    def __init__(self, requests_ex):
        message = self.format_message(requests_ex)
        super(Error, self).__init__(message)
        self.status_code = requests_ex.response.status_code
        data = getattr(requests_ex.response, 'data', {})
        for k, v in data.iteritems():
            setattr(self, k, v)

    @classmethod
    def format_message(cls, requests_ex):
        data = getattr(requests_ex.response, 'data', {})
        status = httplib.responses[requests_ex.response.status_code]
        status = data.pop('status', status)
        status_code = data.pop('status_code', requests_ex.response.status_code)
        desc = data.pop('description', None)
        message = ': '.join(str(v) for v in [status, status_code, desc] if v)
        return message

    def __repr__(self):
        attrs = ', '.join([
            '{0}={1}'.format(k, repr(v))
            for k, v in self.__dict__.iteritems()
        ])
        return '{0}({1})'.format(self.__class__.__name__, attrs)


class Redirection(requests.HTTPError):

    def __init__(self, requests_ex):
        message = '%s' % requests_ex
        response = requests_ex.response
        super(Redirection, self).__init__(message, response=response)


class Client(threading.local, object):
    """
    Wrapper for all HTTP communication, which is done using requests.

    `config`
        The default `Configuration` instance to use. See `Configuration` for
        available configuration settings.
    `error_cls`
        The exception class to use when HTTP errors (i.e. != 2xx) are detected.
        Defaults to `Error`.
    `_configs`
        A stack of `Configuration` instances to be restored. This is useful
        when you want to do an isolated tweak to `Client` configuration for
        a set of calls::

            with Resource.client:
                Resource.client.headers['X-Cup-Of'] = 'Coffee'
                response = Resource.client.get('/drink_machine')

    To use `Client` you must first derive from it, specify the default
    configuration as class attribute `config` and then implement `_serialize`
    and `_deserialize` which serialize and deseralize request data and response
    payloads::

        class Client(wac.Client):

            config = default_config

            def _serialize(self, data):
                data = json.dumps(data)
                return 'application/json', data

            def _deserialize(self, response):
                if response.headers['Content-Type'] != 'application/json':
                    raise Exception("Unsupported content-type '{}'"
                        .format(response.headers['Content-Type']))
                return json.loads(response.content)


    Additionally you might want to do custom exception conversion::

         class Client(wac.Client):

            ...

            def _op(self, *args, **kwargs):
                try:
                    return super(Client, self)._op(*args, **kwargs)
                except wac.Error, ex:
                    if not hasattr(ex, 'type'):
                        raise
                    if ex.type != MyError.MY_TYPE:
                        raise
                    raise MyError(*ex.args, **ex.__dict__)
            ...


    Note that all `Client` instance attributes are thread local but all your
    `Client`s initially will share a `config` so that they can be commonly
    configured.
    """

    __metaclass__ = abc.ABCMeta
    config = None

    def __init__(self, keep_alive=True):
        super(Client, self).__init__()
        self.interface = requests.session() if keep_alive else requests
        self._configs = []

    def get(self, uri, **kwargs):
        return self._op(self.interface.get, uri, **kwargs)

    def post(self, uri, data=None, **kwargs):
        mime_type, data = self._serialize(data)
        kwargs.setdefault('headers', {})
        kwargs['headers']['Content-Type'] = mime_type
        return self._op(self.interface.post, uri, data=data, **kwargs)

    def put(self, uri, data=None, **kwargs):
        mime_type, data = self._serialize(data)
        kwargs.setdefault('headers', {})
        kwargs['headers']['Content-Type'] = mime_type
        return self._op(self.interface.put, uri, data=data, **kwargs)

    def delete(self, uri, **kwargs):
        return self._op(self.interface.delete, uri, **kwargs)

    def _op(self, f, uri, **kwargs):

        def handle_redirect(response):
            if not kwargs.get('return_response', True):
                return
            if kwargs['allow_redirects']:
                return

            http_error_msg = '%s Client Error: Redirect' % (
                response.status_code
            )
            http_error = requests.HTTPError(http_error_msg)
            http_error.response = response
            raise http_error

        def handle_error(ex):
            if (kwargs.get('return_response', True) and
                        'Content-Type' in ex.response.headers):
                ex.response.data = self._deserialize(ex.response)
            for handler in self.config.after_request:
                handler(ex.response)
            if ex.response.status_code in requests.sessions.REDIRECT_STATI:
                raise Redirection(ex)
            ex = self.config.error_cls(ex)
            raise ex

        kwargs.setdefault('headers', {})
        kwargs['headers'].update(self.config.headers)
        kwargs.setdefault('allow_redirects', self.config.allow_redirects)
        if self.config.auth:
            kwargs['auth'] = self.config.auth
        if self.config.timeout is not None:
            kwargs['timeout'] = self.config.timeout

        url = self.config.root_url + uri

        method = f.__name__.upper()
        for handler in self.config.before_request:
            handler(method, url, kwargs)

        try:
            response = f(url, **kwargs)
            if kwargs.get('return_response', True):
                response.raise_for_status()
            if response.status_code in requests.sessions.REDIRECT_STATI:
                handle_redirect(response)
        except requests.HTTPError as ex:
            handle_error(ex)

        response.data = None
        if (kwargs.get('return_response', True) and
                'Content-Type' in response.headers):
            response.data = self._deserialize(response)

        for handler in self.config.after_request:
            handler(response)

        return response

    @abc.abstractmethod
    def _serialize(self, payload):
        pass

    @abc.abstractmethod
    def _deserialize(self, response):
        pass

    def __enter__(self):
        self._configs.append(self.config)
        self.config = self.config.copy()
        return self

    def __exit__(self, type_, value, traceback):
        self.config = self._configs.pop()


# paging

class NoResultFound(Exception):
    pass


class MultipleResultsFound(Exception):
    pass


class Page(_ObjectifyMixin):
    """
    Represents a page of resources in an pagination. These are used by
    `Pagination`.

    `resource_cls`
        A `Resource` class.

    `uri`
        The uri representing the page.

    `data`
        Page data as a dict with the following keys::

        `items`
            Objectified (i.e. instances of `resource`) items on this page.
        `total`
            Total number of items in pagination.
        `offset`
            Offset in items to this page in pagination.
        `limit`
            URI for previous page in pagination.
        `first`:
            URI for first page in pagination.
        `previous`
            URI for previous page in pagination.
        `next`
            URI for next page in pagination.
        `last`
            URI for last page in pagination.

        Defaults to None.
    """

    type = 'page'

    def __init__(self, resource_cls, **data):
        self.resource_cls = resource_cls
        self._objectify(resource_cls, **data)

    @property
    def index(self):
        return int(self.offset / self.total) if self.total else 0


class Pagination(object):
    """
    Collection or index endpoint as a sequence of pages.

    `resource_cls`
         A `Resource` class.

    `uri`
        URI for the endpoint.

    `default_size`
        Default number of items in each page. If a limit parameter is not
        present in `uri` then this default value will be used.

    `current`
        Page data as a dict for the current page if available.

    The standard sequence indexing and slicing protocols are supported.
    """

    def __init__(self, resource_cls, uri, default_size=10, current=None):
        self.resource_cls = resource_cls
        self.uri, limit, _ = self._parse_uri(uri)
        self.size = limit or default_size
        self._current = current

    @staticmethod
    def _parse_uri(uri):
        uri_no_qs, _, qs = uri.partition('?')
        parsed_qs = urlparse.parse_qs(qs)

        limit = None
        if 'limit' in parsed_qs:
            if len(parsed_qs['limit']) > 1:
                raise ValueError(
                    'URI "{0}" has multiple limit parameters "{1}"'.format(
                    uri, parsed_qs['limit'][0]))
            limit = parsed_qs['limit'][0]
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                raise ValueError(
                    'URI "{0}" has non-integer limit parameter "{1}"'.format(
                    uri, limit))
            parsed_qs.pop('limit')

        offset = 0
        if 'offset' in parsed_qs:
            if len(parsed_qs['offset']) > 1:
                raise ValueError(
                    'URI "{0}" has multiple offset parameters'.format(uri))
            offset = parsed_qs['offset'][0]
            try:
                offset = int(offset)
            except (TypeError, ValueError):
                raise ValueError(
                    'URI "{0}" has non-integer offset parameter "{1}"'.format(
                    uri, offset))
            parsed_qs.pop('offset')

        qs = urllib.urlencode(parsed_qs, doseq=True)
        uri = uri_no_qs + '?'
        if qs:
            uri += qs + '&'

        return uri, limit, offset

    def _page(self, key, size=None):
        size = size or self.size
        qs = [
            ('limit', self.size),
            ('offset', key * self.size),
        ]
        qs = urllib.urlencode(qs, doseq=True)
        uri = self.uri + qs
        resp = self.resource_cls.client.get(uri)
        return self.resource_cls.page_cls(self.resource_cls, **resp.data)

    def count(self):
        if self._current:
            total = self._current.total
        else:
            total = self._page(0, 1).total
        return int(math.ceil(total / self.size))

    @property
    def fetched(self):
        return self._current is not None

    @property
    def current(self):
        if not self._current:
            self.first()
        return self._current

    def one(self):
        if self.count() > 1:
            raise MultipleResultsFound()
        self._current = self._page(0)
        return self._current

    def first(self):
        self._current = self._page(0)
        return self._current

    def previous(self):
        if not self.current.previous:
            return None
        self._current = self._current.previous
        return self._current

    def next(self):
        if not self.current.next:
            return None
        self._current = self._current.next
        return self._current

    def __iter__(self):
        page = self.current
        while True:
            yield page
            page = page.next
            if not page:
                break
        if isinstance(page, basestring):
            new_page = Pagination(self.resource_cls, page, self.size)
            page = new_page.current
        self._current = page

    def __len__(self):
        return self.count()

    def _slice(self, key):
        if (key.start is not None and not isinstance(key.start, int) or
            key.stop is not None and not isinstance(key.stop, int) or
                key.step is not None and not isinstance(key.step, int)):
            raise TypeError('slice indices must be integers or None')
        if key.step == 0:
            raise TypeError('slice step cannot be zero')
        start, stop, step = key.indices(self.count())
        pages = [self[i] for i in xrange(start, stop, step)]
        return pages

    def _index(self, key):
        if key < 0:
            key += self.count()
            if key < 0:
                raise IndexError('index out of range')
        elif key > self.count():
            raise IndexError('index  out of range')
        if self.current.index == key:
            return self.current
        return self._page(key)

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self._slice(key)
        elif isinstance(key, int):
            return self._index(key)
        else:
            raise TypeError('indices must be integers, not {0}'.format(
                type(key)))


class PaginationMixin(object):
    """
    Mixin for exposing a `pagination` instance attribute as a sequence of
    resource items (rather than resource `Page`s which is what `Pagination`
    does).

    This is used by `Query` and `ResourceCollection`.

    The standard sequence indexing and slicing protocols are supported.
    """

    def count(self):
        if self.pagination.fetched:
            total = self.pagination.current.total
        else:
            total = self.pagination._page(0, 1).total
        return total

    def all(self):
        return list(self)

    def one(self):
        if self.pagination.fetched and self.pagination.current.offset == 0:
            items = self.pagination.current.items
            total = self.pagination.current.total
        else:
            items = self.pagination._page(0, 2).items
            total = len(items)
        if total > 1:
            raise MultipleResultsFound()
        elif total == 0:
            raise NoResultFound()
        return items[0]

    def first(self):
        if self.pagination.fetched and self.pagination.current.offset == 0:
            items = self.pagination.current.items
        else:
            items = self.pagination._page(0, 1).items
        return items[0] if items else None

    def __iter__(self):
        self.pagination.first()
        for page in self.pagination:
            for v in page.items:
                yield v

    def __len__(self):
        return self.count()

    def _slice(self, key):
        if (key.start is not None and not isinstance(key.start, int) or
            key.stop is not None and not isinstance(key.stop, int) or
                key.step is not None and not isinstance(key.step, int)):
            raise TypeError('slice indices must be integers or None')
        if key.step == 0:
            raise TypeError('slice step cannot be zero')
        start, stop, step = key.indices(self.count())
        page = None
        items = []
        for i in xrange(start, stop, step):
            idx = int(i / self.pagination.size)
            offset = i % self.pagination.size
            if not page or page.index != idx:
                page = self.pagination[idx]
            item = page.items[offset]
            items.append(item)
        return items

    def _index(self, key):
        if key < 0:
            key += self.count()
            if key < 0:
                raise IndexError('index out of range')
        idx = int(key / self.pagination.size)
        page = self.pagination[idx]
        offset = key % self.pagination.size
        if len(self.pagination.current.items) < offset:
            raise IndexError('index out of range')
        return page.items[offset]

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self._slice(key)
        elif isinstance(key, int):
            return self._index(key)
        else:
            raise TypeError('indices must be integers, not {0}'.format(
                type(key)))


# query

class FilterExpression(object):
    """
    A `Query` filter expression.

    `field`
        The field, as a string, the filter expression applies to.
    `op`
        The filtering operator as a string.
    `value`
        The filtering values. Either one or a sequence of them.
    `inv_op`
        The inverse of the `op` filtering operator if invertable. Otherwise
        None.

    You typically never need to create these directly but instead generated
    them via the `f` or `fields` attributes of you resource classes::

        MyResource.fields.a >= 1
        MyResource.fields.name.startswith('abc')
        MyResource.f.created_at < datetime.utcnow()
        ~MyResource.f.description.contains('hiya')
    """

    def __init__(self, field, op, value, inv_op):
        self.field = field
        self.op = op
        self.value = value
        self.inv_op = inv_op

    def __invert__(self):
        if self.inv_op is None:
            raise TypeError('"{0}" cannot be inverted', self)
        return FilterExpression(self.field, self.inv_op, self.value, self.op)

    def __str__(self):
        return '{0} {1} {2}'.format(
            self.field.name, self.field.op, self.field.values)


class SortExpression(object):
    """
    A `Query` sort expression.

    `field`
        The field, as a string, the sort expression applies to.
    `ascending`
        Flag indicating whether the sort if ascending (True) or descending
        (False).

    You typically never need to create these directly but instead generated
    them via the `f` or `fields` attributes of you resource classes::

        MyResource.fields.a.asc()
        MyResource.fields.b.desc()
    """

    def __init__(self, field, ascending):
        self.field = field
        self.ascending = ascending

    def __invert__(self):
        return SortExpression(self.field, not self.ascending)


class Query(PaginationMixin):
    """
    Collection or index endpoint query. It is built up of `FilterExpression`s
    and `SortExpressions` which act to filter and order the resources at the
    endpoint.

    `resource_cls`
        A `Resource` class.

    `uri`
        URI for the endpoint.

    `page_size`
        The number of items in each page.

    Note that the pages that are part of the `Query` can be accessed via the
    `pagination`prooperty. However you can also access `Query` as a sequence
    of `resource`s which is provied by `PaginationMixin`.

    The following filtering format is assumed:

    The following sorting format is assumed:
    """

    def __init__(self, resource_cls, uri, page_size):
        super(Query, self).__init__()
        self.resource_cls = resource_cls
        parsed = self._parse_uri(uri, page_size)
        self.uri, self.filters, self.sorts, self.page_size = parsed
        self._pagination = None

    @staticmethod
    def _parse_uri(uri, page_size):
        if page_size <= 0:
            raise ValueError('page_size must be > 0')
        filters, sorts, page_size = [], [], page_size
        uri, _, qs = uri.partition('?')
        qs = urlparse.parse_qs(qs)
        for k, vs in qs.iteritems():
            for v in vs:
                if k == 'sort':
                    sorts.append(v)
                elif k == 'limit':
                    page_size = int(v)
                    if page_size < 0:
                        raise ValueError(
                            'uri page_size {0} must be > 0'.format(page_size))
                else:
                    filters.append((k, v))
        return uri, filters, sorts, page_size

    def _qs(self):
        qs = []
        qs += self.filters
        qs += self.sorts
        return urllib.urlencode(qs, doseq=True)

    def filter(self, *args, **kwargs):
        for expression in args:
            if not isinstance(expression, FilterExpression):
                raise ValueError('"{0}" is not a FilterExpression'.format(
                    expression))
            if expression.op == '=':
                f = '{0}'.format(expression.field.name)
            else:
                f = '{0}[{1}]'.format(expression.field.name, expression.op)
            values = expression.value
            if not isinstance(values, (list, tuple)):
                values = [values]
            f = (f, ','.join(str(v) for v in values))
            self.filters.append(f)
        for k, values in kwargs.iteritems():
            f = '{0}'.format(k)
            if not isinstance(values, (list, tuple)):
                values = [values]
            f = (f, ','.join(str(v) for v in values))
            self.filters.append(f)
        self._pagination = None  # invalidate pagination
        return self

    def sort(self, *args):
        for expression in args:
            if not isinstance(expression, SortExpression):
                raise ValueError('"{0}" is not a SortExpression'.format(
                    expression))
            v = '{0},{1}'.format(
                expression.field.name,
                'asc' if expression.ascending else 'desc')
            self.sorts.append(('sort', v))
        self._pagination = None  # invalidate pagination
        return self

    def limit(self, v):
        self.page_size = v
        self._pagination = None  # invalidate pagination
        return self

    @property
    def pagination(self):
        if self._pagination is None:
            uri = self.uri + '?' + self._qs()
            self._pagination = Pagination(self.resource_cls, uri, self.page_size)
        return self._pagination


class URIGen(object):
    """
    Defines URI generation information for a resource.

    `collection`
        A collection URI fragment (e.g. apples or barrels/{barrel}/apples).

    `member`
        A member URI fragment ({apples} or {one}/{two}).

    `parent`
        Optional `URIGen`-like object under-which this is always sub-mounted.
        Defaults to None.
    """

    def __init__(self, collection, member, parent=None):
        self.collection = collection
        self.collection_fmt = self._parse(collection)
        if parent:
            self.collection_fmt = parent.member_fmt + self.collection_fmt
        self.member = member
        self.member_fmt = self.collection_fmt + self._parse(member)

    @classmethod
    def _parse(cls, fragment):
        fragment = fragment.strip('/')
        parts = []
        for part in fragment.split('/'):
            m = re.match(r'\{(?P<name>\w[\w_-]*)\}', part)
            if m:
                part = m.group('name')
                parts.append('{' + part + '}')
            else:
                parts.append(part)
        fmt = '/' + '/'.join(parts)
        return fmt

    @property
    def root_uri(self):
        try:
            return self.collection_uri()
        except KeyError:
            return None

    def collection_uri(self, **ids):
        return (self.collection_fmt).format(**ids)

    def member_uri(self, **ids):
        return (self.member_fmt).format(**ids)


# resources

class ResourceCollection(PaginationMixin):
    """
    Collection endpoint.

    `resource_cls`
        A `Resource` class.

    `data`
        The first page. In some cases a nested collection endpoint will be
        rendered by the server with its first page (rather than as just a
        string). In those cases we initialize the `pagination` current page
        with that data.

    Note that the pages that are part of the `ResourceCollection` can be
    accessed via the `pagination` attribute. However you can also access
    `ResourceCollection` as a sequence of `resource`s which is provided by
    `PaginationMixin`.
    """

    def __init__(self, resource_cls, uri, page=None):
        super(ResourceCollection, self).__init__()
        self.uri = uri
        self.resource_cls = resource_cls
        self.pagination = Pagination(resource_cls, uri, current=page)

    def create(self, **kwargs):
        resp = self.resource_cls.client.post(self.uri, data=kwargs)
        return self.resource_cls._load(self.resource_cls, resp.data)

    def filter(self, *args, **kwargs):
        q = self.resource_cls.query_cls(
            self.resource_cls, self.uri, self.pagination.size)
        q.filter(*args, **kwargs)
        return q

    def sort(self, *args):
        q = self.resource_cls.query_cls(
            self.resource_cls, self.uri, self.pagination.size)
        q.sort(*args)
        return q


class ResourceRegistry(dict):
    """
    A registry mapping resources types to classes. It is used to determine
    which resource class should be used when objectifying resource data.

    You only really ever need to create this once and attach it to your base
    resource class as a `registry` class attribute::

        class Resource(wac.Resource):

            client = Client()
            registry = wac.ResourceRegistry()

    """

    def match(self, type):
        cls = self.get(type, None)
        if cls:
            return cls
        raise LookupError(
            "No resource with type '{0}' registered"
            .format(type)
        )


class _ResourceField(object):

    def __init__(self, name):
        self.name = name

    def __getattr__(self, name):
        return _ResourceField('{0}.{1}'.format(self.name, name))

    def asc(self):
        return SortExpression(self, ascending=True)

    def desc(self):
        return SortExpression(self, ascending=False)

    def in_(self, *args):
        return FilterExpression(self, 'in', args, '!in')

    def startswith(self, prefix):
        if not isinstance(prefix, basestring):
            raise ValueError('"startswith" prefix  must be a string')
        return FilterExpression(self, 'startswith', prefix, None)

    def endswith(self, suffix):
        if not isinstance(suffix, basestring):
            raise ValueError('"endswith" suffix  must be a string')
        return FilterExpression(self, 'endswith', suffix, None)

    def contains(self, fragment):
        if not isinstance(fragment, basestring):
            raise ValueError('"contains" fragment must be a string')
        return FilterExpression(self, 'contains', fragment, '!contains')

    def like(self, fragment):
        if not isinstance(fragment, basestring):
            raise ValueError('"like" fragment must be a string')
        return FilterExpression(self, 'like', fragment, '!like')

    def ilike(self, fragment):
        if not isinstance(fragment, basestring):
            raise ValueError('"ilike" fragment must be a string')
        return FilterExpression(self, 'ilike', fragment, '!ilike')

    def __lt__(self, other):
        if isinstance(other, (list, tuple)):
            raise ValueError('"<" operand must be a single value')
        return FilterExpression(self, '<', other, '>=')

    def __le__(self, other):
        if isinstance(other, (list, tuple)):
            raise ValueError('"<=" operand must be a single value')
        return FilterExpression(self, '<=', other, '>')

    def __eq__(self, other):
        if isinstance(other, (list, tuple)):
            raise ValueError('"==" operand must be a single value')
        return FilterExpression(self, '=', other, '!=')

    def __ne__(self, other):
        if isinstance(other, (list, tuple)):
            raise ValueError('"!=" operand must be a single value')
        return FilterExpression(self, '!=', other, '=')

    def __gt__(self, other):
        if isinstance(other, (list, tuple)):
            raise ValueError('">" operand must be a single value')
        return FilterExpression(self, '>', other, '<=')

    def __ge__(self, other):
        if isinstance(other, (list, tuple)):
            raise ValueError('">=" operand must be a single value')
        return FilterExpression(self, '>=', other, '<')


class _ResourceFields(object):

    def __init__(self, field_cls):
        self.field_cls = field_cls

    def __getattr__(self, name):
        field = self.field_cls(name)
        setattr(self, name, field)
        return field


# http://effbot.org/zone/metaclass-plugins.htm
# http://stackoverflow.com/a/396109
class _ResourceMeta(type):

    def __new__(mcs, cls_name, cls_bases, cls_dict):
        cls = type.__new__(mcs, cls_name, cls_bases, cls_dict)
        cls.fields = cls.f = _ResourceFields(cls.field_cls)
        if not cls.type:
            return cls
        if (cls.type in cls.registry and
            not issubclass(cls, cls.registry[cls.type])):
            logger.warning(
               "Overriding type '%s' to %s already registered to '%s'",
               cls.type, cls.__name__, cls.registry[cls.type].__name__)
        cls.registry[cls.type] = cls
        if cls.page_cls.type not in cls.registry:
            cls.registry[cls.page_cls.type] = cls.page_cls
        elif cls.registry[cls.page_cls.type] is not cls.page_cls:
            logger.warning("Page type '%s' already registered to '%s'",
                           cls.page_cls.type,
                           cls.registry[cls.page_cls.type].__name__)
        return cls


class Resource(_ObjectifyMixin):
    """
    The core resource class. Any given URI addresses a type of resource and
    this class is the object representation of that resource.

    `client`

    `registry`

    `type`

    `query_cls`

    `collection_cls`

    `page_cls`

    `field_cls`

    `uri_gen`
        A `URIGen`-like object that use used to match collections and members
        of this resource. This is required.

    `page_size`
        Default number of items to return when pagination a collection of
        resources. Defaults to 25.

    Typically a resource is very simple. You start by defining a base
    resource::

        class Resource(wac.Resource):

            client = Client()

            registry = wac.ResourceRegistry()

    And the enumerate all the resources you care about::

        class Playlist(Resource):

            type = 'playlist'

            uri_gen = wac.URIGen('/v1/playlists', '{playlist}')


        class Song(Resource):

            type = 'song'

            uri_gen = wac.URIGen('/v1/songs', '{song}')


    You can add helper functions to your resource if you like::

        class Playlist(Resource):

            type = 'playlist'

            uri_gen = wac.URIGen('/v1/playlists', '{playlist}')

            def play_them()
                ...

    You can now use your resorces as you would say models of an ORM::

        q = (Playlist.query
            .filter(Playlist.f.tags.contains('nuti'))
            .filter(~Playlist.f.tags.contains('sober'))
            .sort(Playlist.f.created_at.desc()))
        for playlist in q:
            song = playlist.songs.create(
                name='Flutes',
                length=1234,
                tags=['nuti', 'fluti'])
            song.length += 1
            song.save()
    """

    __metaclass__ = _ResourceMeta

    query_cls = Query

    collection_cls = ResourceCollection

    page_cls = Page

    field_cls = _ResourceField

    uri_gen = None

    page_size = 25

    client = None

    registry = None

    type = None

    def __init__(self, **kwargs):
        super(Resource, self).__init__()
        self._objectify(self.__class__, **kwargs)

    def __repr__(self):
        attrs = ', '.join([
            '{0}={1}'.format(k, repr(v))
            for k, v in self.__dict__.iteritems()
        ])
        return '{0}({1})'.format(self.__class__.__name__, attrs)

    @classproperty
    def query(cls):
        if not cls.uri_gen or not cls.uri_gen.root_uri:
            raise TypeError('Unable to query {0} resources directly'
                            .format(cls.__name__))
        return Query(cls, cls.uri_gen.root_uri, page_size=cls.page_size)

    @classmethod
    def get(cls, uri):
        resp = cls.client.get(uri)
        return cls(**resp.data)

    def refresh(self):
        resp = self.client.get(self.uri)
        instance = self.__class__(**resp.data)
        self.__dict__.clear()
        self.__dict__.update(instance.__dict__)
        return self

    def save(self):
        cls = type(self)
        attrs = self.__dict__.copy()
        uri = attrs.pop('uri', None)

        if not uri:
            if not cls.uri_gen or not cls.uri_gen.root_uri:
                raise TypeError('Unable to create {0} resources directly'
                                .format(cls.__name__))
            method = cls.client.post
            uri = cls.uri_gen.root_uri
        else:
            method = self.client.put

        attrs = dict(
            (k, v)
            for k, v in attrs.iteritems()
            if not isinstance(v, (Resource, cls.collection_cls))
        )

        resp = method(uri, data=attrs)

        instance = self.__class__(**resp.data)
        self.__dict__.clear()
        self.__dict__.update(instance.__dict__)

        return self

    def delete(self):
        self.client.delete(self.uri)
