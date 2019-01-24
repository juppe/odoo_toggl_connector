# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2019 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = "res.company"

    toggl_connector_id = fields.Many2one('toggl.connector', 'Toggl Connector ID', help='Toggl Connector ID')
