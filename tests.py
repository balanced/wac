from __future__ import division
from __future__ import unicode_literals

import imp
import json
import os
import math
import unittest2 as unittest
import urllib

from mock import Mock, patch

import wac


# utils

to_json = json.dumps

from_json = json.loads


def configure(root_url, **kwargs):
    default = kwargs.pop('default', True)
    kwargs['client_agent'] = 'test-client/' + wac.__version__
    if 'headers' not in kwargs:
        kwargs['headers'] = {}
    kwargs['headers']['Accept-Type'] = 'application/json'
    if default:
        default_config.reset(root_url, **kwargs)
    else:
        Client.config = wac.Config(root_url, **kwargs)


default_config = wac.Config(None)


class Client(wac.Client):

    config = default_config

    def __init__(self):
        super(Client, self).__init__(keep_alive=False)

    def _serialize(self, data):
        return 'application/json', json.dumps(data)

    def _deserialize(self, response):
        if response.headers['Content-Type'] != 'application/json':
            raise Exception("Unsupported content-type '{0}'"
                            .format(response.headers['Content-Type']))
        data = json.loads(response.content)
        return data


class Resource(wac.Resource):

    client = Client()
    registry = wac.ResourceRegistry()


class Resource1(Resource):

    type = 'one'
    uri_gen = wac.URIGen('/v2/1s', '{one}')


class Resource2(Resource):

    type = 'two'
    uri_gen = wac.URIGen('/v2/2s', '{two}')


class Resource3(Resource):

    type = 'three'
    uri_gen = wac.URIGen('/v2/3s', '{three}')


# tests

TestCase = unittest.TestCase


class TestConfig(TestCase):

    def test_defaults(self):
        config = wac.Config(None)
        self.assertEqual(config.root_url, None)
        self.assertEqual(config.auth, None)
        self.assertEqual(config.headers, {})
        self.assertEqual(config.before_request, [])
        self.assertEqual(config.after_request, [])

    def test_strip_trailing_slash(self):
        config = wac.Config('/fish/tanks/')
        self.assertEqual(config.root_url, '/fish/tanks')

    def test_copy(self):
        config = wac.Config(
            '/fish/tanks/',
            client_agent='cli',
            user_agent='usah',
            auth=('me', 'secret'),
            headers={
                'X-My-Header': 'interesting'
            },
            echo=True,
            keep_alive=True)
        config2 = config.copy()
        self.assertDictEqual(config.__dict__, config2.__dict__)


class TestClient(TestCase):

    def setUp(self):
        super(TestClient, self).setUp()
        self.cli = Client()

    @patch('wac.Client._op')
    def test_post(self, _op):
        self.cli.post('/a/post', data={'hi': 'there'})
        _op.assert_called_once_with(
            wac.requests.post,
            '/a/post',
            headers={'Content-Type': 'application/json'},
            data='{"hi": "there"}')

    @patch('wac.Client._op')
    def test_get(self, _op):
        self.cli.get('/a/get')
        _op.assert_called_once_with(
            wac.requests.get,
            '/a/get')

    @patch('wac.Client._op')
    def test_put(self, _op):
        self.cli.put('/a/put', data={'hi': 'ya'})
        _op.assert_called_once_with(
            wac.requests.put,
            '/a/put',
            headers={'Content-Type': 'application/json'},
            data='{"hi": "ya"}')

    @patch('wac.Client._op')
    def test_delete(self, _op):
        self.cli.delete('/a/del')
        _op.assert_called_once_with(
            wac.requests.delete,
            '/a/del')

    @patch('wac.requests.get')
    def test_op_headers(self, f):
        f.__name__ = 'get'
        response = f.return_value = Mock()
        response.content_length = 0
        response.headers = {'Content-Type': 'application/json'}
        response.content = '{"hi": "ya"}'
        with patch.object(self.cli, 'config') as config:
            config.root_url = 'http://ex.com'
            config.auth = None
            config.keep_alive = False
            config.allow_redirects = False
            config.headers = {
                'X-Custom': 'rimz',
            }
            self.cli._op(f, '/a/uri')
        f.assert_called_once_with(
            'http://ex.com/a/uri',
            headers={'X-Custom': 'rimz'},
            allow_redirects=False)

    @patch('wac.requests.get')
    def test_op_auth(self, f):
        f.__name__ = 'get'
        response = f.return_value = Mock()
        response.headers = {'Content-Type': 'application/json'}
        response.content = '{"hi": "ya"}'
        with patch.object(self.cli, 'config') as config:
            config.root_url = 'http://ex.com'
            config.auth = ('bob', 'passwerd')
            config.headers = {}
            config.keep_alive = False
            config.echo = False
            config.allow_redirects = False
            self.cli._op(f, '/a/uri')
        f.assert_called_once_with(
            'http://ex.com/a/uri',
            headers={},
            auth=('bob', 'passwerd'),
            allow_redirects=False)

    @patch('wac.requests.post')
    def test_serialize(self, f):
        f.__name__ = 'post'
        response = f.return_value = Mock()
        response.headers = {}
        with patch.object(self.cli, 'config') as config:
            config.root_url = 'http://ex.com'
            config.auth = None
            config.echo = False
            config.keep_alive = True
            config.allow_redirects = False
            config.headers = {
                'X-Custom': 'rimz',
            }
            self.cli.post('/an/uri', data={'yo': 'dawg'})
        f.assert_called_once_with(
            'http://ex.com/an/uri',
            headers={'X-Custom': 'rimz', 'Content-Type': 'application/json'},
            allow_redirects=False,
            data='{"yo": "dawg"}')

    @patch('wac.requests.get')
    def test_deserialize(self, f):
        response = f.return_value = Mock()
        f.__name__ = 'get'
        response.headers = {'Content-Type': 'application/json'}
        response.content = '{"hi": "ya"}'
        with patch.object(self.cli, 'config') as config:
            config.root_url = 'http://ex.com'
            config.auth = None
            config.echo = False
            config.keep_alive = False
            config.headers = {}
            config.allow_redirects = False
            self.cli.get('/an/uri')
        f.assert_called_once_with(
            'http://ex.com/an/uri',
            headers={},
            allow_redirects=False)
        self.assertEqual(response.data, {'hi': 'ya'})

        f.reset_mock()

        response = f.return_value = Mock()
        f.__name__ = 'get'
        response.headers = {}
        with patch.object(self.cli, 'config') as config:
            config.root_url = 'http://ex.com'
            config.auth = None
            config.echo = False
            config.keep_alive = True
            config.headers = {}
            config.allow_redirects = False
            self.cli.get('/an/uri')
        f.assert_called_once_with(
            'http://ex.com/an/uri',
            headers={},
            allow_redirects=False)
        self.assertFalse(response.data, None)

        f.reset_mock()

        response = f.return_value = Mock()
        f.__name__ = 'get'
        response.headers = {'Content-Type': 'image/png'}
        with patch.object(self.cli, 'config') as config:
            config.root_url = 'http://ex.com'
            config.auth = None
            config.echo = False
            config.keep_alive = True
            config.allow_redirects = False
            config.headers = {}
            with self.assertRaises(Exception) as ex_ctx:
                self.cli.get('/an/uri')
        self.assertIn(
            "Unsupported content-type 'image/png'", str(ex_ctx.exception))
        f.assert_called_once_with(
            'http://ex.com/an/uri',
            headers={},
            allow_redirects=False)

    def test_config_context(self):
        org_config = self.cli.config
        with self.cli:
            self.cli.config.headers['X-Custom'] = 'toe'
            self.cli.config.two = 'one'
            with self.cli:
                self.cli.config.headers['X-Custom'] = 'finger'
                self.cli.config.two = 'two'
            self.assertIn('X-Custom', self.cli.config.headers)
            self.assertEqual(self.cli.config.headers['X-Custom'], 'toe')
            self.assertEqual(self.cli.config.two, 'one')
        self.assertNotIn('X-Custom', self.cli.config.headers)
        self.assertFalse(hasattr(self.cli.config.headers, 'two'))
        self.assertIs(org_config, self.cli.config)

    @patch('wac.requests.get')
    def test_default_errors(self, _op):
        ex = wac.requests.HTTPError()
        ex.response = Mock()
        ex.response.status_code = 402
        ex.response.content = (
            '{"status": "Bad Request", "status_code": '
            '"400", "description": "Invalid field \'your mom\' -- make '
            'sure its your dad too", "additional": null}')
        ex.response.headers = {
            'Content-Type': 'application/json',
        }
        _op.__name__ = 'get'
        _op.side_effect = ex
        with self.cli:
            self.cli.config.root_url = '/test'
            self.cli.config.echo = False
            with self.assertRaises(wac.Error) as exc:
                self.cli.get('/rejected')
            the_exception = exc.exception
            self.assertEqual(
                the_exception.args[0],
                ("Bad Request: 400: Invalid field 'your mom' -- make sure its "
                 "your dad too")
            )

    @patch('wac.requests.get')
    def test_custom_errors(self, _op):

        class ErrorType(Exception):
            pass

        class ErrorType1(Exception):
            pass

        class ErrorType2(Exception):
            pass

        def convert_error(ex):
            if hasattr(ex.response, 'data'):
                type = ex.response.data.get('type')
                if type == 'type-1':
                    ex = ErrorType1()
                elif type == 'type-2':
                    ex = ErrorType2()
                else:
                    ex = ErrorType()
            return ex

        ex = wac.requests.HTTPError()
        ex.response = Mock()
        ex.response.status_code = 402
        ex_data = {
            'status': '400 Bad Request',
            'status_code': '400',
            'additional': None,
        }
        ex.response.headers = {
            'Content-Type': 'application/json',
        }
        _op.__name__ = 'get'
        _op.side_effect = ex

        with self.cli:
            self.cli.config.root_url = '/test'
            self.cli.config.echo = False
            self.cli.config.error_cls = convert_error

            ex_data['type'] = 'type-1'
            ex.response.content = to_json(ex_data)
            with self.assertRaises(ErrorType1) as exc:
                self.cli.get('/rejected')

            ex_data['type'] = 'type-2'
            ex.response.content = to_json(ex_data)
            with self.assertRaises(ErrorType2) as exc:
                self.cli.get('/rejected')

            ex_data['type'] = 'type-1138'
            ex.response.content = to_json(ex_data)
            with self.assertRaises(ErrorType) as exc:
                self.cli.get('/rejected')

    @patch('wac.requests.post')
    def test_request_handlers(self, f):
        response = f.return_value
        response.headers = {'Content-Type': 'application/json'}
        response.content = '{"bye": "ya"}'
        f.__name__ = 'post'
        f.return_value = response
        before_request = Mock()
        after_request = Mock()
        with self.cli:
            self.cli.config.root_url = '/test'
            self.cli.config.before_request.append(before_request)
            self.cli.config.after_request.append(after_request)
            result = self.cli.post('/a/post/w/hooks', data={'hi': 'ya'})
        before_request.assert_called_once_with(
            'POST',
            '/test/a/post/w/hooks',
            {'headers': {'Content-Type': 'application/json'},
             'allow_redirects': False,
             'data': '{"hi": "ya"}',
             }
        )
        after_request.assert_called_once_with(response)
        self.assertDictEqual(result.data, {'bye': 'ya'})

    @patch('wac.requests.post')
    def test_exception_request_handlers(self, f):
        ex = wac.requests.HTTPError()
        ex.response = Mock()
        ex.response.status_code = 402
        ex.response.content = (
            '{"status": "Bad Request", "status_code": '
            '"400", "description": "Invalid field \'your mom\' -- make '
            'sure its your dad too", "additional": "nothing personal"}')
        ex.response.headers = {
            'Content-Type': 'application/json',
        }
        f.__name__ = 'post'
        f.side_effect = ex
        before_request = Mock()
        after_request = Mock()
        with self.cli:
            self.cli.config.root_url = '/test'
            self.cli.config.keep_alive = False
            self.cli.config.before_request.append(before_request)
            self.cli.config.after_request.append(after_request)
            with self.assertRaises(wac.Error) as ex_ctx:
                self.cli.post('/a/post/w/hooks', data={'hi': 'ya'})
        self.assertEqual(ex_ctx.exception.status_code, 402)
        self.assertEqual(ex_ctx.exception.additional, 'nothing personal')
        before_request.assert_called_once_with(
            'POST',
            '/test/a/post/w/hooks',
            {'headers': {'Content-Type': 'application/json'},
             'allow_redirects': False,
             'data': '{"hi": "ya"}',
             }
        )
        after_request.assert_called_once_with(ex.response)

    @patch('requests.session')
    @patch('wac.Client._op')
    def test_keep_alive(self, op, session):
        ka_client = wac.Client()
        ka_client.config = default_config
        ka_client.config.root_url = 'https://www.google.com'
        ka_client.get('/grapes')
        args, _ = op.call_args
        self.assertEqual(args, (session.return_value.get, '/grapes'))


class TestPage(TestCase):

    @patch('wac.requests.get')
    def test_create(self, get):
        get.__name__ = 'get'
        with patch.object(Resource.client, 'config') as config:
            config.root_url = 'http://ex.com'
            config.echo = False
            config.allow_redirects = False
            config.keep_alive = True
            config.auth = ('bob', 'passwerd')
            response = get.return_value
            data = {
                '_type': 'page',
                '_uris': {
                    'first_uri': {
                        '_type': 'page',
                        'key': 'first',
                    },
                    'previous_uri': {
                        '_type': 'page',
                        'key': 'previous',
                    },
                    'next_uri': {
                        '_type': 'page',
                        'key': 'next',
                    },
                    'last_uri': {
                        '_type': 'page',
                        'key': 'last',
                    },
                },
                'uri': '/a/uri',
                'first_uri': '/a/uri/first',
                'previous_uri': '/a/uri/prev',
                'next_uri': '/a/uri/next',
                'last_uri': '/a/uri/last',
                'total': 100,
                'offset': 44,
                'limit': 2,
                'items': [
                    {'a': 'b', 'one': 2},
                    {'a': 'c', 'one': 3},
                ],
            }
            response.headers = {
                'Content-Type': 'application/json',
            }
            response.content = to_json(data)
            page = wac.Page(Resource, **data)

    def test_links(self):
        with patch.object(Resource1.client, '_op') as _op:
            resp = _op.return_value = Mock()

            common_data = {
                '_type': 'page',
                '_uris': {
                    'first_uri': {
                        '_type': 'page',
                        'key': 'first',
                    },
                    'previous_uri': {
                        '_type': 'page',
                        'key': 'previous',
                    },
                    'next_uri': {
                        '_type': 'page',
                        'key': 'next',
                    },
                    'last_uri': {
                        '_type': 'page',
                        'key': 'last',
                    },
                },
                'first_uri': '/a/uri/first',
                'previous_uri': '/a/uri/prev',
                'next_uri': '/a/uri/next',
                'last_uri': '/a/uri/last',
                'total': 100,
                'offset': 44,
                'limit': 2,
                'items': [
                ],
            }
            data = {
                'uri': '/a/uri',
            }
            data.update(common_data)
            resp.data = data
            page = wac.Page(Resource, **data)

            _op.return_value = Mock(
                headers={
                    'Content-Type': 'application/json',
                })

            data = {
                'uri': '/a/uri/first',
            }
            data.update(common_data)
            _op.return_value.data = data
            link = page.first
            self.assertEqual(link.uri, '/a/uri/first')
            self.assertEqual(link.resource_cls, page.resource_cls)

            data = {
                'uri': '/a/uri/prev',
            }
            data.update(common_data)
            _op.return_value.data = data
            link = page.previous
            self.assertEqual(link.uri, '/a/uri/prev')
            self.assertEqual(link.resource_cls, page.resource_cls)

            data = {
                'uri': '/a/uri/next',
            }
            data.update(common_data)
            _op.return_value.data = data
            link = page.next
            self.assertEqual(link.uri, '/a/uri/next')
            self.assertEqual(link.resource_cls, page.resource_cls)

            data = {
                'uri': '/a/uri/last',
            }
            data.update(common_data)
            _op.return_value.data = data
            link = page.last
            self.assertEqual(link.uri, '/a/uri/last')
            self.assertEqual(link.resource_cls, page.resource_cls)

            self.assertEqual(_op.call_count, 0)

            _op.reset_mock()

            resp = _op.return_value
            data = {
                'uri': '/a/uri',
            }
            data.update(common_data)
            data['previous_uri'] = None
            data['next_uri'] = None
            resp.data = data
            page = wac.Page(Resource, **data)

            data['uri'] = '/a/uri/first'
            link = page.first
            self.assertEqual(link.uri, '/a/uri/first')
            self.assertEqual(link.resource_cls, page.resource_cls)

            link = page.previous
            self.assertEqual(link, None)

            link = page.next
            self.assertEqual(link, None)

            data['uri'] = '/a/uri/last'
            resp.data = data
            link = page.last
            self.assertEqual(link.uri, '/a/uri/last')
            self.assertEqual(link.resource_cls, page.resource_cls)

            self.assertEqual(_op.call_count, 0)


class TestPagination(TestCase):

    @patch('wac.Page')
    def test_links(self, Page):
        page1 = Mock()
        page1.items = [1, 2, 3]
        page2 = Mock()
        page2.items = [4, 5, 6]
        page3 = Mock()
        page3.items = [7, 8]
        page1.previous = None
        page1.next = page2
        page2.previous = page1
        page2.next = page3
        page3.previous = page2
        page3.next = None

        Page.return_value = page1
        uri = '/a/uri'
        pagination = wac.Pagination(Resource1, uri, 25, page1)
        self.assertEqual(pagination.current, page1)

        for expected_page in [page2, page3]:
            page = pagination.next()
            self.assertEqual(page, expected_page)
            self.assertEqual(pagination.current, expected_page)
        page = pagination.next()
        self.assertEqual(page, None)
        self.assertEqual(pagination.current, expected_page)

        for expected_page in [page2, page1]:
            page = pagination.previous()
            self.assertEqual(page, expected_page)
            self.assertEqual(pagination.current, expected_page)
        page = pagination.previous()
        self.assertEqual(page, None)
        self.assertEqual(pagination.current, expected_page)

    @patch.object(wac.Pagination, '_page')
    @patch('wac.Page')
    def test_count(self, Page, _page):
        page1 = Mock(items=[1, 2, 3], total=8)

        def _page_patch(key, size=None):
            return [page1][key]

        _page.side_effect = _page_patch

        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 6, None)
        expected_count = int(math.ceil(page1.total / pagination.size))
        self.assertEqual(pagination.count(), expected_count)
        _page.assert_called_once_with(0, 1)

    def test_count_cached(self):
        page1 = wac.Page(Resource1, **dict(total=101, items=[]))
        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 6, page1)
        expected_count = int(math.ceil(page1.total / pagination.size))
        self.assertEqual(pagination.count(), expected_count)

    @patch.object(wac.Pagination, '_page')
    def test_index(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)

        def _page_patch(key):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 3, page1)
        self.assertEqual(pagination.current, page1)

        page = pagination[0]
        self.assertEqual(page1, page)
        page = pagination[1]
        self.assertEqual(page2, page)
        page = pagination[2]
        self.assertEqual(page3, page)
        page = pagination[-1]
        self.assertEqual(page3, page)
        page = pagination[-2]
        self.assertEqual(page2, page)
        page = pagination[-3]
        self.assertEqual(page1, page)
        with self.assertRaises(IndexError):
            pagination[-4]
        with self.assertRaises(IndexError):
            pagination[100]

    @patch.object(wac.Pagination, '_page')
    def test_slice(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)

        def _page_patch(key, data=None):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/a/uri?offset=4'
        pagination = wac.Pagination(Resource1, uri, 3, page2)
        self.assertEqual(pagination.current, page2)

        pages = [page1, page2, page3]
        self.assertEqual(pages[:], pagination[:])
        self.assertEqual(pages[::-1], pagination[::-1])
        self.assertEqual(pages[::2], pagination[::2])
        self.assertEqual(pages[1:2], pagination[1:2])
        self.assertEqual(pages[100:], pagination[100:])
        self.assertEqual(pages[3:2:12], pagination[3:2:12])

    def test_iter(self):
        page1 = Mock()
        page1.items = [1, 2, 3]
        page2 = Mock()
        page2.items = [4, 5, 6]
        page3 = Mock()
        page3.items = [7, 8]
        page4 = Mock()
        page4.items = [9]
        page1.next = page2
        page2.next = page3
        page3.next = page4
        page4.next = None

        with patch.object(Resource1.client, '_op') as _op:
            with patch.object(Resource1, 'page_cls') as page_cls:
                page_cls.return_value = page1
                resp = _op.return_value
                resp.data = {
                }

                page_cls.return_value = page1
                uri = '/a/uri'
                pagination = wac.Pagination(Resource1, uri, 25, None)
                pages = [p for p in pagination]
                self.assertEqual([page1, page2, page3, page4], pages)

                page_cls.return_value = page2
                uri = '/a/uri'
                pagination = wac.Pagination(Resource1, uri, 25, None)
                pages = [p for p in pagination]
                self.assertEqual([page2, page3, page4], pages)

    @patch.object(wac.Pagination, '_page')
    def test_first(self, _page):

        def _page_patch(key, size=None):
            return pages[key]

        _page.side_effect = _page_patch

        # multiple
        pages = [
            Mock(items=[1, 2, 3], total=5),
            Mock(items=[4, 5], total=5),
        ]
        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 3)
        with self.assertRaises(wac.MultipleResultsFound):
            pagination.one()

        # one
        pages = [
            Mock(items=[1, 2, 3], total=3),
        ]
        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 3)
        self.assertEqual(pagination.one(), pages[0])


class TestQuery(TestCase):

    def test_parse_uri(self):
        uri = '/a/uri'
        q = wac.Query(None, uri, 25)
        self.assertEqual(q._qs(), '')

        uri = '/a/uri?'
        q = wac.Query(None, uri, 25)
        self.assertEqual(q._qs(), '')

        uri = '/a/uri?a[in]=1,2&a[>]=c&b=hiya&d[endswith]=bye'
        q = wac.Query(None, uri, 25)
        self.assertEqual(
            urllib.unquote(q._qs()), 'a[>]=c&b=hiya&d[endswith]=bye&a[in]=1,2')

    def test_filter(self):
        uri = '/a/uri'
        q = wac.Query(None, uri, 25)
        q.filter(Resource1.f.a == 'b')
        self.assertEqual(q.filters[-1], ('a', 'b'))
        q.filter(Resource1.f.a != '101')
        self.assertEqual(q.filters[-1], ('a[!=]', '101'))
        q.filter(Resource1.f.b < 4)
        self.assertEqual(q.filters[-1], ('b[<]', '4'))
        q.filter(Resource1.f.b <= 5)
        self.assertEqual(q.filters[-1], ('b[<=]', '5'))
        q.filter(Resource1.f.c > 123)
        self.assertEqual(q.filters[-1], ('c[>]', '123'))
        q.filter(Resource1.f.c >= 44)
        self.assertEqual(q.filters[-1], ('c[>=]', '44'))
        q.filter(Resource1.f.d.in_(1, 2, 3))
        self.assertEqual(q.filters[-1], ('d[in]', '1,2,3'))
        q.filter(~Resource1.f.d.in_(6, 33, 55))
        self.assertEqual(q.filters[-1], ('d[!in]', '6,33,55'))
        q.filter(Resource1.f.e.contains('it'))
        self.assertEqual(q.filters[-1], ('e[contains]', 'it'))
        q.filter(~Resource1.f.e.contains('soda'))
        self.assertEqual(q.filters[-1], ('e[!contains]', 'soda'))
        q.filter(Resource1.f.f.startswith('la'))
        self.assertEqual(q.filters[-1], ('f[startswith]', 'la'))
        q.filter(Resource1.f.f.endswith('lo'))
        self.assertEqual(q.filters[-1], ('f[endswith]', 'lo'))
        self.assertEqual(
            urllib.unquote(q._qs()),
            'a=b&a[!=]=101&b[<]=4&b[<=]=5&c[>]=123&c[>=]=44&d[in]=1,2,3&'
            'd[!in]=6,33,55&e[contains]=it&e[!contains]=soda&f[startswith]=la&'
            'f[endswith]=lo')

    def test_sort(self):
        uri = '/a/uri'
        q = wac.Query(Resource1, uri, 25)
        q.sort(Resource1.f.me.asc())
        self.assertEqual(q.sorts[-1], ('sort', 'me,asc'))
        q.sort(Resource1.f.u.desc())
        self.assertEqual(q.sorts[-1], ('sort', 'u,desc'))
        self.assertEqual(urllib.unquote(q._qs()), 'sort=me,asc&sort=u,desc')

    @patch.object(wac.Pagination, '_page')
    def test_all(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)
        page1.previous = None
        page1.next = page2
        page2.previous = page1
        page2.next = page3
        page3.previous = page2
        page3.next = None

        def _page_patch(key, data=None):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        expected_items = range(1, 9)
        items = q.all()
        self.assertEqual(expected_items, items)
        self.assertEqual(q.pagination.current, page3)

    @patch.object(wac.Pagination, '_page')
    def test_one(self, _page):

        def _page_patch(key, size=None):
            return pages[key]

        _page.side_effect = _page_patch

        # none
        pages = [Mock(items=[], total=0, offset=0, fetched=False)]
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.NoResultFound):
            q.one()
        self.assertEqual(_page.call_count, 1)
        _page.reset_mock()

        # multiple
        pages = [Mock(items=[1, 2, 3], total=3, offset=0, fetched=False)]
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.MultipleResultsFound):
            q.one()
        self.assertEqual(_page.call_count, 1)
        _page.reset_mock()

        # one
        pages = [Mock(items=['one'], total=1, offset=0, fetched=False)]
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        item = q.one()
        self.assertEqual(item, 'one')
        self.assertEqual(_page.call_count, 1)
        _page.reset_mock()

    @patch.object(wac.Pagination, '_page')
    def test_one_cached(self, _page):

        # none
        page = Mock(items=[], offset=0, total=0, fetched=True)
        _page.return_value = page
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.NoResultFound):
            q.one()
        _page.assert_called_once_with(0, 2)

        # multiple
        page = Mock(items=[1, 2, 3], offset=0, total=3, fetched=True)
        _page.return_value = page
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.MultipleResultsFound):
            q.one()
        _page.assert_called_once_with(0, 2)

        # one
        page = Mock(items=['one'], offset=0, total=1, fetched=True)
        _page.return_value = page
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        item = q.one()
        self.assertEqual(item, 'one')
        _page.assert_called_once_with(0, 2)

    @patch.object(wac.Pagination, '_page')
    def test_first(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)
        page1.previous = None
        page1.next = page2
        page2.previous = page1
        page2.next = page3
        page3.previous = page2
        page3.next = None

        def _page_patch(key, size=None, data=None):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        expected_item = 1
        item = q.first()
        self.assertEqual(expected_item, item)

    @patch.object(wac.Pagination, '_page')
    def test_first_cached(self, _page):
        page = Mock(items=[1, 2, 3], offset=0, total=3)
        _page.return_value = page
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        expected_item = 1
        item = q.first()
        self.assertEqual(expected_item, item)
        self.assertEqual(_page.call_count, 1)

    @patch.object(wac.Pagination, '_page')
    @patch('wac.Page')
    def test_count(self, Page, _page):
        page1 = Mock(items=[1, 2, 3], total=8)

        def _page_patch(key, data=None):
            return [page1][key]

        _page.side_effect = _page_patch

        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        expected_count = 8
        count = q.count()
        self.assertEqual(expected_count, count)

    @patch.object(wac.Pagination, '_page')
    def test_index(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)

        def _page_patch(key, data=None):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        expected_items = range(1, 9)
        for i in xrange(q.count()):
            self.assertEqual(q[i], expected_items[i])

    @patch.object(wac.Pagination, '_page')
    def test_slice(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)

        def _page_patch(key, data=None):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        items = range(1, 9)
        self.assertEqual(q[:], items[:])
        self.assertEqual(q[::-1], items[::-1])
        self.assertEqual(q[6:4], items[6:4])
        self.assertEqual(q[6:4:12], items[6:4:12])
        self.assertEqual(q[2:7:2], items[2:7:2])
        self.assertEqual(q[6:1:-2], items[6:1:-2])

    def test_iter(self):
        page1 = Mock()
        page1.items = [0, 1, 2, 3]
        page1.total = 10
        page2 = Mock()
        page2.items = [4, 5, 6, 7]
        page2.total = 10
        page3 = Mock()
        page3.items = [8, 9]
        page3.total = 10

        page1.next = page2
        page2.next = page3
        page3.next = None

        with patch.object(Resource1, 'page_cls') as page_cls:
            with patch.object(Resource1.client, '_op') as _op:
                page_cls.side_effect = [page1, page1, page2, page3]
                resp = _op.return_value
                resp.data = {
                    '_type': 'page',
                }
                uri = '/a/uri'
                q = wac.Query(Resource1, uri, 4)
                vs = [v for v in q]
                self.assertEqual(range(10), vs)


class TestURIGen(TestCase):

    def test_single_member(self):
        gen = wac.URIGen('as', '{a}')

        class Resource(object):
            pass

        for expected, kwargs in [
            ('/as/1', dict(a=1)),
        ]:
            self.assertEqual(gen.member_uri(**kwargs), expected)

    def test_composite_member(self):
        gen = wac.URIGen('as', '{a}/{b}')

        for expected, kwargs in [
            ('/as/1/ababa', dict(a=1, b='ababa')),
        ]:
            self.assertEqual(gen.member_uri(**kwargs), expected)

    def test_parent(self):
        tree_gen = wac.URIGen('trees', '{tree}')
        apple_gen = wac.URIGen('apples', '{apple}', parent=tree_gen)

        for expected, kwargs in [
            ('/trees/1/apples', dict(tree=1)),
        ]:
            self.assertEqual(apple_gen.collection_uri(**kwargs), expected)

        for expected, kwargs in [
            ('/trees/1/apples/2', dict(tree=1, apple=2)),
        ]:
            self.assertEqual(apple_gen.member_uri(**kwargs), expected)

    def test_root(self):
        tree_gen = wac.URIGen('trees', '{tree}')
        self.assertIsNotNone(tree_gen.root_uri)

        apple_spec = wac.URIGen('trees/{tree}/apples', '{apple}')
        self.assertIsNone(apple_spec.root_uri)


class TestResource(TestCase):

    _objectify_payload = {
        '_type': 'one',
        '_uris': {
            'one_3_uri': {
                '_type': 'three',
                'key': 'one_3',
            },
            'more_3s_uri': {
                '_type': 'page',
                'key': 'more_3s',
            }
        },
        'uri': '/v1/1s/id123',
        'hi': 'there',
        'one': 2,
        'apples': [1, 2, 3],
        'two': {
            '_type': 'two',
            '_uris': {
                'threes_uri': {
                    '_type': 'page',
                    'key': 'threes',
                }
            },
            'uri': '/v2/2s/idee',
            'name': 'zeek',
            'threes_uri': '/v1/3s',
        },
        'one_3_uri': '/v1/3s/abc123',
        'more_3s_uri': '/v1/3s',
    }

    def _objectify_equal(self, o):
        # o
        self.assertItemsEqual(
            ['_type',
             '_uris',
             'uri',
             'hi',
             'two',
             'one',
             'apples',
             'one_3_uri',
             'more_3s_uri',
             ],
            o.__dict__.keys(),
        )
        self.assertEqual(o.hi, 'there')
        self.assertEqual(o.one, 2)
        self.assertEqual(o.apples, [1, 2, 3])
        self.assertEqual(o.one_3_uri, '/v1/3s/abc123')
        self.assertEqual(o.more_3s_uri, '/v1/3s')

        # o.more_3s
        with patch.object(Resource1.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'page',
                'uri': o.more_3s_uri,
            }
            self.assertTrue(isinstance(o.more_3s, wac.ResourceCollection))
            self.assertEqual(o.more_3s.uri, o.more_3s_uri)

        # o.one_three
        with patch.object(Resource2.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'three',
                '_uris': {
                    'ones_uri': {
                        '_type': 'page',
                        'key': 'ones',
                    }
                },
                'one': 'two',
                'two': 'shoes',
                'ones_uri': '/v33/1s',
            }
            self.assertItemsEqual(
                o.one_3.__dict__.keys(),
                ['ones_uri', '_type', '_uris', 'two', 'one'])
            resp.data = {
                '_type': 'page',
                '_uris': {
                },
                'uri': '/v33/1s',
            }
            self.assertTrue(isinstance(o.one_3.ones, wac.ResourceCollection))
            self.assertEqual(o.one_3.ones.uri, '/v33/1s')

        # o.two
        self.assertItemsEqual(
            ['_type',
             '_uris',
             'uri',
             'threes_uri',
             'name',
             ],
            o.two.__dict__,
        )
        self.assertEqual(o.two.name, 'zeek')
        self.assertEqual(o.two.threes_uri, '/v1/3s')
        with patch.object(Resource2.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'page',
                '_uris': {
                },
                'uri': o.two.threes_uri,
            }
            self.assertTrue(isinstance(o.two.threes, wac.ResourceCollection))
        self.assertEqual(o.two.threes.uri, o.two.threes_uri)

    def test_objectify(self):
        o = Resource1(**self._objectify_payload)
        self._objectify_equal(o)

    def test_query(self):
        q = Resource1.query
        self.assertTrue(isinstance(q, wac.Query))
        self.assertEqual(q.uri, Resource1.uri_gen.root_uri)

    @patch('wac.Client._op')
    def test_get(self, _op):
        Resource1.get('/v2/1s/gooid')
        _op.assert_called_once_with(wac.requests.get, '/v2/1s/gooid')

    @patch('wac.Client._op')
    def test_get_collection(self, _op):
        resp = _op.return_value = Mock()
        resp.data = {
            '_type': 'page',
        }
        with self.assertRaises(ValueError) as ex_ctx:
            Resource1.get('/v2/1s')
        self.assertIn(
            'Resource1 type "one" does not match "page"',
            ex_ctx.exception)

    @patch('wac.Client._op')
    def test_get_collection_lookup_failure(self, _op):
        resp = _op.return_value = Mock()
        resp.data = {
            '_type': 'page',
        }
        with self.assertRaises(ValueError) as ex_ctx:
            Resource1.get('/v2/1s')
        self.assertIn(
            'Resource1 type "one" does not match "page"',
            str(ex_ctx.exception))

    @patch('wac.Client._op')
    def test_get_member_mismatch(self, _op):
        resp = _op.return_value = Mock()
        resp.data = {
            '_type': 'two',
        }
        with self.assertRaises(ValueError) as ex_ctx:
            Resource1.get('/v2/2s/id')
        self.assertIn(
            'Resource1 type "one" does not match "two"',
            ex_ctx.exception)

    @patch('wac.Client._op')
    def test_get_member_base(self, _op):
        Resource.get('/v2/1s/gooid')
        _op.assert_called_once_with(wac.requests.get, '/v2/1s/gooid')

    @patch('wac.Client._op')
    def test_create_from_save(self, _op):
        Resource1(test='one', two=3, three=True).save()
        self.assertEqual(_op.call_count, 1)
        self.assertEqual(
            _op.call_args[0],
            (wac.requests.post, '/v2/1s')
        )
        self.assertEqual(_op.call_args[1].keys(), ['headers', 'data'])
        self.assertDictEqual(_op.call_args[1]['headers'], {
            'Content-Type': 'application/json'
        })
        self.assertDictEqual(json.loads(_op.call_args[1]['data']), {
            'test': 'one', 'two': 3, 'three': True,
        })

    @patch('wac.Client._op')
    def test_save(self, _op):
        r = Resource1(uri='/v1/1s/heat', guid='heat')
        r.save()
        _op.assert_called_once_with(
            wac.requests.put,
            '/v1/1s/heat',
            headers={'Content-Type': 'application/json'},
            data='{"guid": "heat"}')

        _op.reset_mock()
        r = Resource1(name='blah')
        r.save()
        _op.assert_called_once_with(
            wac.requests.post,
            '/v2/1s',
            headers={'Content-Type': 'application/json'},
            data='{"name": "blah"}')

    @patch('wac.Client._op')
    def test_save_objectify(self, _op):
        resp = _op.return_value = Mock()
        resp.data = self._objectify_payload
        r = Resource1(uri='/v1/1s/id123', transient='wipe')
        r.save()
        self._objectify_equal(r)
        r.save()
        self._objectify_equal(r)

    @patch('wac.Client._op')
    def test_objectify_uris(self, _op):
        class Resource4(Resource):

            type = 'four'
            uri_gen = wac.URIGen('/v1/4s', '{fours}')

        data = {
            '_type': 'four',
            '_uris': {
                'ones_uri': {'_type': 'page', 'key': 'ones'},
                'two_uri': {'_type': 'two', 'key': 'two'},
            },
            'ones_uri': '/v1/1s',
            'two_uri': '/v1/2s/id',
        }
        r1 = Resource4(**data)

        data = {
            '_type': 'four',
            '_uris': {
                'ones_uri': {'_type': 'page', 'key': 'ones'},
                'one_uri': {'_type': 'one', 'key': 'one'},
                'two_uri': {'_type': 'two', 'key': 'two'},
            },
            'ones_uri': '/v1/somthingelse/1s',
            'one_uri': '/v1/1s/eyedee',
            'two_uri': '/v1/2s/id'
        }
        r2 = Resource4(**data)

        with self.assertRaises(AttributeError):
            r1.one

        with patch.object(Resource4.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'page',
                'uri': r1.ones_uri,
            }
            self.assertTrue(isinstance(r1.ones, wac.ResourceCollection))
            self.assertTrue(r1.ones.uri, '/v1/1s')

        with patch.object(Resource4.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'two',
                'uri': r1.two_uri,
            }
            self.assertTrue(isinstance(r1.two, Resource2))
            self.assertEqual(r1.two.uri, '/v1/2s/id')

        with patch.object(Resource4.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'one',
                'uri': r2.one_uri,
            }
        self.assertTrue(isinstance(r2.one, Resource1))

        with patch.object(Resource4.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                '_type': 'page',
                'uri': r2.ones_uri,
            }
            self.assertTrue(isinstance(r2.ones, wac.ResourceCollection))
            self.assertTrue(r2.ones.uri, '/v1/1s')

    @patch('wac.Client._op')
    def test_update(self, _op):
        Resource1(uri='/v1/1s/eyedee', guid='eyedee').save()
        _op.assert_called_once_with(
            wac.requests.put,
            '/v1/1s/eyedee',
            headers={'Content-Type': 'application/json'},
            data='{"guid": "eyedee"}')

    @patch('wac.Client._op')
    def test_delete(self, _op):
        r = Resource1(uri='/v1/1s/eyedee', guid='eyedee')
        r.delete()
        _op.assert_called_once_with(wac.requests.delete, '/v1/1s/eyedee')


class TestResourceCollection(TestCase):

    def test_filter(self):
        page = Mock(
            _type='page',
            uri='/some/3s',
        )
        resources = wac.ResourceCollection(Resource3, page.uri, page)
        q = resources.filter(Resource3.f.a.ilike('b'))
        self.assertEqual(urllib.unquote(q._qs()), 'a[ilike]=b')


class TestExample(TestCase):

    def test_example(self):
        path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'example.py')
        )
        imp.load_source('example', path)
