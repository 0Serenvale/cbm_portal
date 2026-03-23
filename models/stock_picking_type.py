# -*- coding: utf-8 -*-
from odoo import models, fields


class StockPickingType(models.Model):
    """Add CBM Portal configuration to Operation Types"""
    _inherit = 'stock.picking.type'

    # --- CBM Portal Settings ---
    portal_category = fields.Selection([
        ('request', 'Request'),
        ('consumption_billable', 'Consumption (Billable)'),
        ('consumption_internal', 'Consumption (Internal)'),
        ('return', 'Return'),
    ], string='Portal Category',
       help='How this operation type appears in CBM Portal')

    portal_visible = fields.Boolean(
        'Show in CBM Portal',
        default=False,
        help='If checked, this operation type will appear as an icon in CBM Portal')

    portal_requires_patient = fields.Boolean(
        'Requires Patient',
        default=False,
        help='If checked, user must select a patient before adding products')

    portal_requires_department = fields.Boolean(
        'Requires Department',
        default=False,
        help='If checked, user must select a department partner (CBM: prefixed partners) for delivery address')

    portal_icon = fields.Selection([
        # === HEALTHCARE / MEDICAL ===
        ('heart', 'Heart (Health/Cardio)'),
        ('beaker', 'Beaker (Pharmacy/Lab)'),
        ('eye-dropper', 'Eye Dropper (Medication)'),
        ('shield-check', 'Shield Check (Protection)'),
        ('hand-raised', 'Hand Raised (Stop/Hygiene)'),
        ('fire', 'Fire (Emergency)'),
        ('bolt', 'Bolt (Emergency/Urgent)'),
        ('lifebuoy', 'Lifebuoy (Emergency/Rescue)'),
        ('sparkles', 'Sparkles (Clean/Sterile)'),
        ('sun', 'Sun (Radiology/Light)'),
        ('moon', 'Moon (Night Shift)'),
        ('eye', 'Eye (Ophthalmology)'),
        ('face-smile', 'Smile (Pediatrics)'),
        ('scale', 'Scale (Weight/Measure)'),
        # === PRODUCTS / INVENTORY ===
        ('cube', 'Cube (Products)'),
        ('cube-transparent', 'Cube Transparent (Stock)'),
        ('archive-box', 'Archive Box (Storage)'),
        ('archive-box-arrow-down', 'Archive In (Reception)'),
        ('inbox-stack', 'Inbox Stack (Receptions)'),
        ('inbox-arrow-down', 'Inbox Down (Receive)'),
        ('gift', 'Gift (Samples)'),
        ('shopping-bag', 'Shopping Bag (Supplies)'),
        ('shopping-cart', 'Shopping Cart (Orders)'),
        # === DOCUMENTS / ADMIN ===
        ('document-text', 'Document (Forms)'),
        ('document-check', 'Document Check (Validated)'),
        ('document-duplicate', 'Document Duplicate (Copy)'),
        ('clipboard', 'Clipboard (Tasks)'),
        ('clipboard-document-list', 'Clipboard List (Checklist)'),
        ('clipboard-document-check', 'Clipboard Check (Completed)'),
        ('folder', 'Folder (Group)'),
        ('folder-open', 'Folder Open (Browse)'),
        ('banknotes', 'Banknotes (Invoices)'),
        ('currency-dollar', 'Dollar (Finance)'),
        ('calculator', 'Calculator (Accounting)'),
        ('chart-bar', 'Chart Bar (Reports)'),
        ('chart-pie', 'Chart Pie (Statistics)'),
        ('presentation-chart-line', 'Chart Line (Trends)'),
        # === OPERATIONS / WORKFLOW ===
        ('arrow-path', 'Arrow Path (Return/Exchange)'),
        ('arrows-right-left', 'Arrows Exchange (Transfer)'),
        ('arrow-down-tray', 'Arrow Down (Download/Receive)'),
        ('arrow-up-tray', 'Arrow Up (Upload/Send)'),
        ('arrow-uturn-left', 'U-Turn (Return)'),
        ('truck', 'Truck (Delivery)'),
        ('paper-airplane', 'Paper Airplane (Send)'),
        ('rocket-launch', 'Rocket (Fast/Priority)'),
        # === TOOLS / MAINTENANCE ===
        ('wrench-screwdriver', 'Wrench (Maintenance)'),
        ('wrench', 'Wrench Only (Repair)'),
        ('cog-6-tooth', 'Cog (Settings)'),
        ('cog-8-tooth', 'Cog Large (Config)'),
        ('adjustments-horizontal', 'Adjustments (Preferences)'),
        ('key', 'Key (Access/Security)'),
        ('lock-closed', 'Lock Closed (Secured)'),
        ('lock-open', 'Lock Open (Unlocked)'),
        # === PEOPLE / USERS ===
        ('user', 'User (Person)'),
        ('user-circle', 'User Circle (Profile)'),
        ('user-plus', 'User Plus (Add Patient)'),
        ('user-group', 'User Group (Team)'),
        ('users', 'Users (People)'),
        ('identification', 'ID Card (Patient ID)'),
        # === COMMUNICATION ===
        ('bell', 'Bell (Notifications)'),
        ('bell-alert', 'Bell Alert (Urgent)'),
        ('envelope', 'Envelope (Messages)'),
        ('phone', 'Phone (Contact)'),
        ('chat-bubble-left-right', 'Chat (Communication)'),
        ('megaphone', 'Megaphone (Announcement)'),
        # === STATUS / INFO ===
        ('check-circle', 'Check Circle (Approved)'),
        ('x-circle', 'X Circle (Rejected)'),
        ('exclamation-circle', 'Exclamation (Warning)'),
        ('exclamation-triangle', 'Triangle (Alert)'),
        ('information-circle', 'Info (Information)'),
        ('question-mark-circle', 'Question (Help)'),
        ('clock', 'Clock (Time/Pending)'),
        ('calendar', 'Calendar (Schedule)'),
        ('calendar-days', 'Calendar Days (Appointments)'),
        # === MISC ===
        ('plus-circle', 'Plus Circle (Add New)'),
        ('minus-circle', 'Minus Circle (Remove)'),
        ('qr-code', 'QR Code (Barcode)'),
        ('building-office', 'Building (Department)'),
        ('home', 'Home (Dashboard)'),
        ('map-pin', 'Map Pin (Location)'),
        ('tag', 'Tag (Label)'),
        ('bookmark', 'Bookmark (Favorite)'),
        ('star', 'Star (Priority)'),
        ('flag', 'Flag (Mark)'),
    ], string='Portal Icon', default='cube',
        help='Select the icon to display in CBM Portal')

    # --- Pending Enforcement Thresholds (per operation type) ---
    pending_warn_threshold = fields.Integer(
        string='Seuil Alerte',
        default=3,
        help='Show warning when user has this many pending requests.')
    
    pending_block_threshold = fields.Integer(
        string='Seuil Blocage',
        default=5,
        help='Block new requests when user has this many pending. 0 = no blocking.')

