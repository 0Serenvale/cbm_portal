# -*- coding: utf-8 -*-
import logging
from odoo import http, _, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

# NOTE: User redirect is now handled via res.users.action_id (Odoo's native Home Action)
# fullscreen_kiosk_mode is a separate per-user setting for hiding Odoo UI


class CBMKioskController(http.Controller):
    """HTTP Controllers for CBM Portal Kiosk Client Action"""

    @http.route('/cbm/get_user_context', type='json', auth='user')
    def get_user_context(self):
        """Return user's context: ward, op types, permissions"""
        user = request.env.user
        # CBM Portal Admin = only user IDs 2 (main admin) and 11 (Djamel)
        CBM_ADMIN_IDS = [2, 11]
        is_admin = user.id in CBM_ADMIN_IDS
        
        # Get user's allowed operation types with portal config
        op_types_data = []
        if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
            for op_type in user.allowed_operation_types:
                # Only show if portal_visible is True, OR user is admin
                portal_vis = op_type.portal_visible if hasattr(op_type, 'portal_visible') else False
                _logger.debug(f"[CBM PORTAL] Op type '{op_type.name}' (ID={op_type.id}): portal_visible={portal_vis}, is_admin={is_admin}")
                
                if portal_vis or is_admin:
                    op_types_data.append({
                        'id': op_type.id,
                        'name': op_type.name,
                        'portal_category': op_type.portal_category,
                        'portal_behavior': 'request' if op_type.portal_category == 'request' else 'consumption',
                        'portal_icon': op_type.portal_icon or 'cube',
                        'portal_requires_patient': op_type.portal_requires_patient,
                        'portal_requires_department': op_type.portal_requires_department if hasattr(op_type, 'portal_requires_department') else False,
                        'default_location_src_id': op_type.default_location_src_id.id if op_type.default_location_src_id else False,
                        'default_location_src_name': op_type.default_location_src_id.name if op_type.default_location_src_id else False,
                        'default_location_dest_id': op_type.default_location_dest_id.id if op_type.default_location_dest_id else False,
                        'default_location_dest_name': op_type.default_location_dest_id.name if op_type.default_location_dest_id else False,
                    })
        
        # Get pharmacy location (for request source)
        IrConfig = request.env['ir.config_parameter'].sudo()
        pharmacy_loc_id = int(IrConfig.get_param('clinic_staff_portal.pharmacy_location_id', 0) or 0)
        magasin_loc_id = int(IrConfig.get_param('clinic_staff_portal.magasin_location_id', 0) or 0)
        patient_loc_id = int(IrConfig.get_param('clinic_staff_portal.patient_location_id', 0) or 0)
        
        # Find user's ward - from INTERNAL TRANSFER op type's destination
        # Logic: internal_transfer.destination == consumption.source == user's ward
        # This works for all users who receive stock transfers (nurses, lab, anapath, etc.)
        ward_name = False
        ward_id = False
        if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
            for op_type in user.allowed_operation_types:
                # Find internal transfer operation (code='internal' - case insensitive)
                if op_type.code and op_type.code.lower() == 'internal' and op_type.default_location_dest_id:
                    ward_name = op_type.default_location_dest_id.name
                    ward_id = op_type.default_location_dest_id.id
                    break
        
        # Get CBM Portal settings
        lot_selection_mode = IrConfig.get_param('clinic_staff_portal.lot_selection_mode', 'auto_fefo')
        stock_alert_visibility = IrConfig.get_param('clinic_staff_portal.stock_alert_visibility', 'admin_only')
        
        return {
            'user_id': user.id,
            'user_name': user.name,
            'is_admin': is_admin,
            'operation_types': op_types_data,
            'pharmacy_location_id': pharmacy_loc_id,
            'magasin_location_id': magasin_loc_id,
            'patient_location_id': patient_loc_id,
            'ward_name': ward_name,
            'ward_id': ward_id,
            'fullscreen_kiosk_mode': getattr(user, 'fullscreen_kiosk_mode', False),
            'lot_selection_mode': lot_selection_mode,
            'stock_alert_visibility': stock_alert_visibility,
        }

    @http.route('/cbm/get_custom_tiles', type='json', auth='user')
    def get_custom_tiles(self):
        """Return custom action tiles for CBM Portal 'Quick Links' section
        
        Visibility is controlled by tile.group_ids:
        - Empty group_ids = visible to all users
        - Set group_ids = visible only to users in those groups
        """
        user = request.env.user
        Tile = request.env['clinic.portal.tile']
        
        # Get all action tiles (active, top-level only)
        # Include both 'action' (window actions) and 'client_action' (Discuss, etc.)
        tiles = Tile.search([
            ('type', 'in', ['action', 'client_action']),
            ('active', '=', True),
            ('parent_id', '=', False),
        ], order='sequence')
        
        # Get unread inbox notification count for Messages tile
        unread_count = 0
        try:
            partner = user.partner_id
            if partner:
                unread_count = request.env['mail.notification'].sudo().search_count([
                    ('res_partner_id', '=', partner.id),
                    ('is_read', '=', False),
                    ('notification_type', '=', 'inbox'),
                ])
        except Exception as e:
            _logger.debug(f"[CBM] Could not get unread count: {e}")

        result = []
        for tile in tiles:
            # Check group visibility
            if tile.group_ids:
                # Tile has group restrictions - check if user is in any of those groups
                user_groups = user.groups_id.ids
                tile_groups = tile.group_ids.ids
                if not set(user_groups) & set(tile_groups):
                    continue  # User not in required groups, skip this tile

            # For Messages tile, use unread count instead of pending_count
            pending = tile.pending_count
            if tile.client_action_tag == 'mail.action_discuss':
                pending = unread_count

            result.append({
                'id': tile.id,
                'name': tile.name,
                'type': tile.type,
                'icon': tile.icon or 'cube',
                'color': tile.color or '#714B67',
                'icon_color': tile.icon_color or '#ffffff',
                'sequence': tile.sequence,
                'pending_count': pending,
                'action_id': tile.action_id.id if tile.action_id else False,
                'client_action_tag': tile.client_action_tag or False,
                'description': tile.description or '',
            })

        return result

    @http.route('/cbm/log_access', type='json', auth='user')
    def log_access(self, screen_width=0, screen_height=0, user_agent=''):
        """Log kiosk access for analytics. IP captured from request.
        Returns workstation info + dual-session warning."""
        try:
            AccessLog = request.env['cbm.kiosk.access.log']
            return AccessLog.log_access(
                screen_width=screen_width,
                screen_height=screen_height,
                user_agent=user_agent,
            )
        except Exception as e:
            _logger.warning(f"[CBM] Failed to log kiosk access: {e}")
            return {'success': False}

    @http.route('/cbm/get_pending_approvals', type='json', auth='user')
    def get_pending_approvals(self):
        """Return pending counts for sidebar.
        
        Simplified logic:
        - All users see the sidebar (their own pending work)
        - my_requests_count: Pickings user created that are pending
        - to_approve_count: Pickings needing user's approval (as responsable)
        - my_receptions_count: Incoming pickings to user's responsible locations
        - pending_po_count: POs needing user's approval
        - Admin (configured in CBM settings) sees ALL pending across all users
        """
        user = request.env.user
        
        # Admin check - only configured admin users in CBM Portal settings
        ICP = request.env['ir.config_parameter'].sudo()
        admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
        is_admin = user.id in admin_ids
        
        # Get user's responsible locations
        Location = request.env['stock.location'].sudo()
        responsible_locations = Location.search([
            ('responsible_user_ids', 'in', user.id),
        ])
        is_location_responsable = bool(responsible_locations)
        
        # Check if user is a PO bracket approver
        Bracket = request.env['purchase.approval.bracket'].sudo()
        approver_brackets = Bracket.search([('approver_ids', 'in', user.id)])
        is_po_approver = bool(approver_brackets)
        
        Picking = request.env['stock.picking'].sudo()
        PO = request.env['purchase.order'].sudo()
        
        # --- Count: My Requests (pickings user explicitly requested) ---
        # Only portal_requester_id — NOT create_uid which catches system-generated
        # backorders, chained moves, procurement-created pickings, etc.
        if is_admin:
            my_requests_count = Picking.search_count([
                ('portal_requester_id', '!=', False),
                ('state', 'not in', ['done', 'cancel']),
            ])
        else:
            my_requests_count = Picking.search_count([
                ('portal_requester_id', '=', user.id),
                ('state', 'not in', ['done', 'cancel']),
            ])
        
        # --- Count: To Validate (internal transfers arriving at user's locations) ---
        # Only internal transfers (requests from other departments).
        # NOT incoming (PO receipts) — those are in Réceptions.
        if is_admin:
            to_approve_count = Picking.search_count([
                ('picking_type_code', '=', 'internal'),
                ('state', 'in', ['assigned', 'confirmed', 'waiting']),
            ])
        elif responsible_locations:
            to_approve_count = Picking.search_count([
                ('picking_type_code', '=', 'internal'),
                ('state', 'in', ['assigned', 'confirmed', 'waiting']),
                ('location_dest_id', 'child_of', responsible_locations.ids),
            ])
        else:
            to_approve_count = 0
        
        # --- Count: My Receptions (PO receipts to user's responsible locations) ---
        # Only show if user has incoming operation types.
        # For non-admin: only count receipts arriving at their responsible locations.
        user_incoming_op_types = []
        if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
            user_incoming_op_types = user.allowed_operation_types.filtered(
                lambda op: op.code == 'incoming'
            )

        if is_admin:
            my_receptions_count = Picking.search_count([
                ('picking_type_code', '=', 'incoming'),
                ('state', 'not in', ['done', 'cancel']),
            ])
        elif user_incoming_op_types and responsible_locations:
            my_receptions_count = Picking.search_count([
                ('picking_type_id', 'in', user_incoming_op_types.ids),
                ('state', 'not in', ['done', 'cancel']),
                ('location_dest_id', 'child_of', responsible_locations.ids),
            ])
        else:
            my_receptions_count = 0


        
        # --- Count: Pending PO Approvals ---
        if is_admin:
            pending_po_count = PO.search_count([('state', '=', 'to approve')])
        elif is_po_approver:
            pending_po_count = PO.search_count([
                ('state', '=', 'to approve'),
                ('bracket_approver_ids', 'in', user.id),
            ])
        else:
            pending_po_count = 0
        
        # --- Count: Stock Discrepancies (admin/responsable only) ---
        pending_discrepancy_count = 0
        if is_admin or is_location_responsable:
            Discrepancy = request.env['clinic.stock.discrepancy'].sudo()
            pending_discrepancy_count = Discrepancy.search_count([
                ('state', '=', 'pending'),
            ])
        
        # --- Count: New Maintenance Requests (for maintenance team members only) ---
        my_maintenance_count = 0
        is_maintenance_responsible = False
        try:
            MaintenanceRequest = request.env['maintenance.request']
            MaintenanceTeam = request.env['maintenance.team']
            Stage = request.env['maintenance.stage']
            
            # Check if user is a member of any maintenance team
            user_teams = MaintenanceTeam.search([('member_ids', 'in', user.id)])
            is_maintenance_responsible = bool(user_teams)
            
            if is_maintenance_responsible or is_admin:
                # Find "New Request" stage only (sequence = 0)
                new_stage = Stage.search([('sequence', '=', 0)], limit=1)
                
                if new_stage:
                    # Count all new requests (not archived, in "New Request" stage)
                    base_domain = [
                        ('archive', '=', False),
                        ('stage_id', '=', new_stage.id),
                    ]
                    my_maintenance_count = MaintenanceRequest.sudo().search_count(base_domain)
                
        except Exception as e:
            _logger.warning(f"[CBM] Failed to count maintenance requests: {e}")
        
        # --- Enforcement Status (soft/hard block) - PER TILE CATEGORY ---
        # Each operation type has its own warn/block thresholds
        # We return SEPARATE status for each tile category (request vs consumption)
        # so users blocked for one can still use the other
        enforcement_enabled = ICP.get_param('clinic_staff_portal.pending_enforcement_enabled', 'False').lower() == 'true'

        # Per-tile status: 'ok', 'warning', or 'blocked'
        request_status = 'ok'
        consumption_status = 'ok'

        # Legacy overall status for backwards compatibility
        transfer_status = 'ok'

        if enforcement_enabled and not is_admin:
            # Get user's allowed operation types
            user_op_types = []
            if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
                user_op_types = user.allowed_operation_types

            _logger.info(f"[CBM ENFORCEMENT] User {user.name}: checking {len(user_op_types)} operation types")

            # Categorize operation types by portal_category
            # request = 'request' category (incoming from pharmacy)
            # consumption = 'consumption_billable', 'consumption_internal' categories (outgoing to patient)
            request_blocked = False
            request_warned = False
            consumption_blocked = False
            consumption_warned = False

            for op_type in user_op_types:
                # Count pending transfers for THIS operation type requested by this user
                op_pending_count = Picking.search_count([
                    ('picking_type_id', '=', op_type.id),
                    ('portal_requester_id', '=', user.id),
                    ('state', 'not in', ['done', 'cancel']),
                ])

                warn_threshold = op_type.pending_warn_threshold or 0
                block_threshold = op_type.pending_block_threshold or 0

                _logger.info(f"[CBM ENFORCEMENT] Op '{op_type.name}' (category={op_type.portal_category}): pending={op_pending_count}, warn={warn_threshold}, block={block_threshold}")

                is_blocked = block_threshold > 0 and op_pending_count >= block_threshold
                is_warned = warn_threshold > 0 and op_pending_count >= warn_threshold

                # Categorize by portal_category field
                category = op_type.portal_category or ''
                if category == 'request':
                    if is_blocked:
                        request_blocked = True
                        _logger.info(f"[CBM ENFORCEMENT] REQUEST BLOCKED for op type '{op_type.name}'")
                    elif is_warned:
                        request_warned = True
                elif category in ('consumption_billable', 'consumption_internal'):
                    if is_blocked:
                        consumption_blocked = True
                        _logger.info(f"[CBM ENFORCEMENT] CONSUMPTION BLOCKED for op type '{op_type.name}'")
                    elif is_warned:
                        consumption_warned = True

            # Set per-tile status
            if request_blocked:
                request_status = 'blocked'
            elif request_warned:
                request_status = 'warning'

            if consumption_blocked:
                consumption_status = 'blocked'
            elif consumption_warned:
                consumption_status = 'warning'

            # Legacy overall status (worst of both)
            if request_blocked or consumption_blocked:
                transfer_status = 'blocked'
            elif request_warned or consumption_warned:
                transfer_status = 'warning'

            _logger.info(f"[CBM ENFORCEMENT] Result: request={request_status}, consumption={consumption_status}, overall={transfer_status}")

        # Always show sidebar (all users can have pending work)
        return {
            'show_sidebar': True,
            'is_admin': is_admin,
            'is_location_responsable': is_location_responsable,
            'is_po_approver': is_po_approver,
            # Visibility flags (determines IF card should appear based on actual access)
            'has_transfer_approvals': is_admin or (to_approve_count > 0),
            'has_reception_access': is_admin or bool(user_incoming_op_types),
            'is_maintenance_responsible': is_maintenance_responsible,
            # Counts
            'my_requests_count': my_requests_count,
            'to_approve_count': to_approve_count,
            'my_receptions_count': my_receptions_count,
            'pending_po_count': pending_po_count,
            'pending_discrepancy_count': pending_discrepancy_count,
            'my_maintenance_count': my_maintenance_count,
            'responsible_location_ids': responsible_locations.ids,
            # Operation type IDs for filtering (used by JS click handlers)
            'user_incoming_op_type_ids': user_incoming_op_types.ids if user_incoming_op_types else [],
            # Enforcement - per-tile status
            'enforcement_enabled': enforcement_enabled,
            'transfer_status': transfer_status,  # Legacy overall status
            'request_status': request_status,  # 'ok', 'warning', or 'blocked'
            'consumption_status': consumption_status,  # 'ok', 'warning', or 'blocked'
        }


    @http.route('/cbm/financial_summary', type='json', auth='user')
    def financial_summary(self):
        """Return inventory accountability summary for executives.

        Only visible to users in executive_user_ids setting.
        Shows value of pending transfers (inventory at risk) to nudge responsible staff.

        Returns:
            total_at_risk: float - total value of all pending transfers
            pending_count: int - total number of pending transfers
            currency_symbol: str
            is_executive: bool
        """
        user = request.env.user
        ICP = request.env['ir.config_parameter'].sudo()

        # Check if user is an executive OR CBM admin (IDs 2 and 11)
        exec_ids_str = ICP.get_param('clinic_staff_portal.executive_user_ids', '')
        exec_ids = [int(i) for i in exec_ids_str.split(',') if i.strip().isdigit()]
        is_executive = user.id in exec_ids or user.id in [2, 11]  # CBM admins

        if not is_executive:
            return {
                'is_executive': False,
                'total_at_risk': 0,
                'pending_count': 0,
                'currency_symbol': '',
            }

        # Calculate inventory at risk: pending internal transfers + purchase receipts
        # These are operations that responsables (pharmacist, magasin, etc.) need to validate
        Picking = request.env['stock.picking'].sudo()
        total_at_risk = 0.0

        domain = [
            ('state', 'in', ['assigned', 'confirmed', 'waiting']),
            ('picking_type_id.code', 'in', ['internal', 'incoming']),
        ]
        # Apply accountability start date if configured
        start_date = ICP.get_param('clinic_staff_portal.accountability_start_date', '')
        if start_date:
            domain.append(('create_date', '>=', start_date))

        pending_pickings = Picking.search(domain)

        pending_count = len(pending_pickings)

        for picking in pending_pickings:
            for move in picking.move_ids:
                total_at_risk += move.product_id.standard_price * move.product_uom_qty

        # Currency
        currency = request.env.company.currency_id

        return {
            'is_executive': True,
            'total_at_risk': round(total_at_risk, 0),
            'pending_count': pending_count,
            'currency_symbol': currency.symbol or 'CFA',
        }

    @http.route('/cbm/financial_details', type='json', auth='user')
    def financial_details(self):
        """Return detailed financial breakdown by department.
        
        Returns list of departments with:
            - location_id, location_name
            - responsible_name
            - loss_amount
            - picking_ids (for notify)
            - pending_count
        """
        user = request.env.user
        ICP = request.env['ir.config_parameter'].sudo()
        
        # Check if user is executive OR CBM admin (IDs 2 and 11)
        exec_ids_str = ICP.get_param('clinic_staff_portal.executive_user_ids', '')
        exec_ids = [int(i) for i in exec_ids_str.split(',') if i.strip().isdigit()]
        is_executive = user.id in exec_ids or user.id in [2, 11]  # CBM admins
        
        if not is_executive:
            return {'is_executive': False, 'departments': []}
        
        # Get pending internal transfers + purchase receipts grouped by source location
        # Source location = the responsable's location (pharmacy, magasin, etc.)
        Picking = request.env['stock.picking'].sudo()
        domain = [
            ('state', 'in', ['assigned', 'confirmed', 'waiting']),
            ('picking_type_id.code', 'in', ['internal', 'incoming']),
        ]
        # Apply accountability start date if configured
        start_date = ICP.get_param('clinic_staff_portal.accountability_start_date', '')
        if start_date:
            domain.append(('create_date', '>=', start_date))

        pending_pickings = Picking.search(domain)
        
        # Group by source location
        from collections import defaultdict
        from datetime import date
        location_data = defaultdict(lambda: {
            'loss_amount': 0.0,
            'picking_ids': [],
            'pending_count': 0,
            'oldest_days': 0,
        })
        
        for picking in pending_pickings:
            loc = picking.location_dest_id if picking.picking_type_id.code == 'incoming' else picking.location_id
            loc_id = loc.id
            loc_name = loc.complete_name or loc.name
            
            # Calculate value
            value = sum(m.product_id.standard_price * m.product_uom_qty for m in picking.move_ids)
            location_data[(loc_id, loc_name)]['loss_amount'] += value
            location_data[(loc_id, loc_name)]['picking_ids'].append(picking.id)
            location_data[(loc_id, loc_name)]['pending_count'] += 1
            
            # Calculate days - use scheduled_date or create_date as fallback
            ref_date = picking.scheduled_date or picking.create_date
            if ref_date:
                days = (date.today() - ref_date.date()).days
                if days > 0 and days > location_data[(loc_id, loc_name)]['oldest_days']:
                    location_data[(loc_id, loc_name)]['oldest_days'] = days
        
        # Build result with responsible
        Location = request.env['stock.location'].sudo()
        departments = []
        currency = request.env.company.currency_id
        
        for (loc_id, loc_name), data in sorted(location_data.items(), key=lambda x: -x[1]['loss_amount']):
            location = Location.browse(loc_id)
            # Get responsible from location's responsible_user_ids (from serenvale_stock_location_approval)
            responsible_name = ''
            if hasattr(location, 'responsible_user_ids') and location.responsible_user_ids:
                responsible_name = ', '.join(location.responsible_user_ids.mapped('name'))
            
            departments.append({
                'location_id': loc_id,
                'location_name': loc_name,
                'responsible_name': responsible_name or 'Non assigné',
                'loss_amount': round(data['loss_amount'], 0),
                'currency_symbol': currency.symbol or 'CFA',
                'picking_ids': data['picking_ids'],
                'pending_count': data['pending_count'],
                'oldest_days': data['oldest_days'],
            })
        
        return {
            'is_executive': True,
            'departments': departments,
        }

    @http.route('/cbm/notify_drh', type='json', auth='user')
    def notify_drh(self, picking_ids):
        """Send DRH escalation notification for pending pickings.
        
        Args:
            picking_ids: list of stock.picking IDs to escalate
            
        Returns:
            success: bool
            message: str
        """
        user = request.env.user
        ICP = request.env['ir.config_parameter'].sudo()
        
        # Check if user is executive OR CBM admin (IDs 2 and 11)
        exec_ids_str = ICP.get_param('clinic_staff_portal.executive_user_ids', '')
        exec_ids = [int(i) for i in exec_ids_str.split(',') if i.strip().isdigit()]
        is_executive = user.id in exec_ids or user.id in [2, 11]  # CBM admins
        
        if not is_executive:
            return {'success': False, 'message': 'Accès refusé'}
        
        # Get DRH user
        drh_id_param = ICP.get_param('clinic_staff_portal.drh_user_id', '')
        _logger.info(f"[NOTIFY DRH] drh_id_param={drh_id_param}")
        if not drh_id_param:
            return {'success': False, 'message': 'Liaison RH non configurée'}
        
        try:
            drh_id = int(drh_id_param)
        except (ValueError, TypeError) as e:
            _logger.error(f"[NOTIFY DRH] Failed to parse DRH ID: {drh_id_param}, error: {e}")
            return {'success': False, 'message': f'ID Liaison RH invalide: {drh_id_param}'}
        
        drh_user = request.env['res.users'].sudo().browse(drh_id)
        if not drh_user.exists():
            return {'success': False, 'message': 'Liaison RH introuvable'}

        # Build consolidated picking summary
        Picking = request.env['stock.picking'].sudo()
        pickings = Picking.browse(picking_ids).filtered(lambda p: p.exists())

        if not pickings:
            return {'success': False, 'message': _('Aucun mouvement trouvé')}

        # Calculate full proof data per department
        from datetime import date
        Location = request.env['stock.location'].sudo()
        currency = request.env.company.currency_id
        currency_sym = currency.symbol or 'DA'

        # Group pickings by source location for the proof breakdown
        from collections import defaultdict
        loc_stats = defaultdict(lambda: {
            'count': 0, 'max_days': 0, 'value': 0.0, 'responsible': ''
        })

        for picking in pickings:
            loc = picking.location_id
            loc_key = loc.complete_name or loc.name or _('Non spécifié')

            loc_stats[loc_key]['count'] += 1
            loc_stats[loc_key]['value'] += sum(
                m.product_id.standard_price * m.product_uom_qty
                for m in picking.move_ids
            )

            ref_date = picking.scheduled_date or picking.create_date
            if ref_date:
                days = (date.today() - ref_date.date()).days
                if days > loc_stats[loc_key]['max_days']:
                    loc_stats[loc_key]['max_days'] = days

            # Get responsible from location
            if not loc_stats[loc_key]['responsible'] and hasattr(loc, 'responsible_user_ids') and loc.responsible_user_ids:
                loc_stats[loc_key]['responsible'] = ', '.join(loc.responsible_user_ids.mapped('name'))

        # Build proof table rows
        table_rows = ''
        total_value = 0.0
        for loc_name, stats in sorted(loc_stats.items(), key=lambda x: -x[1]['value']):
            responsible = stats['responsible'] or _('Non assigné')
            total_value += stats['value']
            table_rows += (
                f'<tr>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{loc_name}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{responsible}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:center;">{stats["count"]}</td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:center;">'
                f'<strong style="color:#dc2626;">{stats["max_days"]}j</strong></td>'
                f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:right;">'
                f'{stats["value"]:,.0f} {currency_sym}</td>'
                f'</tr>'
            )

        department_names = ', '.join(loc_stats.keys())

        message_body = f"""
<div style="padding:16px;background:#fff;border-left:4px solid #dc3545;border-radius:6px;font-family:sans-serif;">
    <p style="margin:0 0 12px;font-size:15px;font-weight:700;color:#111827;">
        Rapport de Responsabilité — Transferts en Retard
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:12px;">
        <thead>
            <tr style="background:#f9fafb;">
                <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #e5e7eb;">Département</th>
                <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #e5e7eb;">Responsable</th>
                <th style="padding:6px 10px;text-align:center;border-bottom:2px solid #e5e7eb;">Transferts</th>
                <th style="padding:6px 10px;text-align:center;border-bottom:2px solid #e5e7eb;">Retard Max</th>
                <th style="padding:6px 10px;text-align:right;border-bottom:2px solid #e5e7eb;">Valeur à Risque</th>
            </tr>
        </thead>
        <tbody>{table_rows}</tbody>
        <tfoot>
            <tr style="background:#f9fafb;font-weight:700;">
                <td colspan="4" style="padding:6px 10px;">Total</td>
                <td style="padding:6px 10px;text-align:right;">{total_value:,.0f} {currency_sym}</td>
            </tr>
        </tfoot>
    </table>
    <p style="margin:0;font-size:11px;color:#6b7280;">
        Signalé par {user.name} le {date.today().strftime('%d/%m/%Y')}
    </p>
</div>
"""

        # Send via Odoo Discuss (no stock access needed for DRH)
        try:
            drh_user.partner_id.message_post(
                body=message_body,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
                partner_ids=[drh_user.partner_id.id],
            )
            _logger.info(f"[NOTIFY DRH] Sent accountability report to {drh_user.name} for: {department_names}")
        except Exception as e:
            _logger.error(f"[NOTIFY DRH] Failed to send notification: {e}")
            return {'success': False, 'message': f'Erreur notification: {str(e)[:100]}'}

        return {
            'success': True,
            'message': _('Rapport envoyé à %s (%d mouvement(s))') % (drh_user.name, len(pickings))
        }

    @http.route('/cbm/check_hoarding', type='json', auth='user')
    def check_hoarding(self, product_id, destination_location_id):
        """Check if product has existing stock at destination ward.
        
        Uses same logic as stock_move._check_hoarding_logic but callable via RPC
        for the kiosk client action.
        
        Returns:
            status: 'ok' | 'warning' | 'blocked'
            trusted_qty: float - stock at destination since trust date
            policy: 'none' | 'soft' | 'hard'
            message: str - user-friendly message
        """
        from datetime import datetime, time as datetime_time
        
        # Default response
        response = {
            'status': 'ok',
            'trusted_qty': 0.0,
            'policy': 'none',
            'message': '',
        }
        
        if not product_id or not destination_location_id:
            return response
        
        Location = request.env['stock.location'].sudo()
        ward = Location.browse(destination_location_id)
        
        if not ward.exists():
            return response
        
        # Check if policy is active
        policy = getattr(ward, 'replenishment_policy', 'none') or 'none'
        response['policy'] = policy
        
        if policy == 'none':
            return response
        
        start_date = getattr(ward, 'consumption_start_date', None)
        if not start_date:
            return response
        
        # Calculate trusted balance
        start_datetime = datetime.combine(start_date, datetime_time.min)
        ward_id = ward.id
        
        Move = request.env['stock.move'].sudo()
        
        # INCOMING: What entered the ward (including pending)
        domain_in = [
            ('location_dest_id', '=', ward_id),
            ('product_id', '=', product_id),
            ('date', '>=', start_datetime),
            ('state', 'in', ['done', 'assigned', 'confirmed', 'partially_available']),
        ]
        in_data = Move.read_group(domain_in, ['product_uom_qty:sum'], ['product_id'])
        qty_in = in_data[0]['product_uom_qty'] if in_data else 0.0
        
        # OUTGOING: What left the ward (consumed)
        domain_out = [
            ('location_id', '=', ward_id),
            ('product_id', '=', product_id),
            ('date', '>=', start_datetime),
            ('state', '=', 'done'),
        ]
        out_data = Move.read_group(domain_out, ['product_uom_qty:sum'], ['product_id'])
        qty_out = out_data[0]['product_uom_qty'] if out_data else 0.0
        
        # Trusted balance
        trusted_balance = max(0, qty_in - qty_out)
        response['trusted_qty'] = trusted_balance
        
        # Apply policy
        if trusted_balance > 0:
            if policy == 'hard':
                response['status'] = 'blocked'
                response['message'] = f"Vous avez {trusted_balance} en stock. Consommez d'abord!"
            elif policy == 'soft':
                response['status'] = 'warning'
                response['message'] = f"Vous avez {trusted_balance} en stock"
        
        return response

    @http.route('/cbm/search_products', type='json', auth='user')
    def search_products(self, query, location_id=None, limit=20, purchase_mode=False):
        """Search products.
        
        Args:
            query: Search term
            location_id: Location to check stock (for consumption/transfer mode)
            limit: Max results
            purchase_mode: If True, search ALL purchasable products (for PO creation)
                          If False, search products with stock at location (original)
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        Product = request.env['product.product']
        
        # PO MODE: Search purchasable products filtered by user's allowed categories
        if purchase_mode:
            user = request.env.user
            
            # Base domain: purchasable products
            domain = [('purchase_ok', '=', True)]
            
            # Add category restriction from user settings
            if hasattr(user, 'get_purchase_allowed_product_domain'):
                category_domain = user.get_purchase_allowed_product_domain()
                if category_domain:
                    domain += category_domain
            
            # Add search query
            if query:
                domain += ['|', '|',
                    ('name', 'ilike', query),
                    ('default_code', 'ilike', query),
                    ('barcode', 'ilike', query),
                ]
            
            products = Product.sudo().search(domain, limit=limit)
            
            # Get user's destination location for stock info
            # Uses same logic as clinic_brain: check allowed_operation_types for incoming
            reception_location = None
            location_name = ''
            if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
                incoming_op = user.allowed_operation_types.filtered(lambda op: op.code == 'incoming')
                if incoming_op:
                    reception_location = incoming_op[0].default_location_dest_id
                    if reception_location:
                        location_name = reception_location.name
            

            # Build result with stock info
            result = []
            Quant = request.env['stock.quant'].sudo()
            
            for p in products:
                # Get current stock at reception location
                current_stock = 0
                if reception_location:
                    quants = Quant.search([
                        ('product_id', '=', p.id),
                        ('location_id', '=', reception_location.id),
                    ])
                    current_stock = sum(q.quantity for q in quants)
                
                result.append({
                    'id': p.id,
                    'name': p.display_name,
                    'display_name': p.display_name,
                    'default_code': p.default_code or '',
                    'barcode': p.barcode or '',
                    'standard_price': p.standard_price or 0,
                    'current_stock': current_stock,
                    'location_name': location_name,
                    'uom_name': p.uom_id.name,
                    'uom_po_id': p.uom_po_id.id if p.uom_po_id else p.uom_id.id,
                    'uom_po_name': p.uom_po_id.name if p.uom_po_id else p.uom_id.name,
                    'tracking': p.tracking,
                })
            
            return result


        
        # ORIGINAL MODE: Search products with stock at location
        if not location_id:
            return []
        
        # DEBUG: Log the location being used
        location = request.env['stock.location'].sudo().browse(location_id)
        _logger.info("CBM SEARCH: Using location_id=%s (%s) for stock search", location_id, location.name if location else 'UNKNOWN')
        
        # Use existing _name_search which handles location filtering
        products = Product.with_context(
            portal_source_location_id=location_id
        ).name_search(query, limit=limit)
        
        result = []
        Quant = request.env['stock.quant'].sudo()
        IrConfig = request.env['ir.config_parameter'].sudo()
        lot_selection_mode = IrConfig.get_param('clinic_staff_portal.lot_selection_mode', 'auto_fefo')
        
        for prod_id, prod_name in products:
            product = Product.browse(prod_id)
            
            # Use exact quant at location (NOT free_qty which includes child locations)
            quants = Quant.search([
                ('product_id', '=', prod_id),
                ('location_id', '=', location_id),  # EXACT location match
            ])
            qty_available = sum(q.quantity for q in quants)
            
            _logger.info("CBM SEARCH: Product %s -> qty=%.2f at EXACT location %s (ID=%s)", 
                        prod_name, qty_available, location.name, location_id)
            
            # Auto-select lot if product is lot-tracked and mode is auto_fefo
            lot_id = False
            lot_name = False
            if product.tracking == 'lot' and lot_selection_mode == 'auto_fefo':
                # Find lots with stock at this location, ordered by expiry (FEFO)
                quants_with_lot = Quant.search([
                    ('product_id', '=', prod_id),
                    ('location_id', '=', location_id),
                    ('lot_id', '!=', False),
                    ('quantity', '>', 0),
                ], order='lot_id')
                
                if quants_with_lot:
                    lot_ids = quants_with_lot.mapped('lot_id')
                    if lot_ids:
                        # Use a far-future datetime instead of string to avoid TypeError when comparing with other datetime objects
                        far_future = fields.Datetime.from_string('9999-12-31 23:59:59')
                        lots_sorted = lot_ids.sorted(key=lambda lot: lot.expiration_date or far_future)
                        first_expiry_lot = lots_sorted[:1]
                        if first_expiry_lot:
                            lot_id = first_expiry_lot.id
                            lot_name = first_expiry_lot.name
                            _logger.info("CBM SEARCH: Auto-selected lot %s (FEFO) for %s", lot_name, prod_name)
            
            result.append({
                'id': prod_id,
                'name': prod_name,
                'display_name': product.display_name,
                'barcode': product.barcode,
                'default_code': product.default_code,
                'qty_available': qty_available,
                'uom_id': product.uom_id.id,
                'uom_name': product.uom_id.name,
                'tracking': product.tracking,
                'lot_id': lot_id,
                'lot_name': lot_name,
            })
        
        return result


    @http.route('/cbm/search_barcode', type='json', auth='user')
    def search_barcode(self, barcode, location_id):
        """Search by exact barcode or lot.ref"""
        Product = request.env['product.product']
        Lot = request.env['stock.lot']
        
        product = None
        lot = None
        
        # 1. Search by product barcode
        product = Product.search([('barcode', '=', barcode)], limit=1)
        
        # 2. Search by lot reference
        if not product:
            lot = Lot.search([('ref', '=', barcode)], limit=1)
            if lot:
                product = lot.product_id
        
        # 3. Search by lot name (serial number)
        if not product:
            lot = Lot.search([('name', '=', barcode)], limit=1)
            if lot:
                product = lot.product_id
        
        if not product:
            return {'found': False, 'error': _('Product not found for barcode: %s') % barcode}
        
        qty_available = product.with_context(location=location_id).free_qty
        
        return {
            'found': True,
            'id': product.id,
            'name': product.display_name,
            'barcode': product.barcode,
            'default_code': product.default_code,
            'qty_available': qty_available,
            'uom_id': product.uom_id.id,
            'uom_name': product.uom_id.name,
            'lot_id': lot.id if lot else False,
            'lot_name': lot.name if lot else False,
        }

    @http.route('/cbm/get_quick_picks', type='json', auth='user')
    def get_quick_picks(self, location_id):
        """Get quick pick products for a location with current stock info.

        Returns products configured for quick pick at this location,
        along with their current stock levels.
        """
        Location = request.env['stock.location'].sudo()
        Quant = request.env['stock.quant'].sudo()

        location = Location.browse(location_id)
        if not location.exists() or not location.enable_quick_pick:
            return {'enabled': False, 'products': []}

        if not location.quick_pick_product_ids:
            return {'enabled': True, 'products': []}

        result = []
        for product in location.quick_pick_product_ids:
            # Get current stock at this exact location
            quants = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', '=', location_id),
            ])
            qty_available = sum(q.quantity for q in quants)

            result.append({
                'id': product.id,
                'name': product.display_name,
                'short_name': (product.name or '')[:18],  # Truncated for button display
                'default_code': product.default_code or '',
                'qty_available': qty_available,
                'uom_name': product.uom_id.name,
                'tracking': product.tracking,
            })

        return {
            'enabled': True,
            'location_name': location.name,
            'products': result,
        }

    @http.route('/cbm/check_product_stock_info', type='json', auth='user')
    def check_product_stock_info(self, product_id, user_location_id, source_location_id=None):
        """
        Get comprehensive stock information for a product including:
        - Available stock at user's location
        - Available stock at source location
        - Pending incoming transfers to user's location
        - Helpful suggestions based on stock status
        """
        Product = request.env['product.product'].sudo()
        Picking = request.env['stock.picking'].sudo()
        Quant = request.env['stock.quant'].sudo()

        product = Product.browse(product_id)
        if not product.exists():
            return {'error': _('Product not found')}

        # Stock at user's location
        user_location_qty = 0
        if user_location_id:
            quants = Quant.search([
                ('product_id', '=', product_id),
                ('location_id', '=', user_location_id),
            ])
            user_location_qty = sum(q.quantity - q.reserved_quantity for q in quants)

        # Stock at source location (usually pharmacy)
        source_location_qty = 0
        source_location_name = ''
        if source_location_id:
            source_location = request.env['stock.location'].sudo().browse(source_location_id)
            source_location_name = source_location.name if source_location else ''
            quants = Quant.search([
                ('product_id', '=', product_id),
                ('location_id', '=', source_location_id),
            ])
            source_location_qty = sum(q.quantity - q.reserved_quantity for q in quants)

        # Pending incoming transfers to user's location
        pending_transfers = []
        if user_location_id:
            pending_pickings = Picking.search([
                ('location_dest_id', '=', user_location_id),
                ('state', 'in', ['confirmed', 'assigned', 'waiting']),
                ('move_ids.product_id', '=', product_id),
            ], limit=5)

            for picking in pending_pickings:
                moves = picking.move_ids.filtered(lambda m: m.product_id.id == product_id)
                if moves:
                    qty = sum(m.product_uom_qty for m in moves)
                    pending_transfers.append({
                        'name': picking.name,
                        'qty': qty,
                        'state': picking.state,
                        'state_display': dict(picking._fields['state'].selection).get(picking.state),
                        'origin': picking.origin or '',
                    })

        # Generate helpful message
        message = ''
        message_type = 'info'

        if user_location_qty <= 0 and len(pending_transfers) > 0:
            total_pending = sum(t['qty'] for t in pending_transfers)
            message = f"📦 Pas de stock disponible, mais {total_pending:.0f} unités en transfert vers votre service"
            message_type = 'info'
        elif user_location_qty <= 0 and source_location_qty > 0:
            message = f"ℹ️ Aucun stock ici. Disponible à {source_location_name}: {source_location_qty:.0f} unités"
            message_type = 'info'
        elif user_location_qty <= 0:
            message = f"❌ Stock épuisé dans votre service et à {source_location_name}"
            message_type = 'error'

        return {
            'product_name': product.display_name,
            'user_location_qty': user_location_qty,
            'source_location_qty': source_location_qty,
            'source_location_name': source_location_name,
            'pending_transfers': pending_transfers,
            'message': message,
            'message_type': message_type,
            'uom_name': product.uom_id.name,
        }

    @http.route('/cbm/search_patients', type='json', auth='user')
    def search_patients(self, query, limit=20):
        """Search partners: customers (patients) OR partners with categories (doctors, staff, etc.)
        Returns tag/category info for frontend to display appropriate badges.
        """
        import re
        Partner = request.env['res.partner']
        
        # Search partners by name or ref that are either:
        # 1. Customers (patient with customer_rank > 0)
        # 2. OR have any category/tag assigned (doctors, staff)
        # 
        # Odoo domain Polish notation:
        # '&' applies to the next TWO conditions
        # '|' applies to the next TWO conditions
        # Structure: (name ILIKE query OR ref ILIKE query) AND (customer OR has_tag)
        partners = Partner.search([
            '&',
                '|',
                    ('name', 'ilike', query),
                    ('ref', 'ilike', query),
                '|',
                    ('customer_rank', '>', 0),
                    ('category_id', '!=', False),
        ], limit=limit)
        
        result = []
        for p in partners:
            # Extract CBM ID from display_name pattern "Name [CBMxxxxxx]"
            cbm_id = p.ref or ''
            clean_name = p.name or ''
            
            # Try to parse from display name pattern [CBMxxxxxx]
            match = re.search(r'\[([A-Z]+\d+)\]', p.display_name or p.name or '')
            if match:
                cbm_id = match.group(1)
                # Extract clean name (without the [CBM...] part)
                clean_name = re.sub(r'\s*\[[A-Z]+\d+\]', '', p.display_name or p.name or '').strip()
            
            # Get all category/tag names for this partner
            tags = [cat.name for cat in p.category_id]
            
            # Determine partner type for badge display
            partner_type = 'patient'  # Default
            if any(t in ['Docteur', 'Doctor', 'Médecin'] for t in tags):
                partner_type = 'doctor'
            elif any(t in ['Staff', 'Personnel', 'Employé'] for t in tags):
                partner_type = 'staff'
            elif cbm_id:
                partner_type = 'patient'
            elif tags:
                partner_type = 'other'
            
            result.append({
                'id': p.id,
                'name': p.name,
                'display_name': p.display_name,
                'clean_name': clean_name,
                'ref': p.ref or '',
                'cbm_id': cbm_id,
                'tags': tags,  # All tag names for frontend
                'partner_type': partner_type,  # 'patient', 'doctor', 'staff', 'other'
            })
        
        return result

    @http.route('/cbm/search_patient_barcode', type='json', auth='user')
    def search_patient_barcode(self, barcode):
        """
        Exact match for patient barcode scan.
        Searches by ref field (CBM ID) for instant patient selection.
        
        Args:
            barcode: Scanned barcode value (e.g., "CBM123456")
            
        Returns:
            found: bool
            id, name, display_name, ref, cbm_id if found
        """
        import re
        Partner = request.env['res.partner']
        
        # Clean the barcode (strip whitespace)
        barcode = (barcode or '').strip()
        
        if not barcode:
            return {'found': False, 'error': _('Empty barcode')}
        
        # Exact match on ref field (CBM ID)
        patient = Partner.search([
            ('ref', '=', barcode),
            ('customer_rank', '>', 0),
        ], limit=1)
        
        if not patient:
            # Try case-insensitive match
            patient = Partner.search([
                ('ref', '=ilike', barcode),
                ('customer_rank', '>', 0),
            ], limit=1)
        
        if patient:
            # Extract clean name and CBM ID
            # CBM ID comes from: 1) ref field OR 2) [CBMxxxxxx] pattern in display_name
            cbm_id = patient.ref or ''
            clean_name = patient.name or ''
            
            # Try to parse [CBMxxxxxx] pattern from display_name
            match = re.search(r'\[([A-Z]+\d+)\]', patient.display_name or patient.name or '')
            if match:
                cbm_id = match.group(1)
                clean_name = re.sub(r'\s*\[[A-Z]+\d+\]', '', patient.display_name or patient.name or '').strip()
            
            return {
                'found': True,
                'id': patient.id,
                'name': patient.name,
                'display_name': patient.display_name,
                'clean_name': clean_name,
                'ref': patient.ref or '',
                'cbm_id': cbm_id,  # Only from ref or regex match, empty string if neither
            }
        
        return {'found': False, 'error': _('Patient not found for barcode: %s') % barcode}

    @http.route('/cbm/get_patient_draft_quotation', type='json', auth='user')
    def get_patient_draft_quotation(self, patient_id, location_id=None, sale_order_id=None):
        """
        Fetch consumption data for a patient to pre-populate cart.

        SOURCE OF TRUTH: Consumption Ledger (clinic.consumption.ledger)
        The ledger tracks exactly what was consumed with which lot.
        Falls back to SO lines for migration (existing SOs without ledger entries).

        Args:
            patient_id: Patient partner ID
            location_id: Source location ID to check stock availability
            sale_order_id: Optional specific SO ID to load (for SO-locked consumption)

        Returns:
            Dict with 'sale_order_id' and 'lines' list with product info, quantities, and stock availability
        """
        SaleOrder = request.env['sale.order'].sudo()
        Ledger = request.env['clinic.consumption.ledger'].sudo()
        Quant = request.env['stock.quant'].sudo()
        Product = request.env['product.product'].sudo()

        _logger.info("[CBM Ledger] Loading patient %s, location_id=%s, sale_order_id=%s",
                     patient_id, location_id, sale_order_id)

        # Find the draft SO for this patient
        if sale_order_id:
            draft_order = SaleOrder.browse(int(sale_order_id))
            if not draft_order.exists() or draft_order.partner_id.id != patient_id:
                draft_order = False
        else:
            draft_order = SaleOrder.search([
                ('partner_id', '=', patient_id),
                ('state', '=', 'draft'),
                ('company_id', '=', request.env.company.id),
            ], limit=1, order='create_date asc')

        if not draft_order:
            return {'sale_order_id': None, 'lines': []}

        # Check if ledger has entries for this SO
        ledger_entries = Ledger.search([
            ('sale_order_id', '=', draft_order.id),
            ('state', '=', 'active'),
        ])

        if not ledger_entries:
            # MIGRATION: No ledger entries, try to migrate from SO + stock history
            _logger.info("[CBM Ledger] No ledger entries for SO %s, attempting migration", draft_order.name)
            ledger_entries = Ledger.migrate_from_sale_order(draft_order)
            if ledger_entries:
                _logger.info("[CBM Ledger] Migrated %d entries from stock history", len(ledger_entries))

        # Build product map from ledger (aggregated by product)
        product_map = {}  # product_id -> aggregated data

        for entry in ledger_entries:
            pid = entry.product_id.id
            if entry.qty_available <= 0:
                continue  # Skip fully returned entries

            if pid not in product_map:
                product_map[pid] = {
                    'product_id': pid,
                    'product_name': entry.product_id.name,
                    'display_name': entry.product_id.display_name,
                    'qty': entry.qty_available,
                    'uom_name': entry.product_id.uom_id.name,
                    'qty_available': 0,  # Will be set below
                    'lot_id': False,  # For new consumption, FEFO from location
                    'lot_name': '',
                    'ledger_entry_ids': [entry.id],  # Track which ledger entries back this
                }
            else:
                product_map[pid]['qty'] += entry.qty_available
                product_map[pid]['ledger_entry_ids'].append(entry.id)

        # If ledger is empty but SO has lines, fall back to SO lines (edge case / services)
        if not product_map:
            _logger.info("[CBM Ledger] No ledger data, falling back to SO lines for SO %s", draft_order.name)
            for line in draft_order.order_line:
                if line.product_id and line.product_id.type != 'service':
                    pid = line.product_id.id
                    if pid not in product_map:
                        product_map[pid] = {
                            'product_id': pid,
                            'product_name': line.product_id.name,
                            'display_name': line.product_id.display_name,
                            'qty': line.product_uom_qty,
                            'uom_name': line.product_uom.name,
                            'qty_available': 0,
                            'lot_id': False,
                            'lot_name': '',
                            'ledger_entry_ids': [],  # No ledger backing
                        }
                    else:
                        product_map[pid]['qty'] += line.product_uom_qty

        # Enrich with stock availability and filter by location
        lines = []
        for pid, data in product_map.items():
            product = Product.browse(pid)

            # Skip service products
            if product.type == 'service':
                continue

            belongs_to_location = False
            qty_available = 0
            location_lot_id = False
            location_lot_name = ''

            if location_id and product.type == 'product':
                # Check stock at user's location
                quants = Quant.search([
                    ('product_id', '=', pid),
                    ('location_id', '=', location_id),
                ])
                if quants:
                    belongs_to_location = True
                    qty_available = sum(q.available_quantity for q in quants)

                    # FEFO lot selection for new consumption
                    if product.tracking == 'lot':
                        IrConfig = request.env['ir.config_parameter'].sudo()
                        lot_selection_mode = IrConfig.get_param('clinic_staff_portal.lot_selection_mode', 'auto_fefo')

                        if lot_selection_mode == 'auto_fefo':
                            quants_with_lot = Quant.search([
                                ('product_id', '=', pid),
                                ('location_id', '=', location_id),
                                ('lot_id', '!=', False),
                                ('quantity', '>', 0),
                            ])
                            if quants_with_lot:
                                lot_ids = quants_with_lot.mapped('lot_id')
                                if lot_ids:
                                    far_future = fields.Datetime.from_string('9999-12-31 23:59:59')
                                    lots_sorted = lot_ids.sorted(key=lambda lot: lot.expiration_date or far_future)
                                    first_expiry_lot = lots_sorted[:1]
                                    if first_expiry_lot:
                                        location_lot_id = first_expiry_lot.id
                                        location_lot_name = first_expiry_lot.name
                else:
                    _logger.info("[CBM Ledger] Filtering out product %s - no quant at location %s", product.name, location_id)

            elif product.type == 'consu':
                belongs_to_location = True

            if not belongs_to_location:
                continue

            data['qty_available'] = qty_available
            data['lot_id'] = location_lot_id
            data['lot_name'] = location_lot_name
            lines.append(data)

        _logger.info("[CBM Ledger] Returning %d products for SO %s", len(lines), draft_order.name)

        return {
            'sale_order_id': draft_order.id,
            'sale_order_name': draft_order.name,
            'lines': lines,
        }

    @http.route('/cbm/submit_request', type='json', auth='user')
    def submit_request(self, picking_type_id, lines):
        """
        Create a request picking (pull from source).
        
        Args:
            picking_type_id: Operation type ID
            lines: List of {'product_id': int, 'qty': float}
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        Picking = request.env['stock.picking'].sudo()
        PickingType = request.env['stock.picking.type']
        
        picking_type = PickingType.browse(picking_type_id)
        if not picking_type.exists():
            return {'success': False, 'error': _('Invalid operation type')}
        
        # --- LOCATION-WIDE UNRESERVE HOOK ---
        # Unreserve ALL portal pickings from the SAME source location (all users).
        # Multiple staff may share a location — stuck pickings from any user block everyone.
        source_location_id = picking_type.default_location_src_id.id
        try:
            pending_portal_requests = Picking.search([
                ('location_id', '=', source_location_id),
                ('is_portal_request', '=', True),
                ('state', 'in', ['confirmed', 'assigned', 'waiting']),
            ])
            if pending_portal_requests:
                _logger.info("Portal unreserve: releasing reservations from %d pickings at %s (all users)",
                            len(pending_portal_requests), picking_type.default_location_src_id.name)
                pending_portal_requests.do_unreserve()
                _logger.info("Portal unreserve: complete")
        except Exception as e:
            _logger.warning("Portal unreserve failed (non-critical): %s", str(e))
        
        # --- FIX: Audit Trail - Create with user context, validate with sudo ---
        # Create picking WITHOUT sudo to preserve audit trail (create_uid = actual user)
        # This allows "My Transfers" to work while still bypassing validation checks
        source_location_id = picking_type.default_location_src_id.id
        dest_location_id = picking_type.default_location_dest_id.id

        # Location validation: Ensure locations match operation type defaults
        if source_location_id != picking_type.default_location_src_id.id:
            raise UserError(_('Invalid source location for this operation type'))
        if dest_location_id != picking_type.default_location_dest_id.id:
            raise UserError(_('Invalid destination location for this operation type'))

        picking = Picking.with_context(
            portal_mode=True,
            portal_stock_behavior='request'
        ).create({
            'picking_type_id': picking_type.id,
            'location_id': source_location_id,
            'location_dest_id': dest_location_id,
            'scheduled_date': fields.Datetime.now(),
            'is_portal_request': True,
            'portal_requester_id': request.env.user.id,
            'portal_behavior': 'request',
        })
        
        # Create move lines (portal user has ACL via group_clinic_portal_user)
        Move = request.env['stock.move']
        for line in lines:
            product = request.env['product.product'].browse(line['product_id'])
            Move.create({
                'picking_id': picking.id,
                'product_id': product.id,
                'product_uom_qty': line['qty'],
                'product_uom': product.uom_id.id,
                'name': product.display_name,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            })

        # Confirm the picking WITH sudo to bypass stock warnings (kiosk automation)
        # Picking already created with user context above, so audit trail is preserved
        picking.sudo().action_confirm()

        # Notify managers
        picking._notify_managers()
        
        return {
            'success': True,
            'picking_id': picking.id,
            'picking_name': picking.name,
            'message': _('Request %s submitted successfully!') % picking.name,
        }

    @http.route('/cbm/submit_consumption', type='json', auth='user')
    def submit_consumption(self, picking_type_id, patient_id, lines, department_id=None, sale_order_id=None, confirm_deletion=False):
        """
        Create a consumption picking (billable to patient or department).

        Handles delta calculations for pre-loaded quotation items:
        - qty > original_qty: Consume additional delta
        - qty < original_qty: Create return picking for delta
        - qty == original_qty: Skip (no stock movement)
        - No original_qty: New item, consume full qty

        Args:
            picking_type_id: Operation type ID
            patient_id: Patient partner ID (or None)
            lines: List of {'product_id': int, 'qty': float, 'original_qty': float|False, 'order_line_id': int|False}
            department_id: Department partner ID (optional, for non-patient consumptions)
            sale_order_id: Optional specific SO ID to link consumption to (prevents jumping between SOs)
            confirm_deletion: Boolean - if True, user has confirmed they want to delete/reduce items
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        Picking = request.env['stock.picking'].sudo()
        PickingType = request.env['stock.picking.type']
        
        # NOTE: Unreserve logic moved to submit_request (where it belongs)
        # Consumption uses ward stock (isolated), doesn't need global unreserve
        
        picking_type = PickingType.browse(picking_type_id)
        if not picking_type.exists():
            return {'success': False, 'error': _('Invalid operation type')}
        
        if picking_type.portal_requires_patient and not patient_id:
            return {'success': False, 'error': _('Patient is required for this operation')}

        if picking_type.portal_requires_department and not department_id:
            return {'success': False, 'error': _('Department is required for this operation')}

        import logging
        _logger = logging.getLogger(__name__)

        # Ensure patient_id is proper integer
        if patient_id:
            try:
                patient_id = int(patient_id)
            except (ValueError, TypeError):
                _logger.error("CBM: Invalid patient_id, cannot convert to int: %s", patient_id)
                return {'success': False, 'error': _('Invalid patient ID')}

        # Ensure department_id is proper integer
        if department_id:
            try:
                department_id = int(department_id)
            except (ValueError, TypeError):
                _logger.error("CBM: Invalid department_id, cannot convert to int: %s", department_id)
                return {'success': False, 'error': _('Invalid department ID')}

        # --- DUPLICATE SUBMISSION GUARD ---
        # Check for existing pending pickings for this patient/department + picking type
        # Prevents creating multiple pickings when user clicks submit multiple times
        # CRITICAL: Also check for very recent submissions (last 10 seconds) to catch rapid double-clicks
        from datetime import timedelta
        source_location_id = picking_type.default_location_src_id.id
        ten_seconds_ago = fields.Datetime.now() - timedelta(seconds=10)

        existing_pending_domain = [
            ('picking_type_id', '=', picking_type_id),
            ('location_id', '=', source_location_id),
            ('is_portal_request', '=', True),
            ('state', 'in', ['draft', 'confirmed', 'assigned', 'waiting']),
            ('portal_requester_id', '=', request.env.user.id),
            ('create_date', '>=', ten_seconds_ago),  # Only check very recent submissions
        ]
        # Only check duplicate if we have a specific patient or department
        # Without this, the check would match ANY recent transfer by this user
        should_check_duplicate = False  # Initialize to prevent UnboundLocalError
        if patient_id:
            should_check_duplicate = True
            existing_pending_domain.append(('partner_id', '=', patient_id))
        elif department_id:
            # For department consumptions, check for same department
            should_check_duplicate = True
            existing_pending_domain.append(('partner_id', '=', department_id))
        else:
            # No patient or department specified - skip duplicate check
            # (unusual case, but prevents false positives)
            pass

        existing_pending = False
        if should_check_duplicate:
            existing_pending = Picking.search(existing_pending_domain, limit=1, order='create_date DESC')

        if existing_pending:
            _logger.warning("CBM: Duplicate submission blocked - pending picking %s exists for patient %s",
                           existing_pending.name, patient_id)

            # Notify admin via discrepancy system (deduplicate by picking per day)
            Discrepancy = request.env['clinic.stock.discrepancy'].sudo()
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            existing_alert = Discrepancy.search([
                ('picking_id', '=', existing_pending.id),
                ('state', '=', 'pending'),
                ('create_date', '>=', today_start),
            ], limit=1)

            if not existing_alert:
                # Create discrepancy alert for admin
                patient = request.env['res.partner'].browse(patient_id) if patient_id else False
                Discrepancy.create({
                    'user_id': request.env.user.id,
                    'patient_id': patient_id if patient_id else False,
                    'picking_id': existing_pending.id,
                    'location_id': source_location_id,
                    'picking_type_id': picking_type.id,
                    'notes': 'Transfert bloqué: %s - Patient: %s - Utilisateur a tenté de soumettre à nouveau' % (
                        existing_pending.name,
                        patient.name if patient else 'N/A'
                    ),
                })
                _logger.info("CBM: Created discrepancy alert for blocked duplicate submission %s", existing_pending.name)

            return {
                'success': False,
                'error': "Un transfert en attente (%s) existe déjà pour ce patient. "
                         "L'administrateur a été notifié. "
                         "Veuillez continuer avec d'autres patients en attendant la résolution." % existing_pending.name,
                'show_banner': True,  # Show in banner instead of toast
                'banner_type': 'blocked',  # Type for styling
            }

        # NOTE: No unreserve needed for consumption — we bypass Odoo's reservation
        # entirely (set move state + qty_done directly). This prevents race conditions
        # where unreserving other pickings interferes with concurrent submissions.

        # --- DELTA SEPARATION: Handle pre-loaded quotation items ---
        # Separate lines into: consumption (increases/new), returns (decreases), unchanged (skip)
        consumption_lines = []  # Lines requiring stock consumption
        return_lines = []       # Lines requiring stock return
        unchanged_lines = []    # Lines with no qty change (update SO only)

        for line in lines:
            original_qty = line.get('original_qty')
            current_qty = line['qty']
            order_line_id = line.get('order_line_id')

            if original_qty is not None and original_qty is not False:
                # Pre-loaded item from ledger (or legacy SO line)
                delta = current_qty - original_qty
                if delta > 0:
                    _logger.info("Delta +%.2f for product %s: consume additional", delta, line['product_id'])
                    consumption_lines.append({
                        **line,
                        'qty': delta,
                        'final_qty': current_qty,
                    })
                elif delta < 0:
                    _logger.info("Delta %.2f for product %s: return to stock", delta, line['product_id'])
                    return_lines.append({
                        **line,
                        'qty': abs(delta),
                        'final_qty': current_qty,
                    })
                else:
                    _logger.info("No change for product %s: skip", line['product_id'])
                    unchanged_lines.append(line)
            else:
                # New item: full consumption
                _logger.info("New item product %s: consume full qty %.2f", line['product_id'], current_qty)
                consumption_lines.append({
                    **line,
                    'final_qty': current_qty,
                })

        _logger.info("Delta separation: %d consumption, %d returns, %d unchanged",
                    len(consumption_lines), len(return_lines), len(unchanged_lines))

        # --- CONFIRMATION CHECK: Require user confirmation for deletions/reductions ---
        # This is a safety measure to prevent accidental deletions and catch potential fraud
        if return_lines and not confirm_deletion:
            # Build list of items being deleted/reduced for user confirmation
            Product = request.env['product.product']
            deletion_items = []
            for line in return_lines:
                product = Product.browse(line['product_id'])
                deletion_items.append({
                    'product_id': line['product_id'],
                    'product_name': product.name,
                    'qty_removed': line['qty'],  # The delta being returned
                    'original_qty': line.get('original_qty', 0),
                    'final_qty': line.get('final_qty', 0),
                })

            _logger.info("CBM: Deletion confirmation required for %d items", len(deletion_items))
            return {
                'success': False,
                'requires_confirmation': True,
                'deletion_items': deletion_items,
                'message': _('Vous allez supprimer des produits. Veuillez confirmer.'),
            }

        # --- PRE-VALIDATION: Check stock availability and FILTER unavailable products ---
        # Instead of blocking entire consumption, skip products that aren't available
        # Only the available products will be consumed and added to Sale Order

        Product = request.env['product.product']
        Quant = request.env['stock.quant'].sudo()
        Discrepancy = request.env['clinic.stock.discrepancy'].sudo()

        available_lines = []
        skipped_products = []

        # Only check stock for consumption lines (returns don't need stock check)
        for line in consumption_lines:
            product = Product.browse(line['product_id'])
            
            # Non-stockable products always pass
            if product.type != 'product':
                available_lines.append(line)
                continue
            
            # Get stock at EXACT location only (not including children)
            quants = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', '=', source_location_id),  # Exact match
            ])
            available = sum(q.available_quantity for q in quants)
            
            if line['qty'] <= available:
                # Sufficient stock, include in consumption
                available_lines.append(line)
            else:
                # Insufficient stock - create discrepancy alert and SKIP this product
                source_location_name = request.env['stock.location'].sudo().browse(source_location_id).name
                _logger.warning("Stock insufficient: %s needs %.2f but only %.2f at %s - SKIPPING",
                                product.name, line['qty'], available, source_location_name)
                
                # Check for existing pending discrepancy for same product/location TODAY (deduplication)
                today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                existing_alert = Discrepancy.search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', source_location_id),
                    ('state', '=', 'pending'),
                    ('create_date', '>=', today_start),
                ], limit=1)
                
                if existing_alert:
                    # Use existing alert instead of creating duplicate
                    alert = existing_alert
                    _logger.info("Reusing existing discrepancy alert: %s", alert.name)
                else:
                    # Create new discrepancy alert for investigation
                    alert = Discrepancy.create({
                        'user_id': request.env.user.id,
                        'patient_id': patient_id if patient_id else False,
                        'product_id': product.id,
                        'attempted_qty': line['qty'],
                        'system_qty': available,
                        'location_id': source_location_id,
                        'picking_type_id': picking_type.id,
                    })
                    _logger.info("Created discrepancy alert: %s", alert.name)
                
                skipped_products.append({
                    'product': product.name,
                    'product_id': product.id,
                    'needed': line['qty'],
                    'available': available,
                    'alert': alert.name,
                })
        
        # If NO products have sufficient stock AND no returns AND no unchanged items, return error
        if not available_lines and not return_lines and not unchanged_lines:
            error_msg = _("Unable to process consumption - all products are out of stock:")
            for skip in skipped_products:
                error_msg += _("\n• %(prod)s: need %(qty)s, available %(avail)s") % {
                    'prod': skip['product'],
                    'qty': skip['needed'],
                    'avail': skip['available'],
                }
            return {'success': False, 'error': error_msg}

        # Continue with available_lines only (skipped products won't be in picking or SO)
        lines = available_lines
        
        # Use operation type's configured source and destination
        # - For billable: source is USER's WARD (already in source_location_id)
        # - For internal: source is operation type's default
        
        # Create picking using determined source location
        # Determine partner/delivery address based on operation type configuration:
        # 1. If requires_patient and patient provided → use patient
        # 2. If requires_department and department provided → use department
        # 3. Otherwise → use requesting user
        if patient_id:
            contact_partner_id = patient_id
        elif department_id:
            contact_partner_id = department_id
        else:
            contact_partner_id = request.env.user.partner_id.id

        Move = request.env['stock.move']
        MoveLine = request.env['stock.move.line']
        Lot = request.env['stock.lot']
        SaleOrderLine = request.env['sale.order.line'].sudo()

        picking = None
        return_picking = None

        # --- CONSUMPTION PICKING: For increases and new items ---
        if lines:
            # --- FIX: Location validation before creation ---
            dest_location_id = picking_type.default_location_dest_id.id
            if source_location_id != picking_type.default_location_src_id.id:
                raise UserError(_('Invalid source location for this operation type'))
            if dest_location_id != picking_type.default_location_dest_id.id:
                raise UserError(_('Invalid destination location for this operation type'))

            # Create WITHOUT sudo to preserve audit trail (create_uid = actual user)
            # FIX Issue #2: Include linked_sale_order_id to lock consumption to specific SO
            picking = Picking.create({
                'picking_type_id': picking_type.id,
                'location_id': source_location_id,  # User's ward for consumption
                'location_dest_id': dest_location_id,
                'scheduled_date': fields.Datetime.now(),
                'partner_id': contact_partner_id,  # Patient for billable, requesting user for internal
                'is_portal_request': True,
                'portal_requester_id': request.env.user.id,
                'portal_behavior': 'billable' if picking_type.portal_requires_patient else 'internal',
                'linked_sale_order_id': sale_order_id if sale_order_id else False,
            })

            _logger.info("CBM: Consumption picking %s created (patient=%s, behavior=%s)",
                        picking.name,
                        picking.partner_id.name if picking.partner_id else 'None',
                        picking.portal_behavior)

            # Create move lines for consumption
            for line in lines:
                product = request.env['product.product'].browse(line['product_id'])
                lot_id = line.get('lot_id') or False
                order_line_id = line.get('order_line_id') or False
                final_qty = line.get('final_qty', line['qty'])

                # Store final_qty and order_line_id in origin for SO update
                origin_data = f"{order_line_id}|{final_qty}" if order_line_id else False

                move = Move.create({
                    'picking_id': picking.id,
                    'product_id': product.id,
                    'product_uom_qty': line['qty'],  # Delta qty for stock movement
                    'product_uom': product.uom_id.id,
                    'name': product.display_name,
                    'location_id': picking.location_id.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'origin': origin_data,  # Store order_line_id|final_qty for SO updates
                })

                # Don't pre-assign lots - let Odoo handle lot assignment via reservation
                # This prevents issues with lots that don't exist at the source location

        # --- RETURN PICKING: For decreases (qty reduced from original) ---
        # CRITICAL: Use ledger for lot lookup (LIFO), not SO line
        # The ledger knows exactly which lot was consumed for each entry
        Ledger = request.env['clinic.consumption.ledger'].sudo()

        if return_lines:
            # Return picking: swap source and destination (stock comes BACK to location)
            # Create WITHOUT sudo to preserve audit trail
            return_picking = Picking.create({
                'picking_type_id': picking_type.id,
                'location_id': picking_type.default_location_dest_id.id,  # From patient consumption dest
                'location_dest_id': source_location_id,  # Back to source (ward)
                'scheduled_date': fields.Datetime.now(),
                'partner_id': contact_partner_id,
                'is_portal_request': True,
                'portal_requester_id': request.env.user.id,
                'portal_behavior': 'return',  # Mark as return
                'origin': picking.name if picking else 'Return',
            })

            _logger.info("CBM: Return picking %s created for %d products",
                        return_picking.name, len(return_lines))

            # Track which ledger entries to update after validation
            move_ledger_map = {}  # move_id -> list of {'entry': ledger_entry, 'qty': float, 'lot_id': int}

            for line in return_lines:
                product = request.env['product.product'].browse(line['product_id'])
                qty_to_return = line['qty']

                # Get ledger entries for this product using LIFO
                # This gives us the exact lots that were consumed
                if sale_order_id:
                    ledger_data = Ledger.get_entries_for_return(sale_order_id, product.id, qty_to_return)
                else:
                    ledger_data = []

                if ledger_data:
                    # Create one move per lot (ledger may span multiple lots)
                    for ld in ledger_data:
                        lot_id = ld['lot_id']
                        qty = ld['qty']

                        move = Move.create({
                            'picking_id': return_picking.id,
                            'product_id': product.id,
                            'product_uom_qty': qty,
                            'product_uom': product.uom_id.id,
                            'name': f"[RETURN] {product.display_name}",
                            'location_id': return_picking.location_id.id,
                            'location_dest_id': return_picking.location_dest_id.id,
                        })

                        move_ledger_map[move.id] = {
                            'lot_id': lot_id,
                            'entry': ld['entry'],
                            'qty': qty,
                        }
                        _logger.info("CBM: Return move for %s x %.2f (lot=%s) from ledger entry %s",
                                    product.name, qty, lot_id, ld['entry'].id)
                else:
                    # No ledger entries - this shouldn't happen but handle gracefully
                    # Try SO line as fallback (legacy data)
                    _logger.warning("CBM: No ledger entries for return of %s, trying SO line fallback", product.name)
                    lot_id = False
                    order_line_id = line.get('order_line_id')
                    if order_line_id and product.tracking == 'lot':
                        so_line = SaleOrderLine.browse(int(order_line_id))
                        if so_line.exists() and so_line.lot_id:
                            lot_id = so_line.lot_id.id
                            _logger.info("CBM: Using lot %s from SO line %s (fallback)", so_line.lot_id.name, order_line_id)

                    move = Move.create({
                        'picking_id': return_picking.id,
                        'product_id': product.id,
                        'product_uom_qty': qty_to_return,
                        'product_uom': product.uom_id.id,
                        'name': f"[RETURN] {product.display_name}",
                        'location_id': return_picking.location_id.id,
                        'location_dest_id': return_picking.location_dest_id.id,
                    })

                    move_ledger_map[move.id] = {
                        'lot_id': lot_id,
                        'entry': None,  # No ledger entry
                        'qty': qty_to_return,
                    }

            # Confirm and validate return picking immediately WITH sudo
            # CRITICAL: Returns come FROM patient/virtual location where there is no
            # real stock to reserve. We bypass Odoo's reservation entirely — we already
            # know the exact lot and qty from the consumption ledger. action_confirm()
            # would trigger _action_assign() which hits discrepancy checks and fails
            # silently, leaving returns stuck in 'confirmed' state with qty_done=0.
            return_validated = False
            try:
                # Step 1: Force moves to confirmed state without triggering reservation
                return_picking.sudo().write({'state': 'confirmed'})
                for move in return_picking.sudo().move_ids:
                    move.write({'state': 'confirmed'})

                _logger.info("CBM: Return picking %s set to confirmed (no reservation needed)", return_picking.name)

                # Step 2: Create move lines with qty_done directly from ledger data
                # No reservation — we set qty_done and lot from ledger (source of truth)
                for move in return_picking.move_ids:
                    ledger_info = move_ledger_map.get(move.id, {})
                    lot_id = ledger_info.get('lot_id')

                    # Remove any auto-created empty move lines first
                    if move.move_line_ids:
                        move.move_line_ids.sudo().unlink()

                    # Create fresh move line with qty_done set
                    MoveLine.sudo().create({
                        'move_id': move.id,
                        'product_id': move.product_id.id,
                        'product_uom_id': move.product_uom.id,
                        'reserved_uom_qty': 0,  # No reservation — returning from virtual location
                        'lot_id': lot_id if lot_id else False,
                        'qty_done': move.product_uom_qty,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'picking_id': return_picking.id,
                    })
                    _logger.info("CBM: Return move line created for %s x %.2f (lot_id=%s, qty_done=%.2f)",
                                move.product_id.name, move.product_uom_qty, lot_id, move.product_uom_qty)

                # Step 3: Validate — skip_immediate_transfer prevents wizard,
                # skip_backorder prevents partial delivery wizard
                return_picking.with_context(
                    skip_immediate_transfer=True,
                    skip_backorder=True,
                    skip_sms=True,
                ).sudo().button_validate()
                _logger.info("CBM: Return picking %s validated, state=%s", return_picking.name, return_picking.state)
                return_validated = True

                # Step 4: Update ledger entries to mark quantities as returned
                for move in return_picking.move_ids:
                    ledger_info = move_ledger_map.get(move.id, {})
                    entry = ledger_info.get('entry')
                    qty = ledger_info.get('qty', 0)
                    if entry:
                        entry.mark_returned(qty, return_picking.id)

            except Exception as e:
                import traceback
                _logger.error("CBM: Failed to validate return picking %s: %s\n%s",
                             return_picking.name, str(e), traceback.format_exc())
                return {
                    'success': False,
                    'error': _('Le retour de stock a échoué et nécessite une intervention manuelle. Référence : %s') % return_picking.name,
                    'requires_manual_intervention': True,
                }

            # Update SO lines if return was validated
            if return_validated:
                # Find the draft SO to update
                so_to_update = False
                if sale_order_id:
                    so_to_update = request.env['sale.order'].sudo().browse(int(sale_order_id))
                    if not so_to_update.exists() or so_to_update.state not in ('draft', 'sent'):
                        so_to_update = False

                for line in return_lines:
                    product_id = line['product_id']
                    final_qty = line.get('final_qty', 0)
                    order_line_id = line.get('order_line_id')

                    # Try order_line_id first (legacy), then match by product on SO
                    so_line = False
                    if order_line_id:
                        candidate = SaleOrderLine.browse(int(order_line_id))
                        if candidate.exists() and candidate.order_id.state in ('draft', 'sent'):
                            so_line = candidate
                    elif so_to_update:
                        # Ledger path: find SO line by product
                        matching = so_to_update.order_line.filtered(
                            lambda l: l.product_id.id == product_id
                        )
                        if matching:
                            so_line = matching[0]

                    if so_line:
                        if final_qty <= 0:
                            _logger.info("CBM: Removing SO line for product %s (qty=0)", product_id)
                            so_line.sudo().unlink()
                        else:
                            _logger.info("CBM: Updating SO line for product %s qty to %.2f", product_id, final_qty)
                            so_line.sudo().write({'product_uom_qty': final_qty})
            else:
                _logger.warning("CBM: Return picking %s not validated - SO lines NOT updated", return_picking.name)

        # Execute consumption: confirm picking + create/update sale order
        if picking:
            if picking_type.portal_requires_patient:
                # Billable: Call full consumption logic (creates SO)
                _logger.info("CBM Kiosk: Billable consumption for picking %s, patient %s", picking.name, picking.partner_id.name)
                try:
                    picking._execute_consumption_submit()
                    _logger.info("CBM Kiosk: Successfully executed consumption submit for %s", picking.name)
                except Exception as e:
                    import traceback
                    _logger.error("CBM Kiosk: Error in _execute_consumption_submit: %s\n%s",
                                  str(e), traceback.format_exc())
                    return {'success': False, 'error': str(e)}
            else:
                # Internal or Department consumption: Confirm with sudo to bypass stock checks
                consumption_type = 'department' if picking_type.portal_requires_department else 'internal'
                _logger.info("CBM Kiosk: %s consumption for picking %s (no billing)", consumption_type.capitalize(), picking.name)
                picking.sudo().action_confirm()

                # Auto-validate if user is location responsible
                if request.env.user in picking.approver_ids:
                    _logger.info("CBM Kiosk: User is location responsible for %s, checking for auto-validation", consumption_type)
                    if picking.state == 'assigned':
                        _logger.info("CBM Kiosk: Stock available, auto-validating %s consumption %s", consumption_type, picking.name)
                        for move_line in picking.move_line_ids_without_package:
                            move_line.qty_done = move_line.reserved_uom_qty
                        picking.sudo().button_validate()  # sudo() to bypass stock warnings
                        _logger.info("CBM Kiosk: Successfully auto-validated %s consumption %s", consumption_type, picking.name)
                    else:
                        _logger.info("CBM Kiosk: Stock not available (state: %s), %s consumption pending", picking.state, consumption_type)
                else:
                    _logger.info("CBM Kiosk: User is NOT location responsible, %s consumption %s requires approval", consumption_type, picking.name)

        # Build response message
        if picking and return_picking:
            message = _('Consumption %s and return %s recorded!') % (picking.name, return_picking.name)
        elif picking:
            message = _('Consumption %s recorded!') % picking.name
        elif return_picking:
            message = _('Return %s recorded!') % return_picking.name
        else:
            message = _('No changes to process')

        response = {
            'success': True,
            'picking_id': picking.id if picking else (return_picking.id if return_picking else None),
            'picking_name': picking.name if picking else (return_picking.name if return_picking else None),
            'return_picking_id': return_picking.id if return_picking else None,
            'return_picking_name': return_picking.name if return_picking else None,
            'message': message,
        }

        # Add skipped products warning if any
        if skipped_products:
            response['skipped_products'] = skipped_products
            response['warning'] = _('Some products were skipped due to insufficient stock')

        return response

    @http.route('/cbm/get_department_partners', type='json', auth='user')
    def get_department_partners(self):
        """Get list of department partners (CBM: prefixed partners) for consumption delivery address"""
        Partner = request.env['res.partner'].sudo()

        # Search for partners with names starting with "CBM:"
        departments = Partner.search([
            ('name', '=like', 'CBM:%')
        ], order='name')

        result = []
        for dept in departments:
            result.append({
                'id': dept.id,
                'name': dept.name,
                'display_name': dept.name.replace('CBM:', '').strip(),  # Remove "CBM:" prefix for display
            })

        return result

    @http.route('/cbm/get_history', type='json', auth='user')
    def get_history(self, limit=200):
        """Get current user's portal request history"""
        user = request.env.user
        Picking = request.env['stock.picking']
        
        # Filter: Last 30 days only
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        pickings = Picking.search([
            ('is_portal_request', '=', True),  # Only portal pickings
            ('create_date', '>=', thirty_days_ago.strftime('%Y-%m-%d')),
            '|',
            ('portal_requester_id', '=', user.id),
            ('create_uid', '=', user.id),
        ], limit=limit, order='create_date desc')
        
        result = []
        for picking in pickings:
            result.append({
                'id': picking.id,
                'name': picking.name,
                'state': picking.state,
                'state_display': dict(picking._fields['state'].selection).get(picking.state),
                'portal_behavior': picking.portal_behavior,
                'create_date': picking.create_date.isoformat() if picking.create_date else False,
                'scheduled_date': picking.scheduled_date.isoformat() if picking.scheduled_date else False,
                'partner_name': picking.partner_id.name if picking.partner_id else False,
                'location_src_name': picking.location_id.name if picking.location_id else False,
                'location_dest_name': picking.location_dest_id.name if picking.location_dest_id else False,
                'move_count': len(picking.move_ids_without_package),
                # FIX Issue #1: Add partial consumption indicator for history display
                'is_partial_consumption': picking.is_partial_consumption,
            })

        return result

    @http.route('/cbm/get_picking_detail', type='json', auth='user')
    def get_picking_detail(self, picking_id):
        """Get picking detail with product lines for modal display"""
        Picking = request.env['stock.picking']
        picking = Picking.browse(picking_id)
        
        if not picking.exists():
            return {'error': _('Picking not found')}
        
        # Security check - user must have access
        user = request.env.user
        if picking.portal_requester_id.id != user.id and picking.create_uid.id != user.id:
            # CBM Portal Admin = only user IDs 2 and 11
            CBM_ADMIN_IDS = [2, 11]
            if user.id not in CBM_ADMIN_IDS:
                return {'error': _('Access denied')}
        
        lines = []
        for move in picking.move_ids_without_package:
            lines.append({
                'product_name': move.product_id.display_name,
                'product_code': move.product_id.default_code or '',
                'qty': move.product_uom_qty,
                'qty_done': move.quantity_done,
                'uom': move.product_uom.name,
            })
        
        return {
            'id': picking.id,
            'name': picking.name,
            'state': picking.state,
            'state_display': dict(picking._fields['state'].selection).get(picking.state),
            'partner_name': picking.partner_id.name if picking.partner_id else False,
            'create_date': picking.create_date.isoformat() if picking.create_date else False,
            'lines': lines,
        }

    # ========================================
    # MAINTENANCE REQUEST ENDPOINTS
    # ========================================

    @http.route('/cbm/get_equipment', type='json', auth='user')
    def get_equipment(self, query='', limit=20):
        """Return equipment for maintenance request dropdown.

        All users can search all equipment - no location filtering.
        Uses sudo() to bypass access restrictions.
        """
        try:
            Equipment = request.env['maintenance.equipment'].sudo()

            # Build domain - search by name or serial_no if query provided
            domain = []
            if query:
                domain = ['|', ('name', 'ilike', query), ('serial_no', 'ilike', query)]

            equipment = Equipment.search(domain, limit=limit, order='name')

            return [{
                'id': eq.id,
                'name': eq.name,
                'display_name': eq.display_name,
                'category': eq.category_id.name if eq.category_id else '',
                'location': eq.location_id.name if hasattr(eq, 'location_id') and eq.location_id else '',
                'technician_id': eq.technician_user_id.id if eq.technician_user_id else False,
                'team_id': eq.maintenance_team_id.id if eq.maintenance_team_id else False,
            } for eq in equipment]
        except Exception as e:
            _logger.error("Error in get_equipment: %s", str(e))
            return []

    @http.route('/cbm/submit_maintenance', type='json', auth='user')
    def submit_maintenance(self, equipment_id, description=''):
        """Create a maintenance request with auto-filled fields.

        Auto-fills:
        - name: "Demande maintenance - [Equipment Name]"
        - maintenance_type: 'corrective'
        - employee_id: Current user's employee record
        - user_id: Technician from equipment
        - maintenance_team_id: Team from equipment
        """
        user = request.env.user
        Equipment = request.env['maintenance.equipment'].sudo()
        MaintenanceRequest = request.env['maintenance.request'].sudo()

        # Validate equipment exists
        equipment = Equipment.browse(equipment_id)
        if not equipment.exists():
            return {'success': False, 'error': _('Équipement non trouvé')}

        # Get user's employee record (if hr.employee module is installed)
        employee_id = False
        try:
            Employee = request.env['hr.employee']
            employee = Employee.search([('user_id', '=', user.id)], limit=1)
            if employee:
                employee_id = employee.id
        except Exception:
            pass  # hr.employee may not be installed

        # Get user's ward name for title
        ward_name = ''
        if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
            for op_type in user.allowed_operation_types:
                if op_type.portal_requires_patient and op_type.default_location_src_id:
                    ward_name = op_type.default_location_src_id.name
                    break

        # Build title
        title = _('Demande maintenance - %s') % equipment.name
        if ward_name:
            title = _('Demande maintenance %s - %s') % (ward_name, equipment.name)

        # Create maintenance request vals
        vals = {
            'name': title,
            'equipment_id': equipment_id,
            'maintenance_type': 'corrective',
            'description': description or '',
        }

        # Inherit team/technician from equipment
        if equipment.technician_user_id:
            vals['user_id'] = equipment.technician_user_id.id
        if equipment.maintenance_team_id:
            vals['maintenance_team_id'] = equipment.maintenance_team_id.id
        if equipment.category_id:
            vals['category_id'] = equipment.category_id.id

        # Add employee if available
        if employee_id:
            vals['employee_id'] = employee_id

        try:
            maintenance_request = MaintenanceRequest.create(vals)
            _logger.info(f"[CBM MAINTENANCE] Created request {maintenance_request.name} for equipment {equipment.name}")

            return {
                'success': True,
                'request_id': maintenance_request.id,
                'request_name': maintenance_request.name,
            }
        except Exception as e:
            _logger.error(f"[CBM MAINTENANCE] Failed to create request: {e}")
            return {'success': False, 'error': str(e)[:200]}

    # ==================== PRESCRIPTION ENDPOINTS ====================

    @http.route('/cbm/get_patient_prescriptions', type='json', auth='user')
    def get_patient_prescriptions(self, patient_id, location_id=None):
        """
        Load active prescription lines for a patient (from Bahmni drug orders).

        Returns prescription lines grouped by provider_name, enriched with
        stock availability at the nurse's current location.

        Args:
            patient_id: Patient partner ID
            location_id: Nurse's source location ID (for stock availability)

        Returns:
            Dict with 'prescriptions' list grouped by provider
        """
        Prescription = request.env['clinic.prescription'].sudo()
        Quant = request.env['stock.quant'].sudo()
        Product = request.env['product.product'].sudo()

        prescriptions = Prescription.search([
            ('partner_id', '=', int(patient_id)),
            ('state', '=', 'active'),
        ])

        if not prescriptions:
            return {'prescriptions': [], 'lines': []}

        # Collect all active lines across prescriptions
        lines = []
        for rx in prescriptions:
            for line in rx.line_ids:
                if line.state == 'cancelled':
                    continue

                product = line.product_id
                qty_available = 0
                lot_id = False
                lot_name = ''

                if location_id and product.type == 'product':
                    # Stock at nurse's location
                    quants = Quant.search([
                        ('product_id', '=', product.id),
                        ('location_id', '=', int(location_id)),
                    ])
                    qty_available = sum(q.quantity for q in quants)

                    # FEFO lot selection
                    if product.tracking == 'lot':
                        IrConfig = request.env['ir.config_parameter'].sudo()
                        lot_mode = IrConfig.get_param('clinic_staff_portal.lot_selection_mode', 'auto_fefo')
                        if lot_mode == 'auto_fefo':
                            quants_lot = Quant.search([
                                ('product_id', '=', product.id),
                                ('location_id', '=', int(location_id)),
                                ('lot_id', '!=', False),
                                ('quantity', '>', 0),
                            ])
                            if quants_lot:
                                lot_ids = quants_lot.mapped('lot_id')
                                far_future = fields.Datetime.from_string('9999-12-31 23:59:59')
                                lots_sorted = lot_ids.sorted(
                                    key=lambda lot: lot.expiration_date or far_future
                                )
                                if lots_sorted:
                                    lot_id = lots_sorted[0].id
                                    lot_name = lots_sorted[0].name

                # Remaining qty that can still be applied
                qty_remaining = line.qty_prescribed - line.qty_applied

                lines.append({
                    'prescription_line_id': line.id,
                    'prescription_id': rx.id,
                    'product_id': product.id,
                    'product_name': product.name,
                    'display_name': product.display_name,
                    'uom_name': product.uom_id.name,
                    'qty_prescribed': line.qty_prescribed,
                    'qty_applied': line.qty_applied,
                    'qty_remaining': qty_remaining,
                    'provider_name': line.provider_name or rx.provider_name or '',
                    'external_order_id': line.external_order_id or '',
                    'state': line.state,
                    'stop_reason': line.stop_reason or '',
                    'qty_available': qty_available,
                    'lot_id': lot_id,
                    'lot_name': lot_name,
                    'is_prescription': True,  # Frontend marker
                })

        return {
            'prescriptions': [{
                'id': rx.id,
                'provider_name': rx.provider_name,
                'visit_uuid': rx.visit_uuid,
            } for rx in prescriptions],
            'lines': lines,
        }

    @http.route('/cbm/search_products_non_drug', type='json', auth='user')
    def search_products_non_drug(self, query, location_id=None, limit=20):
        """
        Search products excluding drugs (is_drug=False).
        Used in prescription tile for nurse-added consumables.

        Same logic as search_products but with is_drug filter.
        """
        if not location_id:
            return []

        Product = request.env['product.product']
        Quant = request.env['stock.quant'].sudo()
        IrConfig = request.env['ir.config_parameter'].sudo()
        lot_selection_mode = IrConfig.get_param('clinic_staff_portal.lot_selection_mode', 'auto_fefo')

        location = request.env['stock.location'].sudo().browse(int(location_id))
        _logger.info("CBM PRESCRIPTION SEARCH: location=%s, query=%s", location.name, query)

        # Find products with stock at location, excluding drugs
        quants = Quant.search([
            ('location_id', '=', int(location_id)),
        ])
        product_ids_at_location = quants.mapped('product_id').ids

        if not product_ids_at_location:
            return []

        # Search with is_drug filter
        domain = [
            ('id', 'in', product_ids_at_location),
            ('product_tmpl_id.is_drug', '=', False),
            '|', '|',
            ('name', 'ilike', query),
            ('default_code', 'ilike', query),
            ('barcode', 'ilike', query),
        ]
        products = Product.sudo().search(domain, limit=limit)

        result = []
        for product in products:
            # Stock at exact location
            prod_quants = Quant.search([
                ('product_id', '=', product.id),
                ('location_id', '=', int(location_id)),
            ])
            qty_available = sum(q.quantity for q in prod_quants)

            # FEFO lot
            lot_id = False
            lot_name = False
            if product.tracking == 'lot' and lot_selection_mode == 'auto_fefo':
                quants_with_lot = Quant.search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', int(location_id)),
                    ('lot_id', '!=', False),
                    ('quantity', '>', 0),
                ], order='lot_id')
                if quants_with_lot:
                    lot_ids = quants_with_lot.mapped('lot_id')
                    far_future = fields.Datetime.from_string('9999-12-31 23:59:59')
                    lots_sorted = lot_ids.sorted(
                        key=lambda lot: lot.expiration_date or far_future
                    )
                    if lots_sorted:
                        lot_id = lots_sorted[0].id
                        lot_name = lots_sorted[0].name

            result.append({
                'id': product.id,
                'name': product.display_name,
                'display_name': product.display_name,
                'barcode': product.barcode,
                'default_code': product.default_code,
                'qty_available': qty_available,
                'uom_id': product.uom_id.id,
                'uom_name': product.uom_id.name,
                'tracking': product.tracking,
                'lot_id': lot_id,
                'lot_name': lot_name,
            })

        return result

    @http.route('/cbm/submit_prescription_consumption', type='json', auth='user')
    def submit_prescription_consumption(self, picking_type_id, patient_id,
                                         prescription_lines, consumable_lines=None,
                                         sale_order_id=None, confirm_deletion=False):
        """
        Submit prescription consumption — combines prescribed drugs and nurse-added consumables.

        Validates qty caps on prescription lines, then delegates to submit_consumption
        for the actual stock movements.

        Args:
            picking_type_id: Operation type ID
            patient_id: Patient partner ID
            prescription_lines: List of {prescription_line_id, qty_applied} for drugs
            consumable_lines: List of {product_id, qty} for nurse-added non-drug items
            sale_order_id: Optional linked SO ID
            confirm_deletion: For return confirmation
        """
        PrescriptionLine = request.env['clinic.prescription.line'].sudo()

        if not patient_id:
            return {'success': False, 'error': _('Patient is required')}

        # --- Validate and build lines from prescription ---
        all_lines = []

        for pline_data in (prescription_lines or []):
            pline_id = pline_data.get('prescription_line_id')
            qty_to_apply = pline_data.get('qty_applied', 0)

            if not pline_id or qty_to_apply <= 0:
                continue

            pline = PrescriptionLine.browse(int(pline_id))
            if not pline.exists():
                return {'success': False, 'error': _('Prescription line not found: %s') % pline_id}

            # Validate cap: cannot exceed remaining prescribed qty
            qty_remaining = pline.qty_prescribed - pline.qty_applied
            if qty_to_apply > qty_remaining:
                return {
                    'success': False,
                    'error': _('Cannot apply %(qty)s for %(product)s — only %(remaining)s remaining from prescription') % {
                        'qty': qty_to_apply,
                        'product': pline.product_id.name,
                        'remaining': qty_remaining,
                    }
                }

            all_lines.append({
                'product_id': pline.product_id.id,
                'qty': qty_to_apply,
                'lot_id': pline_data.get('lot_id', False),
                'order_line_id': False,
                '_prescription_line_id': pline.id,  # Internal: for post-submit update
            })

        # --- Add nurse consumable lines ---
        for cline in (consumable_lines or []):
            if cline.get('qty', 0) <= 0:
                continue
            all_lines.append({
                'product_id': cline['product_id'],
                'qty': cline['qty'],
                'lot_id': cline.get('lot_id', False),
                'order_line_id': False,
            })

        if not all_lines:
            return {'success': False, 'error': _('No items to process')}

        # --- Debug: Log what we're sending ---
        import traceback
        _logger.info("[RX SUBMIT] user=%s, picking_type=%s, patient=%s, lines=%s",
                     request.env.user.name, picking_type_id, patient_id,
                     [{k: v for k, v in l.items() if k != '_prescription_line_id'} for l in all_lines])

        # --- Delegate to existing submit_consumption ---
        try:
            result = self.submit_consumption(
                picking_type_id=picking_type_id,
                patient_id=patient_id,
                lines=all_lines,
                sale_order_id=sale_order_id,
                confirm_deletion=confirm_deletion,
            )
        except Exception as e:
            _logger.error("[RX SUBMIT] FAILED for user=%s: %s\n%s",
                          request.env.user.name, str(e), traceback.format_exc())
            return {'success': False, 'error': str(e)}

        _logger.info("[RX SUBMIT] result=%s", result)

        # --- Post-submit: Update prescription line qty_applied ---
        if result.get('success'):
            # Build set of product_ids that were skipped due to insufficient stock
            skipped_product_ids = {s['product_id'] for s in result.get('skipped_products', []) if 'product_id' in s}
            for line_data in all_lines:
                pline_id = line_data.get('_prescription_line_id')
                if not pline_id:
                    continue
                # If product was skipped entirely, do not mark as applied
                if line_data['product_id'] in skipped_product_ids:
                    continue
                pline = PrescriptionLine.browse(pline_id)
                if pline.exists():
                    pline.mark_applied(line_data['qty'])

        return result

    # ========== Purchase Order Endpoints MOVED ==========
    # NOTE: All PO-related endpoints have been moved to
    # clinic_staff_portal/controllers/purchase.py for consolidation.
    # This includes:
    # - get_my_pos, get_po_details, get_purchase_taxes
    # - update_po_line, add_po_line, remove_po_line, update_po_vendor
    #
    # New routes use /cbm/purchase/* prefix instead of /cbm/*

