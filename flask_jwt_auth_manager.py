# Copyright (C) 2025-2026 House Gordon Software Company LTD
# All Rights Reserved
# License: Proprietary
# Version: 0.2

##
## DO NOT MODIFY THIS FILE
##

"""
This is an ugly hack to parse JWT Authorization (implicily: after NGINX + OAuth2-Proxy).
It assumes the authentication process already completed successfully (by OAuth2-Proxy)
and does NOT try to validate the signature of the JWT token - only extract the email/names from it.

Typical Usage:

----------------
    from flask import Flask
    from flask_jwt_auth_manager import JWTAuthManager, current_jwt_user, jwt_auth_required

    app = Flask(__name__)
    JWTAuthManager(app) # Initialization, with default values

    @app.route("/foo")
    @jwt_auth_required
    def foo():
        user = current_jwt_user
        # "user" is an object with the JWT fields, often "email".
        # If coming from Google (and properly configured), you'll also have ".given_name" ".family_name", etc.
        return "Hello " + user.email
----------------

When running locally for devleopment/debugging, and NOT behind a proxy,
the code will "fake" a dummy user as if there's a successful login.
The default user is "john.doe@example.com". You can change it using the options below.
Enable flask's debug for for this to work.


Configuration options (with default values):

# The HTTP Request header name. Rarely changed.
app.config['JWT_AUTH_AUTHORIZATION_REQUEST_HEADER_NAME'] = "Authorization"

# The HTTP Authentication Token prefix string. Rarely Changed
app.config['JWT_AUTH_BEARER_PREFIX'] = "Bearer"

# For local development/debugging (when there's no NGINX/OAuth2-proxy configured):
# If this setting is enabled (which is the default if in DEBUG mode),
# and the request is not behind a proxy (i.e. local flask app running on 127.0.0.1),
# Then afake user will be reported as if authenticated.
# The email/name of the user can be configured (below)
app.config['JWT_AUTH_DUMMY_USER_IF_NO_PROXY'] = (TRUE if DEBUG is TRUE)

app.config['JWT_AUTH_DUMMY_USER_EMAIL'] = "john.doe@example.com"
app.config['JWT_AUTH_DUMMY_USER_FIRST_NAME'] = "John"
app.config['JWT_AUTH_DUMMY_USER_LAST_NAME'] = "Doe"

# If TRUE, details about JWT Authentication decoding and values will be printed as warnings.
app.config['JWT_AUTH_DEBUG'] = (TRUE if running in debug mode)

"""


import sys
import base64
import json

from pprint import pformat
from functools import wraps

from flask import request,current_app,has_request_context,g,abort
from werkzeug.local import LocalProxy



class JWTAuthError(ValueError):
    def __init__(self, message, auth_header_value):
        super().__init__(message)
        self.auth_header_value = auth_header_value


def decode_request_auth_bearer_dict(request_header_name="Authorization",
                                    bearer_prefix="Bearer"):
    """
    Decodes the JWT bearer token from the 'Authorization' header of the request.
    Uses flask's "request" object.

    This function DOES NOT verify the signature if the JWT token.

    Raises:
        JWTAuthError: If the 'Authorization' header is missing, malformed,
                      or the JWT token is invalid.

    Returns:
        dict: The decoded claims (payload) of the JWT token.

    A properly setup google-oauth2 (with scope of "profile") will return a dictionary such as:

    {
      'at_hash': 'q8GFGb2f5Wkes-1244351',
      'aud': '1234567890-6jbadsfasdvbfgfbs.apps.googleusercontent.com',
      'azp': '1234567890-6jbadsfasdvbfgfbs.apps.googleusercontent.com',
      'email': 'assaf.gordon@renertschool.ca',
      'email_verified': True,
      'exp': 1856311671,
      'family_name': 'Gordon',
      'given_name': 'Assaf',
      'hd': 'renertschool.ca',
      'iat': 1858412071,
      'iss': 'https://accounts.google.com',
      'name': 'Assaf Gordon',
      'picture': 'https://lh3.googleusercontent.com/a/ACg8ocLmmGSdRcw_vnfkADean3902jnvads-KQ-fmvoiKSA=s96-c',
      'sub': '1111434664274134575008'
    }

    NOTE: if "scope" does not contain "profile", you won't get "Given Name/Family Name" fields,
    only the "email" (might be good enough, depending on your needs).
    For example/details see:
    https://github.com/oauth2-proxy/oauth2-proxy/issues/1557#issuecomment-1230581907
    https://github.com/oauth2-proxy/oauth2-proxy/issues/1557#issuecomment-1708447079
    """
    auth_header = request.headers.get(request_header_name)
    if not auth_header:
        raise JWTAuthError(f"Missing '{request_header_name}' authorization request header",
                           auth_header_value=auth_header)

    if not auth_header.startswith(bearer_prefix + " "):
        raise JWTAuthError(f"Authorization request header does not start with prefix '{bearer_prefix}'",
                           auth_header_value=auth_header)

    # Get the encoded value after "Bearer"
    try:
        jwt_token = auth_header.split(" ")[1]
    except IndexError:
        raise JWTAuthError(f"Bearer token malformed: token missing after prefix '{bearer_prefix} '",
                           auth_header_value=auth_header)


    # Expected JWT format: header.payload.signature
    # Extract the payload, ignore the header (and sadly, the signature)
    try:
        payload_encoded = jwt_token.split('.')[1]
    except IndexError:
        raise JWTAuthError("JWT token malformed: payload section is missing",
                           auth_header_value=auth_header)

    # Decode the payload (handle Base64Url)
    try:
        payload_encoded += '=' * (-len(payload_encoded) % 4) # Add padding
        payload_json = base64.urlsafe_b64decode(payload_encoded)
    except (binascii.Error) as e:
        # binascii.Error specifically for incorrect base64 padding or invalid characters
        raise JWTAuthError(f"Failed to base64 decode JWT payload: {e}",
                           auth_header_value=auth_header) from e


    # Decode the JSON data
    try:
        claims = json.loads(payload_json)
    except json.JSONDecodeError as e:
        raise JWTAuthError(f"Failed to parse JWT payload as JSON: {e}",
                           auth_header_value=auth_header) from e

    return claims



class JWTAuthUser:
    # Just a thin wrapper from the decoded JWT Auth Bearer Dictionary
    #
    # Given keyword arguments in the constructor, sets them as attributes.
    # Very ugly, but works for our purposes.
    # Later on, could be made into a proper "user" class,
    # with email, user-id, etc.
    #
    #
    # TODO: adapt this to work with Flask-Login (e.g. implement "is_anonyumous")
    #
    # UGLY HACK ALERT: Implicit assumtion that the JWT data comes from google,
    # which provides "given_name" and "family_name" but not "first_name", "last_name" -
    # so those atrributes are created as well.
    def __init__(self, *args, **kwargs):
        self.auth_attributes = set()
        for key, value in kwargs.items():
            self.auth_attributes.add(key)
            setattr(self, key, value)
        self._fudge_google_user_names()

    def _fudge_google_user_names(self):
        ## Google-OAuth2 gives user "family_name" and "given_name" fields,
        ## duplicate them as first_name/last_name.
        self._sync_attributes("given_name","first_name")
        self._sync_attributes("family_name","last_name")

    def __str__(self):
        # Helper function: we assume/hope we have at least "email" field
        email = getattr(self,'email','No-Email-Attribute')
        return f"JWTAuthUser(email={email})"

    def _copy_attributes(self,from_attr, to_attr):
        setattr(self, to_attr, getattr(self, from_attr))
        self.auth_attributes.add(to_attr)

    def _sync_attributes(self,attr1_name, attr2_name):
        if hasattr(self, attr1_name) and not hasattr(self,attr2_name):
            self._copy_attributes(attr1_name,attr2_name)
        if not hasattr(self, attr1_name) and hasattr(self,attr2_name):
            self._copy_attributes(attr2_name,attr1_name)

    def as_dict(self):
        d = {}
        for k in self.auth_attributes:
            d[k] = getattr(self,k)
        return d



class JWTAuthManager:
    """
    A Flask extension for managing JWT authentication, inspired by Flask-Login.
    """

    def __init__(self, app=None):
        self.app = app

        # Default values will be set here, then optionally overridden by app.config
        self.authorization_request_header_name = "Authorization"
        self.bearer_prefix = "Bearer"
        self.dummy_user_email = "john.doe@example.com"
        self.dummy_user_first_name = "John"
        self.dummy_user_last_name = "Doe"
        self.logout_path = "/oauth2/sign_out"
        self.debug = None # Will be set based on app.debug or config
        self.dummy_user_if_no_proxy = None # Will be set based on .debug

        if app is not None:
            self.init_app(app)


    def init_app(self, app):
        self.app = app

        app_config = app.config

        self.authorization_request_header_name = app_config.get(
            'JWT_AUTH_AUTHORIZATION_REQUEST_HEADER_NAME',
            self.authorization_request_header_name
        )
        self.bearer_prefix = app_config.get(
            'JWT_AUTH_BEARER_PREFIX',
            self.bearer_prefix
        )
        self.dummy_user_email = app_config.get(
            'JWT_AUTH_DUMMY_USER_EMAIL',
            self.dummy_user_email
        )
        self.dummy_user_first_name = app_config.get(
            'JWT_AUTH_DUMMY_USER_FIRST_NAME',
            self.dummy_user_first_name
        )
        self.dummy_user_last_name = app_config.get(
            'JWT_AUTH_DUMMY_USER_LAST_NAME',
            self.dummy_user_last_name
        )
        self.logout_path = app_config.get(
            'JWT_AUTH_LOGOUT_PATH',
            self.logout_path
        )

        # Special handling for debug: use specific config if set, otherwise app.debug
        debug_config_value = app_config.get('JWT_AUTH_DEBUG')
        if debug_config_value is not None:
            self.debug = debug_config_value
        else:
            self.debug = app.debug


        # Special handling for faking a user: enable if DEBUG by default.
        dummy_user_config_value = app_config.get('JWT_AUTH_DUMMY_USER_IF_NO_PROXY')
        if dummy_user_config_value is not None:
            self.dummy_user_if_no_proxy = bool(dummy_user_config_value)
        else:
            self.dummy_user_if_no_proxy = bool(app.debug)

        app.extensions['jwtauthmanager'] = self

    def decode_request_auth_bearer(self):
        return decode_request_auth_bearer_dict(request_header_name=self.authorization_request_header_name,
                                               bearer_prefix=self.bearer_prefix)


    def create_dummy_user(self):
        u = JWTAuthUser(email=self.dummy_user_email,
                        name=self.dummy_user_first_name + " " + self.dummy_user_last_name,
                        first_name=self.dummy_user_first_name,
                        last_name=self.dummy_user_last_name,
                        picture="https://lh3.googleusercontent.com/a/ACg8ocIgNWlKkMc3S6ASWRpELCyBKKtZXEviKDL7jTcGCI5ynADGFrA=s96-c")
        return u


    def is_behind_proxy(self):
        # Crude way to check if we're behind a proxy server.
        # Tested with NGINX.
        return bool(request.headers.get("X-Forwarded-For"))


    def get_jwt_auth_user_from_request(self):
        if self.dummy_user_if_no_proxy and not self.is_behind_proxy():
            # If we are not behind a proxy, assume we're in development/debug mode,
            # (e.g. testing locally on 127.0.0.1).
            # so fake a dummy user (since we can't get OAuth2 to complete)
            u = self.create_dummy_user()
            if self.debug:
                current_app.logger.debug("JWTAuth: faking dummy user: " + str(u))
            return u

        try:
            d = self.decode_request_auth_bearer()
            if self.debug:
                current_app.logger.debug("JWTAuth: Dict = " + pformat(d))

            u = JWTAuthUser(**d)
            if self.debug:
                current_app.logger.debug("JWTAuth: User = " + str(u))

        except JWTAuthError as e:
            if self.debug:
                current_app.logger.debug("JWTAuth Error: " + str(e))
            u = None

        return u


current_jwt_user = LocalProxy(lambda: _get_current_jwt_auth_user())


def _get_current_jwt_auth_user():
    if has_request_context():
        jwt_auth = current_app.extensions.get('jwtauthmanager')
        if not jwt_auth:
            raise RuntimeError("JWTAuthManager not initialized")

        if "_jwt_auth_user" not in g:
            g._jwt_auth_user = jwt_auth.get_jwt_auth_user_from_request()

        return g._jwt_auth_user

    return None


def jwt_auth_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        jwt_user = _get_current_jwt_auth_user()
        if jwt_user is None:
            abort(400)

        return func(*args, **kwargs)

    return decorated_view
