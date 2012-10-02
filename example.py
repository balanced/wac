"""
Example client implmented using wac. See `README` for a guided walk-though
based on this example client.
"""
from datetime import datetime
import json

import iso8601
import wac


__version__ = '1.0'


default_config = wac.Config(None)


def configure(root_url, **kwargs):
    """"
    Notice that `configure` can either apply to the default configuration or
    `Client.config`, which is the  configuration used by the current thread
    since `Client` inherits form `threading.local`.
    """
    default = kwargs.pop('default', True)
    kwargs['client_agent'] = 'example-client/' + __version__
    if 'headers' not in kwargs:
        kwargs['headers'] = {}
    kwargs['headers']['Accept-Type'] = 'application/json'
    if default:
        default_config.reset(root_url, **kwargs)
    else:
        Client.config = wac.Config(root_url, **kwargs)


class Client(wac.Client):
    """"
    Here the client handles serializing and deserializing the request and
    response payloads. It also does some API specific massaging of the data
    (e.g. assumes all mapping keys ending with "_at" are iso8601 formatted
    date-time objects and parses them) as well as converting some exception
    types from wac.Error.
    """

    config = default_config

    def _op(self, *args, **kwargs):
        try:
            return super(Client, self)._op(*args, **kwargs)
        except wac.Error, ex:
            raise self._convert_exception(ex)

    @staticmethod
    def _convert_exception(ex):
        if not hasattr(ex, 'type'):
            return ex
        if ex.type == PlaylistError.EXPLODED:
            ex = PlaylistError(*ex.args, **ex.__dict__)
        return ex

    @staticmethod
    def _default_serialize(o):
        if isinstance(o, datetime):
            return o.isoformat() + 'Z'
        raise TypeError(
            'Object of type {} with value of {} is not JSON serializable'
            .format(type(o), repr(o)))

    def _serialize(self, data):
        data = json.dumps(data, default=self._default_serialize)
        return 'application/json', data

    def _deserialize(self, response):
        if response.headers['Content-Type'] != 'application/json':
            raise Exception("Unsupported content-type '{}'".format(
                            response.headers['Content-Type']))
        data = json.loads(response.content)
        return self._parse_deserialized(data)

    @staticmethod
    def _parse_deserialized(e):
        if isinstance(e, dict):
            for key in e.iterkeys():
                if key.endswith('_at') and isinstance(e[key], basestring):
                    e[key] = iso8601.parse_date(e[key])
        return e


class Error(Exception):

    def __init__(self, *args, **kwargs):
        super(Error, self).__init__(*args)
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def __repr__(self):
        attrs = ', '.join(['{}={}'.format(k, repr(v))
                           for k, v in self.__dict__.iteritems()])
        return '{}({}, {})'.format(
            self.__class__.__name__,
            ' '.join(self.args),
            attrs)


class PlaylistError(Error):

    EXPLODED = 'paylist-exploded'


class Resource(wac.Resource):
    """
    The `registry` attribute is used to store information about all resources
    then used when objectifying resource representations deseralized by your
    `Client`.
    """

    client = Client()
    registry = wac.ResourceRegistry()


class Playlist(Resource):

    uri_spec = wac.URISpec('playlists', 'guid', root='/v1')


class Song(Resource):

    uri_spec = wac.URISpec('songs', 'guid')
