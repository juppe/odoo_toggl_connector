# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2021 Johan Tötterman
#
##############################################################################

from odoo import models, fields, api


class Project(models.Model):
    _inherit = "project.project"

    toggl_project_id = fields.Float("Toggl Project Id", digits=(16,0), copy=False, index=True)


class Task(models.Model):
    _inherit = "project.task"

    toggl_task_id = fields.Float("Toggl Task Id", digits=(16,0), copy=False, index=True)
