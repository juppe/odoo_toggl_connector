# -*- coding: utf-8 -*-
##############################################################################
#
#    ODOO Addon module by Johan Tötterman
#    Copyright (C) 2019 Johan Tötterman
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
        'base',
        'project',
        'hr_timesheet',
    ],
    'data': [
        'security/toggl_connector_security.xml',
        'security/ir.model.access.csv',
        'view/toggl_connector_view.xml',
        'view/res_company.xml',
        'view/res_users.xml',
        'wizard/toggl_entries_wizard_view.xml',
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