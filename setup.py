import re

try:
    import setuptools
except ImportError:
    import distutils.core
    setup = distutils.core.setup
else:
    setup = setuptools.setup


setup(
    name='txwac',
    version=(re
             .compile(r".*__version__ = '(.*?)'", re.S)
             .match(open('txwac.py').read())
             .group(1)),
    url='https://github.com/trenton42/txwac/',
    license=open('LICENSE').read(),
    author='wac',
    author_email='wac@example.com',
    description='Writing RESTful API clients.',
    long_description=(
        open('README.rst').read() + '\n\n' +
        open('HISTORY.rst').read()
    ),
    py_modules=['wac'],
    package_data={'': ['LICENSE']},
    include_package_data=True,
    tests_require=[
        'mock>=0.8',
        'simplejson >= 2.1',
        'unittest2 >= 0.5.1',
        'iso8601',
    ],
    install_requires=[
        'treq'
    ],
    test_suite='tests',
    classifiers=[
        'Intended Audience :: Developers',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ],
)
