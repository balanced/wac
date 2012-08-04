from __future__ import division
from __future__ import unicode_literals

import json
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

    uri_spec = wac.URISpec('1s', 'guid', root='/v2')


class Resource2(Resource):

    uri_spec = wac.URISpec('2s', 'sid')


class Resource3(Resource):

    uri_spec = wac.URISpec('3s', 'id')


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
            config={'keepalive': False},
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
            config={'keepalive': False},
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
            config={'keepalive': True},
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
            config={'keepalive': False},
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
            config={'keepalive': True},
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
            config={'keepalive': True},
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
        ex.response.content = ('{"status": "Bad Request", "status_code": '
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
            self.cli.config.error_class = convert_error

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
             'config': {'keepalive': False},
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
        ex.response.content = ('{"status": "Bad Request", "status_code": '
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
             'config': {'keepalive': False},
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
    def test_fetch(self, get):
        get.__name__ = 'get'
        with patch.object(Resource.client, 'config') as config:
            config.root_url = 'http://ex.com'
            config.echo = False
            config.allow_redirects = False
            config.keep_alive = True
            config.auth = ('bob', 'passwerd')
            response = get.return_value
            data = {
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
            page = wac.Page(Resource, '/a/uri')
            fetched1 = page.fetch()
            fetched2 = page.fetch()

        get.assert_called_once_with(
            'http://ex.com/a/uri',
            headers={},
            auth=('bob', 'passwerd'),
            config={'keepalive': True},
            allow_redirects=False)
        self.assertTrue(fetched1 is fetched2)
        self.assertItemsEqual(
            fetched1.keys(),
            ['first_uri', 'last_uri', 'limit', 'next_uri', 'offset',
             'previous_uri', 'total', 'items',
             ])
        for k in [
            'first_uri', 'last_uri', 'limit', 'next_uri', 'offset',
            'previous_uri', 'total',
            ]:
            self.assertEqual(fetched1[k], data[k])
        self.assertEqual(len(fetched1['items']), len(data['items']))

    @patch('wac.requests.get')
    def test_links(self, get):
        get.__name__ = 'get'
        with patch.object(Resource.client, 'config') as config:
            config.root_url = 'http://ex.com'
            config.echo = False
            config.allow_redirects = False
            config.auth = ('bob', 'passwerd')
            config.keep_alive = False

            response = get.return_value
            data = {
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
            response.headers = {
                'Content-Type': 'application/json',
                }
            response.content = to_json(data)
            page = wac.Page(Resource, '/a/uri')

            link = page.first
            self.assertEqual(link.uri, '/a/uri/first')
            self.assertEqual(link.resource, page.resource)
            link = page.previous
            self.assertEqual(link.uri, '/a/uri/prev')
            self.assertEqual(link.resource, page.resource)
            link = page.next
            self.assertEqual(link.uri, '/a/uri/next')
            self.assertEqual(link.resource, page.resource)
            link = page.last
            self.assertEqual(link.uri, '/a/uri/last')
            self.assertEqual(link.resource, page.resource)

            get.assert_called_once_with(
                'http://ex.com/a/uri',
                headers={},
                config={'keepalive': False},
                auth=('bob', 'passwerd'),
                allow_redirects=False)

            get.reset_mock()

            response = get.return_value
            data = {
                'first_uri': '/a/uri/first',
                'previous_uri': None,
                'next_uri': None,
                'last_uri': '/a/uri/last',
                'total': 100,
                'offset': 44,
                'limit': 2,
                'items': [
                    ],
                }
            response.headers = {
                'Content-Type': 'application/json',
                }
            response.content = to_json(data)
            page = wac.Page(Resource, '/a/uri')

            link = page.first
            self.assertEqual(link.uri, '/a/uri/first')
            self.assertEqual(link.resource, page.resource)
            link = page.previous
            self.assertEqual(link, None)
            link = page.next
            self.assertEqual(link, None)
            link = page.last
            self.assertEqual(link.uri, '/a/uri/last')
            self.assertEqual(link.resource, page.resource)

            get.assert_called_once_with(
                'http://ex.com/a/uri',
                headers={},
                auth=('bob', 'passwerd'),
                allow_redirects=False,
                config={'keepalive': False})


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
        pagination = wac.Pagination(None, uri, 25)
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
        page1_unfetched = Mock(fetched=False)
        page1_fetched = Mock(items=[1, 2, 3], total=8, fetched=True)

        def _page_patch(key, size=None, data=None):
            return [page1_fetched][key]

        _page.side_effect = _page_patch

        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 6, None)
        expected_count = int(math.ceil(page1_fetched.total / pagination.size))
        self.assertEqual(pagination.count(), expected_count)
        _page.assert_called_once_with(0, data=None)

    def test_count_cached(self):
        page1 = dict(total=101, items=[])
        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 6, page1)
        expected_count = int(math.ceil(page1['total'] / pagination.size))
        self.assertEqual(pagination.count(), expected_count)

    @patch.object(wac.Pagination, '_page')
    def test_index(self, _page):
        page1 = Mock(items=[1, 2, 3], total=8)
        page2 = Mock(items=[4, 5, 6], total=8)
        page3 = Mock(items=[7, 8], total=8)

        def _page_patch(key, data=None):
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
        page2_data = dict(items=[4, 5, 6], total=8)
        page2 = Mock(**page2_data)
        page3 = Mock(items=[7, 8], total=8)

        def _page_patch(key, data=None):
            return [page1, page2, page3][key]

        _page.side_effect = _page_patch

        uri = '/a/uri?offset=4'
        pagination = wac.Pagination(None, uri, 3, page2_data)
        self.assertEqual(pagination.current, page2)

        pages = [page1, page2, page3]
        self.assertEqual(pages[:], pagination[:])
        self.assertEqual(pages[::-1], pagination[::-1])
        self.assertEqual(pages[::2], pagination[::2])
        self.assertEqual(pages[1:2], pagination[1:2])
        self.assertEqual(pages[100:], pagination[100:])
        self.assertEqual(pages[3:2:12], pagination[3:2:12])

    @patch('wac.Page')
    def test_iter(self, Page):
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

        Page.return_value = page1
        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 25)
        pages = [p for p in pagination]
        self.assertEqual([page1, page2, page3, page4], pages)

        Page.return_value = page2
        uri = '/a/uri'
        pagination = wac.Pagination(None, uri, 25)
        pages = [p for p in pagination]
        self.assertEqual([page2, page3, page4], pages)

    @patch.object(wac.Pagination, '_page')
    def test_first(self, _page):

        def _page_patch(key, data=None):
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

        def _page_patch(key, size=None, data=None):
            return pages[key]

        _page.side_effect = _page_patch

        # none
        pages = [Mock(items=[], total=0, offset=0, fetched=False)]
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.NoResultFound):
            q.one()
        self.assertEqual(_page.call_count, 4)
        _page.reset_mock()

        # multiple
        pages = [Mock(items=[1, 2, 3], total=3, offset=0, fetched=False)]
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.MultipleResultsFound):
            q.one()
        self.assertEqual(_page.call_count, 3)
        _page.reset_mock()

        # one
        pages = [Mock(items=['one'], total=1, offset=0, fetched=False)]
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        item = q.one()
        self.assertEqual(item, 'one')
        self.assertEqual(_page.call_count, 3)
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
        _page.assert_called_once_with(0, data=None)

        # multiple
        page = Mock(items=[1, 2, 3], offset=0, total=3, fetched=True)
        _page.return_value = page
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        with self.assertRaises(wac.MultipleResultsFound):
            q.one()
        _page.assert_called_once_with(0, data=None)

        # one
        page = Mock(items=['one'], offset=0, total=1, fetched=True)
        _page.return_value = page
        uri = '/ur/is'
        q = wac.Query(Resource1, uri, 3)
        _page.reset_mock()
        item = q.one()
        self.assertEqual(item, 'one')
        _page.assert_called_once_with(0, data=None)

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
        page = Mock(items=[1, 2, 3], offset=0, total=3, fetched=True)
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

        with patch('wac.Page') as Page:
            Page.side_effect = [page1, page1, page2, page3]
            uri = '/a/uri'
            q = wac.Query(None, uri, 4)
            vs = [v for v in q]
            self.assertEqual(range(10), vs)


class TestURISpec(TestCase):

    def test_single_id(self):
        spec = wac.URISpec('as', 'id')

        class Resource(object):
            pass

        for uri, expected in [
            ('/as', (True, {'collection': True, 'page_size': 25})),
            ('/as/1', (True, {'collection': False, 'id': '1'})),
            ('/as/1/ababa', (False, {})),
            ('/version1/as', (True, {'collection': True, 'page_size': 25})),
            ('/version2/as/1', (True, {'collection': False, 'id': '1'})),
            ('/version3/as/1/ababa', (False, {})),
            ('/no/way', (False, {})),
            ('/no', (False, {})),
            ('no', (False, {})),
            ]:
            self.assertEqual(spec.match(uri), expected)

    def test_composite_id(self):
        spec = wac.URISpec('as', ('version', 'id'))

        for uri, expected in [
            ('/as', (True, {'collection': True, 'page_size': 25})),
            ('/as/1', (False, {})),
            ('/as/1/ababa',
             (True, {'collection': False, 'id': '1', 'version': 'ababa'})),
            ('/version1/as', (True, {'collection': True, 'page_size': 25})),
            ('/version2/as/1', (False, {})),
            ('/version3/as/1/ababa',
             (True, {'collection': False, 'id': '1', 'version': 'ababa'})),
            ('/version3/as/1/aba/ba', (False, {})),
            ('/no/way', (False, {})),
            ('/no', (False, {})),
            ('no', (False, {})),
            ]:
            self.assertEqual(spec.match(uri), expected)


class TestResource(TestCase):

    _objectify_payload = {
        'uri': '/v1/1s/id123',
        'hi': 'there',
        'one': 2,
        'apples': [1, 2, 3],
        'two': {
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
            ['uri',
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
        self.assertTrue(isinstance(o.more_3s, wac.ResourceCollection))
        self.assertEqual(o.more_3s.uri, o.more_3s_uri)

        # o.one_three
        with patch.object(Resource2.client, '_op') as _op:
            resp = _op.return_value = Mock()
            resp.data = {
                'one': 'two',
                'two': 'shoes',
                'ones_uri': '/v33/1s',
                }
            self.assertItemsEqual(
                o.one_3.__dict__.keys(),
                ['ones_uri', 'two', 'one'])
            self.assertTrue(isinstance(o.one_3.ones, wac.ResourceCollection))
            self.assertEqual(o.one_3.ones.uri, '/v33/1s')

        # o.two
        self.assertItemsEqual(
            ['uri',
             'name',
             'threes_uri',
             ],
            o.two.__dict__,
            )
        self.assertEqual(o.two.name, 'zeek')
        self.assertEqual(o.two.threes_uri, '/v1/3s')
        self.assertTrue(isinstance(o.two.threes, wac.ResourceCollection))
        self.assertEqual(o.two.threes.uri, o.two.threes_uri)

    def test_objectify(self):
        o = Resource1(**self._objectify_payload)
        self._objectify_equal(o)

    def test_query(self):
        q = Resource1.query
        self.assertTrue(isinstance(q, wac.Query))
        self.assertEqual(q.uri, Resource1.uri_spec.collection_uri)

    @patch('wac.Client._op')
    def test_get(self, _op):
        Resource1.get('/v2/1s/gooid')
        _op.assert_called_once_with(wac.requests.get, '/v2/1s/gooid')

    @patch('wac.Client._op')
    def test_get_collection(self, _op):
        with self.assertRaises(ValueError) as ex_ctx:
            Resource1.get('/v2/1s')
        self.assertIn('', ex_ctx.exception)

    @patch('wac.Client._op')
    def test_get_collection(self, _op):
        with self.assertRaises(ValueError) as ex_ctx:
            Resource1.get('/v2/1s')
        self.assertIn(
            "'/v2/1s' resolves to a Resource1 collection",
            str(ex_ctx.exception))

    @patch('wac.Client._op')
    def test_get_member_mismatch(self, _op):
        with self.assertRaises(ValueError) as ex_ctx:
            Resource1.get('/v2/2s/id')
        self.assertIn(
            "'/v2/2s/id' resolves to a Resource2 member which is not a "
            "subclass of Resource1",
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

            uri_spec = wac.URISpec('4s', 'guid')

        data = {
            'ones_uri': '/v1/1s',
            'two_uri': '/v1/2s/id',
            }
        r1 = Resource4(**data)

        data = {
            'ones_uri': '/v1/somthingelse/1s',
            'one_uri': '/v1/1s/eyedee',
            'two_uri': '/v1/2s/id'
            }
        r2 = Resource4(**data)

        with self.assertRaises(AttributeError):
            r1.one
        self.assertTrue(isinstance(r1.ones, wac.ResourceCollection))
        self.assertTrue(r1.ones.uri, '/v1/1s')
        self.assertTrue(isinstance(r1.two, Resource2))
        self.assertEqual(r1.two_uri, '/v1/2s/id')

        self.assertTrue(isinstance(r2.one, Resource1))
        self.assertTrue(isinstance(r2.ones, wac.ResourceCollection))
        self.assertTrue(r2.ones.uri, '/v1/1s')
        self.assertTrue(isinstance(r2.two, Resource2))
        self.assertEqual(r2.two_uri, '/v1/2s/id')

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
