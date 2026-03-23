# Add this to controllers/purchase.py - Replace the create_return endpoint

@http.route('/cbm/purchase/correct_reception', type='json', auth='user')
def correct_reception(self, picking_id, corrections):
    """Correct a completed reception with automatic return/receive operations.

    Unified correction interface that handles ALL scenarios:
    - Quantity corrections (up or down) → auto return/receive
    - Lot number fixes → auto return old + receive new
    - Expiry date fixes
    - Price corrections

    PERMISSIONS: Only location responsible or stock manager can correct

    Args:
        picking_id: Original reception ID (must be 'done')
        corrections: [{
            move_line_id: int,
            product_id: int,
            original_qty: float,  # What was received
            new_qty: float,       # What should have been received
            lot_name: str,
            expiration_date: str (YYYY-MM-DD),
            price_unit: float
        }]

    Returns:
        {success, message, operations: [created pickings]}
    """
    user = request.env.user
    Picking = request.env['stock.picking'].sudo()
    MoveLine = request.env['stock.move.line'].sudo()
    Lot = request.env['stock.lot'].sudo()

    picking = Picking.browse(picking_id)
    if not picking.exists():
        return {'success': False, 'error': _('Reception not found')}

    if picking.state != 'done':
        return {'success': False, 'error': _('Can only correct completed receptions')}

    # PERMISSION CHECK
    dest_location = picking.location_dest_id
    is_responsible = False
    if hasattr(user, 'responsible_location_ids'):
        is_responsible = dest_location.id in user.responsible_location_ids.ids
    is_admin = user.has_group('stock.group_stock_manager')

    if not is_responsible and not is_admin:
        return {
            'success': False,
            'error': _('Seul le responsable de %s peut corriger cette réception') % dest_location.name
        }

    operations = []

    try:
        for correction in corrections:
            move_line = MoveLine.browse(correction['move_line_id'])
            if not move_line.exists():
                continue

            product = move_line.product_id
            original_qty = correction['original_qty']
            new_qty = correction['new_qty']
            qty_delta = new_qty - original_qty

            new_lot_name = correction.get('lot_name', '')
            new_expiry = correction.get('expiration_date', '')
            new_price = correction.get('price_unit')
            old_lot = move_line.lot_id

            # Update PO price if changed
            if new_price is not None:
                po_line = move_line.move_id.purchase_line_id
                if po_line and abs(po_line.price_unit - new_price) > 0.01:
                    old_price = po_line.price_unit
                    po_line.sudo().write({'price_unit': new_price})
                    _logger.info("CBM Correction [%s]: Price %s: %.2f → %.2f",
                               user.name, product.name, old_price, new_price)

            # CASE 1: Quantity decreased → Return excess to vendor
            if qty_delta < 0:
                return_qty = abs(qty_delta)
                return_pick = self._quick_return(
                    picking, product, return_qty, old_lot, user
                )
                if return_pick:
                    operations.append(f"Retour: {return_pick.name} (-{return_qty} {product.uom_id.name})")

            # CASE 2: Quantity increased → Receive additional
            elif qty_delta > 0:
                receive_pick = self._quick_receive(
                    picking, product, qty_delta, new_lot_name, new_expiry, user
                )
                if receive_pick:
                    operations.append(f"Réception: {receive_pick.name} (+{qty_delta} {product.uom_id.name})")

            # CASE 3: Lot/Expiry fix (same qty, different lot)
            lot_changed = new_lot_name and new_lot_name != (old_lot.name if old_lot else '')
            if qty_delta == 0 and lot_changed:
                # Return with old lot
                return_pick = self._quick_return(
                    picking, product, new_qty, old_lot, user
                )
                # Receive with new lot
                receive_pick = self._quick_receive(
                    picking, product, new_qty, new_lot_name, new_expiry, user
                )
                if return_pick and receive_pick:
                    operations.append(f"Correction lot: {old_lot.name if old_lot else 'N/A'} → {new_lot_name}")

        return {
            'success': True,
            'message': _('%d correction(s) effectuée(s)') % len(operations),
            'operations': operations,
        }

    except Exception as e:
        _logger.error("CBM Correction [%s] failed for %s: %s",
                     user.name, picking.name, str(e), exc_info=True)
        return {
            'success': False,
            'error': _('Erreur: %s') % str(e)
        }

def _quick_return(self, original_picking, product, qty, lot, user):
    """Create and auto-validate return picking.

    Uses sudo() but logs user in chatter.
    """
    Picking = request.env['stock.picking'].sudo()
    Move = request.env['stock.move'].sudo()
    MoveLine = request.env['stock.move.line'].sudo()

    # Create return picking (reverse locations)
    return_picking = Picking.create({
        'picking_type_id': original_picking.picking_type_id.return_picking_type_id.id or original_picking.picking_type_id.id,
        'location_id': original_picking.location_dest_id.id,  # From warehouse
        'location_dest_id': original_picking.location_id.id,  # To vendor
        'partner_id': original_picking.partner_id.id,
        'origin': f'Retour de {original_picking.name}',
    })

    # Create move
    move = Move.create({
        'name': product.name,
        'product_id': product.id,
        'product_uom_qty': qty,
        'product_uom': product.uom_id.id,
        'picking_id': return_picking.id,
        'location_id': return_picking.location_id.id,
        'location_dest_id': return_picking.location_dest_id.id,
    })

    # Create move line with lot
    MoveLine.create({
        'move_id': move.id,
        'product_id': product.id,
        'product_uom_id': product.uom_id.id,
        'picking_id': return_picking.id,
        'location_id': return_picking.location_id.id,
        'location_dest_id': return_picking.location_dest_id.id,
        'lot_id': lot.id if lot else False,
        'qty_done': qty,
    })

    # Log user action in chatter
    return_picking.message_post(
        body=f"Correction par {user.name}: Retour {qty} {product.uom_id.name}",
        author_id=user.partner_id.id,
    )

    # Auto-validate with sudo
    return_picking.action_confirm()
    return_picking.action_assign()
    return_picking.with_context(skip_backorder=True, skip_immediate_transfer=True).button_validate()

    _logger.info("CBM Correction [%s]: Return %s validated", user.name, return_picking.name)
    return return_picking

def _quick_receive(self, original_picking, product, qty, lot_name, expiry, user):
    """Create and auto-validate new reception.

    Uses sudo() but logs user in chatter.
    """
    Picking = request.env['stock.picking'].sudo()
    Move = request.env['stock.move'].sudo()
    MoveLine = request.env['stock.move.line'].sudo()
    Lot = request.env['stock.lot'].sudo()

    # Create reception picking (same locations as original)
    new_picking = Picking.create({
        'picking_type_id': original_picking.picking_type_id.id,
        'location_id': original_picking.location_id.id,
        'location_dest_id': original_picking.location_dest_id.id,
        'partner_id': original_picking.partner_id.id,
        'origin': f'Correction de {original_picking.name}',
        'purchase_id': original_picking.purchase_id.id if original_picking.purchase_id else False,
    })

    # Create move
    move = Move.create({
        'name': product.name,
        'product_id': product.id,
        'product_uom_qty': qty,
        'product_uom': product.uom_id.id,
        'picking_id': new_picking.id,
        'location_id': new_picking.location_id.id,
        'location_dest_id': new_picking.location_dest_id.id,
    })

    # Find or create lot
    lot = None
    if lot_name:
        lot = Lot.search([
            ('name', '=', lot_name),
            ('product_id', '=', product.id),
        ], limit=1)
        if not lot:
            lot = Lot.create({
                'name': lot_name,
                'product_id': product.id,
                'company_id': new_picking.company_id.id,
                'expiration_date': expiry if expiry else False,
            })

    # Create move line
    MoveLine.create({
        'move_id': move.id,
        'product_id': product.id,
        'product_uom_id': product.uom_id.id,
        'picking_id': new_picking.id,
        'location_id': new_picking.location_id.id,
        'location_dest_id': new_picking.location_dest_id.id,
        'lot_id': lot.id if lot else False,
        'qty_done': qty,
    })

    # Log user action
    new_picking.message_post(
        body=f"Correction par {user.name}: Réception {qty} {product.uom_id.name}" +
             (f", Lot: {lot_name}" if lot_name else ""),
        author_id=user.partner_id.id,
    )

    # Auto-validate
    new_picking.action_confirm()
    new_picking.action_assign()
    new_picking.with_context(skip_backorder=True, skip_immediate_transfer=True).button_validate()

    _logger.info("CBM Correction [%s]: Receive %s validated", user.name, new_picking.name)
    return new_picking
