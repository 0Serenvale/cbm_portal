# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ClinicPortalTile(models.Model):
    _name = 'clinic.portal.tile'
    _description = 'Clinic Portal Tile'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    
    type = fields.Selection([
        ('stock', 'Stock Operation'),
        ('action', 'Window Action'),
        ('client_action', 'Client Action (Discuss, etc.)'),
        ('folder', 'Folder (Group)'),
    ], string='Type', required=True, default='stock')
    
    # --- THE BEHAVIOR (The "Scenario") ---
    # This solves the "Internal Transfer" clash.
    # Multiple tiles can use the same Operation Type but behave differently.
    stock_behavior = fields.Selection([
        ('request', 'Request (Pull from Warehouse)'),
        ('billable', 'Patient Consumption (Billing)'),
        ('surgery', 'Surgery Kiosk (Fast Billing)'),
        ('internal', 'Internal Use (Non-Billable)'),
        ('return', 'Return (Push to Warehouse)'),
    ], string='Stock Behavior', default='request',
        help="Request: Source = Warehouse (fixed), Dest = User's location\n"
             "Patient Consumption: Source = User's location, Dest = Virtual/Patient, Creates SO\n"
             "Surgery Kiosk: Same as Patient but with barcode scanner UI\n"
             "Internal Use: Source = User's location, Dest = Virtual (no SO)\n"
             "Return: Source = User's location, Dest = Warehouse (fixed)")
    
    # For consumption: where to get stock FROM
    consumption_source = fields.Selection([
        ('ward', "User's Ward (from Access Control)"),
        ('pharmacy', 'Pharmacy Location (from Settings)'),
        ('magasin', 'Magasin Location (from Settings)'),
    ], string='Consumption Source', default='ward',
        help="Where to consume stock from:\n"
             "User's Ward: Uses destination of user's pharmacy operation type\n"
             "Pharmacy: Direct consumption from central pharmacy\n"
             "Magasin: Consumption from supplies warehouse")

    # Link to operation type
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Operation Type',
        help='The stock operation type to use for this tile.')
    
    # Fixed source location (for request/consume behaviors)
    source_location_id = fields.Many2one(
        'stock.location',
        string='Fixed Source Location',
        help='For Request: This is the warehouse to pull from.\n'
             'Leave empty to use picking type default.')
    
    # Fixed destination location (for return behavior)
    dest_location_id = fields.Many2one(
        'stock.location',
        string='Fixed Destination Location', 
        help='For Return: This is the warehouse to return to.\n'
             'Leave empty to use picking type default.')
    
    # For action type
    action_id = fields.Many2one(
        'ir.actions.act_window',
        string='Target Action',
        help='Required for Window Action type. Opens this action directly.')

    # For client_action type (Discuss, etc.)
    client_action_tag = fields.Char(
        string='Client Action Tag',
        help='The tag for client actions (e.g., mail.action_discuss for Discuss app).')

    # --- FOLDER HIERARCHY ---
    parent_id = fields.Many2one(
        'clinic.portal.tile',
        string='Parent Folder',
        ondelete='cascade',
        help='If set, this tile appears inside the parent folder, not on main dashboard.')
    child_ids = fields.One2many(
        'clinic.portal.tile',
        'parent_id',
        string='Sub-Tiles',
        help='Tiles that appear when this folder is clicked.')

    # --- THE VISIBILITY FILTER ---
    # If set, only users allowed in these locations will see this tile
    limit_location_ids = fields.Many2many(
        'stock.location',
        'clinic_tile_limit_location_rel',
        'tile_id',
        'location_id',
        string='Limit to Locations',
        help='If set, only users who have access to at least one of these '
             'locations will see this tile. Leave empty for everyone.')
    
    # Group-based visibility
    group_ids = fields.Many2many(
        'res.groups',
        'clinic_portal_tile_group_rel',
        'tile_id',
        'group_id',
        string='Visible to Groups',
        help='Leave empty to show to all portal users.')

    # User-specific visibility (used by inventory tile — bypasses location rules)
    assigned_user_ids = fields.Many2many(
        'res.users',
        'clinic_portal_tile_user_rel',
        'tile_id',
        'user_id',
        string='Assigned Users',
        help='If set, only these specific users will see this tile. '
             'Takes precedence over group_ids. Used for inventory counting assignments.')

    # Visual - Heroicon selection
    icon = fields.Selection([
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
    ], string='Icon', default='cube',
       help='Heroicon name to display for this tile')
    color = fields.Char(
        string='Background Color',
        default='#714B67',
        help='Hex color code for tile icon background (e.g., #714B67)')
    icon_color = fields.Char(
        string='Icon Color',
        default='#ffffff',
        help='Hex color code for icon (e.g., #ffffff for white)')

    description = fields.Char(
        string='Tooltip Description',
        translate=True,
        help='Description shown as tooltip when hovering over the tile.')

    # Computed visibility for current user
    is_visible_to_user = fields.Boolean(
        string='Visible to User',
        compute='_compute_visibility',
        search='_search_is_visible_to_user')
    
    # Pending count
    pending_count = fields.Integer(
        string='Pending',
        compute='_compute_pending_count',
        help='Number of waiting requests for this tile')

    @api.depends_context('uid')
    def _compute_visibility(self):
        """Compute if tile is visible to current user based on their locations"""
        user = self.env.user
        
        # Get user's allowed locations (from serenvale_stock_access_control)
        user_locations = []
        if hasattr(user, 'allowed_location_ids') and user.allowed_location_ids:
            user_locations = user.allowed_location_ids.ids
        
        for tile in self:
            # Child tiles are NEVER visible on main dashboard
            # They appear inside their parent folder
            if tile.parent_id:
                tile.is_visible_to_user = False
                continue
            
            if not tile.limit_location_ids:
                # No limit = visible to everyone
                tile.is_visible_to_user = True
            elif not user_locations:
                # User has no location restrictions = sees everything
                tile.is_visible_to_user = True
            else:
                # Check if user has access to any of the limited locations
                tile.is_visible_to_user = bool(
                    set(tile.limit_location_ids.ids) & set(user_locations)
                )

    def _search_is_visible_to_user(self, operator, value):
        """Enable searching/filtering by visibility"""
        user = self.env.user
        
        # Get user's allowed locations
        user_locations = []
        if hasattr(user, 'allowed_location_ids') and user.allowed_location_ids:
            user_locations = user.allowed_location_ids.ids
        
        if not user_locations:
            # No restrictions = all tiles visible
            if operator == '=' and value:
                return []
            else:
                return [('id', '=', False)]
        
        # Find tiles visible to this user
        all_tiles = self.sudo().search([])
        visible_ids = []
        for tile in all_tiles:
            if not tile.limit_location_ids:
                visible_ids.append(tile.id)
            elif set(tile.limit_location_ids.ids) & set(user_locations):
                visible_ids.append(tile.id)
        
        if operator == '=' and value:
            return [('id', 'in', visible_ids)]
        else:
            return [('id', 'not in', visible_ids)]

    @api.depends('type', 'picking_type_id')
    def _compute_pending_count(self):
        """Count actual waiting requests for this tile"""
        StockPicking = self.env['stock.picking'].sudo()
        user = self.env.user
        
        for tile in self:
            if tile.type == 'stock' and tile.picking_type_id:
                tile.pending_count = StockPicking.search_count([
                    ('picking_type_id', '=', tile.picking_type_id.id),
                    ('state', 'in', ['draft', 'waiting', 'confirmed']),
                    ('portal_requester_id', '=', user.id),
                ])
            else:
                tile.pending_count = 0

    def action_open_tile(self):
        """Handle tile click - opens stock form, action, or folder children"""
        self.ensure_one()

        # FOLDER: Open POS-style fullscreen selector
        if self.type == 'folder':
            visible_children = self.child_ids.filtered(lambda t: t.active)
            if not visible_children:
                return {'type': 'ir.actions.act_window_close'}
            
            return {
                'type': 'ir.actions.client',
                'tag': 'folder_selector_action',
                'name': self.name,
                'context': {
                    'active_id': self.id,
                    'folder_name': self.name,
                },
            }

        # STOCK: Open picking form
        if self.type == 'stock':
            context = {
                'portal_mode': True,
                'portal_tile_id': self.id,
                'portal_stock_behavior': self.stock_behavior,
                'portal_consumption_source': self.consumption_source,
                'default_picking_type_id': self.picking_type_id.id if self.picking_type_id else False,
                'portal_source_location_id': self.source_location_id.id if self.source_location_id else False,
                'portal_dest_location_id': self.dest_location_id.id if self.dest_location_id else False,
            }
            
            # Use kiosk view for CONSUMPTION behaviors (touch-friendly)
            if self.stock_behavior in ['billable', 'surgery', 'internal']:
                view_id = self.env.ref('clinic_staff_portal.view_picking_kiosk').id
            else:
                # Request/Return uses normal form
                view_id = self.env.ref('clinic_staff_portal.view_picking_form_portal').id
            
            return {
                'type': 'ir.actions.act_window',
                'name': self.name,
                'res_model': 'stock.picking',
                'view_mode': 'form',
                'view_id': view_id,
                'target': 'current',
                'context': context,
            }
        
        # ACTION: Open window action
        if self.type == 'action' and self.action_id:
            action = self.action_id.sudo().read()[0]
            if 'views' in action:
                action['views'] = [(False, 'form')]
            action['target'] = 'current'
            return action

        # CLIENT ACTION: Open client action (Discuss, etc.)
        if self.type == 'client_action' and self.client_action_tag:
            return {
                'type': 'ir.actions.client',
                'tag': self.client_action_tag,
                'target': 'current',
            }

        return {'type': 'ir.actions.act_window_close'}
