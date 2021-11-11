# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2021 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    toggl_entry_id = fields.Float("Toggl Time Entry Id", digits=(16,0), copy=False, index=True)
