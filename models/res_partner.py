# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2021 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    toggl_partner_id = fields.Float("Toggl Partner Id", digits=(16,0), copy=False, index=True)
