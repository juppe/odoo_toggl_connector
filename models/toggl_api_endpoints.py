# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2021 Johan Tötterman
#
##############################################################################

from odoo import models


class TogglConnector(models.Model):
    _inherit = "toggl.connector"

    """
    Functions for calling Toggl Api endpoints:
    """
    def me(self):
        return self.do_request('get', '%s/api/v8/me' % (self.toggl_api_url))

    def users(self, wid):
        return self.do_request('get', '%s/api/v8/workspaces/%s/workspace_users' % (self.toggl_api_url, wid))

    def clients(self, wid):
        return self.do_request('get', '%s/api/v8/workspaces/%s/clients' % (self.toggl_api_url, wid))

    def projects(self, wid, active):
        return self.do_request('get', '%s/api/v8/workspaces/%s/projects?active=%s' % (self.toggl_api_url, wid, active))

    def projects_free(self, wid, active):
        # Projects ans tasks are separated by P: and T: prefix when using Toggl free tier subscription
        projects = self.projects(wid, active)
        return [p for p in projects if not p['name'][0:3] == "T: "] if projects else []

    def tasks_free(self, wid, active):
        # Use projects as tasks when using the free tier subscription
        projects = self.do_request('get', '%s/api/v8/workspaces/%s/projects?active=%s' % (self.toggl_api_url, wid, active))
        return [p for p in projects if p['name'][0:3] == "T: "] if projects else []

    def project(self, project_id):
        return self.do_request('get', '%s/api/v8/projects/%s' % (self.toggl_api_url, project_id))

    def project_tasks(self, project_id):
        return self.do_request('get', '%s/api/v8/projects/%s/tasks' % (self.toggl_api_url, project_id))

    def detailed_report(self, params):
        return self.do_request('get', '%s/reports/api/v2/details/' % (self.toggl_api_url), params=params)

    def create_client(self, params):
        params = {'client': params}
        response = self.do_request('post', '%s/api/v8/clients' % (self.toggl_api_url), data=params)
        return response['data']

    def update_client(self, client_id, params):
        params = {'client': params}
        response = self.do_request('put', '%s/api/v8/clients/%s' % (self.toggl_api_url, client_id), data=params)
        return response['data']

    def create_project(self, params):
        params = {'project': params}
        response = self.do_request('post', '%s/api/v8/projects' % (self.toggl_api_url), data=params)
        return response['data']

    def update_project(self, project_id, params):
        params = {'project': params}
        response = self.do_request('put', '%s/api/v8/projects/%s' % (self.toggl_api_url, project_id), data=params)
        return response['data']

    def create_task(self, params):
        params = {'task': params}
        response = self.do_request('post', '%s/api/v8/tasks' % (self.toggl_api_url), data=params)
        return response['data']

    def create_task_free(self, params):
        # Use projects as tasks when using the free tier subscription
        return self.create_project(params)

    def update_task(self, task_id, params):
        params = {'task': params}
        response = self.do_request('put', '%s/api/v8/tasks/%s' % (self.toggl_api_url, task_id), data=params)
        return response['data']

    def update_task_free(self, task_id, params):
        # Use projects as tasks when using the free tier subscription
        return self.update_project(task_id, params)
