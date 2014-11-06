===
wac
===

.. image:: https://secure.travis-ci.org/balanced/wac.png?branch=master
    :target: http://travis-ci.org/balanced/wac

To write a friendly client for a RESTful API you typically end up doing the
following:

- Write HTTP client commands for communicating with the server. These commands
  do things like marshal payloads, convert errors, invoke request hooks, etc.

- Turn responses deserialized by your client into resource objects (i.e.
  objectify the response).

- Build up queries (e.g. filter, sort) to access resources matching some
  criteria in perhaps a particular order.
  
In the ideal case the client gives your users something approximating an ORM
for your resources. This library is intended to assist you in writing such a
client provided the API you are consuming complies with some basic
conventions:

- Uses HTTP properly.

- Annotates resource representations with type and URI information.

Installation
------------

Simply::

    $ pip install wac

or if you prefer::

    $ easy_install wac

Requirements
------------

- `Python <http://python.org/>`_ >= 2.6, < 3.0
- `Requests <https://github.com/kennethreitz/requests/>`_ >= 1.2.3

Usage
-----

Lets work through an example. The code for this example is in ``example.py``.

- First you import wac:

.. code-block:: python

    import wac
    
- Next define the version of your client:

.. code-block:: python

    __version__ = '1.0'
    
- Also define the configuration which all ``Client``\s will use by default:

.. code-block:: python

    default_config = wac.Config(None)
    
- Now be nice and define a function for updating the configuration(s):

.. code-block:: python

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

- Now the big one, define your ``Client`` which is what will be used to talk to
  a server:

.. code-block:: python

    class Client(wac.Client):

        config = default_config
    
        def _serialize(self, data):
            data = json.dumps(data, default=self._default_serialize)
            return 'application/json', data
    
        def _deserialize(self, response):
            if response.headers['Content-Type'] != 'application/json':
                raise Exception(
                    "Unsupported content-type '{}'"
                    .format(response.headers['Content-Type'])
                )
            data = json.loads(response.content)
            return data

- Then define your base ``Resource``:

.. code-block:: python

    class Resource(wac.Resource):
    
        client = Client()
        registry = wac.ResourceRegistry()
  
- And finally your actual resources:

.. code-block:: python

    class Playlist(Resource):

        type = 'playlist'
    
        uri_gen = wac.URIGen('/v1/playlists', '{playlist}')
    
    
    class Song(Resource):
    
        type = 'song'
    
        uri_gen = wac.URIGen('/v1/songs', '{song}')
 

- Done! Now you can do crazy stuff like this:

.. code-block:: python

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

1. Fork it
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Write your code **and tests**
4. Ensure all tests still pass (`python setup.py test`)
5. Commit your changes (`git commit -am 'Add some feature'`)
6. Push to the branch (`git push origin my-new-feature`)
7. Create new pull request
