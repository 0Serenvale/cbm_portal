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

            # Find active sessions
            sessions = ClinicInventory.search([
                ('state', '=', 'active'),
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
                    _logger.info(
                        "[CBM INVENTORY] User %s found session %s, team %s",
                        user.name, session.name, team.name
                    )
                    return {
                        'found': True,
                        'session_id': session.id,
                        'session_name': session.name,
                        'location_id': session.location_id.id,
                        'location_name': session.location_id.name,
                        'team_id': team.id,
                        'team_name': team.name,
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

            # Search by name or barcode
            domain = [
                '|',
                ('name', 'ilike', query),
                ('barcode', 'ilike', query),
                ('active', '=', True),
            ]
            products = Product.search(domain, limit=limit)

            result = []
            for product in products:
                # Get total quantity across all locations (for reference)
                # Search is NOT location-restricted
                quants = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('lot_id', '=', False),
                ])
                qty_system = sum(q.quantity for q in quants)

                result.append({
                    'id': product.id,
                    'name': product.name,
                    'barcode': product.barcode or '',
                    'uom_name': product.uom_id.name if product.uom_id else 'U',
                    'qty_system': qty_system,
                })

            return result

        except Exception as e:
            _logger.error("[CBM INVENTORY] search_product error: %s", str(e))
            return []

@http.route('/cbm/inventory/search_lot', type='json', auth='user')
    def search_lot(self, lot_name, location_id, limit=10):
        """Search products by lot number.

        When multiple products have the same lot number (e.g., Sonde CH 10, 12, 14, 16),
        return all matching products so user can select the correct one.

        Args:
            lot_name: Lot number/name to search for
            location_id: stock.location ID (for reference qty only)
            limit: Max results (default 10)

        Returns:
            list: [{id, name, barcode, uom_name, qty_system, lot_id, lot_name}]
        """
        try:
            StockLot = request.env['stock.production.lot']
            StockQuant = request.env['stock.quant']
            Product = request.env['product.product']

            # Find all lots matching the lot_name
            lots = StockLot.search([
                ('name', '=', lot_name),
            ], limit=limit)

            if not lots:
                return []

            result = []
            for lot in lots:
                product = lot.product_id

                if not product.active:
                    continue

                # Get total quantity across all locations
                quants = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('lot_id', '=', False),
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
                    'expiry_date': str(lot.expiration_date) if lot.expiration_date else False,
                })

            return result

        except Exception as e:
            _logger.error("[CBM INVENTORY] search_lot error: %s", str(e))
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

            # Get only this team's lines
            lines = ClinicLine.search([
                ('inventory_id', '=', session.id),
                ('team_id', '=', team.id),
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

            # Prepare values
            vals = {
                'inventory_id': session.id,
                'team_id': team.id,
                'product_id': product_id,
                'lot_id': lot_id if lot_id else False,
                'expiry_date': expiry_date if expiry_date else False,
                'qty_counted': float(qty_counted),
                'note': note or '',
            }

            if line_id:
                # Update existing line (must belong to user's team)
                line = ClinicLine.browse(line_id)
                if not line.exists():
                    return {'success': False, 'error': _('Line not found')}
                if line.team_id.id != team.id:
                    return {'success': False, 'error': _('Cannot edit another team\'s line')}

                line.write(vals)
                _logger.info(
                    "[CBM INVENTORY] User %s updated line %s for team %s",
                    user.name, line.id, team.name
                )
                return {'success': True, 'line_id': line.id}
            else:
                # Create new line
                line = ClinicLine.create(vals)
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

            # Verify user belongs to the line's team
            if not line.team_id.user_ids.filtered(lambda u: u.id == user.id):
                return {'success': False, 'error': _('Cannot delete another team\'s line')}

            team_name = line.team_id.name
            line.unlink()

            _logger.info(
                "[CBM INVENTORY] User %s deleted line %s from team %s",
                user.name, line_id, team_name
            )

            return {'success': True}

        except Exception as e:
            _logger.error("[CBM INVENTORY] delete_line error: %s", str(e))
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
            ClinicTeam = request.env['clinic.inventory.team']

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
