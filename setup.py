import os
import sys
import warnings

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

path, script = os.path.split(sys.argv[0])
os.chdir(os.path.abspath(path))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'replyify'))

with open(os.path.join(os.path.dirname(__file__), 'VERSION'), 'r') as v:
    VERSION = v.read()

with open(os.path.join(os.path.dirname(__file__), 'README.rst')) as readme:
    README = readme.read()

install_requires = []
author_email = 'team@replyify.com'
if sys.version_info < (2, 6):
    warnings.warn(
        'Python 2.5 is not officially supported by Replyify. '
        'If you have any questions, please file an issue on Github or '
        'contact us at {}.'.format(author_email),
        DeprecationWarning)
    install_requires.append('requests >= 0.8.8, < 0.10.1')
    install_requires.append('ssl')
else:
    install_requires.append('requests >= 0.8.8')


setup(
    name='replyify',
    version=VERSION,
    description='Replyify REST API Client',
    long_description=README,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    keywords='replyify rest api client',
    url='http://github.com/replyify/replyify-python',
    author='Replyify',
    author_email='team@replyify.com',
    license='MIT',
    packages=['replyify'],
    install_requires=install_requires,
    include_package_data=True,
    zip_safe=False
)
