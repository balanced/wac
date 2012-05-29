===
wac
===

To write a friendly client for a RESTful API you typically end up doing the
following:

- Write HTTP client commands when communicating with the server. These commands
  do things like marshal payloads, convert errors, invoke request hooks, etc.

- Turn responses deserialized by your client into resource objects (i.e.
  objectify the response).

- Build up queries (e.g. filter, sort) to access resources matching some
  criteria in perhaps a particular order.
  
In the ideal case the client gives your users something approximating an ORM
for your resources. This library is intended to assist you in writing such a
client provided the API you are consuming complies with some basic
expectations:

- Uses HTTP properly.

- Identifies resources using URIs.

- Names nested resources consistently.

Installation
------------

Simply::

    $ pip install wac

or if you prefer::

    $ easy_install wac

Requirements
------------

- `Python <http://python.org/>`_ >= 2.6, < 3.0
- `Requests <https://github.com/kennethreitz/requests/>`_ >= 0.11.1  

Usage
-----

Lets work through an example. The code for this example is in ``example.py``.

- First you import wac::

    import wac
    
- Next define your the version of your client::

    __version__ = '1.0'
    
- Also define the default configuration which all `Client` will use by
  default::

    default_config = wac.Config(None)
    
- Now be nice and define a function for updating client configuration(s)::

    def configure(root_url, **kwargs):
        default = kwargs.pop('default', True)
        kwargs['client_agent'] = 'example-client/' + __version__
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers']['Accept-Type'] = 'application/json'
        if default:
            default_config.reset(root_url, **kwargs)
        else:
            Client.config = wac.Config(root_url, **kwargs

- Now the big one, define your `Client` which is what your client will use to
  talk to a server::

    class Client(wac.Client):

        config = default_config
    
        def _serialize(self, data):
            data = json.dumps(data, default=self._default_serialize)
            return 'application/json', data
    
        def _deserialize(self, response):
            if response.headers['Content-Type'] != 'application/json':
                raise Exception("Unsupported content-type '{}'"
                    .format(response.headers['Content-Type']))
            data = json.loads(response.content)
            return data

- Then define your base `Resource`::

    class Resource(wac.Resource):
    
        client = Client()
        registry = wac.ResourceRegistry()
  
- And finally your actual resources::

    class Playlist(Resource):
    
        uri_spec = wac.URISpec('playlists', 'guid', root='/v1')
        
        
    class Song(Resource):
    
        uri_spec = wac.URISpec('songs', 'guid') 

- Done! Now you can do crazy stuff like this::

    import example
    
    example.configure('https://api.example.com', auth=('user', 'passwd'))
    
    q = (example.Playlist.query()
        .filter(Playlist.f.tags.contains('nuti'))
        .filter(~Playlist.f.tags.contains('sober'))
        .sort(Playlist.f.created_at.desc()))
    for playlist in q:
        song = playlist.songs.create(
            name='Flutes',
            length=1234,
            tags=['nuti', 'fluti'])
        song.length += 101
        song.save()

Contributing
------------
Yes please.
