# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import datetime, time
import logging

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = 'stock.move'

    # Field to show trusted balance at destination ward
    ward_qty_trusted = fields.Float(
        string="Recent Stock",
        readonly=True,
        store=False,
        copy=False,
        help="Quantity at destination location based on movements since the 'Trust Date'")
    
    # Nurse-friendly status labels
    hoarding_status = fields.Selection([
        ('ok', ''),  # Empty when OK - no badge shown
        ('warning', 'Has Stock'),  # Soft reminder
        ('blocked', 'Check Stock!')  # Stronger reminder
    ], string="Note", default='ok', store=False, copy=False)

    @api.onchange('product_id', 'product_uom_qty')
    def _check_hoarding_logic(self):
        """
        Enterprise-grade SQL logic to calculate 'Trusted Stock' using read_group.
        Prevents hoarding by checking recent inventory at destination ward.
        """
        # Always initialize fields
        self.ward_qty_trusted = 0.0
        self.hoarding_status = 'ok'
        
        # 1. Basic Guards
        if not self.product_id:
            return

        # Get destination location from picking OR from move itself
        picking = self.picking_id
        ward = False
        
        if picking and picking.location_dest_id:
            ward = picking.location_dest_id
        elif self.location_dest_id:
            ward = self.location_dest_id
            
        if not ward:
            return

        # 2. Check if policy is active on the ward
        if not hasattr(ward, 'replenishment_policy'):
            return
        if ward.replenishment_policy == 'none':
            return
        if not ward.consumption_start_date:
            return

        # 3. Prepare date filter (convert Date to Datetime for comparison)
        start_date = ward.consumption_start_date
        start_datetime = datetime.combine(start_date, time.min)
        
        product_id = self.product_id.id
        ward_id = ward.id

        # 4. SQL QUERY: INCOMING (Credits) - What entered the ward
        # Includes pending requests to prevent multi-tab exploit
        domain_in = [
            ('location_dest_id', '=', ward_id),
            ('product_id', '=', product_id),
            ('date', '>=', start_datetime),
            ('state', 'in', ['done', 'assigned', 'confirmed', 'partially_available']),
        ]
        # Exclude current move if it has an ID
        if self._origin.id:
            domain_in.append(('id', '!=', self._origin.id))

        in_data = self.env['stock.move'].read_group(
            domain_in, 
            ['product_uom_qty:sum'], 
            ['product_id']
        )
        qty_in = in_data[0]['product_uom_qty'] if in_data else 0.0

        # 5. SQL QUERY: OUTGOING (Debits) - What left the ward (consumed)
        domain_out = [
            ('location_id', '=', ward_id),
            ('product_id', '=', product_id),
            ('date', '>=', start_datetime),
            ('state', '=', 'done'),  # Only count completed consumption
        ]

        out_data = self.env['stock.move'].read_group(
            domain_out, 
            ['product_uom_qty:sum'], 
            ['product_id']
        )
        qty_out = out_data[0]['product_uom_qty'] if out_data else 0.0

        # 6. Calculate trusted balance
        trusted_balance = max(0, qty_in - qty_out)
        self.ward_qty_trusted = trusted_balance

        # 7. Apply policy (visual feedback only - no popups)
        if trusted_balance > 0:
            if ward.replenishment_policy == 'hard':
                self.hoarding_status = 'blocked'
                # Don't reset qty - let the UI show warning and user decide
            elif ward.replenishment_policy == 'soft':
                self.hoarding_status = 'warning'
        # Status 'ok' is already set at the start

        else:
            self.hoarding_status = 'ok'

    # --- KIOSK UI BUTTONS ---
    def action_kiosk_increment(self):
        """Add 1 to quantity (for +/- button in kiosk mode)"""
        for move in self:
            move.product_uom_qty += 1
        return True

    def action_kiosk_decrement(self):
        """Subtract 1 from quantity (for +/- button in kiosk mode)"""
        for move in self:
            if move.product_uom_qty > 1:
                move.product_uom_qty -= 1
            else:
                # If qty is 1 and they click minus, remove the line
                move.unlink()
        return True

    # --- BACKEND DISCREPANCY DETECTION ---
    def _action_assign(self, force_qty=False):
        """Override to detect stock discrepancies before reservation (earlier than _action_done)."""
        # Check for insufficient stock BEFORE Odoo tries to reserve/validate
        for move in self:
            if move.state == 'confirmed' and move.product_id.type == 'product' and move.location_id.usage == 'internal':
                # Get available stock at source location
                product_ctx = move.product_id.with_context(location=move.location_id.id)
                available = product_ctx.qty_available

                # If insufficient stock, create discrepancy alert (only once)
                if move.product_uom_qty > available:
                    # Only create alert if picking has patient context (consumption-like)
                    if move.picking_id and move.picking_id.partner_id:
                        # Check if alert already exists for this exact scenario to prevent duplicates
                        existing_alert = self.env['clinic.stock.discrepancy'].search([
                            ('product_id', '=', move.product_id.id),
                            ('location_id', '=', move.location_id.id),
                            ('picking_type_id', '=', move.picking_type_id.id),
                            ('state', '=', 'pending'),
                        ], limit=1)

                        if not existing_alert:
                            try:
                                move.picking_id._create_stock_discrepancy_alert(
                                    move.product_id,
                                    move.product_uom_qty,
                                    available
                                )
                            except Exception as e:
                                # Don't block reservation if alert creation fails
                                _logger.warning(f"Failed to create discrepancy alert: {e}")

        return super()._action_assign(force_qty=force_qty)

    def action_report_discrepancy(self):
        """Manual action to report stock discrepancy from backend UI."""
        self.ensure_one()

        if self.product_id.type != 'product':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Not Applicable'),
                    'message': _('Discrepancies can only be reported for storable products.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        # Get current stock at source location
        product_ctx = self.product_id.with_context(location=self.location_id.id)
        available = product_ctx.qty_available

        # Create discrepancy alert via picking method if available
        if self.picking_id and hasattr(self.picking_id, '_create_stock_discrepancy_alert'):
            alert = self.picking_id._create_stock_discrepancy_alert(
                self.product_id,
                self.product_uom_qty,
                available
            )
        else:
            # Fallback: create alert directly
            Discrepancy = self.env['clinic.stock.discrepancy'].sudo()
            alert = Discrepancy.create({
                'user_id': self.env.user.id,
                'patient_id': self.picking_id.partner_id.id if self.picking_id and self.picking_id.partner_id else False,
                'product_id': self.product_id.id,
                'attempted_qty': self.product_uom_qty,
                'system_qty': available,
                'location_id': self.location_id.id,
                'picking_type_id': self.picking_type_id.id if self.picking_type_id else False,
            })

            # Notify managers
            manager_group = self.env.ref('clinic_staff_portal.group_clinic_portal_manager', raise_if_not_found=False)
            if manager_group:
                for user in manager_group.users.filtered(lambda u: u.active):
                    alert.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        note=_('Stock discrepancy reported: %(user)s reported mismatch for %(prod)s at %(loc)s (Requested: %(qty)s, Available: %(avail)s)') % {
                            'user': self.env.user.name,
                            'prod': self.product_id.name,
                            'loc': self.location_id.name,
                            'qty': self.product_uom_qty,
                            'avail': available,
                        }
                    )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Discrepancy Reported'),
                'message': _('Discrepancy alert %s created successfully.') % alert.name,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'clinic.stock.discrepancy',
                    'res_id': alert.id,
                    'view_mode': 'form',
                    'views': [[False, 'form']],
                }
            }
        }

