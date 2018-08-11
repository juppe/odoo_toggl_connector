# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2018 Johan Tötterman
#
##############################################################################

import requests
import json
from base64 import b64encode

from openerp import models, fields, api
from openerp.exceptions import Warning

class TogglApi(models.Model):
    _name = 'toggl.api'

    # Default headers for requests
    headers = {
        'Authorization': '',
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'User-Agent': 'Odoo_TogglAPI',
    }

    def set_authorization(self, apikey):
        # Set authorization header
        auth = apikey + ':' + 'api_token'
        auth = 'Basic ' + b64encode(auth.encode()).decode('ascii').rstrip()
        self.headers['Authorization'] = auth

    def request_do(self, method, url, params={}, data={}):
        # Do HTTP request to Toggl API
        if method not in ['get','post','put']:
            raise Warning('Unsupported HTTP method: %s' % (method))

        if method=="get" and not 'user_agent' in params:
            params['user_agent'] = 'Odoo_TogglAPI'

        if method!="get":
            if not 'user_agent' in data:
                data['user_agent'] = 'Odoo_TogglAPI'
            data = json.dumps(data).encode("utf-8")

        # Init API request
        r = requests
        action = getattr(r, method)

        try:
            res = action(url, headers=self.headers, params=params, data=data)

        except requests.exceptions.RequestException as e:
            raise Warning("There was an error in your get request: %s" % (e))

        if res.status_code != requests.codes.ok:
           raise Warning("API returned error: %s, %s" % (res, res.text))

        try:
            response = json.loads(res.text)
        except ValueError:
            raise Warning("Decoding JSON response has failed: % s" % res.text)
        return response

    def me(self):
        return self.request_do('get', 'https://www.toggl.com/api/v8/me')

    def clients(self, wid):
        return self.request_do('get', 'https://www.toggl.com/api/v8/workspaces/%s/clients' % wid)

    def projects(self, wid):
        return self.request_do('get', 'https://www.toggl.com/api/v8/workspaces/%s/projects' % wid)

    def project(self, project_id):
        return self.request_do('get', 'https://www.toggl.com/api/v8/projects/%s' % project_id)

    def detailed_report(self, params):
        return self.request_do('get', 'https://toggl.com/reports/api/v2/details/', params=params)

    def create_client(self, params):
        params = {'client': params}
        response = self.request_do('post', 'https://www.toggl.com/api/v8/clients', data=params)
        return response['data']

    def create_project(self, params):
        params = {'project': params}
        response = self.request_do('post', 'https://www.toggl.com/api/v8/projects', data=params)
        return response['data']

    def update_project(self, project_id, params):
        params = {'project': params}
        response = self.request_do('put', 'https://www.toggl.com/api/v8/projects/%s' % project_id, data=params)
        return response['data']

