# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # --- Portal Request Fields ---
    is_portal_request = fields.Boolean(
        string='Portal Request',
        default=False,
        help='Indicates this picking was created via the Clinic Portal')
    portal_requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        help='The portal user who created this request')
    patient_id = fields.Many2one(
        'res.partner',
        string='Patient',
        domain="[('customer_rank', '>', 0)]",
        help='Required for consumption - auto-generates quotation on validation')
    portal_behavior = fields.Selection([
        ('request', 'Request'),
        ('billable', 'Patient Billing'),
        ('surgery', 'Surgery Kiosk'),
        ('internal', 'Internal Use'),
        ('return', 'Return'),
    ], string='Portal Behavior', help='How this request was created')

    barcode_input = fields.Char(
        string='Barcode',
        help='Scan barcode to add product. Clears after processing.')

    # FIX Issue #2: Link consumption to specific SO to prevent jumping between multiple SOs
    linked_sale_order_id = fields.Many2one(
        'sale.order',
        string='Linked Sale Order',
        help='Specific SO this consumption is linked to (prevents jumping between multiple draft SOs)')

    # FIX Issue #1: Flag for partial consumption (some items skipped due to stock)
    is_partial_consumption = fields.Boolean(
        string='Partial Consumption',
        default=False,
        help='Indicates some items were skipped due to insufficient stock')

    # Note: Approval workflow fields (approval_state, approval_required, approver_ids, etc.)
    # are defined in serenvale_stock_access_control module (our dependency)

    @api.model_create_multi
    def create(self, vals_list):
        """Override to enforce pending transfer block threshold at model level.

        This ensures users cannot bypass CBM portal blocking by creating
        pickings directly in the Odoo backend.

        Uses PER-OPERATION-TYPE thresholds from stock.picking.type model.
        """
        user = self.env.user

        # Check enforcement - reuse CBM portal config
        ICP = self.env['ir.config_parameter'].sudo()
        enforcement_enabled = ICP.get_param(
            'clinic_staff_portal.pending_enforcement_enabled', 'False'
        ).lower() == 'true'

        if enforcement_enabled:
            # Check admin exemption (same as CBM portal)
            admin_ids_str = ICP.get_param('clinic_staff_portal.admin_user_ids', '')
            admin_ids = [int(i) for i in admin_ids_str.split(',') if i.strip().isdigit()]
            is_admin = user.id in admin_ids or user.has_group('base.group_system')

            if not is_admin:
                Picking = self.env['stock.picking'].sudo()
                PickingType = self.env['stock.picking.type'].sudo()

                # Check each picking being created
                for vals in vals_list:
                    picking_type_id = vals.get('picking_type_id')
                    if not picking_type_id:
                        continue

                    picking_type = PickingType.browse(picking_type_id)
                    if not picking_type.exists():
                        continue

                    block_threshold = picking_type.pending_block_threshold or 0
                    if block_threshold <= 0:
                        continue  # No blocking for this operation type

                    # Count pending transfers for THIS operation type created by this user
                    pending_count = Picking.search_count([
                        ('picking_type_id', '=', picking_type_id),
                        '|',
                        ('portal_requester_id', '=', user.id),
                        ('create_uid', '=', user.id),
                        ('state', 'not in', ['done', 'cancel']),
                    ])

                    if pending_count >= block_threshold:
                        _logger.warning(
                            "[CBM BLOCK] User %s blocked from creating picking for op type '%s': "
                            "pending=%d >= threshold=%d",
                            user.name, picking_type.name, pending_count, block_threshold
                        )

                        # Get responsible names from the operation type's source location
                        responsible_names = set()
                        if picking_type.default_location_src_id:
                            for resp in picking_type.default_location_src_id.responsible_user_ids:
                                if resp.id != user.id:
                                    responsible_names.add(resp.name)

                        if not responsible_names:
                            responsible_names = {'votre responsable'}

                        raise UserError(_(
                            "Transferts en attente\n\n"
                            "Vous avez %(count)d demande(s) en attente pour '%(op_type)s'.\n\n"
                            "La création de nouvelles demandes est temporairement bloquée "
                            "conformément aux règles de gestion des stocks.\n\n"
                            "Merci de contacter %(responsibles)s pour le traitement.\n\n"
                            "Seuil : %(threshold)d"
                        ) % {
                            'count': pending_count,
                            'op_type': picking_type.name,
                            'responsibles': ', '.join(sorted(responsible_names)),
                            'threshold': block_threshold,
                        })

        return super().create(vals_list)

    def _post_discrepancy_warning_to_log(self):
        """Post discrepancy warning as a message in the chatter/log if stock is insufficient."""
        self.ensure_one()
        warnings = []

        for move in self.move_ids_without_package:
            if move.product_id.type == 'product' and move.location_id.usage == 'internal':
                product_ctx = move.product_id.with_context(location=move.location_id.id)
                available = product_ctx.qty_available

                if move.product_uom_qty > available:
                    warnings.append(
                        f"<li><b>{move.product_id.display_name}</b>: "
                        f"Requested {move.product_uom_qty}, Available {available}</li>"
                    )

        if warnings:
            # Check if similar warning already posted today to avoid duplicates
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0)
            existing_warning = self.message_ids.filtered(
                lambda m: m.create_date >= today_start and 'Insufficient Stock Detected' in (m.body or '')
            )

            if not existing_warning:
                message = (
                    '<b>Insufficient Stock Detected</b><br/>'
                    '<ul>' + ''.join(warnings) + '</ul>'
                    '<p><i>Suggestions:</i></p>'
                    '<ul>'
                    '<li>Unreserve stock and reduce requested quantities</li>'
                    '<li>Check if Purchase Order reception is pending</li>'
                    '<li>Verify stock in other locations</li>'
                    '</ul>'
                )
                self.message_post(
                    body=message,
                    subject='Subject: Stock Warning',
                    message_type='notification',
                    subtype_xmlid='mail.mt_note'
                )


    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        """
        Handle barcode scan input.
        Searches by: product barcode, lot ref, product name (fallback).
        Auto-adds or increments quantity if already in list.
        """
        if not self.barcode_input:
            return
        
        barcode = self.barcode_input.strip()
        self.barcode_input = False  # Clear field after processing
        
        if not barcode:
            return
        
        # Search priority: 1) Product barcode, 2) Lot ref, 3) Product name
        product = None
        lot = None
        
        # 1. Search by product barcode
        product = self.env['product.product'].search([
            ('barcode', '=', barcode)
        ], limit=1)
        
        # 2. Search by lot reference
        if not product:
            lot = self.env['stock.lot'].search([
                ('ref', 'ilike', barcode)
            ], limit=1)
            if lot:
                product = lot.product_id
        
        # 3. Fallback: search by product name (case insensitive)
        if not product:
            product = self.env['product.product'].search([
                '|',
                ('default_code', 'ilike', barcode),
                ('name', 'ilike', barcode),
            ], limit=1)
        
        if not product:
            return {
                'warning': {
                    'title': _('Product Not Found'),
                    'message': _("No product found for barcode: %s") % barcode,
                }
            }
        
        # Check if product already in lines - increment qty
        for move in self.move_ids_without_package:
            if move.product_id.id == product.id:
                move.product_uom_qty += 1
                return
        
        # Add new line
        new_move = self.env['stock.move'].new({
            'product_id': product.id,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
            'name': product.name,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'picking_id': self.id,
        })
        self.move_ids_without_package = self.move_ids_without_package | new_move

    @api.model
    def default_get(self, fields_list):
        """
        Smart location detection using TILE's picking_type_id.
        
        Architecture:
        - Tile defines Operation Type → Operation Type defines Source Location
        - User's ward = Destination of an operation type matching tile's source
        - No dependency on global pharmacy setting for source determination
        """
        res = super().default_get(fields_list)

        if self.env.context.get('portal_mode'):
            user = self.env.user
            behavior = self.env.context.get('portal_stock_behavior') or 'request'
            is_admin = user.has_group('base.group_system')
            
            # Get Patient location from settings (only needed for consumption destination)
            IrConfig = self.env['ir.config_parameter'].sudo()
            patient_loc_id = int(IrConfig.get_param('clinic_staff_portal.patient_location_id', 0) or 0)
            patient_location = self.env['stock.location'].browse(patient_loc_id).exists() if patient_loc_id else False
            
            # Get pharmacy location from settings (for request/return)
            pharmacy_loc_id = int(IrConfig.get_param('clinic_staff_portal.pharmacy_location_id', 0) or 0)
            pharmacy_location = self.env['stock.location'].browse(pharmacy_loc_id).exists() if pharmacy_loc_id else False
            
            # Get magasin location from settings (for magasin consumption)
            magasin_loc_id = int(IrConfig.get_param('clinic_staff_portal.magasin_location_id', 0) or 0)
            magasin_location = self.env['stock.location'].browse(magasin_loc_id).exists() if magasin_loc_id else False
            
            # Get user's allowed operation types
            user_op_types = False
            if hasattr(user, 'allowed_operation_types') and user.allowed_operation_types:
                user_op_types = user.allowed_operation_types
            
            # Non-admin without access control = blocked
            if not is_admin and not user_op_types:
                raise UserError(_(
                    "Access Control Error\n\n"
                    "Your account has no 'Allowed Operation Types' configured.\n"
                    "Please contact your Administrator."
                ))
            
            # Find user's ward (destination from their pharmacy request op type)
            user_ward = False
            if user_op_types and pharmacy_location:
                pharmacy_op = user_op_types.filtered(
                    lambda op: op.default_location_src_id.id == pharmacy_location.id
                )
                if pharmacy_op:
                    user_ward = pharmacy_op[0].default_location_dest_id
            
            # Find appropriate picking type for this behavior
            picking_type = False
            
            if behavior == 'request':
                # Request: FROM Pharmacy TO User's Ward
                source_loc = pharmacy_location
                dest_loc = user_ward
                # Find matching op type
                if user_op_types and pharmacy_location and user_ward:
                    picking_type = user_op_types.filtered(
                        lambda op: op.default_location_src_id.id == pharmacy_location.id
                                   and op.default_location_dest_id.id == user_ward.id
                    )
                    picking_type = picking_type[0] if picking_type else False
                    
            elif behavior in ['billable', 'surgery']:
                # Pharmacy Consumption: FROM User's Ward TO Patient
                source_loc = user_ward
                dest_loc = patient_location or self.env['stock.location'].search([('usage', '=', 'customer')], limit=1)
                
            elif behavior == 'internal':
                # Magasin/Internal Consumption: Use magasin if available, else ward
                source_loc = magasin_location or user_ward
                dest_loc = patient_location or self.env['stock.location'].search([('usage', '=', 'customer')], limit=1)
                
            elif behavior == 'return':
                # Return: FROM User's Ward TO Pharmacy
                source_loc = user_ward
                dest_loc = pharmacy_location
            
            # Non-admin without source = blocked
            if not is_admin and not source_loc:
                raise UserError(_(
                    "Configuration Error\n\n"
                    "Cannot determine source location for this operation.\n"
                    "Please ensure your access control is configured properly."
                ))
            
            res['location_id'] = source_loc.id if source_loc else False
            res['location_dest_id'] = dest_loc.id if dest_loc else False
            res['picking_type_id'] = picking_type.id if picking_type else False
            res['is_portal_request'] = True
            res['portal_requester_id'] = user.id
            res['portal_behavior'] = behavior

        return res

    def action_portal_submit(self):
        """
        GATEKEEPER: Validation + Wizard Launch for Consumption
        For Request/Internal/Return: Direct submit
        For Billable/Surgery: Validate then show confirmation wizard
        """
        self.ensure_one()
        behavior = self.portal_behavior

        # --- COMMON VALIDATION ---
        
        # Check: Empty Lines
        if not self.move_ids_without_package:
            return self._notify_error(
                _('No Products'),
                _('Please add at least one product before submitting.'))

        # Check: Locations are set
        if not self.location_id or not self.location_dest_id:
            return self._notify_error(
                _('Setup Required'),
                _('Your account needs configuration. Please contact your supervisor.'))

        # --- ROUTE BASED ON BEHAVIOR ---
        
        if behavior in ['billable', 'surgery']:
            # CONSUMPTION ENGINE
            
            # Check: Patient required for billing
            if not self.partner_id:
                return self._notify_error(
                    _('Patient Required'),
                    _('Please select a patient before submitting.'))
            
            # Check: Stock Availability (consumption only)
            for move in self.move_ids_without_package:
                if move.product_id.type == 'product':
                    available = move.product_id.with_context(location=self.location_id.id).free_qty
                    if move.product_uom_qty > available:
                        return self._notify_error(
                            _('Insufficient Stock'),
                            _("You want %(qty)s of '%(prod)s', but only %(avail)s available.") % {
                                'qty': move.product_uom_qty,
                                'prod': move.product_id.name,
                                'avail': available,
                            })
            
            # Launch confirmation wizard
            return {
                'name': _('Confirm Consumption'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.consumption.confirm',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_picking_id': self.id}
            }
        else:
            # REQUEST ENGINE (request/internal/return): Direct submit
            return self._execute_request_submit()

    def _notify_error(self, title, message):
        """Return a soft notification instead of UserError"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'warning',
                'sticky': True,
            }
        }

    def _execute_request_submit(self):
        """Execute submit for Request/Internal/Return behaviors"""
        self.ensure_one()
        
        # Confirm the picking
        self.action_confirm()

        # Notify stock managers
        self._notify_managers()

        # Return to dashboard with success message
        return self._return_to_dashboard(_('Request Submitted Successfully!'))

    def _execute_consumption_submit(self):
        """
        Execute consumption: Confirm stock + Append to Sale Order
        Called from the confirmation wizard OR RPC controller.
        
        SAFETY FEATURES:
        1. Double-click guard: Check picking state
        2. Race condition: Re-check stock availability
        3. Atomic transaction: Try/except with rollback
        4. Scoped sudo: Only for SO creation
        
        Raises UserError on validation failures so controller can catch them.
        """
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("*** _execute_consumption_submit START for %s (state=%s, partner=%s)", 
                     self.name, self.state, self.partner_id.name if self.partner_id else 'NONE')
        
        # --- SAFETY #1: Double-click guard ---
        if self.state not in ['draft', 'waiting', 'confirmed']:
            raise UserError(_('This consumption has already been submitted.'))
        
        # --- SAFETY #2: Filter out OOS moves instead of blocking ---
        # Only available moves will be consumed and added to Sale Order
        moves_to_process = self.env['stock.move']
        moves_to_skip = self.env['stock.move']
        
        for move in self.move_ids_without_package:
            if move.product_id.type != 'product':
                # Non-stockable always pass
                moves_to_process += move
                continue
            
            product_ctx = move.product_id.with_context(location=self.location_id.id)
            available = product_ctx.free_qty  # Use free_qty (on_hand - reserved), not qty_available
            _logger.info("Stock check: %s - need %.2f, free_qty=%.2f (on_hand=%.2f) at %s",
                         move.product_id.name, move.product_uom_qty, available,
                         product_ctx.qty_available, self.location_id.name)
            
            if move.product_uom_qty <= available:
                moves_to_process += move
            else:
                # Insufficient stock - create discrepancy alert and skip this move
                alert = self._create_stock_discrepancy_alert(
                    move.product_id, 
                    move.product_uom_qty, 
                    available
                )
                _logger.warning("Stock OOS for %s, created discrepancy alert: %s - SKIPPING", 
                               move.product_id.name, alert.name)
                moves_to_skip += move
        
        # If NO moves can be processed, raise error
        if not moves_to_process:
            raise UserError(_('Unable to process consumption - all products are out of stock.'))
        
        # --- SAFETY #3: Ensure patient is set for billing ---
        if not self.partner_id:
            raise UserError(_('Patient is required for billable consumption. Please select a patient.'))
        
        # --- Remove skipped moves completely to prevent orphaned reservations ---
        # CRITICAL: We must unreserve and unlink (not just cancel) to ensure:
        # 1. Quant reserved_quantity is decremented
        # 2. No orphan moves left in 'assigned' state when picking is validated
        skipped_product_names = []  # Save names before unlinking for logging
        if moves_to_skip:
            skipped_product_names = moves_to_skip.mapped('product_id.name')
            _logger.info("Removing %d OOS moves: %s", 
                        len(moves_to_skip), 
                        ', '.join(skipped_product_names))
            # First unreserve any reserved stock (only these specific moves)
            moves_to_skip._do_unreserve()
            # Then unlink the move lines to clean up completely
            moves_to_skip.mapped('move_line_ids').unlink()
            # Finally unlink the moves themselves (removes from picking)
            moves_to_skip.unlink()
        
        # FIX Issue #1: Mark as partial if any moves were skipped
        if moves_to_skip:
            self.is_partial_consumption = True

        # --- Create Sale Order and Confirm Picking ---
        try:
            # Create/update Sale Order (with sudo for permission)
            # FIX Issue #2: Use linked_sale_order_id if set (SO-locked consumption)
            _logger.info("*** Creating/finding SO for patient %s (linked_so=%s)",
                        self.partner_id.name, self.linked_sale_order_id.id if self.linked_sale_order_id else 'None')
            sale_order = self._get_or_create_patient_sale_order(
                sale_order_id=self.linked_sale_order_id.id if self.linked_sale_order_id else None
            )
            _logger.info("*** Using SO %s (id=%s)", sale_order.name, sale_order.id)
            
            # Add ONLY processed moves to SO (not skipped ones)
            # UPDATE existing lines if they have order_line_id, CREATE new lines otherwise
            SaleOrderLine = self.env['sale.order.line'].sudo()
            for move in moves_to_process:
                # Check if this move came from a pre-loaded quotation line
                # Origin format: "order_line_id|final_qty" or just "order_line_id" (legacy)
                order_line_id = False
                final_qty = move.product_uom_qty  # Default to move qty
                if move.origin:
                    if '|' in move.origin:
                        # New format: order_line_id|final_qty
                        parts = move.origin.split('|')
                        if parts[0].isdigit():
                            order_line_id = parts[0]
                            try:
                                final_qty = float(parts[1])
                            except (ValueError, IndexError):
                                final_qty = move.product_uom_qty
                    elif move.origin.isdigit():
                        # Legacy format: just order_line_id
                        order_line_id = move.origin

                if order_line_id:
                    # UPDATE existing line quantity with final_qty (absolute, not delta)
                    existing_line = SaleOrderLine.browse(int(order_line_id))
                    if existing_line.exists() and existing_line.order_id.id == sale_order.id:
                        _logger.info("*** Updating SO line ID %s: %s from %.2f to %.2f",
                                    order_line_id, move.product_id.name, existing_line.product_uom_qty, final_qty)
                        existing_line.write({
                            'product_uom_qty': final_qty,
                            # lot_id set later by _sync_so_lines_from_ledger
                        })
                    else:
                        _logger.warning("*** Order line ID %s not found or belongs to different order, creating new line", order_line_id)
                        order_line_id = False  # Fall through to CREATE

                if not order_line_id:
                    product = move.product_id

                    # Check for existing SO line with same product to avoid duplicates
                    # Match on product only — lot_id is False at this point (resolved after validation)
                    # Bahmni enforces unique product+lot per SO, so we must merge
                    existing_match = sale_order.order_line.filtered(
                        lambda sol: sol.product_id.id == product.id
                    )
                    if existing_match:
                        line = existing_match[0]
                        new_qty = line.product_uom_qty + move.product_uom_qty
                        _logger.info("*** Merging into existing SO line %s: %s from %.2f to %.2f",
                                    line.id, product.name, line.product_uom_qty, new_qty)
                        line.write({'product_uom_qty': new_qty})
                    else:
                        # CREATE new line
                        price_unit = product.lst_price
                        if price_unit <= 0:
                            price_unit = product.standard_price

                        _logger.info("*** Adding SO line: %s x %s (price=%.2f) — lot assigned post-validation",
                                    product.name, move.product_uom_qty, price_unit)
                        SaleOrderLine.create({
                            'order_id': sale_order.id,
                            'product_id': product.id,
                            'product_uom_qty': move.product_uom_qty,
                            'product_uom': move.product_uom.id,
                            # lot_id intentionally omitted — set by _sync_so_lines_from_ledger
                            'price_unit': price_unit,
                        })
            
            # Confirm picking through Odoo's standard chain (merge, push rules, etc.)
            # but SKIP action_assign() (reservation). Reservation is what causes the
            # discrepancy messages — it fails when quant.reserved_quantity is inconsistent.
            # We set qty_done + FEFO lot manually after confirm, then validate.
            _logger.info("*** Confirming picking %s (no reservation)", self.name)
            self.sudo().action_confirm()
            _logger.info("*** Picking state after confirm: %s", self.state)

            # Remove any move lines auto-created by confirm, then create our own
            # with qty_done + lot from FEFO (no reservation needed)
            MoveLine = self.env['stock.move.line'].sudo()
            for move in self.move_ids_without_package:
                if move.move_line_ids:
                    move.move_line_ids.sudo().unlink()

                # Get lot from FEFO (earliest expiry) if product is lot-tracked
                lot_id = False
                if move.product_id.tracking == 'lot':
                    quants = self.env['stock.quant'].sudo().search([
                        ('product_id', '=', move.product_id.id),
                        ('location_id', '=', self.location_id.id),
                        ('lot_id', '!=', False),
                        ('quantity', '>', 0),
                    ])
                    if quants:
                        best = quants.sorted(
                            key=lambda q: q.lot_id.expiration_date or fields.Datetime.max
                        )
                        lot_id = best[0].lot_id.id

                MoveLine.create({
                    'move_id': move.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'picking_id': self.id,
                    'lot_id': lot_id,
                    'reserved_uom_qty': 0,
                    'qty_done': move.product_uom_qty,
                })
                _logger.info("*** Move line: %s x %.2f (lot_id=%s, qty_done=%.2f)",
                            move.product_id.name, move.product_uom_qty, lot_id, move.product_uom_qty)

            # Validate
            if self.move_ids_without_package:
                result = self.sudo().with_context(
                    skip_backorder=True,
                    skip_immediate=True,      # correct key checked by _pre_action_done_hook
                    skip_sms=True,
                ).button_validate()
                if result is not True:
                    # button_validate() returned a wizard dict instead of completing —
                    # this means Odoo detected a problem (immediate transfer dialog, backorder, etc.)
                    raise UserError(_(
                        'La validation du transfert a échoué (résultat inattendu: %s). '
                        'Vérifiez les quantités et les lots.'
                    ) % type(result).__name__)
                _logger.info("*** Picking %s validated, state=%s", self.name, self.state)
            else:
                _logger.warning("*** No moves remaining - cancelling picking")
                self.action_cancel()

            # FIX: Update qty_delivered on SO lines to prevent double delivery
            # When SO is confirmed later, Odoo won't create another picking for already-delivered qty
            if self.state == 'done':
                _logger.info("*** Updating qty_delivered on SO lines to match product_uom_qty")
                for so_line in sale_order.order_line:
                    if so_line.product_uom_qty > so_line.qty_delivered:
                        so_line.sudo().write({'qty_delivered': so_line.product_uom_qty})
                        _logger.info("*** SO line %s: qty_delivered set to %.2f",
                                    so_line.product_id.name, so_line.product_uom_qty)

                # CRITICAL: Write to consumption ledger AFTER validation
                # This is the source of truth for returns - captures exact lot from move_line
                Ledger = self.env['clinic.consumption.ledger'].sudo()
                for move_line in self.move_line_ids_without_package:
                    if move_line.qty_done > 0:
                        Ledger.create_from_move_line(move_line, sale_order.id)
                        _logger.info("*** Ledger entry created: %s x %.2f (lot=%s)",
                                    move_line.product_id.name, move_line.qty_done,
                                    move_line.lot_id.name if move_line.lot_id else 'N/A')

                # Rebuild SO lines from ledger (source of truth for product+lot+qty)
                # Bahmni requires: one SO line per lot, no duplicate lots, lot_id mandatory at confirm
                # The ledger knows the exact lot per move — SO must mirror that
                self._sync_so_lines_from_ledger(sale_order)

            # Log on both records
            sale_order.sudo().message_post(
                body=_('Consommation ajoutée depuis: %s') % self.name)
            
            # Include skipped products in log (use saved names since moves are unlinked)
            if skipped_product_names:
                skipped_names = ', '.join(skipped_product_names)
                self.message_post(
                    body=_('Facturé à: <a href="/web#id=%s&model=sale.order">%s</a><br/>'
                           '<b> Ignorés (rupture):</b> %s') % (
                        sale_order.id, sale_order.name, skipped_names))
            else:
                self.message_post(
                    body=_('Facturé à: <a href="/web#id=%s&model=sale.order">%s</a>') % (
                        sale_order.id, sale_order.name))
            
            _logger.info("*** _execute_consumption_submit SUCCESS: picking=%s, SO=%s", self.name, sale_order.name)
            
        except UserError:
            # Re-raise user errors as-is
            raise
        except Exception as e:
            # Log and re-raise other errors
            _logger.error("*** _execute_consumption_submit FAILED: %s", str(e))
            raise UserError(_('An error occurred while processing: %s') % str(e))
        
        # Return the sale order for reference
        return sale_order

    def _sync_so_lines_from_ledger(self, sale_order):
        """
        Rebuild SO lines to match ledger state (source of truth).

        Aggregates ledger by product+lot → ensures one SO line per product+lot.
        Handles multi-lot scenarios where FEFO splits across lots for the same product.
        """
        Ledger = self.env['clinic.consumption.ledger'].sudo()
        SaleOrderLine = self.env['sale.order.line'].sudo()

        # Get all active ledger entries for this SO, grouped by product+lot
        entries = Ledger.search([
            ('sale_order_id', '=', sale_order.id),
            ('state', '=', 'active'),
        ])

        from collections import defaultdict
        # (product_id, lot_id or False) -> total qty_consumed
        ledger_totals = defaultdict(float)
        for entry in entries:
            key = (entry.product_id.id, entry.lot_id.id if entry.lot_id else False)
            ledger_totals[key] += entry.qty_consumed

        _logger.info("*** Syncing SO %s lines from ledger: %d product+lot combos",
                     sale_order.name, len(ledger_totals))

        # Process each product+lot from ledger
        for (product_id, lot_id), total_qty in ledger_totals.items():
            # Find existing SO line with this product+lot
            if lot_id:
                existing = sale_order.order_line.filtered(
                    lambda sol, pid=product_id, lid=lot_id:
                    sol.product_id.id == pid and sol.lot_id.id == lid
                )
            else:
                existing = sale_order.order_line.filtered(
                    lambda sol, pid=product_id:
                    sol.product_id.id == pid and not sol.lot_id
                )

            if existing:
                line = existing[0]
                if line.product_uom_qty != total_qty:
                    _logger.info("*** SO line qty adjusted: %s lot=%s from %.2f to %.2f",
                                line.product_id.name, lot_id, line.product_uom_qty, total_qty)
                    line.write({'product_uom_qty': total_qty})
                if lot_id and not line.lot_id:
                    line.write({'lot_id': lot_id})
                    _logger.info("*** SO line lot assigned: %s -> %s", line.product_id.name, lot_id)
            else:
                # Need a new SO line for this product+lot
                # Try to split from an existing no-lot line for the same product
                no_lot_line = sale_order.order_line.filtered(
                    lambda sol, pid=product_id: sol.product_id.id == pid and not sol.lot_id
                )
                if no_lot_line:
                    line = no_lot_line[0]
                    remainder = line.product_uom_qty - total_qty
                    if remainder > 0:
                        # Split: assign this lot+qty, leave remainder for next lot
                        line.write({'product_uom_qty': total_qty, 'lot_id': lot_id or False})
                        SaleOrderLine.create({
                            'order_id': sale_order.id,
                            'product_id': product_id,
                            'product_uom_qty': remainder,
                            'product_uom': line.product_uom.id,
                            'price_unit': line.price_unit,
                        })
                        _logger.info("*** SO line split: %s lot=%s qty=%.2f, remainder=%.2f",
                                    line.product_id.name, lot_id, total_qty, remainder)
                    else:
                        # Covers entire line or more
                        line.write({'product_uom_qty': total_qty, 'lot_id': lot_id or False})
                        _logger.info("*** SO line reassigned: %s lot=%s qty=%.2f",
                                    line.product_id.name, lot_id, total_qty)
                else:
                    # No line exists at all — create
                    product = self.env['product.product'].browse(product_id)
                    price_unit = product.lst_price or product.standard_price
                    SaleOrderLine.create({
                        'order_id': sale_order.id,
                        'product_id': product_id,
                        'product_uom_qty': total_qty,
                        'product_uom': product.uom_id.id,
                        'lot_id': lot_id or False,
                        'price_unit': price_unit,
                    })
                    _logger.info("*** SO line created from ledger: %s lot=%s qty=%.2f",
                                product.name, lot_id, total_qty)

    def _get_or_create_patient_sale_order(self, sale_order_id=None):
        """Find existing draft SO for patient or create new one

        Args:
            sale_order_id: Optional specific SO ID to use (for SO-locked consumption)

        Uses sudo() because portal users may not have Sales access.
        """
        self.ensure_one()

        SaleOrder = self.env['sale.order'].sudo()

        # FIX Issue #2: If sale_order_id provided, use that specific SO
        # This ensures consumption is linked to ONE SO, not jumping between SOs
        if sale_order_id:
            existing_order = SaleOrder.browse(int(sale_order_id))
            if existing_order.exists() and existing_order.partner_id.id == self.partner_id.id:
                return existing_order
            # If SO doesn't match patient, fall through to search/create

        # Search for existing draft order for this patient (oldest first for consistency)
        existing_order = SaleOrder.search([
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'draft'),
            ('company_id', '=', self.company_id.id),
        ], limit=1, order='create_date asc')  # Changed: oldest first

        # Get pricelist: try 'Pharm Price list', fallback to partner's pricelist, then first available
        # We need this for both existing and new orders
        Pricelist = self.env['product.pricelist'].sudo()
        pricelist = Pricelist.search([
            ('name', 'ilike', 'Pharm Price')
        ], limit=1)

        if not pricelist:
            # Fallback to partner's pricelist
            pricelist = self.partner_id.property_product_pricelist

        if not pricelist:
            # Last resort: first active pricelist
            pricelist = Pricelist.search([('active', '=', True)], limit=1)

        if existing_order:
            # FIX: Ensure existing order has a pricelist (required for price computation)
            # Some orders from OpenMRS/Bahmni may not have pricelist set
            if not existing_order.pricelist_id and pricelist:
                _logger.info("*** Setting missing pricelist on existing SO %s", existing_order.name)
                existing_order.write({'pricelist_id': pricelist.id})
            return existing_order

        # Create new SO
        return SaleOrder.create({
            'partner_id': self.partner_id.id,
            'origin': _('Portal Consumption: %s') % self.name,
            'company_id': self.company_id.id,
            'pricelist_id': pricelist.id,  # Required field
        })

    def _create_stock_discrepancy_alert(self, product, attempted_qty, system_qty):
        """Create a stock discrepancy alert when consumption is blocked.
        
        Args:
            product: product.product record
            attempted_qty: float - qty nurse tried to consume
            system_qty: float - qty system shows available
        
        Returns:
            clinic.stock.discrepancy record
        """
        self.ensure_one()
        
        Discrepancy = self.env['clinic.stock.discrepancy'].sudo()
        
        # Check for existing pending discrepancy for same product/location (deduplication)
        existing_alert = Discrepancy.search([
            ('product_id', '=', product.id),
            ('location_id', '=', self.location_id.id),
            ('state', '=', 'pending'),
        ], limit=1)
        
        if existing_alert:
            # Return existing alert instead of creating duplicate
            return existing_alert
        
        alert = Discrepancy.create({
            'user_id': self.env.user.id,
            'patient_id': self.partner_id.id if self.portal_behavior == 'billable' else False,
            'product_id': product.id,
            'attempted_qty': attempted_qty,
            'system_qty': system_qty,
            'location_id': self.location_id.id,
            'picking_type_id': self.picking_type_id.id,
        })
        
        # Notify Clinic Portal Managers only (not all system admins)
        manager_group = self.env.ref('clinic_staff_portal.group_clinic_portal_manager', raise_if_not_found=False)
        
        users_to_notify = self.env['res.users']
        if manager_group:
            users_to_notify = manager_group.users
        
        # Create activity for each admin
        for user in users_to_notify.filtered(lambda u: u.active):
            alert.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                note=_('Stock discrepancy: %(user)s tried to consume %(qty)s of %(prod)s for patient %(patient)s, but system shows only %(avail)s at %(loc)s') % {
                    'user': self.env.user.name,
                    'qty': attempted_qty,
                    'prod': product.name,
                    'patient': self.partner_id.name if self.partner_id else 'Unknown',
                    'avail': system_qty,
                    'loc': self.location_id.name,
                }
            )
        
        # Post message on alert for context
        alert.message_post(
            body=_('<b>Stock Discrepancy Alert</b><br/>'
                   '<b>Nurse:</b> %(user)s<br/>'
                   '<b>Patient:</b> %(patient)s<br/>'
                   '<b>Product:</b> %(prod)s<br/>'
                   '<b>Location:</b> %(loc)s<br/>'
                   '<b>Attempted Qty:</b> %(qty)s<br/>'
                   '<b>System Stock:</b> %(avail)s<br/><br/>'
                   '<i>Please investigate: Nurse error or inventory issue?</i>') % {
                'user': self.env.user.name,
                'patient': self.partner_id.name if self.partner_id else 'Unknown',
                'prod': product.name,
                'loc': self.location_id.name,
                'qty': attempted_qty,
                'avail': system_qty,
            }
        )
        
        return alert


    def _notify_managers(self):
        """Notify source location responsables with a To-Do activity.
        
        Only notifies users who are responsible for the SOURCE location,
        i.e., the pharmacy staff who will process the request.
        
        NOTE: If location has require_approval enabled, the approval workflow
        (_notify_approvers_needed) already handles notifications - skip here.
        """
        self.ensure_one()
        
        # Skip if approval workflow handles notifications
        if self.location_id.require_approval:
            return  # Let _notify_approvers_needed handle it
        
        try:
            # Get responsables from source location (e.g., pharmacy staff)
            source_location = self.location_id
            if source_location and hasattr(source_location, 'responsible_user_ids'):
                responsables = source_location.responsible_user_ids.filtered(
                    lambda u: u.active
                )
                
                for user in responsables:
                    self.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        note=_('New Portal Request from %s') % self.portal_requester_id.name
                    )
        except Exception:
            pass

    def _return_to_dashboard(self, message):
        """Return rainbow man + redirect to CBM Kiosk"""
        return {
            'effect': {
                'fadeout': 'medium',
                'message': message,
                'type': 'rainbow_man',
            },
            'type': 'ir.actions.client',
            'tag': 'cbm_kiosk_action',
        }

    def button_validate(self):
        """Override to notify requester and auto-create quotation for consumption"""
        # Post discrepancy warning to log if stock insufficient (before validation attempt)
        for picking in self:
            picking._post_discrepancy_warning_to_log()

        res = super().button_validate()

        for picking in self:
            if picking.is_portal_request and picking.portal_requester_id:
                # Notify requester that their request is processed
                picking.message_post(
                    body=_('✓ Your request has been processed and is ready!'),
                    partner_ids=[picking.portal_requester_id.partner_id.id],
                    subtype_xmlid='mail.mt_comment',
                )

                # Note: Billable consumption SO is created during submit, not validation
                pass

        return res

    # ──────────────────────────────────────────────────────────────
    # Accountability Cron — 3-tier escalation
    # Day 8:  Warning document (24h deadline, blocks kiosk if not signed)
    # Day 9:  Kiosk auto-blocked (existing document blocking mechanism)
    # Day 10: DRH escalation report
    # ──────────────────────────────────────────────────────────────

    @api.model
    def _cron_send_late_transfer_report(self):
        """Daily cron: 3-tier accountability escalation.

        Checks internal transfers + purchase receptions pending validation.
        - >= 8 days: Warning document to responsible user (24h deadline)
        - >= 9 days: Kiosk blocked (automatic via document deadline mechanism)
        - >= 10 days: DRH escalation report
        """
        from collections import defaultdict
        from datetime import date, timedelta
        import base64

        ICP = self.env['ir.config_parameter'].sudo()
        Document = self.env['clinic.document'].sudo()

        # --- Config ---
        # Master enable/disable toggle (set via Settings > Clinic Portal > Accountability)
        cron_enabled = ICP.get_param('clinic_staff_portal.accountability_cron_enabled', 'True')
        if cron_enabled not in ('True', '1', 'true'):
            _logger.info("[ACCOUNTABILITY CRON] Disabled via settings. Skipping.")
            return

        # Hold toggles — set to 'True' in System Parameters to pause
        warning_held = ICP.get_param('clinic_staff_portal.hold_warning_documents', 'False').lower() == 'true'
        escalation_held = ICP.get_param('clinic_staff_portal.hold_drh_escalation', 'False').lower() == 'true'

        if warning_held and escalation_held:
            _logger.info("[ACCOUNTABILITY CRON] Both warning and escalation are on hold. Skipping.")
            return

        drh_id_str = ICP.get_param('clinic_staff_portal.drh_user_id', '')
        drh_user = False
        if drh_id_str and drh_id_str.isdigit():
            drh_user = self.env['res.users'].sudo().browse(int(drh_id_str))
            if not drh_user.exists():
                drh_user = False

        WARNING_DAYS = 8    # Day 8: warning document
        ESCALATION_DAYS = 10  # Day 10: DRH report

        today = date.today()
        today_dt = fields.Date.today()
        currency = self.env.company.currency_id
        currency_sym = currency.symbol or 'DA'

        # --- Find all pending transfers (internal + incoming) ---
        domain = [
            ('state', 'in', ['assigned', 'confirmed', 'waiting']),
            ('picking_type_id.code', 'in', ['internal', 'incoming']),
        ]
        start_date = ICP.get_param('clinic_staff_portal.accountability_start_date', '')
        if start_date:
            domain.append(('create_date', '>=', start_date))

        all_pending = self.sudo().search(domain)

        def _get_days(picking):
            ref = picking.scheduled_date or picking.create_date
            return (today - ref.date()).days if ref else 0

        # --- Group by source location ---
        loc_data = defaultdict(lambda: {
            'pickings': self.env['stock.picking'],
            'location': False,
            'responsible_users': self.env['res.users'],
            'responsible_names': '',
            'count': 0,
            'max_days': 0,
            'value': 0.0,
        })

        for picking in all_pending:
            days = _get_days(picking)
            if days < WARNING_DAYS:
                continue  # Not late enough

            if picking.picking_type_id.code == 'incoming':
                src_loc = picking.location_dest_id
            else:
                src_loc = picking.location_id
            loc_key = src_loc.id

            loc_data[loc_key]['pickings'] |= picking
            loc_data[loc_key]['location'] = src_loc
            loc_data[loc_key]['count'] += 1

            value = sum(m.product_id.standard_price * m.product_uom_qty for m in picking.move_ids)
            loc_data[loc_key]['value'] += value

            if days > loc_data[loc_key]['max_days']:
                loc_data[loc_key]['max_days'] = days

            if not loc_data[loc_key]['responsible_users'] and hasattr(src_loc, 'responsible_user_ids') and src_loc.responsible_user_ids:
                loc_data[loc_key]['responsible_users'] = src_loc.responsible_user_ids
                loc_data[loc_key]['responsible_names'] = ', '.join(src_loc.responsible_user_ids.mapped('name'))

        if not loc_data:
            _logger.info("[ACCOUNTABILITY CRON] No late transfers found (threshold: %d days).", WARNING_DAYS)
            return

        # --- TIER 1: Day 8+ — Generate warning documents ---
        if warning_held:
            _logger.info("[ACCOUNTABILITY CRON] Warning documents on hold, skipping Tier 1.")
        for loc_id, data in loc_data.items():
            if warning_held:
                break
            if data['max_days'] < WARNING_DAYS:
                continue

            src_loc = data['location']
            loc_name = src_loc.complete_name or src_loc.name or 'Non spécifié'
            responsible_users = data['responsible_users']

            if not responsible_users:
                _logger.warning("[ACCOUNTABILITY CRON] No responsible users for location %s, skipping warning.", loc_name)
                continue

            # Check if a warning document already exists for this location this week
            week_start = today - timedelta(days=today.weekday())
            existing_warning = Document.search([
                ('name', 'like', f'Avertissement — {loc_name}'),
                ('create_date', '>=', fields.Datetime.to_string(
                    fields.Datetime.now().replace(
                        year=week_start.year, month=week_start.month, day=week_start.day,
                        hour=0, minute=0, second=0
                    )
                )),
                ('requires_acknowledgement', '=', True),
            ], limit=1)

            if existing_warning:
                _logger.info("[ACCOUNTABILITY CRON] Warning already sent this week for %s (doc #%d).", loc_name, existing_warning.id)
                continue

            # Build picking details for the PDF
            picking_details = []
            for picking in data['pickings'].sorted(key=lambda p: p.scheduled_date or p.create_date):
                ref_date = picking.scheduled_date or picking.create_date
                days = _get_days(picking)
                products = ', '.join(
                    f"{m.product_id.name} ({m.product_uom_qty:.0f})"
                    for m in picking.move_ids[:5]
                )
                if len(picking.move_ids) > 5:
                    products += f' (+{len(picking.move_ids) - 5} autres)'
                picking_details.append({
                    'name': picking.name,
                    'type': picking.picking_type_id.name or '',
                    'date': ref_date.strftime('%d/%m/%Y') if ref_date else '-',
                    'days': days,
                    'products': products,
                })

            # Generate PDF via QWeb report
            report_ctx = {
                'report_date': today.strftime('%d/%m/%Y'),
                'responsible_name': data['responsible_names'] or 'Non assigné',
                'location_name': loc_name,
                'threshold_days': WARNING_DAYS,
                'total_value': f"{data['value']:,.0f}",
                'currency': currency_sym,
                'total_count': data['count'],
                'pickings': picking_details,
            }

            pdf_data = False
            try:
                # Load director stamp/signature from settings
                director_stamp = ICP.get_param('clinic_staff_portal.director_stamp', '')
                director_signature = ICP.get_param('clinic_staff_portal.director_signature', '')
                director_name = ICP.get_param('clinic_staff_portal.director_name', '')
                director_title = ICP.get_param('clinic_staff_portal.director_title', '')

                doc_vals = {
                    'name': f'Avertissement — {loc_name}',
                    'category': 'policy',
                    'resource_type': 'pdf',
                    'requires_acknowledgement': True,
                    'lock_on_overdue': True,
                    'deadline': today_dt + timedelta(days=1),  # 24h deadline
                    'target_user_ids': [(6, 0, responsible_users.ids)],
                    'location_ids': [(6, 0, [src_loc.id])],
                    'notify_users': False,  # We handle notification ourselves
                    'active': True,
                }
                if director_stamp:
                    doc_vals['stamp_image'] = director_stamp
                if director_signature:
                    doc_vals['signature_image'] = director_signature
                if director_name:
                    doc_vals['signatory_name'] = director_name
                if director_title:
                    doc_vals['signatory_title'] = director_title

                temp_doc = Document.create(doc_vals)

                # Render PDF — pass report_ctx via data= (not with_context)
                # so QWeb template accesses variables directly
                report = self.env.ref('clinic_staff_portal.action_report_accountability_warning', raise_if_not_found=False)
                if report:
                    pdf_content, _ = report.sudo()._render_qweb_pdf(
                        report.report_name, [temp_doc.id], data=report_ctx,
                    )
                    pdf_data = base64.b64encode(pdf_content)

                if pdf_data:
                    temp_doc.write({
                        'file_data': pdf_data,
                        'file_name': f'Avertissement_{loc_name.replace("/", "_")}_{today.strftime("%Y%m%d")}.pdf',
                    })
                    # Manually send notification (notify_users was False during create)
                    temp_doc._send_notification()
                    _logger.info(
                        "[ACCOUNTABILITY CRON] Warning document #%d created for %s (%d transfers, %s %s).",
                        temp_doc.id, loc_name, data['count'], f"{data['value']:,.0f}", currency_sym
                    )
                else:
                    # No PDF engine available — still create the document without PDF
                    temp_doc.write({
                        'resource_type': 'link',
                        'url': '#',
                        'description': (
                            f"AVERTISSEMENT: {data['count']} transferts en retard "
                            f"({data['value']:,.0f} {currency_sym}). Délai: 24h."
                        ),
                    })
                    temp_doc._send_notification()
                    _logger.warning(
                        "[ACCOUNTABILITY CRON] PDF generation failed for %s, created link document #%d.",
                        loc_name, temp_doc.id
                    )

            except Exception as e:
                _logger.error("[ACCOUNTABILITY CRON] Failed to create warning for %s: %s", loc_name, e)
                continue

        # --- TIER 3: Day 10+ — DRH escalation report ---
        if escalation_held:
            _logger.info("[ACCOUNTABILITY CRON] DRH escalation on hold, skipping Tier 3.")
            return
        if not drh_user:
            _logger.warning("[ACCOUNTABILITY CRON] DRH user not configured, skipping escalation report.")
            return

        # Find locations with transfers >= ESCALATION_DAYS
        escalation_locations = {
            loc_id: data for loc_id, data in loc_data.items()
            if data['max_days'] >= ESCALATION_DAYS
        }

        if not escalation_locations:
            _logger.info("[ACCOUNTABILITY CRON] No transfers at escalation threshold (%d days).", ESCALATION_DAYS)
            return

        # Check which warnings were acknowledged vs not
        escalation_rows = ''
        total_esc_count = 0
        total_esc_value = 0.0

        for loc_id, data in sorted(escalation_locations.items(), key=lambda x: -x[1]['value']):
            src_loc = data['location']
            loc_name = src_loc.complete_name or src_loc.name or 'Non spécifié'
            responsible = data['responsible_names'] or 'Non assigné'

            # Find if there's a warning document and its acknowledgement status
            warning_doc = Document.search([
                ('name', 'like', f'Avertissement — {loc_name}'),
                ('requires_acknowledgement', '=', True),
                ('active', '=', True),
            ], order='create_date desc', limit=1)

            warning_status = 'Aucun avertissement'
            warning_date = '-'
            ack_status = '<strong style="color:#991b1b;">Non signé</strong>'

            if warning_doc:
                warning_date = warning_doc.create_date.strftime('%d/%m/%Y') if warning_doc.create_date else '-'
                current_acks = warning_doc.acknowledgement_ids.filtered(
                    lambda a: a.document_version == warning_doc.version
                )
                if current_acks:
                    ack_names = ', '.join(current_acks.mapped('user_id.name'))
                    ack_dates = ', '.join(
                        a.acknowledged_date.strftime('%d/%m/%Y %H:%M') for a in current_acks
                        if a.acknowledged_date
                    )
                    ack_status = f'<span style="color:#059669;">Signé par {ack_names} ({ack_dates})</span>'
                    warning_status = 'Signé mais transferts toujours en attente'
                else:
                    warning_status = 'Envoyé, non signé'

            total_esc_count += data['count']
            total_esc_value += data['value']

            # Detail of late pickings for this location
            picking_rows = ''
            for picking in data['pickings'].sorted(key=lambda p: p.scheduled_date or p.create_date):
                ref_date = picking.scheduled_date or picking.create_date
                days = _get_days(picking)
                if days < ESCALATION_DAYS:
                    continue
                products = ', '.join(
                    f"{m.product_id.name} ({m.product_uom_qty:.0f})"
                    for m in picking.move_ids[:3]
                )
                if len(picking.move_ids) > 3:
                    products += f' (+{len(picking.move_ids) - 3})'
                picking_rows += (
                    f'<tr>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #f3f4f6;font-size:12px;">{picking.name}</td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #f3f4f6;font-size:12px;">'
                    f'{ref_date.strftime("%d/%m/%Y") if ref_date else "-"}</td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:center;">'
                    f'<strong style="color:#991b1b;">{days} j</strong></td>'
                    f'<td style="padding:4px 8px;border-bottom:1px solid #f3f4f6;font-size:11px;">{products}</td>'
                    f'</tr>'
                )

            escalation_rows += f"""
            <div style="margin-top:20px;border:1px solid #fecaca;border-radius:6px;overflow:hidden;">
                <div style="background:#fef2f2;padding:12px 16px;">
                    <strong style="font-size:14px;">{loc_name}</strong>
                    <span style="float:right;color:#991b1b;font-weight:600;">{data['value']:,.0f} {currency_sym}</span>
                    <br/>
                    <span style="font-size:12px;color:#6b7280;">
                        Responsable: {responsible} | {data['count']} transferts | Max: {data['max_days']} jours
                    </span>
                </div>
                <div style="padding:8px 16px;font-size:12px;">
                    <p style="margin:0 0 4px;">
                        <strong>Avertissement:</strong> {warning_date} — {ack_status}
                    </p>
                </div>
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f9fafb;">
                            <th style="padding:4px 8px;text-align:left;font-size:11px;">Réf.</th>
                            <th style="padding:4px 8px;text-align:left;font-size:11px;">Date</th>
                            <th style="padding:4px 8px;text-align:center;font-size:11px;">Retard</th>
                            <th style="padding:4px 8px;text-align:left;font-size:11px;">Produits</th>
                        </tr>
                    </thead>
                    <tbody>{picking_rows}</tbody>
                </table>
            </div>
            """

        report_date = today.strftime('%d/%m/%Y')
        company_name = self.env.company.name or 'Clinique'

        message_body = f"""
<div style="font-family:'Segoe UI',Roboto,sans-serif;max-width:800px;margin:0 auto;">
    <!-- Header -->
    <div style="background:#991b1b;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h2 style="margin:0;font-size:18px;font-weight:600;">
            RAPPORT D'ESCALADE — Transferts en Retard Critique
        </h2>
        <p style="margin:6px 0 0;font-size:13px;color:#fecaca;">
            {company_name} | {report_date} | Seuil critique : ≥ {ESCALATION_DAYS} jours
        </p>
    </div>

    <!-- Body -->
    <div style="background:#fff;padding:24px;border:1px solid #e5e7eb;border-top:none;">
        <p style="margin:0 0 16px;font-size:14px;color:#374151;">
            Madame, Monsieur,
        </p>
        <p style="margin:0 0 8px;font-size:14px;color:#374151;line-height:1.6;">
            Ce rapport d'escalade concerne des réceptions et transferts internes en attente
            de validation depuis <strong style="color:#991b1b;">{ESCALATION_DAYS} jours ou plus</strong>.
        </p>
        <p style="margin:0 0 20px;font-size:14px;color:#374151;line-height:1.6;">
            Malgré l'envoi d'avertissements aux responsables concernés, la situation n'a pas été régularisée.
            Le risque d'inventaire total s'élève à
            <strong style="color:#991b1b;">{total_esc_value:,.0f} {currency_sym}</strong>
            sur <strong>{total_esc_count}</strong> opération(s).
        </p>

        <!-- Escalation timeline -->
        <div style="background:#f9fafb;border-radius:6px;padding:12px 16px;margin-bottom:20px;font-size:13px;">
            <strong>Chronologie d'escalade :</strong><br/>
            <span style="color:#6b7280;">
                Jour 8 : Avertissement envoyé (document avec délai 24h)<br/>
                Jour 9 : Accès kiosque bloqué si non signé<br/>
                Jour 10 : <strong style="color:#991b1b;">Ce rapport d'escalade à la DRH</strong>
            </span>
        </div>

        <!-- Per-location escalation details -->
        <h3 style="margin:0 0 12px;font-size:15px;color:#111827;border-bottom:2px solid #991b1b;padding-bottom:8px;">
            Détail par Emplacement
        </h3>
        {escalation_rows}
    </div>

    <!-- Footer -->
    <div style="background:#fef2f2;padding:16px 24px;border:1px solid #fecaca;border-top:none;border-radius:0 0 8px 8px;">
        <p style="margin:0;font-size:12px;color:#991b1b;text-align:center;font-weight:600;">
            Action requise de la Direction des Ressources Humaines
        </p>
        <p style="margin:4px 0 0;font-size:11px;color:#6b7280;text-align:center;">
            Ce rapport est généré automatiquement par le système CBM Portal.
        </p>
    </div>
</div>
"""

        # Send escalation to DRH via internal Odoo message
        try:
            drh_user.partner_id.message_post(
                body=message_body,
                message_type='notification',
                subtype_xmlid='mail.mt_note',
                partner_ids=[drh_user.partner_id.id],
            )
            _logger.info(
                "[ACCOUNTABILITY CRON] Sent escalation report to %s: %d transfers at %d+ days, %s %s.",
                drh_user.name, total_esc_count, ESCALATION_DAYS,
                f'{total_esc_value:,.0f}', currency_sym
            )
        except Exception as e:
            _logger.error("[ACCOUNTABILITY CRON] Failed to send escalation report: %s", e)
