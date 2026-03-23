# -*- coding: utf-8 -*-
"""
CBM Portal Purchase Controller

Handles all purchase-related operations:
- Vendor search and creation
- Product creation (for purchase context)
- PO creation
- Reception/validation workflow

Moved from clinic_brain/controllers/brain_portal.py for consolidation.
"""

from odoo import http, _, fields
from datetime import timedelta, datetime
from odoo.http import request
import logging
import base64

_logger = logging.getLogger(__name__)


class CBMPurchaseController(http.Controller):
    """Purchase and reception endpoints for CBM Portal."""

    # ========== Helper Methods ==========

    def _get_user_location_type(self, user):
        """Determine if user works at a ward (request) or reception (PO) location."""
        if not hasattr(user, 'allowed_operation_types') or not user.allowed_operation_types:
            return ('none', 0)
        
        op_types = user.allowed_operation_types
        
        # Check for incoming (reception) operation type - main stock locations
        reception_op = op_types.filtered(lambda op: op.code == 'incoming')
        if reception_op:
            return ('reception', reception_op[0].id)
        
        # Check for internal transfer (request from pharmacy) - ward locations
        request_op = op_types.filtered(
            lambda op: op.portal_category == 'request' if hasattr(op, 'portal_category') else False
        )
        if request_op:
            return ('ward', request_op[0].id)
        
        return ('none', 0)

    # ========== Vendor Endpoints ==========

    @http.route('/cbm/purchase/get_vendors', type='json', auth='user')
    def get_vendors(self, query='', limit=20):
        """Return vendors for dropdown selection."""
        domain = [('supplier_rank', '>', 0)]
        if query:
            domain.append(('name', 'ilike', query))
        vendors = request.env['res.partner'].sudo().search(domain, limit=limit, order='name')
        return [{'id': v.id, 'name': v.name} for v in vendors]

    @http.route('/cbm/purchase/create_vendor', type='json', auth='user')
    def create_vendor(self, name):
        """Create new vendor on the fly (minimal - just name).
        
        Used in CBM Portal replenishment page for quick vendor creation.
        """
        if not name or len(name.strip()) < 2:
            return {'success': False, 'error': _('Vendor name too short')}
        
        vendor = request.env['res.partner'].sudo().create({
            'name': name.strip(),
            'supplier_rank': 1,
            'company_type': 'company',
        })
        
        _logger.info("CBM Purchase: Created vendor '%s' (ID=%d) for user %s", 
                    vendor.name, vendor.id, request.env.user.name)
        
        return {
            'success': True,
            'vendor_id': vendor.id,
            'vendor_name': vendor.name,
        }

    # ========== Product Endpoints ==========

    @http.route('/cbm/purchase/create_product', type='json', auth='user')
    def create_product(self, name, default_code=None):
        """Create new product using location's default template.
        
        Follows same logic as user access control:
        - Get user's picking type → destination location → default template
        - Apply template defaults to new product
        """
        user = request.env.user
        _, picking_type_id = self._get_user_location_type(user)
        
        if not picking_type_id:
            return {'success': False, 'error': _('No picking type configured for your location')}
        
        picking_type = request.env['stock.picking.type'].sudo().browse(picking_type_id)
        location = picking_type.default_location_dest_id
        
        vals = {
            'name': name,
            'purchase_ok': True,
            'sale_ok': True,
            'type': 'product',  # Default to storable
        }
        if default_code:
            vals['default_code'] = default_code
        
        # Apply template defaults if location has one
        if location and location.default_product_template_id:
            template = location.default_product_template_id
            vals.update({
                'type': template.type,
                'categ_id': template.categ_id.id,
                'tracking': template.tracking,
            })
            if template.uom_id:
                vals['uom_id'] = template.uom_id.id
            if template.uom_po_id:
                vals['uom_po_id'] = template.uom_po_id.id
            if hasattr(template, 'use_expiration_date'):
                vals['use_expiration_date'] = template.use_expiration_date
            
            _logger.info("CBM Purchase: Applying template '%s' from location '%s'", 
                        template.name, location.name)
        
        product = request.env['product.product'].sudo().create(vals)
        
        _logger.info("CBM Purchase: Created product '%s' (ID=%d) for user %s", 
                    product.display_name, product.id, user.name)
        
        return {
            'success': True,
            'product_id': product.id,
            'product_name': product.display_name,
        }

    # ========== Purchase Order Endpoints ==========

    @http.route('/cbm/purchase/get_product_purchase_uoms', type='json', auth='user')
    def get_product_purchase_uoms(self, product_id):
        """Get available purchase UoMs for a product.

        Returns all UoMs in the same category as the product's UoM,
        so users can select vendor-specific UoM (e.g., Box of 10, Box of 50).
        """
        Product = request.env['product.product'].sudo()
        UoM = request.env['uom.uom'].sudo()

        product = Product.browse(product_id)
        if not product.exists():
            return {'success': False, 'error': _('Product not found')}

        # Get all UoMs in the same category as product's base UoM
        category = product.uom_id.category_id
        available_uoms = UoM.search([
            ('category_id', '=', category.id),
            ('active', '=', True),
        ], order='name')

        uom_list = []
        for uom in available_uoms:
            uom_list.append({
                'id': uom.id,
                'name': uom.name,
                'factor': uom.factor,
                'factor_inv': uom.factor_inv,
                'uom_type': uom.uom_type,
                'is_po_default': uom.id == product.uom_po_id.id,
                'is_base': uom.id == product.uom_id.id,
            })

        return {
            'success': True,
            'uoms': uom_list,
            'default_uom_id': product.uom_po_id.id if product.uom_po_id else product.uom_id.id,
            'default_uom_name': product.uom_po_id.name if product.uom_po_id else product.uom_id.name,
        }

    @http.route('/cbm/purchase/create_po', type='json', auth='user')
    def create_po(self, vendor_id, lines, reference=None):
        """Legacy endpoint - redirects to create_po_full."""
        return self.create_po_full(vendor_id, reference or '', lines)

    @http.route('/cbm/purchase/create_po_full', type='json', auth='user')
    def create_po_full(self, vendor_id, reference, lines):
        """Create PO with optional vendor invoice reference.

        Args:
            vendor_id: res.partner ID (required)
            reference: Vendor invoice number (optional, unique per vendor if provided)
            lines: list of {product_id, qty, price, tax_ids (optional), uom_id (optional)}
        """
        user = request.env.user
        
        if not vendor_id:
            return {'success': False, 'error': _('Le fournisseur est obligatoire')}

        # Reference is optional - strip if provided
        reference = reference.strip() if reference else ''

        if not lines:
            return {'success': False, 'error': _('Aucun produit sélectionné')}

        # Don't use sudo() for PO creation to preserve create_uid for chatter tracking
        # User must have purchase rights if they can access CBM portal
        PO = request.env['purchase.order']
        POLine = request.env['purchase.order.line']

        # Check reference uniqueness per vendor (only if reference is provided)
        # Exclude cancelled POs - reference can be reused after cancellation
        if reference:
            existing = PO.sudo().search([
                ('partner_id', '=', vendor_id),
                ('partner_ref', '=', reference),
                ('state', '!=', 'cancel'),
            ], limit=1)

            if existing:
                return {
                    'success': False,
                    'error': _('La référence "%s" existe déjà pour ce fournisseur (BC: %s)') % (reference, existing.name)
                }
        
        # Get user's picking type for the PO
        loc_type, picking_type_id = self._get_user_location_type(user)

        # VALIDATION: Ensure picking type exists - don't allow silent fallback
        if not picking_type_id:
            return {
                'success': False,
                'error': _('Votre compte n\'est pas configuré pour créer des bons de commande. '
                          'Veuillez contacter l\'administrateur pour configurer vos types d\'opérations autorisés.')
            }

        # Set default scheduled date (7 days from now for lead time)
        default_date_planned = fields.Datetime.now() + timedelta(days=7)

        po_vals = {
            'partner_id': vendor_id,
            'state': 'draft',
            'company_id': request.env.company.id,
            'origin': _('Portail CBM'),
            'date_order': fields.Datetime.now(),
            'picking_type_id': picking_type_id,  # Always set (validated above)
        }
        if reference:
            po_vals['partner_ref'] = reference  # Vendor invoice reference (optional)

        po = PO.create(po_vals)

        # Add lines with taxes
        for line_data in lines:
            product = request.env['product.product'].browse(line_data['product_id'])
            if not product.exists():
                continue

            # Get vendor-specific price from supplierinfo
            vendor_price = product.standard_price  # Fallback to standard cost
            supplierinfo = request.env['product.supplierinfo'].sudo().search([
                ('product_tmpl_id', '=', product.product_tmpl_id.id),
                ('partner_id', '=', vendor_id),
            ], order='min_qty, id', limit=1)

            if supplierinfo:
                vendor_price = supplierinfo.price
                _logger.info("CBM Purchase: Using vendor price %.2f for product %s (supplier: %s)",
                            vendor_price, product.display_name, supplierinfo.partner_id.name)

            # Get UoM from frontend or fallback to product's purchase UoM
            uom_id = line_data.get('uom_id')
            if not uom_id:
                uom_id = product.uom_po_id.id if product.uom_po_id else product.uom_id.id

            # Validate UoM is in same category as product's base UoM
            uom = request.env['uom.uom'].browse(uom_id)
            if uom.exists() and uom.category_id != product.uom_id.category_id:
                _logger.warning("CBM Purchase: Invalid UoM %s for product %s (different category)",
                              uom.name, product.display_name)
                uom_id = product.uom_po_id.id if product.uom_po_id else product.uom_id.id

            line_vals = {
                'order_id': po.id,
                'product_id': product.id,
                'product_qty': line_data.get('qty', 1),
                'product_uom': uom_id,
                'price_unit': line_data.get('price', vendor_price),  # Use vendor price
                'name': product.display_name,
                'date_planned': default_date_planned,  # This propagates to picking's scheduled_date
            }

            # Handle taxes if provided
            tax_ids = line_data.get('tax_ids', [])
            if tax_ids:
                line_vals['taxes_id'] = [(6, 0, tax_ids)]

            POLine.create(line_vals)
        
        _logger.info("CBM Purchase: Created PO %s with %d lines, ref=%s, vendor=%s, user=%s", 
                    po.name, len(lines), reference, po.partner_id.name, user.name)
        
        return {
            'success': True,
            'po_id': po.id,
            'po_name': po.name,
            'reference': reference,
            'message': _('Bon de commande %s créé') % po.name,
        }

    @http.route('/cbm/purchase/submit_for_approval', type='json', auth='user')
    def submit_for_approval(self, po_id):
        """Submit draft PO for approval via bracket workflow.
        
        Triggers button_confirm which checks bracket approval requirements.
        """
        PO = request.env['purchase.order'].sudo()
        
        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('Bon de commande non trouvé')}
        
        if po.state != 'draft':
            return {'success': False, 'error': _('Seul un BC en brouillon peut être soumis')}
        
        if not po.order_line:
            return {'success': False, 'error': _('Le BC doit avoir au moins une ligne')}

        try:
            # button_confirm triggers bracket approval workflow
            po.button_confirm()
        except Exception as e:
            _logger.error("CBM Purchase: Failed to confirm PO %s: %s", po.name, str(e))
            # Return success anyway - PO exists, user can retry or check status
            return {
                'success': True,
                'po_id': po.id,
                'po_name': po.name,
                'state': po.state,
                'state_label': dict(po._fields['state'].selection).get(po.state, po.state),
                'approval_info': {},
                'message': _('BC %s créé (vérifiez le statut)') % po.name,
            }

        # Check new state
        new_state = po.state
        state_label = dict(po._fields['state'].selection).get(new_state, new_state)

        # Get approval info if pending (wrapped in try-catch to not fail the response)
        approval_info = {}
        try:
            if new_state == 'to approve':
                bracket = po._find_applicable_bracket() if hasattr(po, '_find_applicable_bracket') else None
                if bracket:
                    approval_info = {
                        'bracket_name': bracket.name,
                        'approvers': list(bracket.approver_ids.mapped('name')),
                    }
        except Exception as e:
            _logger.warning("CBM Purchase: Could not get approval info for PO %s: %s", po.name, str(e))

        _logger.info("CBM Purchase: Submitted PO %s for approval, new state=%s, user=%s",
                    po.name, new_state, request.env.user.name)

        return {
            'success': True,
            'po_id': po.id,
            'po_name': po.name,
            'state': new_state,
            'state_label': state_label,
            'approval_info': approval_info,
            'message': _('BC %s soumis pour approbation') % po.name if new_state == 'to approve'
                      else _('BC %s confirmé') % po.name,
        }

    @http.route('/cbm/purchase/create_and_submit_po', type='json', auth='user')
    def create_and_submit_po(self, vendor_id, reference, lines):
        """Atomic operation - create PO and submit for approval in one transaction.

        This prevents orphan draft POs when submit fails after creation.
        """
        # Create the PO
        create_result = self.create_po_full(vendor_id, reference, lines)

        if not create_result['success']:
            return create_result

        po_id = create_result['po_id']

        # Immediately submit for approval in same transaction
        submit_result = self.submit_for_approval(po_id)

        # Combine results
        return {
            'success': submit_result['success'],
            'po_id': po_id,
            'po_name': create_result['po_name'],
            'state': submit_result.get('state'),
            'state_label': submit_result.get('state_label'),
            'approval_info': submit_result.get('approval_info', {}),
            'message': submit_result.get('message'),
            'error': submit_result.get('error'),
        }

    @http.route('/cbm/purchase/get_approval_status', type='json', auth='user')
    def get_approval_status(self, po_id):
        """Get approval status and bracket info for a PO."""
        PO = request.env['purchase.order'].sudo()
        
        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('BC non trouvé')}
        
        result = {
            'success': True,
            'po_id': po.id,
            'state': po.state,
            'state_label': dict(po._fields['state'].selection).get(po.state, po.state),
            'is_approved': po.state == 'purchase',
            'is_pending': po.state == 'to approve',
            'approval_date': po.date_approve.isoformat() if po.date_approve else None,
        }
        
        # Get bracket info if available
        if hasattr(po, '_find_applicable_bracket'):
            bracket = po._find_applicable_bracket()
            if bracket:
                result['bracket'] = {
                    'name': bracket.name,
                    'approvers': list(bracket.approver_ids.mapped('name')),
                }
        
        return result

    @http.route('/cbm/purchase/get_my_pos', type='json', auth='user')
    def get_my_pos(self, limit=50):
        """Return POs created by current user with dashboard stats.

        Returns:
            {
                'pos': [...],  # List of PO records
                'stats': {     # Dashboard statistics
                    'draft_count': int,
                    'to_approve_count': int,
                    'reception_count': int,
                }
            }
        """
        user = request.env.user
        PO = request.env['purchase.order'].sudo()
        Picking = request.env['stock.picking'].sudo()

        # Get all POs for this user
        pos = PO.search([
            ('create_uid', '=', user.id),
        ], order='create_date desc', limit=limit)

        # Calculate stats
        draft_count = PO.search_count([
            ('create_uid', '=', user.id),
            ('state', '=', 'draft'),
        ])

        to_approve_count = PO.search_count([
            ('create_uid', '=', user.id),
            ('state', '=', 'to approve'),
        ])

        # Count pending receptions from user's POs only
        loc_type, picking_type_id = self._get_user_location_type(user)
        reception_count = 0

        result = []
        for po in pos:
            ready_pickings = po.picking_ids.filtered(lambda p: p.state == 'assigned')
            done_pickings = po.picking_ids.filtered(lambda p: p.state == 'done')

            # Count this PO's receivable pickings for the stats
            if len(ready_pickings) > 0:
                reception_count += 1

            # Determine approval badge type
            approval_badge = None
            if po.state == 'to approve':
                approval_badge = 'waiting'
            elif po.state == 'purchase':
                approval_badge = 'approved'
            elif po.state == 'cancel':
                approval_badge = 'rejected'

            result.append({
                'id': po.id,
                'name': po.name,
                'reference': po.partner_ref or '',  # Vendor invoice reference
                'vendor_name': po.partner_id.name,
                'state': po.state,
                'state_label': dict(po._fields['state'].selection).get(po.state, po.state),
                'approval_badge': approval_badge,
                'date': po.date_order.strftime('%d/%m/%Y') if po.date_order else '',
                'amount_total': po.amount_total,
                'currency_symbol': po.currency_id.symbol or 'DA',
                'can_receive': len(ready_pickings) > 0,
                'picking_id': ready_pickings[0].id if ready_pickings else False,
                'has_done_pickings': len(done_pickings) > 0,
                'done_picking_id': done_pickings[0].id if done_pickings else False,
                'line_count': len(po.order_line),
            })

        return {
            'pos': result,
            'stats': {
                'draft_count': draft_count,
                'to_approve_count': to_approve_count,
                'reception_count': reception_count,
            }
        }

    @http.route('/cbm/purchase/get_po_details', type='json', auth='user')
    def get_po_details(self, po_id):
        """Return PO with lines for editing."""
        PO = request.env['purchase.order'].sudo()

        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('PO not found')}

        lines = []
        for line in po.order_line:
            lines.append({
                'id': line.id,
                'product_id': line.product_id.id,
                'product_name': line.product_id.display_name,
                'product_code': line.product_id.default_code or '',
                'qty': line.product_qty,
                'price': line.price_unit,
                'uom_name': line.product_uom.name,
                'taxes': ', '.join(line.taxes_id.mapped('name')),
                'tax_ids': line.taxes_id.ids,
                'subtotal': line.price_subtotal,
            })

        return {
            'success': True,
            'po': {
                'id': po.id,
                'name': po.name,
                'vendor_id': po.partner_id.id,
                'vendor_name': po.partner_id.name,
                'reference': po.partner_ref or '',
                'state': po.state,
                'state_label': dict(po._fields['state'].selection).get(po.state, po.state),
                'amount_total': po.amount_total,
                'currency_symbol': po.currency_id.symbol or 'DA',
            },
            'lines': lines,
        }

    @http.route('/cbm/purchase/get_purchase_taxes', type='json', auth='user')
    def get_purchase_taxes(self):
        """Get available purchase taxes for current company."""
        company = request.env.company
        taxes = request.env['account.tax'].sudo().search([
            ('type_tax_use', '=', 'purchase'),
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], order='sequence, name')

        return {
            'success': True,
            'taxes': [{'id': t.id, 'name': t.name, 'amount': t.amount} for t in taxes]
        }

    @http.route('/cbm/purchase/confirm_po', type='json', auth='user')
    def confirm_po(self, po_id):
        """Confirm draft PO and send for approval."""
        PO = request.env['purchase.order'].sudo()

        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('PO not found')}

        if po.state != 'draft':
            return {'success': False, 'error': _('Only draft POs can be confirmed')}

        if not po.order_line:
            return {'success': False, 'error': _('Cannot confirm PO without lines')}

        try:
            po.button_confirm()
            _logger.info("CBM Purchase: PO %s confirmed by %s", po.name, request.env.user.name)

            return {
                'success': True,
                'message': _('PO %s confirmed') % po.name,
                'new_state': po.state,
            }
        except Exception as e:
            _logger.error("CBM Purchase: Failed to confirm PO %s: %s", po.name, str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/cbm/purchase/delete_po', type='json', auth='user')
    def delete_po(self, po_id):
        """Delete draft PO."""
        PO = request.env['purchase.order'].sudo()

        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('PO not found')}

        if po.state != 'draft':
            return {'success': False, 'error': _('Only draft POs can be deleted')}

        try:
            po_name = po.name
            po.unlink()
            _logger.info("CBM Purchase: PO %s deleted by %s", po_name, request.env.user.name)

            return {
                'success': True,
                'message': _('PO %s deleted') % po_name,
            }
        except Exception as e:
            _logger.error("CBM Purchase: Failed to delete PO %s: %s", po.name, str(e))
            return {'success': False, 'error': str(e)}

    @http.route('/cbm/purchase/update_po_line', type='json', auth='user')
    def update_po_line(self, line_id, field, value):
        """Update a single field on a PO line (auto-save)."""
        POLine = request.env['purchase.order.line'].sudo()

        line = POLine.browse(line_id)
        if not line.exists():
            return {'success': False, 'error': _('Line not found')}

        if line.order_id.state != 'draft':
            return {'success': False, 'error': _('Only draft POs can be edited')}

        allowed_fields = {'product_qty': float, 'price_unit': float, 'taxes_id': 'taxes'}

        if field not in allowed_fields:
            return {'success': False, 'error': _('Field not editable')}

        try:
            if field == 'taxes_id':
                tax_ids = [int(x) for x in value] if value else []
                line.write({'taxes_id': [(6, 0, tax_ids)]})
            else:
                typed_value = allowed_fields[field](value)
                line.write({field: typed_value})

            return {
                'success': True,
                'line': {
                    'id': line.id,
                    'qty': line.product_qty,
                    'price': line.price_unit,
                    'subtotal': line.price_subtotal,
                    'taxes': ', '.join(line.taxes_id.mapped('name')),
                    'tax_ids': line.taxes_id.ids,
                },
                'po_total': line.order_id.amount_total,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/cbm/purchase/add_po_line', type='json', auth='user')
    def add_po_line(self, po_id, product_id, qty=1, price=0):
        """Add a new line to PO."""
        PO = request.env['purchase.order'].sudo()
        Product = request.env['product.product'].sudo()

        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('PO not found')}

        if po.state != 'draft':
            return {'success': False, 'error': _('Only draft POs can be edited')}

        product = Product.browse(product_id)
        if not product.exists():
            return {'success': False, 'error': _('Product not found')}

        if price <= 0:
            price = product.standard_price or 0

        try:
            line = request.env['purchase.order.line'].sudo().create({
                'order_id': po.id,
                'product_id': product.id,
                'product_qty': qty,
                'price_unit': price,
                'name': product.display_name,
                'product_uom': product.uom_po_id.id or product.uom_id.id,
                'date_planned': po.date_order or fields.Datetime.now(),
                'taxes_id': [(5, 0, 0)],
            })

            return {
                'success': True,
                'line': {
                    'id': line.id,
                    'product_id': product.id,
                    'product_name': product.display_name,
                    'product_code': product.default_code or '',
                    'qty': line.product_qty,
                    'price': line.price_unit,
                    'uom_name': line.product_uom.name,
                    'taxes': ', '.join(line.taxes_id.mapped('name')),
                    'tax_ids': line.taxes_id.ids,
                    'subtotal': line.price_subtotal,
                },
                'po_total': po.amount_total,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/cbm/purchase/remove_po_line', type='json', auth='user')
    def remove_po_line(self, line_id):
        """Remove a line from PO."""
        POLine = request.env['purchase.order.line'].sudo()

        line = POLine.browse(line_id)
        if not line.exists():
            return {'success': False, 'error': _('Line not found')}

        if line.order_id.state != 'draft':
            return {'success': False, 'error': _('Only draft POs can be edited')}

        po = line.order_id

        try:
            line.unlink()
            return {
                'success': True,
                'po_total': po.amount_total,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/cbm/purchase/update_po_vendor', type='json', auth='user')
    def update_po_vendor(self, po_id, vendor_id):
        """Change PO vendor."""
        PO = request.env['purchase.order'].sudo()
        Partner = request.env['res.partner'].sudo()

        po = PO.browse(po_id)
        if not po.exists():
            return {'success': False, 'error': _('PO not found')}

        if po.state != 'draft':
            return {'success': False, 'error': _('Only draft POs can be edited')}

        vendor = Partner.browse(vendor_id)
        if not vendor.exists():
            return {'success': False, 'error': _('Vendor not found')}

        try:
            po.write({'partner_id': vendor_id})
            return {
                'success': True,
                'vendor_id': vendor.id,
                'vendor_name': vendor.name,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ========== Reception Endpoints ==========

    @http.route('/cbm/purchase/get_pending_receptions', type='json', auth='user')
    def get_pending_receptions(self, limit=50, include_done=False):
        """Return pickings ready to receive (from approved POs).

        Args:
            limit: Max number of results
            include_done: If True, also return recently completed receptions (last 7 days)
        """
        user = request.env.user
        Picking = request.env['stock.picking'].sudo()

        # Get user's incoming picking type
        loc_type, picking_type_id = self._get_user_location_type(user)

        if loc_type != 'reception' or not picking_type_id:
            return {'pickings': [], 'error': _('No reception location configured')}

        # Build domain based on include_done flag
        if include_done:
            # Include done receptions from last 7 days
            from datetime import datetime, timedelta
            seven_days_ago = datetime.now() - timedelta(days=7)
            domain = [
                ('picking_type_id', '=', picking_type_id),
                '|',
                    ('state', 'in', ['assigned', 'waiting', 'confirmed']),
                    '&',
                        ('state', '=', 'done'),
                        ('write_date', '>=', seven_days_ago),
            ]
        else:
            # Only pending receptions
            domain = [
                ('picking_type_id', '=', picking_type_id),
                ('state', 'in', ['assigned', 'waiting', 'confirmed']),
            ]

        # Find pickings (newest first)
        pickings = Picking.search(domain, order='scheduled_date desc', limit=limit)
        
        result = []
        for picking in pickings:
            result.append({
                'id': picking.id,
                'name': picking.name,
                'origin': picking.origin or '',
                'partner_name': picking.partner_id.name if picking.partner_id else '',
                'scheduled_date': picking.scheduled_date.isoformat() if picking.scheduled_date else '',
                'state': picking.state,
                'state_label': dict(picking._fields['state'].selection).get(picking.state, picking.state),
                'line_count': len(picking.move_ids),
                'po_name': picking.purchase_id.name if picking.purchase_id else '',
            })
        
        return {'pickings': result}

    @http.route('/cbm/purchase/get_reception_details', type='json', auth='user')
    def get_reception_details(self, picking_id):
        """Return picking lines with lot/expiry info for reception form."""
        Picking = request.env['stock.picking'].sudo()
        
        picking = Picking.browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': _('Picking not found')}
        
        lines = []
        for move in picking.move_ids:
            # Get or create move lines
            move_lines = move.move_line_ids
            if not move_lines:
                # Create initial move line for this move
                move_lines = request.env['stock.move.line'].sudo().create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'location_id': move.location_id.id,
                    'location_dest_id': move.location_dest_id.id,
                    'qty_done': 0,
                })
            
            for line in move_lines:
                # Get PO line price for display/editing
                po_line = move.purchase_line_id
                price_unit = po_line.price_unit if po_line else 0.0

                lines.append({
                    'id': line.id,
                    'move_id': move.id,
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'product_tracking': line.product_id.tracking,
                    'expected_qty': move.product_uom_qty,
                    'qty_done': line.qty_done,
                    'uom_name': move.product_uom.name,
                    'uom_id': move.product_uom.id,
                    'price_unit': price_unit,
                    'lot_id': line.lot_id.id if line.lot_id else False,
                    'lot_name': line.lot_id.name if line.lot_id else '',
                    'expiration_date': line.lot_id.expiration_date.isoformat() if line.lot_id and line.lot_id.expiration_date else '',
                })
        
        return {
            'success': True,
            'picking': {
                'id': picking.id,
                'name': picking.name,
                'origin': picking.origin or '',
                'partner_name': picking.partner_id.name if picking.partner_id else '',
                'po_name': picking.purchase_id.name if picking.purchase_id else '',
                'scheduled_date': picking.scheduled_date.isoformat() if picking.scheduled_date else '',
            },
            'lines': lines,
        }

    @http.route('/cbm/purchase/generate_lots', type='json', auth='user')
    def generate_lots(self, picking_id):
        """Generate NEW lots for all products in picking (Custom Portal Logic).
        
        Unlike product_barcode module, this ALWAYS creates a new lot per reception
        to ensure fresh expiration dates.
        """
        Picking = request.env['stock.picking'].sudo()
        Lot = request.env['stock.lot'].sudo()
        MoveLine = request.env['stock.move.line'].sudo()
        
        picking = Picking.browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': _('Picking not found')}
        
        try:
            count_created = 0
            
            for move in picking.move_ids_without_package:
                product = move.product_id
                
                # Enable tracking if needed
                if product.tracking == 'none':
                    product.product_tmpl_id.tracking = 'lot'
                
                # ALWAYS create new lot for this reception
                # Naming: LOT-{code}-{picking_id} to ensure uniqueness per reception
                lot_name = f"LOT-{product.default_code or product.id}-{picking.id}"
                
                # Check if we already created it for THIS picking (idempotency)
                lot = Lot.search([
                    ('name', '=', lot_name),
                    ('product_id', '=', product.id),
                    ('company_id', '=', picking.company_id.id)
                ], limit=1)
                
                if not lot:
                    # New lot with fresh expiration (3 years)
                    expiration_date = fields.Datetime.now() + timedelta(days=365 * 3)
                    lot = Lot.create({
                        'name': lot_name,
                        'product_id': product.id,
                        'company_id': picking.company_id.id,
                        'expiration_date': expiration_date,
                    })
                    count_created += 1
                
                # Assign to move lines
                if move.move_line_ids:
                    for ml in move.move_line_ids:
                        if not ml.lot_id:
                            ml.write({'lot_id': lot.id})
                else:
                    # Create move line if none exists
                    MoveLine.create({
                        'move_id': move.id,
                        'picking_id': picking.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'lot_id': lot.id,
                        'qty_done': move.product_uom_qty,
                    })
            
            # Reload lines data
            lines = []
            for move in picking.move_ids:
                for line in move.move_line_ids:
                    lines.append({
                        'id': line.id,
                        'move_id': move.id,
                        'product_id': line.product_id.id,
                        'product_name': line.product_id.display_name,
                        'product_tracking': line.product_id.tracking,
                        'expected_qty': move.product_uom_qty,
                        'qty_done': line.qty_done,
                        'uom_name': move.product_uom.name,
                        'lot_id': line.lot_id.id if line.lot_id else False,
                        'lot_name': line.lot_id.name if line.lot_id else '',
                        'expiration_date': line.lot_id.expiration_date.isoformat() if line.lot_id and line.lot_id.expiration_date else '',
                    })
            
            return {
                'success': True,
                'message': _('Generated %d new lots') % count_created,
                'lines': lines,
            }
        except Exception as e:
            _logger.error("CBM Purchase: Failed to generate lots for %s: %s", picking.name, str(e))
            return {'success': False, 'error': str(e)}

    def _create_vendor_bill_from_po(self, po):
        """Create a vendor bill from a purchase order with proper invoice lines.

        Uses Odoo's standard purchase.order method if available, otherwise
        manually creates the bill with lines.

        Args:
            po: purchase.order record

        Returns:
            account.move record or False
        """
        try:
            AccountMove = request.env['account.move'].sudo()

            # Build invoice lines from PO lines
            invoice_lines = []
            for line in po.order_line:
                # Skip lines without product or zero qty
                if not line.product_id or line.product_qty <= 0:
                    continue

                # Get the account for the product
                accounts = line.product_id.product_tmpl_id.get_product_accounts(fiscal_pos=po.fiscal_position_id)
                expense_account = accounts.get('expense') or accounts.get('stock_input')

                if not expense_account:
                    # Fallback to category account
                    expense_account = line.product_id.categ_id.property_account_expense_categ_id

                line_vals = {
                    'name': line.name or line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom.id,
                    'quantity': line.product_qty,
                    'price_unit': line.price_unit,
                    'purchase_line_id': line.id,
                    'tax_ids': [(6, 0, line.taxes_id.ids)] if line.taxes_id else [],
                }

                if expense_account:
                    line_vals['account_id'] = expense_account.id

                invoice_lines.append((0, 0, line_vals))

            if not invoice_lines:
                _logger.warning("CBM Purchase: No valid lines to create bill for PO %s", po.name)
                return False

            # Create the vendor bill
            bill_vals = {
                'move_type': 'in_invoice',
                'partner_id': po.partner_id.id,
                'purchase_id': po.id,
                'ref': po.partner_ref or po.name,
                'invoice_date': fields.Date.today(),
                'invoice_origin': po.name,
                'invoice_line_ids': invoice_lines,
                'currency_id': po.currency_id.id,
                'company_id': po.company_id.id,
            }

            # Set fiscal position if present
            if po.fiscal_position_id:
                bill_vals['fiscal_position_id'] = po.fiscal_position_id.id

            bill = AccountMove.create(bill_vals)

            _logger.info("CBM Purchase: Created vendor bill %s with %d lines from PO %s",
                        bill.name, len(invoice_lines), po.name)

            return bill

        except Exception as e:
            _logger.error("CBM Purchase: Failed to create vendor bill from PO %s: %s",
                         po.name, str(e), exc_info=True)
            return False

    def _generate_and_attach_bill_pdf(self, bill):
        """Generate PDF for vendor bill using custom report and attach it.

        Creates a new PDF each time this is called (on validation or correction).
        Users in CBM portal see only the latest PDF.
        Responsible users in Odoo interface see all PDFs (versioned by timestamp).

        Args:
            bill: account.move record (vendor bill)

        Returns:
            attachment record or False
        """
        try:
            # Try custom report first, fall back to standard invoice report
            report = None
            try:
                report = request.env.ref('serenvale_custom_invoice_print.action_report_clinic_invoice').sudo()
            except ValueError:
                _logger.info("CBM Purchase: Custom invoice report not found, using standard report")
                try:
                    report = request.env.ref('account.account_invoices').sudo()
                except ValueError:
                    _logger.warning("CBM Purchase: No invoice report available")
                    return False

            if not report:
                return False

            # Generate PDF content
            pdf_content, _ = report._render_qweb_pdf(bill.ids)

            # Create timestamp for filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{bill.name.replace('/', '_')}_{timestamp}.pdf"

            # Encode PDF to base64
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')

            # Create attachment
            attachment = request.env['ir.attachment'].sudo().create({
                'name': filename,
                'type': 'binary',
                'datas': pdf_base64,
                'res_model': 'account.move',
                'res_id': bill.id,
                'mimetype': 'application/pdf',
                'description': f'Facture fournisseur générée automatiquement le {timestamp}',
            })

            _logger.info("CBM Purchase: Generated PDF %s for vendor bill %s", filename, bill.name)
            return attachment

        except Exception as e:
            _logger.error("CBM Purchase: Failed to generate PDF for bill %s: %s",
                         bill.name, str(e), exc_info=True)
            return False

    @http.route('/cbm/purchase/validate_reception', type='json', auth='user')
    def validate_reception(self, picking_id, lines):
        """Validate reception with lot/expiry and optional price update per line.

        Args:
            picking_id: stock.picking ID
            lines: [{move_line_id, qty_done, lot_name, expiration_date, price_unit (optional)}]
        """
        from datetime import datetime, timedelta

        Picking = request.env['stock.picking'].sudo()
        MoveLine = request.env['stock.move.line'].sudo()
        Lot = request.env['stock.lot'].sudo()

        picking = Picking.browse(picking_id)
        if not picking.exists():
            return {'success': False, 'error': _('Picking not found')}

        _logger.info("CBM Purchase: Starting validation of reception %s (state: %s, PO: %s)",
                    picking.name, picking.state, picking.origin)

        min_expiry_date = datetime.now().date() + timedelta(days=30)

        # Process each line
        for line_data in lines:
            line = MoveLine.browse(line_data.get('move_line_id'))
            if not line.exists():
                continue

            qty_done = line_data.get('qty_done', 0)
            lot_name = line_data.get('lot_name', '')
            expiration_date_str = line_data.get('expiration_date', '')
            price_unit = line_data.get('price_unit')  # Optional price update

            _logger.info("CBM Purchase: Processing line %s - product=%s, qty=%s, lot=%s, expiry=%s, price=%s",
                        line.id, line.product_id.display_name, qty_done, lot_name, expiration_date_str, price_unit)

            # Validate expiration date (minimum 30 days)
            if expiration_date_str:
                try:
                    expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d').date()
                    if expiration_date < min_expiry_date:
                        return {
                            'success': False,
                            'error': _('Product %s: expiration date must be at least 30 days from today') % line.product_id.display_name
                        }
                except ValueError as e:
                    _logger.error("CBM Purchase: Invalid expiration date format '%s': %s",
                                expiration_date_str, str(e))
                    return {
                        'success': False,
                        'error': _('Invalid expiration date format for %s (expected YYYY-MM-DD)') % line.product_id.display_name
                    }

            # Handle lot for tracked products
            lot = None
            if line.product_id.tracking != 'none':
                # Lot is REQUIRED for tracked products with quantity
                if qty_done > 0 and not lot_name:
                    return {
                        'success': False,
                        'error': _('Produit %s: le numéro de lot est obligatoire') % line.product_id.display_name
                    }

                if lot_name:
                    # Find or create lot
                    lot = Lot.search([
                        ('name', '=', lot_name),
                        ('product_id', '=', line.product_id.id),
                        ('company_id', '=', picking.company_id.id),
                    ], limit=1)

                    if not lot:
                        lot_vals = {
                            'name': lot_name,
                            'product_id': line.product_id.id,
                            'company_id': picking.company_id.id,
                        }
                        if expiration_date_str:
                            lot_vals['expiration_date'] = expiration_date_str
                        lot = Lot.create(lot_vals)
                        _logger.info("CBM Purchase: Created new lot %s for product %s",
                                    lot_name, line.product_id.display_name)
                    elif expiration_date_str and not lot.expiration_date:
                        lot.write({'expiration_date': expiration_date_str})
                        _logger.info("CBM Purchase: Updated expiration date for lot %s", lot_name)

            # Update move line
            update_vals = {'qty_done': qty_done}
            if lot:
                update_vals['lot_id'] = lot.id
            line.write(update_vals)

            # Update PO line price if provided (allows price correction during reception)
            if price_unit is not None and price_unit >= 0:
                po_line = line.move_id.purchase_line_id
                if po_line and po_line.exists():
                    old_price = po_line.price_unit
                    if old_price != price_unit:
                        po_line.sudo().write({'price_unit': price_unit})
                        _logger.info("CBM Purchase: Updated PO line price from %.2f to %.2f for product %s",
                                   old_price, price_unit, line.product_id.display_name)

        # Validate the picking (triggers UoM conversion + vendor bill)
        try:
            # Log all move lines before validation
            _logger.info("CBM Purchase: Pre-validation check for picking %s:", picking.name)
            for move in picking.move_ids:
                _logger.info("  Move %s: product=%s, demand=%s, state=%s",
                           move.id, move.product_id.display_name, move.product_uom_qty, move.state)
                for ml in move.move_line_ids:
                    _logger.info("    MoveLine %s: qty_done=%s, lot=%s",
                               ml.id, ml.qty_done, ml.lot_id.name if ml.lot_id else 'None')

            _logger.info("CBM Purchase: Calling button_validate on picking %s", picking.name)
            result = picking.with_context(skip_immediate_transfer=True).button_validate()

            _logger.info("CBM Purchase: button_validate returned: %s", result)

            # Handle wizard if returned
            if isinstance(result, dict) and 'res_model' in result:
                wizard_model = result.get('res_model')
                wizard_context = result.get('context', {})

                if wizard_model == 'stock.picking.validate.wizard':
                    _logger.info("CBM Purchase: Handling stock.picking.validate.wizard")
                    # Create wizard from context (no res_id in action dict)
                    wizard = request.env['stock.picking.validate.wizard'].sudo().with_context(**wizard_context).create({
                        'picking_id': wizard_context.get('default_picking_id'),
                    })
                    wizard.btn_confirm()  # This wizard uses btn_confirm
                elif wizard_model == 'stock.backorder.confirmation':
                    _logger.info("CBM Purchase: Handling backorder confirmation wizard")
                    wizard_id = result.get('res_id')
                    wizard = request.env['stock.backorder.confirmation'].sudo().browse(wizard_id)
                    wizard.process()
                else:
                    _logger.warning("CBM Purchase: Unexpected wizard returned: %s", wizard_model)

            # Reload picking to get updated state
            picking = Picking.browse(picking_id)
            final_state = picking.state

            _logger.info("CBM Purchase: Validated reception %s - final state: %s, user: %s",
                        picking.name, final_state, request.env.user.name)

            # Verify the picking is actually done
            if final_state != 'done':
                _logger.warning("CBM Purchase: Picking %s validation completed but state is %s (not 'done')",
                              picking.name, final_state)
                # Log move states to understand why
                for move in picking.move_ids:
                    _logger.warning("  Move %s state: %s (demand: %s, done: %s)",
                                  move.id, move.state, move.product_uom_qty,
                                  sum(ml.qty_done for ml in move.move_line_ids))

            # Generate vendor bill if picking is done
            bill_name = None
            if final_state == 'done':
                po = picking.purchase_id
                if po and po.exists():
                    try:
                        # Check if a bill already exists for this PO
                        existing_bill = request.env['account.move'].sudo().search([
                            ('purchase_id', '=', po.id),
                            ('move_type', '=', 'in_invoice'),
                        ], limit=1)

                        if not existing_bill:
                            # Use Odoo's standard action_create_invoice method
                            # This properly creates the bill with all lines
                            bill = self._create_vendor_bill_from_po(po)
                            if bill:
                                bill_name = bill.name
                                _logger.info("CBM Purchase: Created draft vendor bill %s for PO %s",
                                           bill_name, po.name)

                                # Generate and attach PDF
                                self._generate_and_attach_bill_pdf(bill)
                            else:
                                _logger.warning("CBM Purchase: Could not create vendor bill for PO %s", po.name)
                        else:
                            bill = existing_bill
                            bill_name = existing_bill.name
                            _logger.info("CBM Purchase: Vendor bill %s already exists for PO %s",
                                       bill_name, po.name)

                            # Regenerate PDF since reception was validated
                            self._generate_and_attach_bill_pdf(bill)
                    except Exception as bill_error:
                        _logger.error("CBM Purchase: Failed to create vendor bill for %s: %s",
                                    po.name, str(bill_error), exc_info=True)
                        # Don't fail the whole operation if bill creation fails

            return {
                'success': True,
                'message': _('Reception %s validated successfully') % picking.name,
                'picking_state': final_state,
                'picking_name': picking.name,
                'bill_name': bill_name,
            }
        except Exception as e:
            _logger.error("CBM Purchase: Failed to validate reception %s: %s", picking.name, str(e), exc_info=True)
            return {
                'success': False,
                'error': _('Erreur lors de la validation: %s') % str(e)
            }

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

            # Regenerate PDF for vendor bill after corrections
            po = picking.purchase_id
            if po and po.exists():
                bill = request.env['account.move'].sudo().search([
                    ('purchase_id', '=', po.id),
                    ('move_type', '=', 'in_invoice'),
                ], limit=1)
                if bill and bill.exists():
                    self._generate_and_attach_bill_pdf(bill)
                    _logger.info("CBM Correction: Regenerated PDF for vendor bill %s", bill.name)

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

    @http.route('/cbm/purchase/get_bill_pdf', type='http', auth='user')
    def get_bill_pdf(self, picking_id):
        """Download the latest PDF for the vendor bill associated with a picking.

        This endpoint returns the most recent PDF attachment.
        Users in CBM portal see only this latest version.
        Responsible users in Odoo interface can see all historical PDFs.

        Args:
            picking_id: Stock picking ID

        Returns:
            PDF file download or error
        """
        try:
            picking = request.env['stock.picking'].sudo().browse(int(picking_id))
            if not picking.exists():
                return request.make_response("Picking not found", headers={'Content-Type': 'text/plain'})

            po = picking.purchase_id
            if not po or not po.exists():
                return request.make_response("No PO found for this picking", headers={'Content-Type': 'text/plain'})

            # Find vendor bill
            bill = request.env['account.move'].sudo().search([
                ('purchase_id', '=', po.id),
                ('move_type', '=', 'in_invoice'),
            ], limit=1)

            if not bill or not bill.exists():
                return request.make_response("No vendor bill found", headers={'Content-Type': 'text/plain'})

            # Get latest PDF attachment (sorted by create_date desc)
            attachment = request.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', bill.id),
                ('mimetype', '=', 'application/pdf'),
            ], order='create_date desc', limit=1)

            if not attachment or not attachment.exists():
                # Generate PDF if none exists
                attachment = self._generate_and_attach_bill_pdf(bill)
                if not attachment:
                    return request.make_response("Failed to generate PDF", headers={'Content-Type': 'text/plain'})

            # Return PDF
            import base64
            pdf_data = base64.b64decode(attachment.datas)

            return request.make_response(
                pdf_data,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', f'attachment; filename="{attachment.name}"'),
                    ('Content-Length', len(pdf_data)),
                ]
            )

        except Exception as e:
            _logger.error("CBM Purchase: Failed to get bill PDF for picking %s: %s",
                         picking_id, str(e), exc_info=True)
            return request.make_response(f"Error: {str(e)}", headers={'Content-Type': 'text/plain'})
