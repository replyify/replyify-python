Official Replyify Bindings for Python
=====================================

A Python library for Replyify's API.


Installation
------------

You can install this package by using the pip tool and installing:
::
    $ pip install replyify
    
Or:
::
    $ easy_install replyify
    

Register Your Application with Replyify
----------------------------------------

1) Sign up for Replyify at https://app.replyify.com/access/signup
2) Register your application at https://app.replyify.com/oauth2/applications/register
3) Use OAuth2 workflow to obtain an access token for a user
4) Make calls on the users behalf

Credentials:
API calls require an access token obtained using OAuth2.  Once you obtain an access token for a user you can set the `REPLYIFY_ACCESS_TOKEN` with environment variables, manually after importing `replyify`, or with each request:
::
	$ export REPLYIFY_ACCESS_TOKEN='{ your access token }'
	...

You can also set them manually:
::
	import replyify
	replyify.access_token = '{ add key here }'
	...

or with each request:
::
	import replyify
	campaign = replyify.Campaign.retrieve('asdf-...-1234', access_token='{ access token here }')

	

Using the Replyify API
----------------------

Documentation for the python bindings can be found here:

- https://app.replyify.com/api/docs
- http://replyify.com/api/docs/python

In the standard documentation (the first link), most of the reference pages will have examples in Replyify's official bindings (including Python). Just click on the Python tab to get the relevant documentation.

In the full API reference for python (the second link), the right half of the page will provide example requests and responses for various API calls.