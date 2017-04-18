# Replyify Python bindings
# API docs at http://replyify.com/api/docs
# Authors:
# Marco DiDomenico <marco@replyify.com>

# Configuration variables
import os
access_token = os.getenv('REPLYIFY_ACCESS_TOKEN', None)
refresh_token = os.getenv('REPLYIFY_REFRESH_TOKEN', None)
api_base = os.getenv('REPLYIFY_API_BASE', 'https://api.replyify.com')
upload_api_base = os.getenv('REPLYIFY_API_UPLOAD_BASE', 'https://uploads.replyify.com')
api_version = None
verify_ssl_certs = bool(os.getenv('REPLYIFY_API_VERIFY_SSL_CERTS', True))
default_http_client = None


from replyify.utils import json, logger  # noqa

from replyify.resources import (  # noqa
    Account,
    Campaign,
    CampaignContact,
    Contact,
    ContactField,
    Note,
    Reply,
    Signature,
    Tag,
    Template,
    Timeline,
    TimelineItem,
    TimelineJob,
)
