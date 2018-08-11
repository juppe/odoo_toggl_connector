# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Open Source Management Solution
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2018 Johan Tötterman
#
##############################################################################

from openerp import models, fields, api

class res_users(models.Model):
    _inherit = "res.users"

    toggl_api_token = fields.Char('Toggl API token', help='Toggl API token')
    toggl_workspace_id = fields.Integer('Toggl workspace ID', help='Toggl workspace ID')
    toggl_analytic_account = fields.Many2one('account.analytic.account', string='Default analytic account', help='Default analytic account for Toggl time entries')
    toggl_skip_projects = fields.Many2many('project.project', string='Projects to skip', help='Projects to skip when syncing to Toggl')
