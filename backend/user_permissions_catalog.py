"""
user_permissions_catalog.py — the master list of staff permissions, grouped by category.

The catalog is authored as plain text (CATALOG_TEXT) below — a line with no " - " is a
CATEGORY header; a line "Label - description" is a permission under the current category.
`build_catalog()` parses it into [{category, items:[{key,label,desc}]}] with a stable
snake_case `key` per permission (used as the storage key in user_permissions).

This is the single source of truth for the permissions editor (the grouped checkbox grid)
and for any code that wants to check a permission by key.
"""
import re

CATALOG_TEXT = """
Accounts
Accounts Action - Allow user to access actions buttons under account listing
Accounts Demo Sub Role View - Allow user to view demo accounts of there sub role as well
Accounts Detail View - Allow user to view account detail view
Accounts Ib Sub Role View - Allow user to view IB accounts of there sub role as well
Accounts Live Sub Role View - Allow user to view Live accounts of there sub role as well
Accounts Mam Sub Role View - Allow user to view mam accounts of there sub role as well
Accounts Sub Role View - Allow user to view accounts of there sub role as well
Announcements
Announcements Create - Allow user to create announcements
Announcements Delete - Allow user to delete announcements
Announcements Update - Allow user to update announcements
Articles
Articles Create - Allow user to create articles
Articles Delete - Allow user to delete articles
Articles Update - Allow user to update articles
Client
Client Menu Sub - Allow to user to view his sub user Client as well
Clients Create - Allow user to create clients
Clients Delete - Allow user to delete clients
Clients Demo Account - Allow user to view & create demo account
Clients Deposit - Allow user to view deposit
Clients Live Account - Allow user to view and create live account
Clients Sub Role View - Allow to user to view his sub user Client as well
Clients Transfer - Allow user to view all transfer
Clients Update - Allow user to update clients
Clients Withdraw - Allow user to view all withdraw
Menu Clients D1 - Allow users to view d1 clients menu
Menu Clients D2 - Allow user to view d2 clients menu
Menu Clients D3 - Allow user to view d3 clients menu
Menu Clients Main - Allow user to view menu clients main
Contacts
Contacts Create - Allow user to create contacts
Contacts Delete - Allow user to delete contacts
Contacts Sub Role View - Allow to user to view his sub user contacts as well
Contacts Update - Allow user to update contacts
Contacts View - Allow user to view all contacts
Contracts
Contracts Create - Allow user to create contracts
Contracts Delete - Allow user to delete contracts
Contracts Sign - Allow user to sign contracts
Contracts Update - Allow user to update contracts
Contracts View All - Allow user to view all contracts
Credits
Credits Create - Allow user to create credit notes
Credits Delete - Allow user to delete credit notes
Credits Send - Allow user to send credit notes
Credits Update - Allow user to update credit notes
Credits View All - Allow user to view all creditnotes
Deals
Deals Create - Allow user to create deals
Deals Delete - Allow user to delete deals
Deals Send Email - Allow user to send deal emails
Deals Sub Role View - Allow user to view deals of sub roles as well
Deals Update - Allow user to update deals
Deposit
Deposit Account Approve - Deposit account approve
Deposit Account Create - Deposit account create
Deposit Account Reject - Deposit account reject
Disable Deposit - Restrict client side deposit
Ekyc
Ekyc Approve - Allow user to approve/reject ekyc doucment
Ekyc Reject - Allow user to approve/reject ekyc document
Estimates
Estimates Comment - Allow user to post estimate comments
Estimates Create - Allow user to create estimates
Estimates Delete - Allow user to delete estimates
Estimates Send - Allow user to sent estimates
Estimates Update - Allow user to update estimates
Estimates View All - Allow user to view all estimates
Events
Events Create - Allow user to create events
Events Update - Allow user to update events
Expenses
Expenses Create - Allow user to create expenses
Expenses Delete - Allow user to delete expenses
Expenses Update - Allow user to update expenses
Expenses View All - Allow user to view all expenses
Files
Files Create - Allow user to create files
Files Delete - Allow user to delete files
Files Update - Allow user to update files
Invoices
Invoices Comment - Allow user to post invoice comments
Invoices Create - Allow user to create invoices
Invoices Delete - Allow user to delete invoices
Invoices Pay - Allow user to pay invoices offline
Invoices Remind - Allow user to send invoice reminders
Invoices Send - Allow user to send invoices
Invoices Update - Allow user to update invoices
Invoices View All - Allow user to view all invoices
Issues
Issues Create - Allow user to create issues
Issues Delete - Allow user to delete issues
Issues Update - Allow user to update issues
Lead
Change Staff External Invitee - Allow staff to change external invitee user
Lead Activity - Allow to user to view lead activity
Lead Calendar - Allow users to Access Lead Calendar Menu
Lead Calls - Allow user to Access Leads Calls
Lead Comments - Allow user to Access Lead Comments Menu
Lead Demo Account Create - Allow user to access Lead Demo Account Create
Lead Demo Accounts - Allow user to access lead_demo accounts Menu
Lead Email - Allow user to access Lead Email
Lead Files - Allow User to access Lead Files Menu
Lead Info - Allow user to view Lead Info
Lead Live Account - Allow User to access Lead Live Account Menu
Lead Live Account Create - Allow to user access Lead Live Account Create
Lead Menu - Allow user to Access Lead Menu
Lead Menu Sub - Allow user to access Lead Menu of Sub user
Lead Overview - Allow user to Access Leads overview page
Lead Sms - Allow User to access Lead SMS Menu
Lead View - Allow User to Access lead View
Lead Whatsapp - Allow user to Access Lead Whatsapp Menu
Leads Create - Allow user to create leads
Leads Delete - Allow user to delete leads
Leads Update - Allow user to update leads
Menu Leads Main - Allow users to view menu leads main
Menu Leads Registered - Allow user to view leads register menu
Menu Leads Verified - Allow user to view leads verified menu
Menus
Menu Accounts - Allow user to view account menu
Menu Automated Emails - Allow user to automated emails contents menu
Menu Bonus Transactions - Allow user to view bonus menu
Menu Calendar - Allow user to view calendar menu
Menu Clients - Allow user to view clients menu
Menu Contacts - Allow user to view contacts menu
Menu Contents - Allow user to view contents menu
Menu Contracts - Allow user to view contracts menu
Menu Creditnotes - Allow user to view creditnotes menu
Menu Daily Analysis - Allow user to view transaction menu
Menu Deals - Allow user to view deals menu
Menu Demo Accounts - Allow user to view demo account menu
Menu Deposit Transactions - Allow user to view transaction menu
Menu Ekyc - Allow user to approve/reject ekyc doucment
Menu Email - Allow user to view transaction menu
Menu Email Campaigns - Allow user to email campaigns contents menu
Menu Email Marketing - Allow user to email marketing contents menu
Menu Estimates - Allow user to view estimates menu
Menu Expenses - Allow user to view expenses menu
Menu Home - Allow user to view homepage
Menu Ib Accounts - Allow user to view ib account menu
Menu Ib Clients - Allow User to view IB Clients menu
Menu Ib Requests - Allow User to view IB requests menu
Menu Investments - Allow user to investments contents menu
Menu Invoices - Allow user to view invoices menu
Menu Items - Allow user to view items menu
Menu Knowledgebase - Allow user to view knowledgebase menu
Menu Ld Account Transactions - Allow user to ld account transactions
Menu Leads - Allow user to view leads menu
Menu Live Accounts - Allow user to view live account menu
Menu Mam Accounts - Allow user to view mam account menu
Menu Marketing - Allow user to view marketing menu
Menu Marketing Main - Allow user to marketing main contents menu
Menu Messages - Allow user to view messages menu
Menu Notes - Allow user to view notes menu
Menu Partners - Allow User to view Partner menu
Menu Payments - Allow user to view payments menu
Menu Projects - Allow user to view projects menu
Menu Reports - Allow user to view reports menu
Menu Sales - Allow user to view sales menu
Menu Settings - Allow user to view settings menu
Menu Settings Account Groups - Allow user to view account groups settings menu
Menu Settings Account Types - Allow user to view account types settings menu
Menu Settings General - Allow user to view general settings menu
Menu Settings Lead - Allow user to view lead settings menu
Menu Settings Opportunities - Allow user to view opportunities settings menu
Menu Settings Payment - Allow user to view system settings menu
Menu Settings System - Allow user to view system settings menu
Menu Settings Theme - Allow user to view theme settings menu
Menu Settings Ticket - Allow user to view ticket settings menu
Menu Settings Translation - Allow user to view translation settings menu
Menu Settings Wallet Types - Allow user to view wallet types settings menu
Menu Sms Campaigns - Allow user to sms campaigns contents menu
Menu Social Campaigns - Allow user to social campaigns contents menu
Menu Social Trading - Allow user to social trading contents menu
Menu Subscriptions - Allow user to view subscriptions menu
Menu Tasks - Allow user to view tasks menu
Menu Tax Rates - Allow user to view tax rates menu
Menu Templates - Allow user to templates contents menu
Menu Tickets - Allow user to view tickets menu
Menu Todo - Allow user to access todo menu
Menu Tools - Allow user to tools contents menu
Menu Transactions - Allow user to view transaction menu
Menu Transfer Transactions - Allow user to view transaction menu
Menu Users - Allow user to view users menu
Menu Wallet - Allow user to view wallet menu
Menu Wallet Transactions - Allow user to view all Wallet transaction menu
Menu Withdrawal Transactions - Allow user to view transaction menu
Menu Archived Accounts - Allow user to view archived accounts menu
Menu Enquiries - Allow user to view enquiries menu
Menu Ib Contest - Permission to view IB contest menu
Menu Loyaltypoints Transactions - Allow user to view loyalty points transactions
Menu Products - Allow user to see products menu
Menu Settings Wallet Card Details - Allow user to view menu wallet card settings
Menu Wallet Accounts - Allow user to view menu wallet accounts
Menu Settings Ib Contests - Allows User to set up Contests and Promotional Events
Milestones
Milestones Create - Allow user to create milestones
Milestones Delete - Allow user to delete milestones
Milestones Update - Allow user to update milestones
Pamm
Pamm Account Approve Reject - Pamm Account Approve/Reject
Partner
Partner Relation Action - partner relation action
Payments
Payments Delete - Allow user to delete payments
Payments Update - Allow user to update payments
Payments View All - Allow user to view all projects
Project
Project Menu Bugs - Allow user to view project bugs
Project Menu Calendar - Allow user to view project calendar
Project Menu Comments - Allow user to view project discussions
Project Menu Dashboard - Allow user to view project overview
Project Menu Files - Allow user to view project files
Project Menu Gantt - Allow user to view project gantt
Project Menu Links - Allow user to view project links
Project Menu Milestones - Allow user to view project milestones
Project Menu Notes - Allow user to view project notes
Project Menu Tasks - Allow user to view project tasks
Project Menu Team - Allow user to view project team
Project Menu Timesheets - Allow user to view project timesheet
Projects Copy - Allow user to clone projects
Projects Create - Allow user to create projects
Projects Delete - Allow user to delete projects
Projects Download - Allow user to download projects PDF
Projects Update - Allow user to update projects
Projects View All - Allow user to view all projects
Projects View Clients - Allow user to view project clients
Projects View Cost - Allow user to view project cost
Projects View Expenses - Allow user to view project expenses
Projects View Hours - Allow user to view project hours
Projects View Notes - Allow user to view project notes
Projects View Tasks - Allow user to view project tasks
Projects View Team - Allow user to view project team
Projects View Used Budget - Allow user to view project budget
Roles
Roles Create - Allow user to create roles
Roles Delete - Allow user to delete roles
Roles Update - Allow user to update roles
Roles View All - Allow user to view all roles
Settings
Settings Update - Allow user to update settings
Settings - Allow user to modify settings
Subscriptions
Subscriptions Create - Allow user to create customer subscriptions
Subscriptions Delete - Allow user to delete subscriptions
Subscriptions Update - Allow user to view subscription listing
Tasks
Tasks Complete - Allow user to mark tasks as completed
Tasks Create - Allow user to create tasks
Tasks Delete - Allow user to delete tasks
Tasks Update - Allow user to update tasks
Taxes
Taxes Create - Allow user to create taxes
Taxes Delete - Allow user to delete taxes
Taxes Update - Allow user to update taxes
Tickets
Tickets Action - Allow to user to view action buttons
Tickets Create - Allow user to create tickets
Tickets Delete - Allow user to delete tickets
Tickets Detail View - Allow user to view ticket detail view
Tickets List View - Allow user to access tickets list view
Tickets Reporter - Allow user to select ticket reporter
Tickets Sub Role View - Allow to user to view his sub user Tickets as well
Tickets Update - Allow user to update tickets
Timer
Timer Create - Allow user to create time entry
Timer Delete - Allow user to delete logged time
Timer Start - Allow user to start timer
Timer Update - Allow user to update logged time
Transactions
Transactions Detail View - Allow user to view details
Transfer
Disable Transfer - Restrict client side Transfer
Transfer Account Approve - transfer account approve
Transfer Account Create - transfer account create
Transfer Account Reject - transfer account reject
Users
User Impersonate - Allow admin to impersonate user
User Menu Sub - Allow user to view list of sub users
Users Assign - Allow user to assign other users
Users Create - Allow user to create other users
Users Delete - Allow user to delete users
Users Update - Allow user to update users
Withdrawal
Disable Withdrawal - Restrict client side Withdrawal
Withdrawal Account Approve - withdrawal account approve
Withdrawal Account Create - withdrawal account create
Withdrawal Account Reject - withdrawal account reject
Other
Activities View All - Allow user to view all activities
Allow Ip Address - Allow user to view IP address
Allow User For Third Party Trasnsfer - Allow User For Third Party Transfer
Allow User To Edit Pamm Profile Pic - Allow user to edit PAMM profile picture
Change Sales Agent - change sales agent
Client Bonus Create - Allow user to create clients bonus
Client Ib Account Tab - Allow user to view client IB account Tab
Client Ld Account Tab - Allow user to view client LD account Tab
Client Mam Account Tab - Allow user to view client MAM account Tab
Client Pamm Account Tab - Allow user to view client PAMM account Tab
Client Phone Update - This is to Enable/Disable Contact update option
Clients Archive - Allow user to view Archive buttons
Clients Bonus Tab - Allow user to view clients bonus tab
Clients Contact - Allow user to view clients/leads contact feature
Comments Delete - Allow user to delete comments
Comments Update - This is to Enable/Disable Comments update option
Create Ib Account Button - Enable Create IB account button in IB TAB
Delete Deposites - Allow user to delete deposites
Delete Withdrawals - Allow user to delete withdraw
Demo Account Create - Demo account create
Deposit Commission Tab - Allow staff to see their commission
Download Clients Csv - Allow users to download Clients csv
Download Leads Csv - Allow users to download leads csv
Enable Add Commission Ib Accounts - Allow user to access add commission
Enable Campaign Create - Allow user to view campaign create button
Enable Csv Export - Allow user to export csv file
Enable Demo Accounts Csv Export - Allow user to download all the demo accounts CSV
Enable Encrypt Client Email Phone - Enable Clients emails and phone encryption
Enable Loyalty System Program - Allow Client side loyalty system program
Enable Switch Group Ib Accounts - Allow user to access IB switch group
Enable Update Partner Ib - allow user to change IB Partner
Funding Bonus Sub Role View - Allow user to access Funding Bonus of sub user as well
Funding Deposits Sub Role View - Allow user to access Funding Deposits of sub-user as well
Funding Transfer Sub Role View - Allow user to access Funding Transfer of sub-user as well
Funding Withdrawal Sub Role View - Allow user to access Funding Withdrawal of sub-user as well
Highlight User Email - Highlight the user email in funding page
Install Updates - Allow user to install updates
Ld Transaction Delete - allow user to delete ld transaction
Lead Phone Update - This is to Enable/Disable Contact update option
Links Create - Allow user to create links
Live Account Create - Live account create
Messages Send To All - Allow user to send messages to all users
Pamm Account Transaction - Allow user for PAMM account transaction
Parent Clients - This is the Parent permission for Clients
Partner Column Hide - Enable this permission to hide partner column
Reminders Create - Allow user to create reminders
Reports Module - Allow user to view to view report sub menus
Reset Balance Button - Allow user to view reset balance button
Show Archived Clients - allow user to view archived clients
Show Dashboard Funding Statistics - Allow user to view dashboard funding stastics
Staff Invite Link - Allow user to send staff invite link
Top Search - Allow user to allow top search
View All Accounts - Allow user to view all accounts
View All Clients - Allow user to view all clients
View All Ekyc - Allow user to view all ekyc
View All Fundings - Allow user to view all funding
View All Leads - Allow user to view all leads
View All Sales Agents - Allow User To View All Sales Agents
View All Tickets - Allow user to view all tickets
View All User - Allow user to view all users
View Sham Cash Payment Method - allow user to view sham payment method
View Staff Users - Allow user to view staff users
View Single Client - Allow user to view single client
View Single Lead - Allow user to view single lead
"""


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")


def build_catalog():
    """Parse CATALOG_TEXT into [{category, items:[{key,label,desc}]}]. Stable, deduped by key."""
    cats = []
    cur = None
    seen = set()
    for line in CATALOG_TEXT.splitlines():
        line = line.strip()
        if not line:
            continue
        if " - " in line:
            label, desc = line.split(" - ", 1)
            label, desc = label.strip(), desc.strip()
            key = _slug(label)
            if cur is None:
                cur = {"category": "Other", "items": []}
                cats.append(cur)
            if key in seen:
                continue
            seen.add(key)
            cur["items"].append({"key": key, "label": label, "desc": desc})
        else:
            cur = {"category": line, "items": []}
            cats.append(cur)
    return [c for c in cats if c["items"]]


CATALOG = build_catalog()
ALL_KEYS = {it["key"] for c in CATALOG for it in c["items"]}


if __name__ == "__main__":
    n = sum(len(c["items"]) for c in CATALOG)
    print(f"{len(CATALOG)} categories, {n} permissions")
    for c in CATALOG[:3]:
        print(" ", c["category"], "->", [it["key"] for it in c["items"][:3]], "...")
