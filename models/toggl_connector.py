# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2021 Johan Tötterman
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
    subscription_type = fields.Selection(
        selection=[
            ("pro", "Premium Subscription"),
            ("free", "Free Subscription"),
        ],
        string="Toggl Subscription Type",
        required=True,
        default="pro",
    )
    toggl_api_url = fields.Char('Toggl API Url',
        default='https://api.track.toggl.com',
        required=True
    )

    # Default headers for requests
    headers = {
        'Authorization': '',
        'Content-Type': 'application/json',
        'Accept': '*/*',
        'User-Agent': 'Odoo_TogglAPI',
    }

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
        toggl_user = next(filter(lambda c: c['email'] == employee.toggl_username, toggl_users), None)

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
            report_params['page'] += 1
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

            task = None
            project = None

            if self.subscription_type == 'free' and time_entry['project'][0:3] == 'T: ':
                task = self.env['project.task'].search([
                    ('toggl_task_id', '=', time_entry['pid'])
                ], limit=1)
            elif self.subscription_type == 'free' and time_entry['project'][0:3] == 'P: ':
                project = self.env['project.project'].search([
                    ('toggl_task_id', '=', time_entry['pid'])
                ], limit=1)
            elif 'tid' in time_entry and time_entry['tid']:
                task = self.env['project.task'].search([
                    ('toggl_task_id', '=', time_entry['tid'])
                ], limit=1)
            elif 'pid' in time_entry and time_entry['pid']:
                project = self.env['project.project'].search([
                    ('toggl_project_id', '=', time_entry['pid'])
                ], limit=1)

            if task:
                timesheet['task_id'] = task.id
                if task.project_id:
                    timesheet['project_id'] =  task.project_id.id
                    timesheet['account_id'] =  task.project_id.analytic_account_id.id
            elif project:
                timesheet['project_id'] =  project.id
                timesheet['account_id'] =  project.analytic_account_id.id

            # Check if entry exists in Odoo
            odoo_te = self.env['account.analytic.line'].search([
                ('toggl_entry_id', '=', time_entry['id']),
            ], limit=1)

            if not odoo_te:
                # Create  time entry
                logger.warning("Toggl: Create time entry: %s" % (timesheet['name']))
                entryid = self.env['account.analytic.line'].create(timesheet)
                synced_entries.append(entryid.id)
            elif update_entries:
                # Update time entry
                logger.warning("Toggl: Update time entry: %s" % (timesheet['name']))
                try:
                    odoo_te.write(timesheet)
                    synced_entries.append(odoo_te.id)
                except Exception as e:
                    logger.warning("Toggl: Update time entry failed! %s" % (e))
        return synced_entries

    def sync_projects_to_toggl_button(self):
        self.ensure_one()
        user = self.env['res.users'].browse(self.env.uid)
        toggl = self.env['toggl.connector'].search([
            ('company_id', '=', user.company_id.id)
        ])

         # Sync projects and tasks
        toggl.sync_projects_to_toggl()
        toggl.sync_tasks_to_toggl()

    def sync_projects_to_toggl_cron(self, sync_all=False):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = self.env['toggl.connector'].search([
            ('company_id', '=', user.company_id.id)
        ])

        # Sync everything checked or when running sync first time, we sync all projects/tasks
        if sync_all or not toggl.last_cron_run:
            # Sync all projects and tasks
            logger.warning("Toggl: Sync all projects to Toggl")
            toggl.sync_projects_to_toggl()
            return

        # Which records to include in sync
        time_from = toggl.last_cron_run
        logger.warning("Toggl: Cron last run: %s" % time_from)

        # Update timestamp
        toggl.last_cron_run = fields.Datetime.now()

        # Sync projects and tasks
        toggl.sync_projects_to_toggl(time_from)
        toggl.sync_tasks_to_toggl(time_from)

    def sync_projects_to_toggl(self, time_from=False):
        self.ensure_one()
        self.toggl_api_init()

        # Fetch all clients from Toggl in one API call
        toggl_clients = self.clients(self.toggl_workspace_id)
        toggl_client_ids = [c['id'] for c in toggl_clients] if toggl_clients else []

        partners = self.env['res.partner'].with_context(active_test=False).search([
            ('toggl_partner_id', '!=', False),
            ('toggl_partner_id', 'not in', toggl_client_ids),
        ])

        # Remove toggl_partner_id from partners, that have a
        # toggl_partner_id that's no longer present in Toggl
        partners.sudo().write({
            'toggl_partner_id': False
        })

        # Fetch all projects from Toggl in one API call
        if self.subscription_type == 'free':
            toggl_projects = self.projects_free(self.toggl_workspace_id, 'both')
        else:
            toggl_projects = self.projects(self.toggl_workspace_id, 'both')

        toggl_project_ids = [p['id'] for p in toggl_projects] if toggl_projects else []

        projects = self.env['project.project'].with_context(active_test=False).search([
            ('toggl_project_id', '!=', False),
            ('toggl_project_id', 'not in', toggl_project_ids),
        ])

        # Remove toggl_project_id from projects, that have a
        # toggl_project_id that's no longer present in Toggl
        projects.write({
            'toggl_project_id': False
        })

        # Fetch all active projects from Odoo
        projectdomain = [
            ('active', '=', True),
            ('id', 'not in', self.toggl_skip_projects.ids),
        ]

        if time_from:
            # Only projects that are updated since the last run
            projectdomain.append(('write_date', '>=', time_from))

        projects = self.env['project.project'].search(projectdomain)
        for project in projects:
            if project.partner_id:
                toggl_partner_info = {}
                if project.partner_id.toggl_partner_id:
                    toggl_partner_info = next(filter(lambda c: c['id'] == project.partner_id.toggl_partner_id, toggl_clients), None)

                # Create or update Client in Toggl
                self.create_update_toggl_client(project.partner_id, toggl_partner_info)

            toggl_project_info = {}
            if project.toggl_project_id:
                toggl_project_info = next(filter(lambda p: p['id'] == project.toggl_project_id, toggl_projects), None)

            # Create or update Project in Toggl
            self.create_update_toggl_project(project, toggl_project_info)

        # Archive Toggl projects that are not active in Odoo anymore
        toggl_active_projects = [p for p in toggl_projects if p['active']]
        for toggl_project in toggl_active_projects:
            odoo_project = self.env['project.project'].search([
                ('active', '=', True),
                ('id', 'not in', self.toggl_skip_projects.ids),
                ('toggl_project_id', '=', toggl_project['id']),
            ])
            if not odoo_project:
                logger.warning("Toggl: Deactivate project: %s" % toggl_project['name'])
                self.update_project(toggl_project['id'], {
                    'active': False,
                })

    def sync_tasks_to_toggl(self, time_from=False):
        self.ensure_one()
        self.toggl_api_init()

        # Fetch task types from Odoo
        # In this API we only sync tasks to Toggl that are in a
        # stage that is not folded by default in Odoo's Kanban view
        task_types = self.get_task_types()

        # Toggl synced projects from Odoo
        projects = self.env['project.project'].search([
            ('toggl_project_id', '!=', None),
        ])

        # Fetch all tasks from Toggl
        if self.subscription_type == 'free':
            toggl_tasks = self.tasks_free(self.toggl_workspace_id, 'both')
        else:
            toggl_tasks = []
            for project in projects:
                toggl_tasks.extend(self.project_tasks(project.toggl_project_id))

        toggl_task_ids = [p['id'] for p in toggl_tasks] if toggl_tasks else []

        tasks = self.env['project.task'].with_context(active_test=False).search([
            ('toggl_task_id', '!=', None),
            ('toggl_task_id', 'not in', toggl_task_ids),
        ])

        # Remove toggl_project_id from projects, that have a
        # toggl_project_id that's no longer present in Toggl
        tasks.write({
            'toggl_task_id': None
        })

        # Sync tasks for all active projects on Toggl
        for project in projects:
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
                toggl_task_info = {}
                if task.toggl_task_id:
                    toggl_task_info = next(filter(lambda t: t['id'] == task.toggl_task_id, toggl_tasks), None)

                # Create or update Toggl Task from Odoo task
                self.create_update_toggl_task(task, toggl_task_info)

        # Archive Toggl tasks that are not active in Odoo anymore
        toggl_active_tasks = [t for t in toggl_tasks if t['active']]
        for toggl_task in toggl_active_tasks:
            odoo_task = self.env['project.task'].search([
                ('active', '=', True),
                ('project_id.active', '=', True),
                ('stage_id', 'in', task_types),
                ('toggl_task_id', '=', toggl_task['id']),
            ])
            if not odoo_task:
                logger.warning("Toggl: Deactivate task: %s" % toggl_task['name'])
                if self.subscription_type == 'free':
                    self.update_task_free(toggl_task['id'], {
                        'active': False,
                    })
                else:
                    self.update_task(toggl_task['id'], {
                        'active': False,
                    })

    def get_task_types(self):
        # Return active task types (i.e. not filded in kanban view)
        return self.env['project.task.type'].search([('fold', '=', False)]).mapped('id')

    def create_update_toggl_project(self, project, toggl_project_info):
        # Project name
        project_name = "%s [%s]" % (project.name, project.id)

        if self.subscription_type == 'free':
            project_name = "P: %s" % (project_name)

        if not project.toggl_project_id:
            logger.warning("Toggl: Create project: %s" % project_name)

            # Create Toggl project
            response = self.create_project({
                'name': project_name,
                'wid': self.toggl_workspace_id,
                'is_private': False,
                'cid': project.partner_id.toggl_partner_id,
            })

            # Update Toggl Project id to project in Odoo
            # .sudo() because we are only touching the toggl_project_id-field...
            project.sudo().write({
                'toggl_project_id': response['id'],
            })
        elif project.toggl_project_id:
            # Update only if some info has changed
            do_update = False
            if 'name' in toggl_project_info and project_name != toggl_project_info['name']:
                do_update = True
            if not 'name' in toggl_project_info and project_name:
                do_update = True
            if 'cid' in toggl_project_info and project.partner_id.toggl_partner_id != toggl_project_info['cid']:
                do_update = True
            if not 'cid' in toggl_project_info and project.partner_id.toggl_partner_id:
                do_update = True
            if 'active' in toggl_project_info and not toggl_project_info['active']:
                do_update = True

            if do_update:
                logger.warning("Toggl: Update project: %s" % project_name)

                self.update_project(project.toggl_project_id, {
                    'active': True,
                    'name': project_name,
                    'wid': self.toggl_workspace_id,
                    'is_private': False,
                    'cid': project.partner_id.toggl_partner_id,
                })
        return project.toggl_project_id

    def create_update_toggl_task(self, task, toggl_task_info):
        # Task name
        task_name = "%s [%s]" % (task.name, task.id)

        if self.subscription_type == 'free':
            task_name = "T: %s" % (task_name)

        if not task.toggl_task_id:
            logger.warning("Toggl: Create task: %s" % task_name)

            # Create Toggl task
            if self.subscription_type == 'free':
                response = self.create_task_free({
                    'name': task_name,
                    'wid': self.toggl_workspace_id,
                    'is_private': False,
                    'cid': task.project_id.partner_id.toggl_partner_id,
                })
            else:
                response = self.create_task({
                    'name': task_name,
                    'pid': task.project_id.toggl_project_id,
                    'wid': self.toggl_workspace_id,
                })

            # Update Toggl Task id to task in Odoo
            # .sudo() because we are only touching the toggl_task_id-field...
            task.sudo().write({
                'toggl_task_id': response['id'],
            })
        elif task.toggl_task_id:
            # Update only if some info has changed
            do_update = False
            if 'name' in toggl_task_info and task_name != toggl_task_info['name']:
                do_update = True
            if not 'name' in toggl_task_info and task_name:
                do_update = True
            if 'active' in toggl_task_info and not toggl_task_info['active']:
                do_update = True

            if self.subscription_type == 'pro':
                if 'pid' in toggl_task_info and task.project_id.toggl_project_id != toggl_task_info['pid']:
                    do_update = True
                if not 'pid' in toggl_task_info and task.project_id.toggl_project_id:
                    do_update = True

            if do_update:
                logger.warning("Toggl: Update task: %s" % task_name)

                if self.subscription_type == 'free':
                    self.update_task_free(task.toggl_task_id, {
                        'active': True,
                        'name': task_name,
                        'wid': self.toggl_workspace_id,
                        'is_private': False,
                        'cid': task.project_id.partner_id.toggl_partner_id,
                    })
                else:
                    self.update_task(task.toggl_task_id, {
                        'active': True,
                        'name': task_name,
                        'pid': task.project_id.toggl_project_id,
                        'wid': self.toggl_workspace_id,
                    })

        return task.toggl_task_id

    def create_update_toggl_client(self, partner, toggl_partner_info):
        if not partner.toggl_partner_id:
            logger.warning("Toggl: Create client: %s" % partner.name)

            response = self.create_client({
                'name': partner.name,
                'wid': self.toggl_workspace_id,
            })

            # Update Toggl Client id to partner in Odoo
            # .sudo() because we are only touching the toggl_partner_id-field...
            partner.sudo().write({
                'toggl_partner_id': response['id'],
            })
        elif partner.toggl_partner_id:
            # Update only if some info has changed
            do_update = False
            if 'name' in toggl_partner_info and partner.name != toggl_partner_info['name']:
                do_update = True
            if not 'name' in toggl_partner_info and partner.name:
                do_update = True

            if do_update:
                logger.warning("Toggl: Update client: %s" % partner.name)

                response = self.update_client(partner.toggl_partner_id, {
                    'name': partner.name,
                })
        return partner.toggl_partner_id

    def toggl_api_init(self):
        # Set authorization header
        auth = self.toggl_api_token + ':' + 'api_token'
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
           raise Warning("API returned error: %s, %s, %s" % (res, res.text, url))

        try:
            response = json.loads(res.text)
        except ValueError:
            raise Warning("Decoding JSON response has failed: % s" % res.text)
        return response
