"""
Library for helping you write nice clients for RESTful APIs.
"""
from __future__ import division
import abc
import copy
import logging
import math
import pprint
import threading
import httplib
import urllib
import urlparse

import requests
from requests.models import REDIRECT_STATI


__version__ = '0.8'

__all__ = [
    'Config',
    'Error',
    'Redirection',
    'Client',
    'NoResultFound',
    'MultipleResultsFound',
    'URISpec',
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
    `error_class`
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
        Flag indicating whether connections should be reused. Defaults to
        False.
    """

    def __init__(self,
            root_url,
            client_agent=None,
            user_agent=None,
            auth=None,
            headers=None,
            echo=False,
            allow_redirects=False,
            error_class=None,
            keep_alive=False):
        self.reset(
            root_url,
            client_agent=client_agent,
            user_agent=user_agent,
            auth=auth,
            headers=headers,
            echo=echo,
            allow_redirects=allow_redirects,
            error_class=error_class,
            keep_alive=keep_alive)

    def reset(self,
            root_url,
            client_agent=None,
            user_agent=None,
            auth=None,
            headers=None,
            echo=False,
            allow_redirects=False,
            error_class=None,
            keep_alive=False):
        headers = headers or {}
        self.root_url = root_url.rstrip('/') if root_url else None
        user_agent = ' '.join(p for p in [client_agent, user_agent] if p)
        if user_agent:
            headers['User-Agent'] = user_agent
        self.auth = auth
        self.headers = headers
        self.allow_redirects = allow_redirects
        self.error_class = error_class or Error
        self.before_request = []
        self.after_request = []
        self.keep_alive = keep_alive
        if echo:
            self.before_request.append(Config._echo_request)
            self.after_request.append(Config._echo_response)

    @staticmethod
    def _echo_request(method, url, **kwargs):
        print url, method
        pprint.pprint(kwargs)

    @staticmethod
    def _echo_response(response):
        pprint.pprint(response.content)


class Error(requests.HTTPError):
    """
    Represents HTTP errors detected by `Client` as specialization of
    `requests.HTTPError`.

    `message`
        String message formatted by `format_message`. For different formatting
         derived from `Error`, change `format_message` and pass that as the
         `error_class` when configuring your `Client`.
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
        if isinstance(data, dict):
            for k, v in data.iteritems():
                setattr(self, k, v)

    def __repr__(self):
        attrs = ', '.join([
           '{}={}'.format(k, repr(v))
           for k, v in self.__dict__.iteritems()
           ])
        return '{}({})'.format(self.__class__.__name__, attrs)

    @classmethod
    def format_message(cls, requests_ex):
        data = getattr(requests_ex.response, 'data', {})
        status = httplib.responses[requests_ex.response.status_code]
        status = data.pop('status', status)
        status_code = data.pop('status_code', requests_ex.response.status_code)
        desc = data.pop('description', None)
        message = ': '.join(str(v) for v in [status, status_code, desc] if v)
        return message


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
    `error_class`
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
        kwargs.setdefault('headers', {})
        kwargs.setdefault('config', {})
        kwargs['headers'].update(self.config.headers)
        kwargs.setdefault('allow_redirects', self.config.allow_redirects)
        if 'keep_alive' not in kwargs['config']:
            kwargs['config']['keepalive'] = self.config.keep_alive
        if self.config.auth:
            kwargs['auth'] = self.config.auth

        url = self.config.root_url + uri

        method = f.__name__.upper()
        for handler in self.config.before_request:
            handler(method, url, kwargs)

        try:
            response = f(url, **kwargs)
            if kwargs.get('return_response', True):
                response.raise_for_status(kwargs['allow_redirects'])
        except requests.HTTPError, ex:
            if (kwargs.get('return_response', True) and
                'Content-Type' in ex.response.headers):
                ex.response.data = self._deserialize(ex.response)
            for handler in self.config.after_request:
                handler(ex.response)
            if ex.response.status_code in REDIRECT_STATI:
                raise Redirection(ex)
            ex = self.config.error_class(ex)
            raise ex

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
        self.config = copy.deepcopy(self.config)
        return self

    def __exit__(self, type_, value, traceback):
        self.config = self._configs.pop()


# paging

class NoResultFound(Exception):
    pass


class MultipleResultsFound(Exception):
    pass


class Page(object):
    """
    Represents a page of resources in an pagination. These are used by
    `Pagination`.

    `uri`
        The uri representing the page.
    `resource`
        The resource class.
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

    Note that page data is lazily fetched on first access.
    """

    def __init__(self, resource, uri, data=None):
        self.resource = resource
        self.uri = uri
        self._page = data
        if self._page is not None:
            self._page['items'] = [
                self.resource(**items) for items in self._page['items']
                ]

    def __repr__(self):
        attrs = ', '.join(
            '{}={}'.format(k, v)
            for k, v in [
                ('uri', self.uri),
                ('qs', self.qs),
                ('resource', self.resource),
                ])
        return '{}({})'.format('Page', attrs)

    def fetch(self):
        if not self.fetched:
            resp = self.resource.client.get(self.uri)
            page = resp.data
            page['items'] = [
                self.resource(**items) for items in page['items']
                ]
            self._page = page
        return self._page

    @property
    def fetched(self):
        return self._page is not None

    @property
    def index(self):
        return int(self.offset / self.total) if self.total else 0

    @property
    def items(self):
        return self.fetch()['items']

    @property
    def total(self):
        return self.fetch()['total']

    @property
    def offset(self):
        return self.fetch()['offset']

    @property
    def limit(self):
        return self.fetch()['limit']

    @property
    def first(self):
        uri = self.fetch()['first_uri']
        return Page(self.resource, uri)

    @property
    def previous(self):
        uri = self.fetch()['previous_uri']
        return Page(self.resource, uri) if uri else None

    @property
    def next(self):
        uri = self.fetch()['next_uri']
        return Page(self.resource, uri) if uri else None

    @property
    def last(self):
        uri = self.fetch()['last_uri']
        return Page(self.resource, uri)


class Pagination(object):
    """
    Collection or index endpoint as a sequence of pages.

    `resource`
        The class representing this endpoints resources.
    `uri`
        URI for the endpoint.
    `default_size`
        Default number of items in each page. If a limit parameter is not
        present in `uri` then this default value will be used.
    `current`
        Page data as a dict for the current page if available.

    The standard sequence indexing and slicing protocols are supported.
    """

    def __init__(self, resource, uri, default_size=10, current=None):
        self.resource = resource
        self.uri, limit, offset = self._parse_uri(uri)
        self.size = limit or default_size
        self.current = self._page(int(offset / self.size), data=current)

    @staticmethod
    def _parse_uri(uri):
        uri_no_qs, _, qs = uri.partition('?')
        parsed_qs = urlparse.parse_qs(qs)

        limit = None
        if 'limit' in parsed_qs:
            if len(parsed_qs['limit']) > 1:
                raise ValueError(
                    'URI "{}" has multiple limit parameters "{}"'.format(
                    uri, parsed_qs['limit'][0]))
            limit = parsed_qs['limit'][0]
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                raise ValueError(
                    'URI "{}" has non-integer limit parameter "{}"'.format(
                    uri, limit))
            parsed_qs.pop('limit')

        offset = 0
        if 'offset' in parsed_qs:
            if len(parsed_qs['offset']) > 1:
                raise ValueError(
                    'URI "{}" has multiple offset parameters'.format(uri))
            offset = parsed_qs['offset'][0]
            try:
                offset = int(offset)
            except (TypeError, ValueError):
                raise ValueError(
                    'URI "{}" has non-integer offset parameter "{}"'.format(
                    uri, offset))
            parsed_qs.pop('offset')

        qs = urllib.urlencode(parsed_qs, doseq=True)
        uri = uri_no_qs + '?'
        if qs:
            uri += qs + '&'

        return uri, limit, offset

    def _page(self, key, size=None, data=None):
        size = size or self.size
        qs = [
            ('limit', self.size),
            ('offset', key * self.size),
            ]
        qs = urllib.urlencode(qs, doseq=True)
        uri = self.uri + qs
        return Page(self.resource, uri, data)

    def count(self):
        if self.current.fetched:
            total = self.current.total
        else:
            total = self._page(0, 1).total
        return int(math.ceil(total / self.size))

    def one(self):
        if self.count() > 1:
            raise MultipleResultsFound()
        self.current = self[0]
        return self.current

    def first(self):
        self.current = self[0]
        return self.current

    def previous(self):
        if not self.current.previous:
            return None
        self.current = self.current.previous
        return self.current

    def next(self):
        if not self.current.next:
            return None
        self.current = self.current.next
        return self.current

    def __iter__(self):
        page = self.current
        while True:
            yield page
            page = page.next
            if not page:
                break
            self.current = page

    def __len__(self):
        return self.count()

    def _slice(self, key):
        if (key.start != None and not isinstance(key.start, int) or
            key.stop != None and not isinstance(key.stop, int) or
            key.step != None and not isinstance(key.step, int)):
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
            raise TypeError('indices must be integers, not {}'.format(
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
        page = self.pagination.current
        if page.feched:
            total = page.total
        else:
            total = self.pagination._page(0, 1).total
        return total

    def all(self):
        return list(self)

    def one(self):
        page = self.pagination.current
        if page.fetched and page.offset == 0:
            items = page.items
            total = page.total
        else:
            items = self.pagination._page(0, 2).items
            total = len(items)
        if total > 1:
            raise MultipleResultsFound()
        elif total == 0:
            raise NoResultFound()
        return items[0]

    def first(self):
        page = self.pagination.current
        if page.fetched and page.offset == 0:
            items = page.items
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
        if (key.start != None and not isinstance(key.start, int) or
            key.stop != None and not isinstance(key.stop, int) or
            key.step != None and not isinstance(key.step, int)):
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
            raise TypeError('indices must be integers, not {}'.format(
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
            raise TypeError('"{}" cannot be inverted', self)
        return FilterExpression(self.field, self.inv_op, self.value, self.op)

    def __str__(self):
        return '{} {} {}'.format(
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

    `resource`
        The class representing this endpoints resources.
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

    def __init__(self, resource, uri, page_size):
        super(Query, self).__init__()
        self.resource = resource
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
                        raise ValueError('uri page_size {} must be > 0'.format(
                            page_size))
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
                raise ValueError('"{}" is not a FilterExpression'.format(
                    expression))
            if expression.op == '=':
                f = '{}'.format(expression.field.name)
            else:
                f = '{}[{}]'.format(expression.field.name, expression.op)
            values = expression.value
            if not isinstance(values, (list, tuple)):
                values = [values]
            f = (f, ','.join(str(v) for v in values))
            self.filters.append(f)
        for k, values in kwargs.iteritems():
            f = '{}'.format(k)
            if not isinstance(values, (list, tuple)):
                values = [values]
            f = (f, ','.join(str(v) for v in values))
            self.filters.append(f)
        self._pagination = None  # invalidate pagination
        return self

    def sort(self, *args):
        for expression in args:
            if not isinstance(expression, SortExpression):
                raise ValueError('"{}" is not a SortExpression'.format(
                    expression))
            v = '{},{}'.format(
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
        if not self._pagination:
            uri = self.uri + '?' + self._qs()
            self._pagination = Pagination(self.resource, uri, self.page_size)
        return self._pagination


# uri specs

class URISpec(object):
    """
    Defines a resource URI. This information is later used to match a uri
    to a resource class.

    `collection`
        The name of the resource collection as a string (e.g. "apples").
    `ids`
        The ids to consider when matching a member uri. If a single id then
        this can simply be a string (e.g. "guid" or "id"). If a member uri
        contains multiple ids then this should be a list of strings (e.g.
        ["parent_guid", "guid"]).
    `root`
        Path to the root of this resource's collection endpoint. If None, the
        default, there is no root collection endpoint for the resource. That
        means you cannot perform certain top level queries or saves::

                class MyResource(Resource)

                    uri_spec = wac.URISpec('identities', 'guid', root='/v2')


                MyResource.query  # fails
                MyResource(a='123').save()  # fails
    `page_size`
        Default number of items in pages for this type of resource.
    """

    def __init__(self, collection, ids, root=None, page_size=25):
        self.collection = collection
        if isinstance(ids, basestring):
            ids = [ids]
        self.ids = ids
        if root is not None:
            self.collection_uri = root + '/' + collection
        if page_size <= 0:
            raise ValueError('page_size must be > 0')
        self.page_size = page_size

    def match(self, uri):
        uri = uri.partition('?')[0].rstrip('/')
        if uri.endswith(self.collection):
            return True, {'collection': True, 'page_size': self.page_size}
        t = uri
        id_ = {}
        for k in self.ids:
            t, _, v = t.rpartition('/')
            if v is None:
                break
            id_[k] = v
        if t.endswith(self.collection):
            flags = {'collection': False}
            flags.update(id_)
            return True, flags
        return False, {}


# resources

class ResourceRegistry(dict):
    """
    A registry mapping resources classes to `URISpec`s. It is used to determine
    which resource class shluld be used when objectifying a URI.

    You only really ever need to create this once and attach it to your base
    resource class as a `registry` class attribute::

        class Resource(wac.Resource):

            client = Client()
            registry = wac.ResourceRegistry()

    """

    def match(self, uri):
        uri = uri.rstrip('/')
        for resource_cls, spec in self.iteritems():
            matched, flags = spec.match(uri)
            if matched:
                return resource_cls, flags
        raise LookupError("No resource with uri spec matching '{}'"
            .format(uri))


class _ResourceField(object):

    def __init__(self, name):
        self.name = name

    def __getattr__(self, name):
        return _ResourceField('{}.{}'.format(self.name, name))

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

    def __getattr__(self, name):
        field = _ResourceField(name)
        setattr(self, name, field)
        return field


# http://effbot.org/zone/metaclass-plugins.htm
# http://stackoverflow.com/a/396109
class _ResourceMeta(type):

    def __new__(mcs, cls_name, cls_bases, cls_dict):
        cls = type.__new__(mcs, cls_name, cls_bases, cls_dict)
        cls.fields = cls.f = _ResourceFields()
        if hasattr(cls, 'uri_spec'):
            cls.registry[cls] = cls.uri_spec
        return cls


class Resource(object):
    """
    The core resource class. Any given URI addresses a type of resource and
    this class the an object representation of that resource.

    Typically a resource is very simple. You start by defining a base
    resource::

        class Resource(wac.Resource):

            client = Client()
            registry = wac.ResourceRegistry()

    And the enumerate all the resources you care about::

        class Playlist(Resource):

            uri_spec = wac.URISpec('playlists', 'guid', root='/v1')


        class Song(Resource):

            uri_spec = wac.URISpec('songs', 'guid')


    You can add helper functions to your resource if you like::

        class Playlist(Resource):

            uri_spec = wac.URISpec('playlists', 'guid', root='/v1')

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

    def __init__(self, **kwargs):
        super(Resource, self).__init__()
        self._objectify(**kwargs)

    def __repr__(self):
        attrs = ', '.join([
            '{}={}'.format(k, repr(v))
            for k, v in self.__dict__.iteritems()
            ])
        return '{}({})'.format(self.__class__.__name__, attrs)

    def _attach_property(self, new_key, key):

        def _load(self):
            uri = getattr(self, key)
            try:
                resource, flags = self.registry.match(uri)
            except LookupError:
                logger.warning(
                    "Unable to determine resource for '%s' from '%s'. "
                    "Make sure it is added in resources.py!", new_key, key)
            else:
                if not flags.get('collection', False):
                    resp = resource.client.get(uri)
                    return resource(**resp.data)
                else:
                    return ResourceCollection(
                        resource, uri, flags['page_size'])
            return None

        if not hasattr(self.__class__, new_key):
            setattr(self.__class__, new_key, property(_load))

    def _objectify(self, **kwargs):
        # iterate through the schema
        for key, value in kwargs.iteritems():
            # sub-resource
            if isinstance(value, dict) and 'uri' in value:
                uri = value['uri']
                try:
                    resource, flags = self.registry.match(uri)
                except LookupError:
                    logger.warning(
                        "Unable to determine resource for '%s' from '%s'. "
                        "Make sure it is added in resources.py! Defaulting to "
                        "dictionary based access", key, uri)
                    setattr(self, key, value)
                else:
                    if not flags.get('collection', False):
                        value = resource(**value)
                    else:
                        value = ResourceCollection(
                            resource, uri, flags['page_size'], value)
                    setattr(self, key, value)
            # uri
            elif isinstance(key, basestring) and key.endswith('_uri'):
                self._attach_property(key[:-4], key)
                setattr(self, key, value)
            else:
                setattr(self, key, value)

    @classproperty
    def query(cls):
        if not hasattr(cls.uri_spec, 'collection_uri'):
            raise TypeError('Unable to query {} resources directly'
                .format(cls.__name__))
        page_size = cls.uri_spec.page_size
        return Query(cls, cls.uri_spec.collection_uri, page_size=page_size)

    @classmethod
    def get(cls, uri):
        resp = cls.client.get(uri)
        return cls(**resp.data)

    def save(self):
        attrs = self.__dict__.copy()
        uri = attrs.pop('uri', None)

        if not uri:
            if not hasattr(self.uri_spec, 'collection_uri'):
                raise TypeError('Unable to create {} resources directly'
                    .format(self.__class__.__name__))
            method = self.client.post
            uri = self.uri_spec.collection_uri
        else:
            method = self.client.put

        attrs = dict(
            (k, v) for k, v in attrs.iteritems() if not isinstance(v, Resource)
            )

        response = method(uri, data=attrs)

        instance = self.__class__(**response.data)
        self.__dict__.clear()
        self.__dict__.update(instance.__dict__)

        return self

    def delete(self):
        self.client.delete(self.uri)


class ResourceCollection(PaginationMixin):
    """
    Collection endpoint.

    `resource`
        The class representing this endpoints resources.
    `uri`
        URI for the endpoint.
    `page_size`
        The number of items in each page.
    `page`
        The first page. In some cases a nested collection endpoint will be
        rendered by the server with its first page (rather than as just a
        string). In those cases we initialize the `pagination` current page
        with that data.

    Note that the pages that are part of the `ResourceCollection` can be
    accessed via the `pagination` attribute. However you can also access
    `ResourceCollection` as a sequence of `resource`s which is provided by
    `PaginationMixin`.
    """

    def __init__(self, resource, uri, page_size, page=None):
        super(ResourceCollection, self).__init__()
        self.resource = resource
        self.uri = uri
        self.pagination = Pagination(resource, uri, page_size, page)

    def create(self, **kwargs):
        resp = self.resource.client.post(self.uri, data=kwargs)
        return self.resource(**resp.data)

    def filter(self, *args, **kwargs):
        q = Query(self.resource, self.uri, self.pagination.size)
        q.fiter(*args, **kwargs)
        return q

    def sort(self, *args):
        q = Query(self.resource, self.uri, self.pagination.size)
        q.sort(*args)
        return q
