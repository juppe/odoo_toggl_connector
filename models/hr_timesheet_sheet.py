# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2018 Johan Tötterman
#
##############################################################################

import re

from openerp import models, fields, api
from openerp.exceptions import Warning

import logging
logger = logging.getLogger(__name__)

class hr_timesheet_sheet(models.Model):
    _inherit = "hr_timesheet_sheet.sheet"

    def toggl_api_init(self, user):
        api_key = user.toggl_api_token
        workspace_id = user.toggl_workspace_id

        if not api_key or not workspace_id:
            raise Warning ('Please fill in your Toggl API Key and Workspace ID in your user preferences.')

        # Init Toggl api
        self.toggl = self.env['toggl.api']
        self.toggl.set_authorization(api_key)
        self.toggl.workspace_id = workspace_id
        self.toggl.me = self.toggl.me()

    @api.multi
    def sync_time_entries_from_toggl(self):
        user = self.env['res.users'].browse(self.env.uid)
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)

        if not employee:
            raise Warning ('Please link your Odoo user to an Employee.')

        if employee != self.employee_id:
            raise Warning ('You can only interact with Toggl from your own timesheet.')

        if not employee.journal_id:
            raise Warning ('Please assign an Analytic Journal to your employee.')

        if not user.toggl_analytic_account:
            raise Warning ('Please assign a default Analytic Account to your user.')

        self.toggl_api_init(user)

        report_params = {
            'workspace_id': self.toggl.workspace_id,
            'user_ids': self.toggl.me['data']['id'],
            'since': self.date_from,
            'until': self.date_to,
            'page': 1,
        }

        time_entries = []

        # Get detailed report of Toggl time entries, one page a time
        while True:
            time_entries_page = self.toggl.detailed_report(params=report_params)
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

            hr_timesheet = {
                'sheet_id': self.id,
                'name': time_entry['description'],
                'user_id': self.env.uid,
                'date': time_entry['start'][0:10],
                'account_id': user.toggl_analytic_account.id,
                'journal_id': employee.journal_id.id,
                'unit_amount': duration,
                'ref': time_entry['id'],
                'task_id': None,
                'issue_id': None,
            }

            # Match Odoo project/task/issue info from Togl time entry project info
            te_project = re.search(r"([PIT]): (.*) \[([0-9]*)\] \[([0-9]*)\]", time_entry['project'])

            if te_project:
                project_type = unicode(te_project.group(1))
                description = unicode(te_project.group(2))
                project_id = int(te_project.group(3))
                analytic_account_id = int(te_project.group(4))

                if analytic_account_id:
                    # Fetch Project/Analytic Account (account.analytic.account)
                    analytic_account = self.env['account.analytic.account'].search([('id', '=', analytic_account_id)], limit=1)

                    if analytic_account:
                        hr_timesheet['account_id'] =  analytic_account['id']
                        hr_timesheet['to_invoice'] =  analytic_account['to_invoice']

                # Toggl Project is an Odoo task
                if project_type and project_id and project_type == "T":
                    hr_timesheet['task_id'] = project_id
                # Toggl Project is an Odoo issue
                elif project_type and project_id and project_type == "I":
                    hr_timesheet['issue_id'] = project_id

            # Check if entry exists in Odoo
            odoo_te = self.env['hr.analytic.timesheet'].search([
                ('user_id', '=', self.env.uid),
                ('ref', '=', time_entry['id']),
            ], limit=1)

            if not odoo_te:
                # Create  time entry
                self.env['hr.analytic.timesheet'].create(hr_timesheet)
                logger.warning("Create time entry: %s" % (hr_timesheet['name']))
            elif not odoo_te.invoice_id:
                # Update time entry
                odoo_te.write(hr_timesheet)
                logger.warning("Update time entry: %s" % (hr_timesheet['name']))

    @api.multi
    def sync_projects_to_toggl(self):
        user = self.env['res.users'].browse(self.env.uid)
        self.toggl_api_init(user)

        # Fetch clients from Toggl
        toggl_clients = self.toggl.clients(self.toggl.workspace_id)
        if not toggl_clients:
            toggl_clients = []

        # Fetch all project from Toggl
        self.toggl_projects = self.toggl.projects(self.toggl.workspace_id)
        if not self.toggl_projects:
            self.toggl_projects = []

        # Active projects in Toggl
        toggl_projects_active = []

        # Fetch task types from Odoo
        # In this API we only sync tasks and issues to Toggl
        # that are in a stage that is not folded in Odoo's Kanban view
        task_types = self.env['project.task.type'].search([('fold', '=', False)])
        task_types = task_types.mapped('id')

        # Skip these projects when syncing to Toggl
        projects_skipped = user.toggl_skip_projects.mapped('name')

        # Fetch all open analytic accounts from Odoo
        analytic_accounts = self.env['account.analytic.account'].search([('state', '=', 'open')])

        for analytic_account in analytic_accounts:

            # Fetch all open projects from Odoo
            projects = self.env['project.project'].search([
                ('state', '=', 'open'),
                ('analytic_account_id', '=', analytic_account.id),
                ('name', 'not in', projects_skipped),
            ])

            if not projects:
                # Analytic account has no project, then we use the analytic account as a project in Toggl
                projects = [analytic_account]

            for project in projects:
                client_id = 0

                if project.partner_id:
                    cliname = project.partner_id.name

                    client_exists = filter(lambda c: c['name']==cliname, toggl_clients)

                    if not client_exists:
                        response = self.toggl.create_client({
                            'name': cliname,
                            'wid': self.toggl.workspace_id,
                        })
                        toggl_clients.append(response)
                        client_id = response['id']
                    else:
                        client_id = client_exists[0]['id']

                if hasattr(project, 'analytic_account_id'):
                    # This is a project
                    aa_id = project.analytic_account_id.id
                    is_project = True
                else:
                    # This is an analytic account
                    aa_id = project['id']
                    is_project = False

                # Create Toggl project
                toggl_pid = self.create_toggl_project({
                    'type': 'P',
                    'name': project['name'],
                    'id': project['id'],
                    'analytic_account_id': aa_id,
                    'client_id': client_id,
                })
                toggl_projects_active.append(toggl_pid)

                if is_project:
                    # Fetch tasks from Odoo
                    tasks = self.env['project.task'].search([
                        ('active', '=', True),
                        ('project_id', '=', project['id']),
                        ('stage_id', 'in', task_types),
                    ])

                    for task in tasks:
                        # Create Toggl project from Odoo task
                        toggl_pid = self.create_toggl_project({
                            'type': 'T',
                            'name': task['name'],
                            'id': task['id'],
                            'analytic_account_id': aa_id,
                            'client_id': client_id,
                        })
                        toggl_projects_active.append(toggl_pid)

                    # Fetch issues from Odoo
                    issues = self.env['project.issue'].search([
                        ('active', '=', True),
                        ('project_id', '=', project['id']),
                        ('stage_id', 'in', task_types),
                    ])

                    for issue in issues:
                        # Create Toggl project from Odoo issue
                        toggl_pid = self.create_toggl_project({
                            'type': 'I',
                            'name': issue['name'],
                            'id': issue['id'],
                            'analytic_account_id': aa_id,
                            'client_id': client_id,
                        })
                        toggl_projects_active.append(toggl_pid)

        # Deactivate Toggl projects that are not active in Odoo anymore
        for project in self.toggl_projects:
            if not project['id'] in toggl_projects_active:
                response = self.toggl.update_project(project['id'], {
                    'active': False,
                })
                logger.warning("Deactivate project: %s" % project['name'])

    def create_toggl_project(self, params):
        # Project name is the only field we have access to when using Toggl free tier,
        # therefore we create this 'silly' structured name for the project
        project_name = "%s: %s [%s] [%s]" % (params['type'], params['name'], params['id'], params['analytic_account_id'])

        # Check if this project already exists in Toggl
        reg = re.compile("%s: .* \\[%s\\] \\[%s\\]" % (params['type'], params['id'], params['analytic_account_id']))
        toggl_project = filter(lambda p: reg.match(p['name']), self.toggl_projects)

        if not toggl_project:
            project = {
                'name': project_name.encode(),
                'wid': self.toggl.workspace_id,
                'is_private': False,
            }

            if params['client_id']:
                project['cid'] = params['client_id']

            # Create Toggl project
            response = self.toggl.create_project(project)
            logger.warning("Create project: %s" % project_name)
            return response['id']
        elif project_name != toggl_project[0]['name']:
            response = self.toggl.update_project(toggl_project[0]['id'], {
                'active': True,
                'name': project_name,
            })
            logger.warning("Update project: %s != %s" % (project_name, toggl_project[0]['name']))
            return response['id']
        else:
            return toggl_project[0]['id']
