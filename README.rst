=====
txwac
=====

This is a `Twisted <https://twistedmatrix.com/trac/>` fork of `wac <https://github.com/bninja/wac>`. See the wac documentation for more details.

This fork operates nearly identically to wac except for these exceptions:

- Everything that hits the wire returns a Deferred
- Multi-page iteration is not possible
- len(obj) is not possible on objects that hit the wire to get the count
- This uses `treq <https://github.com/dreid/treq>` which is not 100% compatible with requests. Most notably, headers are handled differently and response objects have slightly different attribute names

TODO
----

- Conversion of the original wac tests to trial based tests. The tests that are here will not work correctly