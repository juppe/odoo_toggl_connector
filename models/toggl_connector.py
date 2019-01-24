# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2019 Johan Tötterman
#
##############################################################################

import requests
import json
import re
from base64 import b64encode

from odoo import models, fields, api
from odoo.exceptions import Warning

import logging
logger = logging.getLogger(__name__)

class TogglConnector(models.Model):
    _name = "toggl.connector"
    _description = "Toggl Connector"

    name = fields.Char('Connector Name')
    toggl_api_token = fields.Char('Toggl API token', help='Toggl API token. The API token can be found on the "My Profile" page in Toggl.', required=True)
    toggl_workspace_id = fields.Integer('Toggl workspace ID', help='Toggl workspace ID. The workspace ID can be found as a part of the url e.g. when navigating to the Workspace Settings page in Toggl.', required=True)
    toggl_analytic_account = fields.Many2one('account.analytic.account', string='Default analytic account', help='Default analytic account for Toggl time entries. (Used when Project/Task is not chosen on the time entry in Toggl).', required=True)
    toggl_skip_projects = fields.Many2many('project.project', string='Projects to skip', help='Skip these projects when syncing to Toggl.')
    last_cron_run = fields.Datetime('Latest run', help="Date of lastest cron run")

    # Default headers for requests
    headers = {
        'Authorization': '',
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'User-Agent': 'Odoo_TogglAPI',
    }

    # All Toggl projects
    toggl_projects = []

    @api.one
    def sync_time_entries_from_toggl(self, date_from, date_to):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = user.company_id.toggl_connector_id
        employee = self.env['hr.employee'].search([('user_id', '=', user.id)])

        if not employee:
            raise Warning ('Please link your Odoo user to an Employee.')
        elif len(employee) > 1:
            raise Warning ('Please link your Odoo user to exactly one Employee.')

        toggl.toggl_api_init()

        # Fetch all workspace users
        toggl_users = toggl.users(self.toggl_workspace_id)

        # Pick correct Toggl user
        toggl_user = next(filter(lambda c: c['email']==user.toggl_username, toggl_users), None)

        if not toggl_user:
            raise Warning ('Please check that your Toggl Username (Email) is correct in Odoo')

        report_params = {
            'workspace_id': self.toggl_workspace_id,
            'user_ids': toggl_user['uid'],
            'since': date_from,
            'until': date_to,
            'page': 1,
        }

        time_entries = []

        # Get detailed report of Toggl time entries, one page at a time
        while True:
            time_entries_page = toggl.detailed_report(params=report_params)
            report_params['page']+=1
            time_entries += time_entries_page['data']

            if not time_entries_page['data']:
                break

        # Process time entries and insert/update them in Odoo
        for time_entry in time_entries:
            # Duration in hours (msec --> hour)
            duration = round(time_entry['dur'] / 1000.0 / 3600.0, 2)

            if not time_entry['description']:
              time_entry['description'] = "/"

            if not time_entry['project']:
              time_entry['project'] = ""

            timesheet = {
                'name': time_entry['description'],
                'employee_id': employee.id,
                'date': time_entry['start'][0:10],
                'account_id': toggl.toggl_analytic_account.id,
                'unit_amount': duration,
                'toggl_entry_id': time_entry['id'],
            }

            # Match Toggl Project to Odoo Project or Task
            if time_entry['project'][0:2] == "T:" and time_entry['pid']:
                task = self.env['project.task'].search([
                    ('toggl_task_id', '=', time_entry['pid'])
                ], limit=1)
                if task:
                    timesheet['task_id'] = task.id
                    if task.project_id:
                        timesheet['project_id'] =  task.project_id.id
                        timesheet['account_id'] =  task.project_id.analytic_account_id.id

            elif time_entry['project'][0:2] == "P:" and time_entry['pid']:
                project = self.env['project.project'].search([
                    ('toggl_project_id', '=', time_entry['pid'])
                ], limit=1)
                if project:
                    timesheet['project_id'] =  project.id
                    timesheet['account_id'] =  project.analytic_account_id.id

            # Check if entry exists in Odoo
            odoo_te = self.env['account.analytic.line'].search([
                ('toggl_entry_id', '=', time_entry['id']),
            ], limit=1)

            if not odoo_te:
                # Create  time entry
                logger.warning("Create time entry: %s" % (timesheet['name']))
                self.env['account.analytic.line'].create(timesheet)
            else:
                # Update time entry
                logger.warning("Update time entry: %s" % (timesheet['name']))
                odoo_te.write(timesheet)

    @api.model
    def sync_projects_to_toggl_cron(self, sync_all=False):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = user.company_id.toggl_connector_id

        if sync_all:
            # Sync all projects and tasks
            toggl.sync_projects_to_toggl()
            return

        # Which records to include in sync
        time_from = toggl.last_cron_run
        logger.warning("Toggl: Cron last run: %s" % time_from)

        # Update timestamp
        toggl.last_cron_run = fields.datetime.now()

        # Sync projects and tasks
        toggl.with_context(time_from=time_from).sync_projects_to_toggl()

    @api.one
    def sync_projects_to_toggl(self):
        self.toggl_api_init()

        # Only sync tasks that are touched since the last run
        time_from = self.env.context.get('time_from', False)

        # Fetch clients from Toggl
        toggl_clients = self.clients(self.toggl_workspace_id)
        if not toggl_clients:
            toggl_clients = []

        # Fetch all project from Toggl in one API call
        self.toggl_projects = self.projects(self.toggl_workspace_id, 'both')
        if not self.toggl_projects:
            self.toggl_projects = []

        # Fetch task types from Odoo
        # In this API we only sync tasks and issues to Toggl
        # that are in a stage that is not folded by default in Odoo's Kanban view
        task_types = self.get_task_types()

        # Skip these projects when syncing to Toggl
        skip_projects = self.toggl_skip_projects.mapped('name')

        # Fetch all projects from Odoo
        projects = self.env['project.project'].search([
            ('name', 'not in', skip_projects),
        ])

        for project in projects:
            client_id = 0

            if project.partner_id:
                cliname = project.partner_id.name

                # Check if client exists in Toggl
                client_exists = next(filter(lambda c: c['name']==cliname, toggl_clients), None)

                if not client_exists:
                    response = self.create_client({
                        'name': cliname,
                        'wid': self.toggl_workspace_id,
                    })
                    toggl_clients.append(response)
                    client_id = response['id']
                else:
                    client_id = client_exists['id']

            # Create Toggl project
            toggl_pid = self.create_toggl_project({
                'type': 'P',
                'name': project.name,
                'id': project.id,
                'client_id': client_id,
                'toggl_id': project.toggl_project_id,
            })
            project.toggl_project_id=toggl_pid

            # Fetch tasks from Odoo
            taskdomain = [
                ('project_id', '=', project.id),
                ('stage_id', 'in', task_types),
            ]
            if time_from:
                taskdomain.append(('write_date', '>=', time_from))

            tasks = self.env['project.task'].search(taskdomain)

            for task in tasks:
                # Create Toggl project from Odoo task
                toggl_tid = self.create_toggl_project({
                    'type': 'T',
                    'name': task.name,
                    'id': task.id,
                    'client_id': client_id,
                    'toggl_id': task.toggl_task_id,
                })
                task.toggl_task_id=toggl_tid

    @api.one
    def archive_completed_projects(self):
        # Deactivate Toggl projects that are not active in Odoo anymore
        self.toggl_api_init()

        # Active task types
        task_types = self.get_task_types()

        # Fetch all active projects from Toggl
        toggl_projects = self.projects(self.toggl_workspace_id, 'true')

        for toggl_project in toggl_projects:
            task = self.env['project.task'].search([
                ('toggl_task_id', '=', toggl_project['id']),
                ('stage_id', 'in', task_types),
            ])

            if not task:
                response = self.update_project(toggl_project['id'], {
                    'active': False,
                })
                logger.warning("Toggl: Deactivate project: %s" % toggl_project['name'])

    def get_task_types(self):
        # Return active task types (i.e. not filded in kanban view)
        return self.env['project.task.type'].search([('fold', '=', False)]).mapped('id')

    def create_toggl_project(self, params):
        # Project name, including info about if it's a taks or a project and its Odoo id
        project_name = "%s: %s [%s]" % (params['type'], params['name'], params['id'])

        # Check if this project already exists in Toggl
        toggl_project = next(filter(lambda p: p['id']==params['toggl_id'], self.toggl_projects), None)

        if not toggl_project:
            logger.warning("Toggl: Create project: %s" % project_name)
            project = {
                'name': project_name,
                'wid': self.toggl_workspace_id,
                'is_private': False,
                'cid': params['client_id'],
            }

            # Create Toggl project
            response = self.create_project(project)
            return response['id']
        elif (project_name != toggl_project['name'] or
                ('cid' in toggl_project and toggl_project['cid'] != params['client_id']) or
                (not toggl_project['active'])):
            logger.warning("Toggl: Update project: %s" % project_name)
            response = self.update_project(toggl_project['id'], {
                'active': True,
                'name': project_name,
                'cid': params['client_id'],
            })
            return response['id']
        else:
            return toggl_project['id']

    def toggl_api_init(self):
        # Initilaize Toggl API
        self.set_authorization_header(self.toggl_api_token)

    def set_authorization_header(self, apitoken):
        # Set authorization header
        auth = apitoken + ':' + 'api_token'
        auth = 'Basic ' + b64encode(auth.encode()).decode('ascii').rstrip()
        self.headers['Authorization'] = auth

    def do_request(self, method, url, params={}, data={}):
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

    """
    Functions for calling Toggl Api endpoints:
    """
    def me(self):
        return self.do_request('get', 'https://www.toggl.com/api/v8/me')

    def users(self, wid):
        return self.do_request('get', 'https://www.toggl.com/api/v8/workspaces/%s/workspace_users' % wid)

    def clients(self, wid):
        return self.do_request('get', 'https://www.toggl.com/api/v8/workspaces/%s/clients' % wid)

    def projects(self, wid, active):
        return self.do_request('get', 'https://www.toggl.com/api/v8/workspaces/%s/projects?active=%s' % (wid, active))

    def project(self, project_id):
        return self.do_request('get', 'https://www.toggl.com/api/v8/projects/%s' % project_id)

    def detailed_report(self, params):
        return self.do_request('get', 'https://toggl.com/reports/api/v2/details/', params=params)

    def create_client(self, params):
        params = {'client': params}
        response = self.do_request('post', 'https://www.toggl.com/api/v8/clients', data=params)
        return response['data']

    def create_project(self, params):
        params = {'project': params}
        response = self.do_request('post', 'https://www.toggl.com/api/v8/projects', data=params)
        return response['data']

    def update_project(self, project_id, params):
        params = {'project': params}
        response = self.do_request('put', 'https://www.toggl.com/api/v8/projects/%s' % project_id, data=params)
        return response['data']
