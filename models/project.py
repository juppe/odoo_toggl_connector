# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2019 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api

class Project(models.Model):
    _inherit = "project.project"

    toggl_project_id = fields.Integer("Toggl Project Id", copy=False, index=True)

class Task(models.Model):
    _inherit = "project.task"

    toggl_task_id = fields.Integer("Toggl Task Id", copy=False, index=True)
