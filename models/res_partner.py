# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2019 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = "res.partner"

    toggl_partner_id = fields.Integer("Toggl Partner Id", copy=False, index=True)
