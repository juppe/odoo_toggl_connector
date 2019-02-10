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
import time
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import Warning

import logging
logger = logging.getLogger(__name__)

class TogglWizard(models.TransientModel):
    _name = "toggl.wizard"
    _description = "Import Toggl Time Entries"

    @api.model
    def _default_last_fetch(self):
        user = self.env['res.users'].browse(self.env.uid)
        if user and user.toggl_last_fetch:
            return user.toggl_last_fetch

    last_fetch = fields.Date('Last fetch', default=_default_last_fetch)
    update_existing = fields.Boolean('Update existing time entries', default=True)

    date_from = fields.Date('Date From', default=_default_last_fetch, required=True)
    date_to = fields.Date('Date To', default=lambda *a: time.strftime('%Y-%m-%d'), required=True)

    def import_time_entries(self):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = self.env['toggl.connector'].search([
            ('company_id', '=', user.company_id.id)
        ])

        if not toggl:
            raise Warning("No Toggl Settings defined for your company")

        toggl.sync_time_entries_from_toggl(self.date_from, self.date_to, self.update_existing)

        user.toggl_last_fetch = self.date_to

        return {
            'name': _('My Timesheets'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.analytic.line',
            'type': 'ir.actions.act_window',
        }
