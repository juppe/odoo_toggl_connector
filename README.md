# Toggl connector for Odoo version 11.0

This is software does two things:
1. It allows you to import time entries from [Toggl](https://www.toggl.com/app/timer) as timesheet activities into [Odoo](https://www.odoo.com)
1. It allows you to export your projects, tasks and issues from Odoo to Toggl.

NOTE: This software is designed for a specific use case and it is built for users using Toggl's Free plan. The Free plan e.g. doesn't include tasks in Toggl, so this software will create Odoo tasks and issues as projects in Toggl.
Projects, tasks and issues exported by this module will have names including formatted information about Odoo's project, task and issue ids. So please don't edit project names in Toggl if you want your time entries to find the correct project, task or issue when importing them to Odoo.

The intended use case also icludes that you don't manage your clients and projects in Toggl. Clients, projects, tasks and issues should be maintained in Odoo and all that information will be transferred from Odoo using this module. This software will automatically archive all your Toggl projects that are not in an active state in Odoo.

This module is designed for Odoo version 11.0

## How to use this module
* Install it as an addon in Odoo
* Set up your Toggl API settings in your Odoo user information. (Settings --> Users --> Your user --> Preferences --> Toggl API)
  * You can also choose projects to skip, if you have projects you never want to sync to Toggl
  * Choose a suitable analytic account for your imported Toggle time entries
* Create an Employee for your user in Odoo. (Human resources --> Employees)
  * Choose an analytic journal for your time entries (Human resources --> Employees --> Your Employee --> HR Settings --> Analytic Journal)
* Go to My Current Timesheet, save it and after that you can import all Toggl time entries for the specific period to that timesheet. (Human resources --> My Current Timesheet)
  * From the My Current Timesheet ui you can also sync all your active projects from Odoo to Toggl
