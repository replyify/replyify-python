# Replyify Python bindings
# API docs at http://replyify.com/api/docs
# Authors:
# Marco DiDomenico <marco@replyify.com>

# Configuration variables

api_key = None
api_base = 'https://api.replyify.com'
upload_api_base = 'https://uploads.replyify.com'
api_version = None
verify_ssl_certs = True
default_http_client = None


from replyify.utils import json, logger  # noqa
