# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2021 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    toggl_username = fields.Char('Toggl Username', help='Toggl Username (Email)')
    toggl_last_fetch = fields.Date('Last date Toggl Timesheets were fetched')
