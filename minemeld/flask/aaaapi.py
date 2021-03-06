#  Copyright 2016 Palo Alto Networks, Inc
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging
import collections

from flask import request
from flask import jsonify

import flask.ext.login

from . import app
from . import config

LOG = logging.getLogger(__name__)

API_USERS_ATTRS_ATTR = 'API_USERS_ATTRS'
FEEDS_USERS_ATTRS_ATTR = 'FEEDS_USERS_ATTRS'
FEEDS_ATTRS_ATTR = 'FEEDS_ATTRS'


Subsystem = collections.namedtuple(
    'Subsystem',
    ['authdb', 'attrs', 'enabled', 'enabled_default'],
    verbose=True
)


_SUBSYSTEM_MAP = {
    'api': Subsystem(
        authdb='USERS_DB',
        enabled='API_AUTH_ENABLED',
        enabled_default=True,
        attrs=config.APIConfigDict(attribute=API_USERS_ATTRS_ATTR, level=50)
    ),
    'feeds': Subsystem(
        authdb='FEEDS_USERS_DB',
        enabled='FEEDS_AUTH_ENABLED',
        enabled_default=False,
        attrs=config.APIConfigDict(attribute=FEEDS_USERS_ATTRS_ATTR, level=50)
    )
}


_FEEDS_ATTRS = config.APIConfigDict(attribute=FEEDS_ATTRS_ATTR, level=50)


@app.route('/aaa/users/<subsystem>', methods=['GET'])
@flask.ext.login.login_required
def get_users(subsystem):
    subsystem = _SUBSYSTEM_MAP.get(subsystem, None)
    if subsystem is None:
        return jsonify(error='Invalid subsystem'), 400

    result = {
        'enabled': config.get(subsystem.enabled, subsystem.enabled_default),
        'users': {}
    }
    users = config.get(subsystem.authdb).users()
    users_attrs = subsystem.attrs.value()
    LOG.debug(users_attrs)
    for u in users:
        attrs = {}
        if u in users_attrs:
            attrs = users_attrs[u]
        result['users'][u] = attrs

    return jsonify(result=result)


@app.route('/aaa/users/<subsystem>/<username>', methods=['PUT'])
@flask.ext.login.login_required
def set_user_password(subsystem, username):
    subsystem = _SUBSYSTEM_MAP.get(subsystem, None)
    if subsystem is None:
        return jsonify(error='Invalid subsystem'), 400

    with config.lock():
        users_db = config.get(subsystem.authdb)
        if not users_db.path:
            return jsonify(error='Users database not available')

        try:
            password = request.get_json()['password']
        except Exception:
            return jsonify(error='Invalid request'), 400

        users_db.set_password(username, password)
        users_db.save()

        return jsonify(result='ok')


@app.route('/aaa/users/<subsystem>/<username>/attributes', methods=['POST'])
@flask.ext.login.login_required
def set_user_attributes(subsystem, username):
    subsystem = _SUBSYSTEM_MAP.get(subsystem, None)
    if subsystem is None:
        return jsonify(error='Invalid subsystem'), 400

    with config.lock():
        users_db = config.get(subsystem.authdb)
        if not users_db.path:
            return jsonify(error='Users database not available')

        if username not in users_db.users():
            return jsonify(error='Unknown user'), 400

        try:
            attributes = request.get_json()
        except Exception:
            return jsonify(error='Invalid request'), 400

        if not isinstance(attributes, dict):
            return jsonify(error='Attributes should be a dict'), 400

        subsystem.attrs.set(username, attributes)

        return jsonify(result='ok')


@app.route('/aaa/users/<subsystem>/<username>', methods=['DELETE'])
@flask.ext.login.login_required
def delete_user(subsystem, username):
    subsystem = _SUBSYSTEM_MAP.get(subsystem, None)
    if subsystem is None:
        return jsonify(error='Invalid subsystem'), 400

    with config.lock():
        users_db = config.get(subsystem.authdb)
        if not users_db.path:
            return jsonify(error='Users database not available')

        # delete user from database and tags
        if users_db.delete(username):
            users_db.save()

        subsystem.attrs.delete(username)

        return jsonify(result='ok')


@app.route('/aaa/feeds', methods=['GET'])
@flask.ext.login.login_required
def get_feeds():
    result = {
        'enabled': config.get(
            _SUBSYSTEM_MAP['feeds'].enabled,
            _SUBSYSTEM_MAP['feeds'].enabled_default
        ),
        'feeds': _FEEDS_ATTRS.value()
    }
    return jsonify(result=result)


@app.route('/aaa/feeds/<feedname>/attributes', methods=['PUT', 'POST'])
@flask.ext.login.login_required
def set_feed_attributes(feedname):
    with config.lock():
        try:
            attributes = request.get_json()
        except Exception:
            return jsonify(error='Invalid request'), 400

        if not isinstance(attributes, dict):
            return jsonify(error='Attributes should be a dict'), 400

        _FEEDS_ATTRS.set(feedname, attributes)

        return jsonify(result='ok')


@app.route('/aaa/feeds/<feedname>', methods=['DELETE'])
@flask.ext.login.login_required
def delete_feed(feedname):
    with config.lock():
        _FEEDS_ATTRS.delete(feedname)

        return jsonify(result='ok')


@app.route('/aaa/tags', methods=['GET'])
@flask.ext.login.login_required
def get_tags():
    tags = set()

    for _, subsystem in _SUBSYSTEM_MAP.iteritems():
        for _, attributes in subsystem.attrs.value().iteritems():
            if 'tags' in attributes:
                for t in attributes['tags']:
                    tags.add(t)
    for _, attributes in _FEEDS_ATTRS.value().iteritems():
        if 'tags' in attributes:
            for t in attributes['tags']:
                tags.add(t)

    return jsonify(result=list(tags - set(['any', 'anonymous'])))
