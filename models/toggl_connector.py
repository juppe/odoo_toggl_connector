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

    _sql_constraints = [('toggl_company_uniq',
                         'unique(company_id)',
                         'Only one Toggl connection per company is allowed')]

    name = fields.Char('Connector Name')
    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        default=lambda self: self.env['res.company']._company_default_get()
    )
    toggl_api_token = fields.Char('Toggl API token',
        help="""Toggl API token of Toggl Worskspace Admin.
            The API token can be found on the "My Profile" page in Toggl.""",
        required=True
    )
    toggl_workspace_id = fields.Integer('Toggl workspace ID',
        help="""Toggl workspace ID. The workspace ID can be found as a
            part of the url e.g. when navigating to
            the Workspace Settings page in Toggl.""",
        required=True
    )
    toggl_default_project = fields.Many2one('project.project',
        string='Default project',
        help="""Default project for Toggl time entries
            that are without a project in Toggl.""",
        required=True
    )
    toggl_skip_projects = fields.Many2many('project.project',
        string='Projects to skip',
        help='Skip these projects when syncing to Toggl.'
    )
    last_cron_run = fields.Datetime('Latest run',
        help="Date of lastest cron run"
    )

    # Default headers for requests
    headers = {
        'Authorization': '',
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'User-Agent': 'Odoo_TogglAPI',
    }

    # All Toggl projects, clients and tasks
    toggl_clients = []
    toggl_projects = []
    toggl_tasks = {}

    @api.multi
    def sync_time_entries_from_toggl(self, date_from, date_to, update_entries):
        self.ensure_one()
        user = self.env['res.users'].browse(self.env.uid)
        employee = self.env['hr.employee'].search([('user_id', '=', user.id)])

        if not employee:
            raise Warning ('Please link your Odoo user to an Employee.')
        elif len(employee) > 1:
            raise Warning ('Please link your Odoo user to exactly one Employee.')

        self.toggl_api_init()

        # Synced entries
        synced_entries = []

        # Fetch all workspace users
        toggl_users = self.users(self.toggl_workspace_id)

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
            time_entries_page = self.detailed_report(params=report_params)
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
                'project_id': self.toggl_default_project.id,
                'account_id': self.toggl_default_project.analytic_account_id.id,
                'unit_amount': duration,
                'toggl_entry_id': time_entry['id'],
            }

            if time_entry['tid']:
                # Match Toggl Task to Odoo Task and Project
                task = self.env['project.task'].search([
                    ('toggl_task_id', '=', time_entry['tid'])
                ], limit=1)
                if task:
                    timesheet['task_id'] = task.id
                    if task.project_id:
                        timesheet['project_id'] =  task.project_id.id
                        timesheet['account_id'] =  task.project_id.analytic_account_id.id
            elif time_entry['pid']:
                # Match Toggl Project to Odoo Project
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
                logger.debug("Toggl: Create time entry: %s" % (timesheet['name']))
                entryid = self.env['account.analytic.line'].create(timesheet)
                synced_entries.append(entryid.id)
            elif update_entries:
                # Update time entry
                logger.debug("Toggl: Update time entry: %s" % (timesheet['name']))
                try:
                    odoo_te.write(timesheet)
                    synced_entries.append(odoo_te.id)
                except Exception as e:
                    logger.warning("Toggl: Update time entry failed! %s" % (e))
        return synced_entries

    @api.multi
    def sync_projects_to_toggl_button(self):
        self.ensure_one()
        user = self.env['res.users'].browse(self.env.uid)
        toggl = self.env['toggl.connector'].search([
            ('company_id', '=', user.company_id.id)
        ])
        toggl.sync_projects_to_toggl()
        toggl.sync_tasks_to_toggl()

    @api.model
    def sync_to_toggl_cron(self, sync_all=False):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = self.env['toggl.connector'].search([
            ('company_id', '=', user.company_id.id)
        ])

        # Sync everything checked or when running sync first time, we sync all projects/tasks
        if sync_all or not toggl.last_cron_run:
            # Sync all projects and tasks
            logger.debug("Toggl: Sync all projects to Toggl")
            toggl.sync_projects_to_toggl()
            return

        # Which records to include in sync
        time_from = toggl.last_cron_run
        logger.debug("Toggl: Cron last run: %s" % time_from)

        # Update timestamp
        toggl.last_cron_run = fields.Datetime.now()

        # Sync projects and tasks
        toggl.sync_projects_to_toggl(time_from)
        toggl.sync_tasks_to_toggl(time_from)

    @api.model
    def archive_completed_tasks_projects_cron(self):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = self.env['toggl.connector'].search([
            ('company_id', '=', user.company_id.id)
        ])

        # Arcive completed
        toggl.archive_completed_projects_tasks()

    def sync_projects_to_toggl(self, time_from=False):
        self.ensure_one()
        self.toggl_api_init()

        # Fetch all clients from Toggl in one API call
        # and keep them in a class variable
        self.toggl_clients = self.clients(self.toggl_workspace_id)
        if not self.toggl_clients:
            self.toggl_clients = []

        # Fetch all projects from Toggl in one API call
        # and keep them in a class variable
        self.toggl_projects = self.projects(self.toggl_workspace_id, 'both')
        if not self.toggl_projects:
            self.toggl_projects = []

        # Skip these projects when syncing to Toggl
        skip_projects = self.toggl_skip_projects.mapped('name')

        # Fetch all active projects from Odoo
        projectdomain = [
            ('active', '=', True),
            ('name', 'not in', skip_projects),
        ]

        if time_from:
            # Only projects that are touched since the last run
            projectdomain.append(('write_date', '>=', time_from))

        projects = self.env['project.project'].search(projectdomain)

        for project in projects:
            client_id = 0

            if project.partner_id:
                client_id = self.create_toggl_client({
                    'name': project.partner_id.name,
                    'toggl_id': project.partner_id.toggl_partner_id,
                })
                # Update Toggl Client id to partner in Odoo
                # .sudo() because we are only touching the toggl_partner_id-field...
                project.partner_id.sudo().write({
                    'toggl_partner_id': client_id,
                })

            # Create Toggl project
            toggl_pid = self.create_toggl_project({
                'name': project.name,
                'id': project.id,
                'client_id': client_id,
                'toggl_id': project.toggl_project_id,
            })

            # Update Toggl Project id to project in Odoo
            # .sudo() because we are only touching the toggl_project_id-field...
            project.sudo().write({
                'toggl_project_id': toggl_pid,
            })

    def sync_tasks_to_toggl(self, time_from=False):
        self.ensure_one()
        self.toggl_api_init()

        # Fetch task types from Odoo
        # In this API we only sync tasks and issues to Toggl
        # that are in a stage that is not folded by default in Odoo's Kanban view
        task_types = self.get_task_types()

        # Sync tasks for all active projects on Toggl
        for toggl_project in self.toggl_projects:
            project = self.env['project.project'].search([
                ('toggl_project_id', '=', toggl_project['id']),
            ])

            if not project:
                logger.debug("Toggl: Project not found in Odoo: %s" % toggl_project['name'])
                continue

            # Fecth Project tasks from Toggl and put them in class variable
            toggl_tasks = self.project_tasks(project.toggl_project_id)
            self.toggl_tasks[toggl_project['id']] = toggl_tasks

            # Fetch tasks from Odoo
            taskdomain = [
                ('project_id', '=', project.id),
                ('stage_id', 'in', task_types),
            ]
            if time_from:
                 # Only sync tasks that are touched since the last run
                taskdomain.append(('write_date', '>=', time_from))

            tasks = self.env['project.task'].search(taskdomain)

            for task in tasks:
                # Create Toggl Task from Odoo task
                toggl_tid = self.create_toggl_task({
                    'name': task.name,
                    'pid': project.toggl_project_id,
                    'id': task.id,
                    'toggl_id': task.toggl_task_id,
                })
                # Update Toggl Task id to task in Odoo
                # .sudo() because we are only touching the toggl_task_id-field...
                task.sudo().write({
                    'toggl_task_id': toggl_tid,
                })

    def archive_completed_projects_tasks(self):
        # Deactivate Toggl projects that are not active in Odoo anymore
        self.ensure_one()
        self.toggl_api_init()

        # Active task types
        task_types = self.get_task_types()

        # Fetch all active projects from Toggl
        toggl_projects = self.projects(self.toggl_workspace_id, 'true')

        for toggl_project in toggl_projects:
            project = self.env['project.project'].search([
                ('toggl_project_id', '=', toggl_project['id'])
            ], limit=1)

            # Project not active in Odoo anymore, arcive it in Toggl too
            # When project is archived it's tasks are also archived
            if not project:
                logger.warning("Toggl: Deactivate project: %s" % toggl_project['name'])
                self.update_project(toggl_project['id'], {
                    'active': False,
                })
                continue

            # Fetch project's tasks
            toggl_tasks = self.project_tasks(project.toggl_project_id)
            if not toggl_tasks:
                continue

            for toggl_task in toggl_tasks:
                # Task not active in Odoo anymore, archive it in Toggl too
                task = self.env['project.task'].search([
                    ('toggl_task_id', '=', toggl_task['id']),
                    ('stage_id', 'in', task_types),
                ])

                if not task:
                    logger.warning("Toggl: Deactivate task: %s" % toggl_task['name'])
                    self.update_task(toggl_task['id'], {
                        'active': False,
                    })

    def get_task_types(self):
        # Return active task types (i.e. not filded in kanban view)
        return self.env['project.task.type'].search([('fold', '=', False)]).mapped('id')

    def create_toggl_project(self, params):
        # Project name, including info about if it's a taks or a project and its Odoo id
        project_name = "%s [%s]" % (params['name'], params['id'])

        # Check if this project already exists in Toggl
        toggl_project = next(filter(lambda p: p['id']==params['toggl_id'], self.toggl_projects), None)

        if not toggl_project:
            logger.debug("Toggl: Create project: %s" % project_name)
            # Create Toggl project
            response = self.create_project({
                'name': project_name,
                'wid': self.toggl_workspace_id,
                'is_private': False,
                'cid': params['client_id'],
            })
            self.toggl_projects.append(response)
            return response['id']
        elif (project_name != toggl_project['name'] or
                (toggl_project.get('cid', 0) != params['client_id']) or
                (not toggl_project['active'])):
            logger.debug("Toggl: Update project: %s" % project_name)
            response = self.update_project(toggl_project['id'], {
                'active': True,
                'name': project_name,
                'cid': params['client_id'],
            })
            return response['id']
        else:
            return toggl_project['id']

    def create_toggl_task(self, params):
        # Task name, including info about if it's a taks or a project and its Odoo id
        task_name = "%s [%s]" % (params['name'], params['id'])

        # All Toggl tasks associated to this task's project
        toggl_tasks = self.toggl_tasks[params['pid']]
        toggl_task = None

        # Check if this task already exists in Toggl
        if toggl_tasks:
            toggl_task = next(filter(lambda t: t['id']==params['toggl_id'], toggl_tasks), None)

        if not toggl_task:
            logger.debug("Toggl: Create task: %s" % task_name)
            task = {
                'name': task_name,
                'pid': params['pid'],
                'wid': self.toggl_workspace_id,
            }

            # Create Toggl task
            response = self.create_task(task)
            return response['id']
        elif (task_name != toggl_task['name'] or
                (not toggl_task['active'])):
            logger.debug("Toggl: Update task: %s" % task_name)
            response = self.update_task(toggl_task['id'], {
                'active': True,
                'name': task_name,
            })
            return response['id']
        else:
            return toggl_task['id']

    def create_toggl_client(self, params):
        # Check if client exists in Toggl
        toggl_client = next(filter(lambda c: c['id']==params['toggl_id'], self.toggl_clients), None)

        if not toggl_client:
            logger.debug("Toggl: Create client: %s" % params['name'])
            response = self.create_client({
                'name': params['name'],
                'wid': self.toggl_workspace_id,
            })
            self.toggl_clients.append(response)
            return response['id']
        elif params['name'] != toggl_client['name']:
            logger.debug("Toggl: Update client: %s" % params['name'])
            response = self.update_client(toggl_client['id'], {
                'name': params['name'],
            })
            return response['id']
        else:
            return toggl_client['id']

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

    def project_tasks(self, project_id):
        return self.do_request('get', 'https://www.toggl.com/api/v8//projects/%s/tasks' % project_id)

    def detailed_report(self, params):
        return self.do_request('get', 'https://toggl.com/reports/api/v2/details/', params=params)

    def create_client(self, params):
        params = {'client': params}
        response = self.do_request('post', 'https://www.toggl.com/api/v8/clients', data=params)
        return response['data']

    def update_client(self, client_id, params):
        params = {'client': params}
        response = self.do_request('put', 'https://www.toggl.com/api/v8/clients/%s' % client_id, data=params)
        return response['data']

    def create_project(self, params):
        params = {'project': params}
        response = self.do_request('post', 'https://www.toggl.com/api/v8/projects', data=params)
        return response['data']

    def update_project(self, project_id, params):
        params = {'project': params}
        response = self.do_request('put', 'https://www.toggl.com/api/v8/projects/%s' % project_id, data=params)
        return response['data']

    def create_task(self, params):
        params = {'task': params}
        response = self.do_request('post', 'https://www.toggl.com/api/v8/tasks', data=params)
        return response['data']

    def update_task(self, task_id, params):
        params = {'task': params}
        response = self.do_request('put', 'https://www.toggl.com/api/v8/tasks/%s' % task_id, data=params)
        return response['data']
