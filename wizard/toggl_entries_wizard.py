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
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import Warning

import logging
logger = logging.getLogger(__name__)

class TogglWizard(models.TransientModel):
    _name = "toggl.wizard"
    _description = "Import Toggl Time Entries"

    name = fields.Char('Connector Name')
    date_from = fields.Date('Date From', default=lambda *a: time.strftime('%Y-%m-%d'))
    date_to = fields.Date('Date To', default=lambda *a: time.strftime('%Y-%m-%d'))

    def import_time_entries(self):
        user = self.env['res.users'].browse(self.env.uid)
        toggl = user.company_id.toggl_connector_id

        toggl.sync_time_entries_from_toggl(self.date_from, self.date_to)

        return {
            'name': _('My Timesheets'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.analytic.line',
            'type': 'ir.actions.act_window',
        }
