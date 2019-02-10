# Toggl connector for Odoo version 11.0

This is software does two things:
1. It allows you to import time entries from [Toggl](https://www.toggl.com/app/timer) as timesheet entries into [Odoo](https://www.odoo.com)
1. It allows you to export your projects and tasks from Odoo to Toggl. (Only tasks beloning to a project are synced)

NOTE: This software is designed for users using one of Toggl's paid workspaces. This software uses Toggl Tasks, and they are not available on the free tier. Toggl offers a 30 day trial, if you don't have a Starter, Premium or Enterprise workspace and want to try this out.

The intended use case includes that you don't manage your clients, projects and tasks in Toggl. Clients, projects and tasks should be maintained in Odoo. This software will automatically archive all your Toggl tasks that are not in an active state in Odoo. (Here 'active' means that the task stage in Odoo is not folded by default in the kanban view).
The intended use case also includes that you use Toggl as your primary time tracking too. You should not enter or modify your timesheets in Odoo. Everything is synced from Toggl and changes made to time entries on Odoo will be overwritten during sync.

This module is designed for Odoo version 11.0

## How to use this module
* Install this software as an addon in Odoo
* Set up your Toggl Connector Settings. You need your Toggl workspace ID and the API token of an admin user in that workspace. (Settings --> Technical --> Toggl Connector Settings)
  * Choose projects to skip, if you have projects you don't want to sync to Toggl
  * Choose a suitable default project for your Toggle time entries that are missing project info in Toggl.
* Activate the Toggl Connector scheduled action to run at a frequency suitable to you. (Settings --> Technical --> Automation --> Scheduled Actions --> Toggl Connector: Sync Projects and Tasks to Toggl)
* Set up your Toggl username in your Odoo user information. (Settings --> Users --> Your user --> Preferences --> Toggl API)
* Give user access to the Toggl Connector. (Settings --> Users --> Your user --> Application Accesses --> Toggl Connector)
  * The 'Toggl Connector Manager' user access level can edit the Toggl Connector Settings.
  * The 'Toggl Connector User' access level can access the 'Toggl Time Entries' wizard.
* Create an Employee for your user in Odoo. (Human resources --> Employees)
* Go to the Timesheets menu and launch the Toggl 'Time Entries wizard' to import your time entries from Toggl.
