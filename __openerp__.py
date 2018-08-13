# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2018 Johan Tötterman
#
##############################################################################

{
    'name': 'Odoo - Toggl Connector',
    'version': '0.1',
    'license': 'Other proprietary',
    'category': 'Timesheets',
    'description': 'Toggl Connector for Odoo',
    'author': 'Johan Tötterman',
    'maintainer': 'Johan Tötterman',
    'website': 'http://www.sprintit.fi',
    'depends': [
        'project',
        'project_issue',
        'hr_timesheet',
        'hr_timesheet_sheet',
    ],
    'data': [
        'security/toggl_security.xml',
        'security/ir.model.access.csv',
        'view/hr_timesheet_sheet.xml',
        'view/res_users.xml',
    ],
    'demo': [
    ],
    'test': [
    ],
    'external_dependencies': {
    },
    'installable': True,
    'auto_install': False,
 }
