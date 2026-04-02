# -*- coding: utf-8 -*-
"""
Inventory Controller for CBM Portal.

Provides staff and manager endpoints for physical inventory counting:
- Staff: count entry, product search, line management, per-team PDF
- Manager: session overview, reconciliation view, final PDF
"""
import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


def _lot_expiry_str(lot):
    """Safely extract expiry date from lot as YYYY-MM-DD string.

    lot.expiration_date is Datetime (if product_expiry is installed) or missing.
    Returns date string or False.
    """
    try:
        exp = getattr(lot, 'expiration_date', None)
        if exp:
            # Datetime → Date string
            return str(exp.date()) if hasattr(exp, 'date') else str(exp)[:10]
    except Exception:
        pass
    return False


class InventoryController(http.Controller):
    """Controller for inventory operations in CBM Portal."""

    # ========================================
    # STAFF ENDPOINTS
    # ========================================

    @http.route('/cbm/inventory/get_session', type='json', auth='user')
    def get_session(self):
        """Return active inventory session for current user.

        Searches for active clinic.inventory sessions where the current user
        is assigned to a team (user_ids many2many).

        Returns:
            dict: {
                found: bool,
                session_id: int (optional),
                session_name: str,
                location_id: int,
                location_name: str,
                team_id: int,
                team_name: str,
            } or {found: False}
        """
        try:
            user = request.env.user
            ClinicInventory = request.env['clinic.inventory']
            ClinicTeam = request.env['clinic.inventory.team']

            # Find active or pending sessions (staff sees status page if pending)
            sessions = ClinicInventory.search([
                ('state', 'in', ['active', 'pending_approval']),
            ])

            if not sessions:
                return {'found': False}

            # Check which team user belongs to
            for session in sessions:
                teams = ClinicTeam.search([
                    ('inventory_id', '=', session.id),
                    ('user_ids', 'in', user.id),
                ])

                if teams:
                    team = teams[0]
                    user_submitted = user in team.submitted_user_ids

                    # Count user's lines for summary (create_uid = who saved them)
                    ClinicLine = request.env['clinic.inventory.line']
                    user_lines = ClinicLine.search([
                        ('inventory_id', '=', session.id),
                        ('team_id', '=', team.id),
                        ('create_uid', '=', user.id),
                    ])
                    line_count = len(user_lines)
                    product_count = len(set(user_lines.mapped('product_id').ids))

                    _logger.info(
                        "[CBM INVENTORY] User %s found session %s, team %s (submitted=%s)",
                        user.name, session.name, team.name, user_submitted
                    )
                    return {
                        'found': True,
                        'session_id': session.id,
                        'session_name': session.name,
                        'session_state': session.state,
                        'location_id': session.location_id.id,
                        'location_name': session.location_id.name,
                        'team_id': team.id,
                        'team_name': team.name,
                        'user_submitted': user_submitted,
                        'line_count': line_count,
                        'product_count': product_count,
                    }

            _logger.info("[CBM INVENTORY] User %s not assigned to any active session", user.name)
            return {'found': False}

        except Exception as e:
            _logger.error("[CBM INVENTORY] get_session error: %s", str(e))
            return {'found': False}

    @http.route('/cbm/inventory/search_product', type='json', auth='user')
    def search_product(self, query, location_id, limit=10):
        """Search products by name or barcode.

        Returns matching products with system stock quantity at the given location.

        Args:
            query: Search string (name or barcode)
            location_id: stock.location ID to fetch quantities from
            limit: Max results (default 10)

        Returns:
            list: [{id, name, barcode, uom_name, qty_system}]
        """
        try:
            StockQuant = request.env['stock.quant']
            Product = request.env['product.product']

            # Search by name or barcode — explicit & wraps the | so active filter applies to both
            domain = [
                '&',
                '|',
                ('name', 'ilike', query),
                ('barcode', 'ilike', query),
                ('active', '=', True),
            ]
            products = Product.search(domain, limit=limit)

            result = []
            for product in products:
                # Get total quantity at the session location
                quants = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location_id),
                ])
                qty_system = sum(q.quantity for q in quants)

                result.append({
                    'id': product.id,
                    'name': product.name,
                    'barcode': product.barcode or '',
                    'uom_name': product.uom_id.name if product.uom_id else 'U',
                    'qty_system': qty_system,
                    'tracking': product.tracking,  # 'none', 'lot', 'serial'
                })

            return result

        except Exception as e:
            _logger.error("[CBM INVENTORY] search_product error: %s", str(e))
            return []

    @http.route('/cbm/inventory/search_lot', type='json', auth='user')
    def search_lot(self, lot_name, location_id, limit=10):
        """Search products by lot number (partial match).

        Returns all lots matching the search term with their product info.
        Multiple products can share the same lot number.

        Args:
            lot_name: Lot number/name to search for (partial match)
            location_id: stock.location ID (for reference qty only)
            limit: Max results (default 10)

        Returns:
            list: [{id, name, barcode, uom_name, qty_system, lot_id, lot_name, expiry_date, tracking}]
        """
        try:
            StockLot = request.env['stock.production.lot']
            StockQuant = request.env['stock.quant']

            # Find lots matching the lot_name (partial match for dropdown)
            lots = StockLot.search([
                ('name', 'ilike', lot_name),
            ], limit=limit)

            if not lots:
                return []

            result = []
            for lot in lots:
                product = lot.product_id

                if not product.active:
                    continue

                # Get quantity at the session location for this lot
                quants = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('lot_id', '=', lot.id),
                    ('location_id', '=', location_id),
                ])
                qty_system = sum(q.quantity for q in quants)

                result.append({
                    'id': product.id,
                    'name': product.name,
                    'barcode': product.barcode or '',
                    'uom_name': product.uom_id.name if product.uom_id else 'U',
                    'qty_system': qty_system,
                    'lot_id': lot.id,
                    'lot_name': lot.name,
                    'expiry_date': _lot_expiry_str(lot),
                    'tracking': product.tracking,
                })

            return result

        except Exception as e:
            _logger.error("[CBM INVENTORY] search_lot error: %s", str(e))
            return []

    @http.route('/cbm/inventory/get_product_lots', type='json', auth='user')
    def get_product_lots(self, product_id, location_id):
        """Return available lots for a product at a location.

        Used when a lot-tracked product is selected from the search dropdown.
        Staff picks which lot they are counting.

        Args:
            product_id: product.product ID
            location_id: stock.location ID

        Returns:
            list: [{lot_id, lot_name, expiry_date, qty_system}]
        """
        try:
            StockQuant = request.env['stock.quant']
            Product = request.env['product.product'].browse(product_id)

            if not Product.exists():
                return []

            # Get all lots registered for this product (regardless of stock level)
            # Staff may be counting product that has been consumed — show all known lots
            StockLot = request.env['stock.production.lot']
            lots = StockLot.search([
                ('product_id', '=', product_id),
            ], limit=50, order='name')

            # Build lot → qty mapping from quants at this location
            quants = StockQuant.search([
                ('product_id', '=', product_id),
                ('location_id', '=', location_id),
                ('lot_id', '!=', False),
            ])
            qty_by_lot = {}
            for quant in quants:
                qty_by_lot[quant.lot_id.id] = qty_by_lot.get(quant.lot_id.id, 0) + quant.quantity

            result = []
            for lot in lots:
                result.append({
                    'lot_id': lot.id,
                    'lot_name': lot.name,
                    'expiry_date': _lot_expiry_str(lot),
                    'qty_system': qty_by_lot.get(lot.id, 0),
                })

            # Also allow "No lot" option so staff can add product without lot
            # (for uncounted lots or new stock)
            result.append({
                'lot_id': False,
                'lot_name': _('(Sans lot / Nouveau)'),
                'expiry_date': False,
                'qty_system': 0,
            })

            return result

        except Exception as e:
            _logger.error("[CBM INVENTORY] get_product_lots error: %s", str(e))
            return []

    @http.route('/cbm/inventory/get_lines', type='json', auth='user')
    def get_lines(self, session_id):
        """Return only current user's team lines.

        Staff should NOT see other teams' lines or system quantities.

        Args:
            session_id: clinic.inventory ID

        Returns:
            list: [{id, product_id, product_name, barcode, lot_name, expiry_date, qty_counted, uom_name, note}]
        """
        try:
            user = request.env.user
            ClinicInventory = request.env['clinic.inventory']
            ClinicTeam = request.env['clinic.inventory.team']
            ClinicLine = request.env['clinic.inventory.line']

            # Verify session exists and user is assigned
            session = ClinicInventory.browse(session_id)
            if not session.exists():
                return []

            # Find user's team in this session
            team = ClinicTeam.search([
                ('inventory_id', '=', session.id),
                ('user_ids', 'in', user.id),
            ], limit=1)

            if not team:
                _logger.warning(
                    "[CBM INVENTORY] User %s not assigned to session %s",
                    user.name, session.name
                )
                return []

            # Get only this user's lines (create_uid = the user who saved them)
            lines = ClinicLine.search([
                ('inventory_id', '=', session.id),
                ('team_id', '=', team.id),
                ('create_uid', '=', user.id),
            ], order='product_id, lot_id')

            result = []
            for line in lines:
                result.append({
                    'id': line.id,
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.name,
                    'barcode': line.product_id.barcode or '',
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'lot_name': line.lot_id.name if line.lot_id else '',
                    'expiry_date': str(line.expiry_date) if line.expiry_date else False,
                    'qty_counted': line.qty_counted,
                    'uom_name': line.uom_id.name if line.uom_id else 'U',
                    'note': line.note or '',
                })

            _logger.debug(
                "[CBM INVENTORY] User %s loaded %d lines for team %s",
                user.name, len(result), team.name
            )

            return result

        except Exception as e:
            _logger.error("[CBM INVENTORY] get_lines error: %s", str(e))
            return []

    @http.route('/cbm/inventory/save_line', type='json', auth='user')
    def save_line(self, session_id, product_id, lot_id, expiry_date, qty_counted, note, line_id=False):
        """Create or update a single inventory line.

        Args:
            session_id: clinic.inventory ID
            product_id: product.product ID
            lot_id: stock.production.lot ID (optional)
            expiry_date: YYYY-MM-DD or False
            qty_counted: float
            note: str
            line_id: int (optional, for update)

        Returns:
            dict: {success: bool, line_id: int} or {success: False, error: str}
        """
        try:
            user = request.env.user
            ClinicInventory = request.env['clinic.inventory']
            ClinicTeam = request.env['clinic.inventory.team']
            ClinicLine = request.env['clinic.inventory.line']

            # Verify session exists and is active
            session = ClinicInventory.browse(session_id)
            if not session.exists() or session.state != 'active':
                return {'success': False, 'error': _('Session not active')}

            # Find user's team
            team = ClinicTeam.search([
                ('inventory_id', '=', session.id),
                ('user_ids', 'in', user.id),
            ], limit=1)

            if not team:
                return {'success': False, 'error': _('Not assigned to this session')}

            # Normalize expiry_date to YYYY-MM-DD (Date field can't accept datetime strings)
            expiry_date_val = False
            if expiry_date:
                expiry_date_val = str(expiry_date)[:10]  # trim time if datetime string

            # Reject save if user already submitted their count
            if user in team.submitted_user_ids:
                return {'success': False, 'error': _('You already submitted your count. Wait for manager review.')}

            # Prepare values
            vals = {
                'inventory_id': session.id,
                'team_id': team.id,
                'product_id': product_id,
                'lot_id': lot_id if lot_id else False,
                'expiry_date': expiry_date_val,
                'qty_counted': float(qty_counted),
                'note': note or '',
            }

            if line_id:
                # Update existing line (must belong to this team)
                line = ClinicLine.browse(line_id)
                if not line.exists():
                    return {'success': False, 'error': _('Line not found')}
                if line.team_id.id != team.id:
                    return {'success': False, 'error': _('Cannot edit another team\'s line')}

                # sudo(): portal user has perm_write=0, team ownership verified above
                line.sudo().write(vals)
                _logger.info(
                    "[CBM INVENTORY] User %s updated line %s for team %s",
                    user.name, line.id, team.name
                )
                return {'success': True, 'line_id': line.id}
            else:
                # Create new line (sudo: consistent with write path)
                line = ClinicLine.sudo().create(vals)
                _logger.info(
                    "[CBM INVENTORY] User %s created line %s for team %s",
                    user.name, line.id, team.name
                )
                return {'success': True, 'line_id': line.id}

        except Exception as e:
            _logger.error("[CBM INVENTORY] save_line error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route('/cbm/inventory/delete_line', type='json', auth='user')
    def delete_line(self, line_id):
        """Delete a line (must belong to user's team).

        Args:
            line_id: clinic.inventory.line ID

        Returns:
            dict: {success: bool} or {success: False, error: str}
        """
        try:
            user = request.env.user
            ClinicLine = request.env['clinic.inventory.line']

            line = ClinicLine.browse(line_id)
            if not line.exists():
                return {'success': False, 'error': _('Line not found')}

            # Verify user owns this line (create_uid)
            if line.create_uid.id != user.id:
                return {'success': False, 'error': _('Cannot delete another user\'s line')}

            # Reject delete if user already submitted
            if user in line.team_id.submitted_user_ids:
                return {'success': False, 'error': _('Cannot delete after submission')}

            team_name = line.team_id.name
            # sudo(): portal user has perm_unlink=0, ownership verified above
            line.sudo().unlink()

            _logger.info(
                "[CBM INVENTORY] User %s deleted line %s from team %s",
                user.name, line_id, team_name
            )

            return {'success': True}

        except Exception as e:
            _logger.error("[CBM INVENTORY] delete_line error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route(['/cbm/inventory/submit', '/cbm/inventory/submit_draft'], type='json', auth='user')
    def submit(self, session_id):
        """Submit current user's count for their team.

        Per-user submission: adds user to team.submitted_user_ids.
        If all users in all teams have submitted, session auto-transitions
        to pending_approval with system qty refreshed.

        Args:
            session_id: clinic.inventory ID

        Returns:
            dict: {success, all_submitted} or {success: False, error: str}
        """
        try:
            user = request.env.user
            ClinicInventory = request.env['clinic.inventory']
            ClinicTeam = request.env['clinic.inventory.team']
            ClinicLine = request.env['clinic.inventory.line']

            session = ClinicInventory.browse(session_id)
            if not session.exists():
                return {'success': False, 'error': _('Session not found')}

            team = ClinicTeam.search([
                ('inventory_id', '=', session.id),
                ('user_ids', 'in', user.id),
            ], limit=1)

            if not team:
                return {'success': False, 'error': _('Access denied')}

            if session.state != 'active':
                return {'success': False, 'error': _('Session is not active')}

            # Check user already submitted — return current session state
            if user in team.submitted_user_ids:
                return {'success': True, 'all_submitted': session.state == 'pending_approval'}

            # Verify user has lines (create_uid = who saved them)
            user_lines = ClinicLine.search([
                ('inventory_id', '=', session.id),
                ('team_id', '=', team.id),
                ('create_uid', '=', user.id),
            ], limit=1)
            if not user_lines:
                return {'success': False, 'error': _('Cannot submit without counted lines')}

            # Per-user submit — may auto-complete session
            # sudo(): writes to team.submitted_user_ids and session.state
            all_submitted = session.sudo().action_user_submit(user, team)

            _logger.info(
                "[CBM INVENTORY] User %s submitted count (all_done=%s)",
                user.name, all_submitted
            )

            return {'success': True, 'all_submitted': all_submitted}

        except ValueError as e:
            _logger.error("[CBM INVENTORY] submit validation error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}
        except Exception as e:
            _logger.error("[CBM INVENTORY] submit error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route('/cbm/inventory/recount', type='json', auth='user')
    def recount(self, session_id):
        """Clear all counted lines and restart inventory from scratch.

        Keeps session in 'active' state for re-counting.
        Deletes all existing lines for this session's team.

        Args:
            session_id: clinic.inventory ID

        Returns:
            dict: {success: bool} or {success: False, error: str}
        """
        try:
            user = request.env.user
            ClinicInventory = request.env['clinic.inventory']
            ClinicTeam = request.env['clinic.inventory.team']
            ClinicLine = request.env['clinic.inventory.line']

            # Verify session exists
            session = ClinicInventory.browse(session_id)
            if not session.exists():
                return {'success': False, 'error': _('Session not found')}

            # Verify user is assigned to this session's team
            team = ClinicTeam.search([
                ('inventory_id', '=', session.id),
                ('user_ids', 'in', user.id),
            ], limit=1)

            if not team:
                return {'success': False, 'error': _('Access denied')}

            # Verify session is active (can't recount if already submitted)
            if session.state != 'active':
                return {'success': False, 'error': _('Cannot recount a submitted session')}

            # Reject recount if user already submitted
            if user in team.submitted_user_ids:
                return {'success': False, 'error': _('Cannot recount after submission')}

            # Delete only this user's lines (create_uid scoping)
            lines_to_delete = ClinicLine.search([
                ('inventory_id', '=', session.id),
                ('team_id', '=', team.id),
                ('create_uid', '=', user.id),
            ])

            deleted_count = len(lines_to_delete)
            # sudo(): portal user has perm_unlink=0, ownership verified by user_id filter
            lines_to_delete.sudo().unlink()

            _logger.info(
                "[CBM INVENTORY] User %s restarted counting for session %s (deleted %d lines)",
                user.name, session.name, deleted_count
            )

            return {'success': True}

        except ValueError as e:
            _logger.error("[CBM INVENTORY] recount validation error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}
        except Exception as e:
            _logger.error("[CBM INVENTORY] recount error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route('/cbm/inventory/team_pdf/<int:session_id>', type='http', auth='user')
    def team_pdf(self, session_id, **kwargs):
        """Generate per-team PDF for current user's team.

        Access: User must be assigned to the session's team.

        Args:
            session_id: clinic.inventory ID

        Returns:
            PDF file or 403 Forbidden
        """
        try:
            user = request.env.user
            ClinicInventory = request.env['clinic.inventory']
            ClinicTeam = request.env['clinic.inventory.team']

            # Verify session exists
            session = ClinicInventory.browse(session_id)
            if not session.exists():
                return request.make_response(
                    "Session not found.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=404
                )

            # Find user's team
            team = ClinicTeam.search([
                ('inventory_id', '=', session.id),
                ('user_ids', 'in', user.id),
            ], limit=1)

            if not team:
                return request.make_response(
                    "Access denied.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=403
                )

            # Render team PDF
            report = request.env.ref(
                'clinic_staff_portal.action_report_inventory_team'
            ).sudo()
            pdf_content, _ = report._render_qweb_pdf(
                report.report_name, [session.id]
            )

            filename = 'Inventory_Team_%s.pdf' % team.name.replace('/', '_')
            _logger.info(
                "[CBM INVENTORY] Generated team PDF for session %s, team %s, user %s",
                session.id, team.name, user.name
            )

            return request.make_response(
                pdf_content,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', 'attachment; filename="%s"' % filename),
                    ('Content-Length', len(pdf_content)),
                ]
            )

        except Exception as e:
            _logger.error("[CBM INVENTORY] team_pdf error: %s", str(e))
            return request.make_response(
                "Error generating PDF.",
                headers=[('Content-Type', 'text/plain; charset=utf-8')]
            )

    # ========================================
    # CONFIGURATION ENDPOINTS
    # ========================================

    @http.route('/cbm/inventory/config', type='json', auth='user')
    def get_inventory_config(self):
        """Get active/draft inventory session for banner display.

        Available to ALL authenticated users (banner is for all staff).
        Looks for sessions in draft or active state with a future or current date range.
        Banner shows 7 days before start and stays until end date passes.

        Returns:
            dict with session data, or {} if nothing upcoming
        """
        try:
            ClinicInventory = request.env['clinic.inventory'].sudo()

            # Find the next upcoming or currently active session
            session = ClinicInventory.search([
                ('state', 'in', ['draft', 'active']),
            ], order='date asc', limit=1)

            if not session:
                return {}

            return {
                'id': session.id,
                'name': session.name,
                'inventory_start_date': str(session.date),
                'inventory_end_date': str(session.end_date) if session.end_date else str(session.date),
                'duration_days': session.duration_days,
                'generated_announcement': session.generated_announcement or '',
                'state': session.state,
            }

        except Exception as e:
            _logger.error("[CBM INVENTORY] get_inventory_config error: %s", str(e))
            return {}

    # ========================================
    # MANAGER ENDPOINTS
    # ========================================

    def _check_inventory_manager_access(self, user, ICP):
        """Verify user is an admin/manager for inventory.

        Returns:
            bool: True if user is in admin_user_ids or is system admin
        """
        admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
        admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
        is_admin = user.id in admin_ids

        is_system_admin = user.has_group('base.group_system')

        return is_admin or is_system_admin

    @http.route('/cbm/inventory/get_all_sessions', type='json', auth='user')
    def get_all_sessions(self):
        """Return all inventory sessions (all states). Manager only.

        Returns:
            dict: {success: bool, sessions: []} or {success: False, error: str}
        """
        try:
            user = request.env.user
            ICP = request.env['ir.config_parameter'].sudo()

            if not self._check_inventory_manager_access(user, ICP):
                return {'success': False, 'error': _('Access denied')}

            ClinicInventory = request.env['clinic.inventory']
            sessions = ClinicInventory.search([], order='date desc')

            result = []
            for session in sessions:
                result.append({
                    'id': session.id,
                    'name': session.name,
                    'date': str(session.date),
                    'location_id': session.location_id.id,
                    'location_name': session.location_id.name,
                    'state': session.state,
                    'state_display': dict(session._fields['state'].selection).get(session.state, session.state),
                    'team_count': session.team_count,
                    'line_count': session.line_count,
                    'responsible_id': session.responsible_id.id,
                    'responsible_name': session.responsible_id.name,
                })

            _logger.info("[CBM INVENTORY] Manager %s loaded %d sessions", user.name, len(result))
            return {'success': True, 'sessions': result}

        except Exception as e:
            _logger.error("[CBM INVENTORY] get_all_sessions error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route('/cbm/inventory/get_session_stats', type='json', auth='user')
    def get_session_stats(self, session_id):
        """Return reconciliation view for a session. Manager only.

        Args:
            session_id: clinic.inventory ID

        Returns:
            dict: {
                success: bool,
                session: {id, name, location_name, state, date},
                teams: [{
                    team_id,
                    team_name,
                    lines: [{
                        product_id,
                        product_name,
                        lot_name,
                        expiry_date,
                        qty_counted,
                        qty_system,
                        variance,
                        uom_name,
                    }]
                }]
            }
        """
        try:
            user = request.env.user
            ICP = request.env['ir.config_parameter'].sudo()

            if not self._check_inventory_manager_access(user, ICP):
                return {'success': False, 'error': _('Access denied')}

            ClinicInventory = request.env['clinic.inventory']

            session = ClinicInventory.browse(session_id)
            if not session.exists():
                return {'success': False, 'error': _('Session not found')}

            # Build response with all teams and their lines
            teams_data = []
            for team in session.team_ids:
                lines_data = []
                for line in team.inventory_id.line_ids.filtered(lambda l: l.team_id.id == team.id):
                    lines_data.append({
                        'id': line.id,
                        'product_id': line.product_id.id,
                        'product_name': line.product_id.name,
                        'lot_id': line.lot_id.id if line.lot_id else False,
                        'lot_name': line.lot_id.name if line.lot_id else '',
                        'expiry_date': str(line.expiry_date) if line.expiry_date else False,
                        'qty_counted': line.qty_counted,
                        'qty_system': line.qty_system,
                        'variance': line.variance,
                        'uom_name': line.uom_id.name if line.uom_id else 'U',
                    })

                teams_data.append({
                    'team_id': team.id,
                    'team_name': team.name,
                    'lines': lines_data,
                })

            _logger.info(
                "[CBM INVENTORY] Manager %s loaded stats for session %s with %d teams",
                user.name, session.name, len(teams_data)
            )

            return {
                'success': True,
                'session': {
                    'id': session.id,
                    'name': session.name,
                    'location_id': session.location_id.id,
                    'location_name': session.location_id.name,
                    'state': session.state,
                    'date': str(session.date),
                },
                'teams': teams_data,
            }

        except Exception as e:
            _logger.error("[CBM INVENTORY] get_session_stats error: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route('/cbm/inventory/final_pdf/<int:session_id>', type='http', auth='user')
    def final_pdf(self, session_id, **kwargs):
        """Generate combined reconciliation PDF. Manager only.

        Columns: Product | Lot | Expiry | Team A | Team B | ... | System Qty | Variance

        Args:
            session_id: clinic.inventory ID

        Returns:
            PDF file or 403 Forbidden
        """
        try:
            user = request.env.user
            ICP = request.env['ir.config_parameter'].sudo()

            if not self._check_inventory_manager_access(user, ICP):
                return request.make_response(
                    "Access denied.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=403
                )

            ClinicInventory = request.env['clinic.inventory']
            session = ClinicInventory.browse(session_id)

            if not session.exists():
                return request.make_response(
                    "Session not found.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=404
                )

            # Render final PDF
            report = request.env.ref(
                'clinic_staff_portal.action_report_inventory_final'
            ).sudo()
            pdf_content, _ = report._render_qweb_pdf(
                report.report_name, [session.id]
            )

            filename = 'Inventory_Final_%s.pdf' % session.name.replace('/', '_')
            _logger.info(
                "[CBM INVENTORY] Generated final PDF for session %s by manager %s",
                session.id, user.name
            )

            return request.make_response(
                pdf_content,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', 'attachment; filename="%s"' % filename),
                    ('Content-Length', len(pdf_content)),
                ]
            )

        except Exception as e:
            _logger.error("[CBM INVENTORY] final_pdf error: %s", str(e))
            return request.make_response(
                "Error generating PDF.",
                headers=[('Content-Type', 'text/plain; charset=utf-8')]
            )
