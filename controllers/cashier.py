# -*- coding: utf-8 -*-
"""
Cashier Module Controller

Handles all /cbm/cashier/* endpoints for:
- Search quotations/invoices
- Validate quotations (Happy Path)
- Pay remainder (Orange cards)
- Convention split calculations
"""
import logging
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class CBMCashierController(http.Controller):
    """HTTP Controllers for CBM Cashier Module"""
    
    # ==================== SEARCH ====================
    
    @http.route('/cbm/cashier/search', type='json', auth='user')
    def search(self, query='', limit=20):
        """
        Search quotations and invoices for cashier tile.
        
        Only returns:
        - Quotations with service-type products only (no stockables)
        - Invoices linked to such quotations
        
        Returns traffic light color codes:
        - blue: Quotation (draft) - needs validation
        - orange: Invoice (posted, unpaid) - needs payment
        - green: Invoice (posted, paid) - print receipt
        - red: Invoice (cancelled/reversed)
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied', 'results': []}
        
        results = []
        query = query.strip()
        
        # Determine if we should show today's records (default view) or search
        today = fields.Date.context_today(request.env.user)
        is_default_view = not query or len(query) < 2
        
        SaleOrder = request.env['sale.order'].sudo()
        AccountMove = request.env['account.move'].sudo()
        
        if is_default_view:
            # Default view: show quotations created OR modified today
            order_domain = [
                ('state', '=', 'draft'),
                '|',
                ('create_date', '>=', today),
                ('write_date', '>=', today),
            ]
        else:
            # Search view: build domain based on query
            order_domain = [
                ('state', '=', 'draft'),
                '|', '|', '|',
                ('name', 'ilike', query),
                ('partner_id.name', 'ilike', query),
                ('partner_id.phone', 'ilike', query),
                ('partner_id.ref', 'ilike', query),
            ]
        
        # Search quotations
        quotations = SaleOrder.search(
            order_domain,
            limit=limit,
            order='write_date desc'
        )
        
        if is_default_view:
            # Default view: show invoices created OR modified today
            invoice_domain = [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                '|',
                ('create_date', '>=', today),
                ('write_date', '>=', today),
            ]
        else:
            # Search view: build domain based on query
            invoice_domain = [
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                '|', '|', '|',
                ('name', 'ilike', query),
                ('partner_id.name', 'ilike', query),
                ('partner_id.phone', 'ilike', query),
                ('partner_id.ref', 'ilike', query),
            ]
        
        invoices = AccountMove.search(
            invoice_domain,
            limit=limit,
            order='write_date desc'
        )
        
        # Filter to services-only quotations
        for order in quotations:
            has_stockable = any(
                line.product_id.type != 'service' 
                for line in order.order_line 
                if line.product_id and not line.display_type
            )
            if has_stockable:
                continue
            
            # Get convention info from pricelist
            convention_name = None
            convention_pct = None
            if hasattr(order.pricelist_id, 'convention_coverage_pct') and order.pricelist_id.convention_coverage_pct > 0:
                convention_name = order.pricelist_id.name
                convention_pct = order.pricelist_id.convention_coverage_pct
            
            results.append({
                'type': 'quotation',
                'id': order.id,
                'name': order.name,
                'partner_id': order.partner_id.id,
                'partner_name': order.partner_id.name,
                'partner_ref': order.partner_id.ref or '',
                'date': order.date_order.strftime('%d/%m/%Y') if order.date_order else '',
                'amount_total': order.amount_total,
                'amount_residual': 0,
                'state': order.state,
                'convention_name': convention_name,
                'convention_pct': convention_pct,
                'color': 'blue',
            })

        # Process invoices (already loaded above based on query/today)
        for invoice in invoices:
            # Check if originated from services-only sale order
            if invoice.invoice_origin:
                origin_order = SaleOrder.search([('name', '=', invoice.invoice_origin)], limit=1)
                if origin_order:
                    has_stockable = any(
                        line.product_id.type != 'service' 
                        for line in origin_order.order_line 
                        if line.product_id and not line.display_type
                    )
                    if has_stockable:
                        continue
            
            # Determine color
            if invoice.state == 'cancel' or invoice.payment_state == 'reversed':
                color = 'red'
            elif invoice.payment_state in ('paid', 'in_payment'):
                color = 'green'
            else:
                color = 'orange'
            
            # Get convention info
            convention_name = None
            convention_pct = None
            if invoice.invoice_origin:
                origin_order = SaleOrder.search([('name', '=', invoice.invoice_origin)], limit=1)
                if origin_order and hasattr(origin_order.pricelist_id, 'convention_coverage_pct'):
                    if origin_order.pricelist_id.convention_coverage_pct > 0:
                        convention_name = origin_order.pricelist_id.name
                        convention_pct = origin_order.pricelist_id.convention_coverage_pct
            
            results.append({
                'type': 'invoice',
                'id': invoice.id,
                'name': invoice.name,
                'partner_id': invoice.partner_id.id,
                'partner_name': invoice.partner_id.name,
                'partner_ref': invoice.partner_id.ref or '',
                'date': invoice.invoice_date.strftime('%d/%m/%Y') if invoice.invoice_date else '',
                'amount_total': invoice.amount_total,
                'amount_residual': invoice.amount_residual,
                'state': invoice.state,
                'payment_state': invoice.payment_state,
                'convention_name': convention_name,
                'convention_pct': convention_pct,
                'color': color,
            })
        
        # Sort by date desc
        results.sort(key=lambda x: x['date'], reverse=True)
        
        return {'results': results[:limit]}
    
    # ==================== ACCESS CHECK ====================
    
    @http.route('/cbm/cashier/check_access', type='json', auth='user')
    def check_access(self):
        """Check if current user has cashier access."""
        has_access = request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier')
        return {'has_access': has_access}
    
    # ==================== SPLIT CALCULATION ====================
    
    @http.route('/cbm/cashier/get_split', type='json', auth='user')
    def get_split(self, order_id, pricelist_id=None):
        """
        Calculate convention split for a quotation.
        Returns the patient share vs convention share based on pricelist.
        
        Args:
            order_id: Sale order ID
            pricelist_id: Optional - use this pricelist for calculation instead of order's
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        SaleOrder = request.env['sale.order'].sudo()
        order = SaleOrder.browse(order_id)
        
        if not order.exists():
            return {'error': 'Quotation not found'}
        
        # Use provided pricelist or order's default
        if pricelist_id:
            pricelist = request.env['product.pricelist'].sudo().browse(pricelist_id)
            if not pricelist.exists():
                pricelist = order.pricelist_id
        else:
            pricelist = order.pricelist_id
        
        amount_total = order.amount_total
        
        # Get order lines (exclude display-only lines and down payment lines with qty=0)
        lines = []
        for line in order.order_line.filtered(lambda ln: not ln.display_type):
            # Skip down payment lines with qty=0 (leftover from previous partial invoices)
            if line.product_uom_qty <= 0:
                continue
            # Skip down payment products (is_downpayment flag or name pattern)
            if getattr(line, 'is_downpayment', False):
                continue
            lines.append({
                'name': line.product_id.name or line.name,
                'qty': line.product_uom_qty,
                'price_unit': line.price_unit,
                'price_subtotal': line.price_subtotal,
            })
        
        # Check if pricelist has convention coverage
        has_convention = (
            hasattr(pricelist, 'convention_coverage_pct') 
            and pricelist.convention_coverage_pct > 0
        )
        
        if has_convention:
            convention_pct = pricelist.convention_coverage_pct
            convention_share = amount_total * (convention_pct / 100)
            patient_share = amount_total - convention_share
            
            return {
                'has_convention': True,
                'convention_name': pricelist.name,
                'convention_pct': convention_pct,
                'payer_partner_id': pricelist.payer_partner_id.id if pricelist.payer_partner_id else None,
                'payer_name': pricelist.payer_partner_id.name if pricelist.payer_partner_id else None,
                'amount_total': amount_total,
                'patient_share': patient_share,
                'convention_share': convention_share,
                'lines': lines,
            }
        
        return {
            'has_convention': False,
            'amount_total': amount_total,
            'patient_share': amount_total,
            'convention_share': 0,
            'lines': lines,
        }
    
    @http.route('/cbm/cashier/get_pricelists', type='json', auth='user')
    def get_pricelists(self):
        """Get all available pricelists for convention selection."""
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        Pricelist = request.env['product.pricelist'].sudo()
        pricelists = Pricelist.search([('active', '=', True)])
        
        result = []
        for pl in pricelists:
            convention_pct = getattr(pl, 'convention_coverage_pct', 0) or 0
            payer_name = pl.payer_partner_id.name if hasattr(pl, 'payer_partner_id') and pl.payer_partner_id else None
            
            result.append({
                'id': pl.id,
                'name': pl.name,
                'convention_pct': convention_pct,
                'payer_name': payer_name,
                'is_convention': convention_pct > 0,
            })
        
        # Sort: conventions first, then by name
        result.sort(key=lambda x: (-x['convention_pct'], x['name']))
        
        return {'pricelists': result}
    
    # ==================== VALIDATION (BLUE CARDS) ====================
    
    @http.route('/cbm/cashier/validate', type='json', auth='user')
    def validate(self, order_id, payment_method='cash', amount=None, pricelist_id=None):
        """
        Validate quotation, create invoice, register payment(s).

        Args:
            order_id: Sale order ID
            payment_method: 'cash' or 'card'
            amount: Optional - partial payment amount. If None, pays full amount.
            pricelist_id: Optional - apply this pricelist before validation.

        Happy Path flow:
        1. Apply pricelist if provided
        2. Confirm sale order
        3. Create invoice
        4. Post invoice
        5. Register patient payment (full or partial)
        6. Register convention payment if applicable
        """
        # DEBUG: Log received parameters
        _logger.info("=" * 80)
        _logger.info("[CBM VALIDATE] RECEIVED PARAMS:")
        _logger.info("[CBM VALIDATE]   order_id=%s, type=%s", order_id, type(order_id))
        _logger.info("[CBM VALIDATE]   amount=%s, type=%s", amount, type(amount))
        _logger.info("[CBM VALIDATE]   payment_method=%s", payment_method)
        _logger.info("[CBM VALIDATE]   pricelist_id=%s", pricelist_id)
        _logger.info("=" * 80)

        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}

        SaleOrder = request.env['sale.order'].sudo()
        ICP = request.env['ir.config_parameter'].sudo()

        order = SaleOrder.browse(order_id)
        if not order.exists():
            return {'error': 'Quotation not found'}
        
        if order.state != 'draft':
            return {'error': 'Quotation already validated'}
        
        # Apply pricelist if provided
        if pricelist_id:
            new_pricelist = request.env['product.pricelist'].sudo().browse(pricelist_id)
            if new_pricelist.exists() and order.pricelist_id.id != new_pricelist.id:
                order.pricelist_id = new_pricelist
        
        # Get journal based on payment method
        journal = self._get_payment_journal(payment_method, ICP)
        if not journal:
            return {'error': 'Payment journal not configured'}
        
        # Get convention split info
        pricelist = order.pricelist_id
        has_convention = (
            hasattr(pricelist, 'convention_coverage_pct') 
            and pricelist.convention_coverage_pct > 0
            and pricelist.payer_partner_id
        )
        
        _logger.info(f"[CBM VALIDATE] Pricelist: {pricelist.name}, coverage: {getattr(pricelist, 'convention_coverage_pct', 0)}, payer: {pricelist.payer_partner_id.name if pricelist.payer_partner_id else 'None'}, has_convention: {has_convention}")
        
        # Calculate convention shares before confirmation
        convention_share = 0
        convention_pct = 0
        original_total = order.amount_total  # Store before any modifications
        if has_convention:
            convention_pct = pricelist.convention_coverage_pct
            convention_share = original_total * (convention_pct / 100)
            
            _logger.info(f"[CBM VALIDATE] Adding discount line to order: -{convention_share}")
            
            # Find or create a service product for this specific convention
            product_code = f"CONV_{pricelist.id}"  # Unique code per pricelist
            product_name = f"Convention {pricelist.name}"
            
            discount_product = request.env['product.product'].sudo().search([
                ('default_code', '=', product_code)
            ], limit=1)
            
            if not discount_product:
                # Create the discount product for this convention
                discount_product = request.env['product.product'].sudo().create({
                    'name': product_name,
                    'default_code': product_code,
                    'type': 'service',
                    'categ_id': request.env.ref('product.product_category_all').id,
                    'sale_ok': True,
                    'purchase_ok': False,
                    'list_price': 0,
                    'taxes_id': [(5, 0, 0)],  # No taxes
                    'invoice_policy': 'order',  # Ensure discount line is invoiced immediately
                })
                _logger.info(f"[CBM VALIDATE] Created convention product: {product_name}")
            
            # Get default UoM (Unit)
            uom_unit = request.env.ref('uom.product_uom_unit', raise_if_not_found=False)
            if not uom_unit:
                uom_unit = request.env['uom.uom'].sudo().search([('name', '=', 'Unit')], limit=1)
            
            # Add discount line with convention name
            order.write({
                'order_line': [(0, 0, {
                    'product_id': discount_product.id,
                    'name': f"{product_name} (-{convention_pct}%)",
                    'product_uom_qty': 1,
                    'product_uom': uom_unit.id if uom_unit else False,
                    'price_unit': -convention_share,
                })]
            })
            _logger.info(f"[CBM VALIDATE] Order total after discount: {order.amount_total}")

        # CLEANUP: Remove down payment lines with qty=0 (leftover from previous partial invoices)
        # These cause "Quantity for Down payment is 0.0" error during invoice creation
        downpayment_zero_lines = order.order_line.filtered(
            lambda ln: ln.product_uom_qty <= 0 or getattr(ln, 'is_downpayment', False)
        )
        if downpayment_zero_lines:
            _logger.info(f"[CBM VALIDATE] Removing {len(downpayment_zero_lines)} down payment/zero qty lines")
            downpayment_zero_lines.unlink()

        try:
            # Step 1: Confirm order (this will auto-create and post invoice if Bahmni setting is enabled)
            if order.state == 'draft':
                order.action_confirm()
            
            # Step 2: Get or create invoice
            existing_invoices = order.invoice_ids.filtered(lambda i: i.state != 'cancel')
            if existing_invoices:
                invoice = existing_invoices[0]
                _logger.info(f"[CBM VALIDATE] Using existing invoice {invoice.name}, state: {invoice.state}")
            else:
                invoices = order._create_invoices(final=True)
                if not invoices:
                    return {'error': 'Failed to create invoice - check product invoicing policy'}
                invoice = invoices[0]
                _logger.info(f"[CBM VALIDATE] Created new invoice {invoice.name}, state: {invoice.state}")
            
            # Step 3: Post invoice if still draft
            if invoice.state == 'draft':
                invoice.action_post()
            
            _logger.info(f"[CBM VALIDATE] Invoice {invoice.name}, total: {invoice.amount_total}")
            
            # Step 4: Create CNAS invoice if convention was applied
            cnas_invoice = None
            if has_convention and convention_share > 0:
                # Get convention journal from settings
                convention_journal_id = int(ICP.get_param(
                    'clinic_staff_portal.cashier_convention_journal_id', 0))
                convention_journal = None
                if convention_journal_id:
                    convention_journal = request.env['account.journal'].sudo().browse(convention_journal_id)
                    if not convention_journal.exists():
                        convention_journal = None
                
                # Create CNAS invoice for convention share
                cnas_invoice = request.env['account.move'].sudo().create({
                    'move_type': 'out_invoice',
                    'partner_id': pricelist.payer_partner_id.id,
                    'invoice_date': invoice.invoice_date or fields.Date.today(),
                    'journal_id': convention_journal.id if convention_journal else invoice.journal_id.id,
                    'ref': f"Convention pour {invoice.partner_id.name} - {invoice.name}",
                    'invoice_line_ids': [(0, 0, {
                        'name': f"Part convention {pricelist.name} pour {invoice.partner_id.name}",
                        'quantity': 1,
                        'price_unit': convention_share,
                    })],
                })
                cnas_invoice.action_post()
                _logger.info(f"[CBM VALIDATE] Created CNAS invoice: {cnas_invoice.name}")
            
            # Step 4: Post patient invoice (now with discount if convention)
            if invoice.state == 'draft':
                invoice.action_post()
                _logger.info(f"[CBM VALIDATE] Posted invoice: {invoice.name}, total: {invoice.amount_total}")
            
            # Step 5: Determine payment amount
            # Use updated invoice total (with discount if convention was applied)
            final_total = invoice.amount_total
            if amount is not None and amount > 0:
                payment_amount = min(amount, final_total)
            else:
                payment_amount = final_total
            
            # Step 6: Register patient payment
            if payment_amount > 0:
                self._create_and_post_payment(
                    partner=invoice.partner_id,
                    amount=payment_amount,
                    journal=journal,
                    invoice=invoice,
                )
                _logger.info(f"[CBM VALIDATE] Patient payment: {payment_amount}")
            
            return {
                'success': True,
                'invoice_id': invoice.id,
                'invoice_name': invoice.name,
                'amount_total': original_total if has_convention else invoice.amount_total,
                'patient_share': invoice.amount_total,
                'convention_share': convention_share,
                'convention_name': pricelist.name if has_convention else None,
                'cnas_invoice_id': cnas_invoice.id if cnas_invoice else None,
                'payment_method': payment_method,
            }
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Validation failed: {e}")
            return {'success': False, 'error': str(e)[:200]}
    
    # ==================== INVOICE INFO (ORANGE CARDS) ====================
    
    @http.route('/cbm/cashier/get_invoice_info', type='json', auth='user')
    def get_invoice_info(self, invoice_id):
        """Get invoice info for orange card payment modal."""
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        AccountMove = request.env['account.move'].sudo()
        invoice = AccountMove.browse(invoice_id)
        
        if not invoice.exists():
            return {'error': 'Invoice not found'}
        
        # Get invoice lines - try both field names
        lines = []
        
        # Debug: check what fields are available
        all_lines = invoice.line_ids  # In Odoo 16, line_ids contains ALL lines
        invoice_lines = invoice.invoice_line_ids  # This should contain only invoice lines (not tax/payment lines)
        
        _logger.info(f"[CBM CASHIER] Invoice {invoice.id}: line_ids count = {len(all_lines)}, invoice_line_ids count = {len(invoice_lines)}")
        
        # Try invoice_line_ids first (preferred), fall back to line_ids filtered
        target_lines = invoice_lines if invoice_lines else all_lines
        
        for line in target_lines:
            _logger.info(f"[CBM CASHIER] Line: {line.name}, display_type={line.display_type}, exclude_from_invoice_tab={getattr(line, 'exclude_from_invoice_tab', 'N/A')}")
            # EXCLUDE sections and notes - include everything else (False, None, '', 'product', etc.)
            if line.display_type not in ('line_section', 'line_note'):
                # Also skip lines excluded from invoice tab (like tax lines)
                if not getattr(line, 'exclude_from_invoice_tab', False):
                    lines.append({
                        'name': line.product_id.name if line.product_id else line.name,
                        'qty': line.quantity,
                        'price_unit': line.price_unit,
                        'price_subtotal': line.price_subtotal,
                    })
        
        _logger.info(f"[CBM CASHIER] Filtered lines count: {len(lines)}")
        
        # Check for convention from sale order
        convention_name = None
        convention_pct = 0
        if invoice.invoice_origin:
            sale_order = request.env['sale.order'].sudo().search([
                ('name', '=', invoice.invoice_origin)
            ], limit=1)
            if sale_order and sale_order.pricelist_id:
                pricelist = sale_order.pricelist_id
                if hasattr(pricelist, 'convention_coverage_pct') and pricelist.convention_coverage_pct > 0:
                    convention_name = pricelist.name
                    convention_pct = pricelist.convention_coverage_pct
        
        return {
            'invoice_id': invoice.id,
            'invoice_name': invoice.name,
            'partner_name': invoice.partner_id.name,
            'partner_ref': invoice.partner_id.ref or '',
            'amount_total': invoice.amount_total,
            'amount_residual': invoice.amount_residual,
            'amount_paid': invoice.amount_total - invoice.amount_residual,
            'lines': lines,
            'convention_name': convention_name,
            'convention_pct': convention_pct,
        }
    
    # ==================== PAY (ORANGE CARDS) ====================
    
    @http.route('/cbm/cashier/pay', type='json', auth='user')
    def pay(self, invoice_id, amount, payment_method='cash'):
        """
        Register payment for an unpaid invoice (orange card).
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        AccountMove = request.env['account.move'].sudo()
        ICP = request.env['ir.config_parameter'].sudo()
        
        invoice = AccountMove.browse(invoice_id)
        if not invoice.exists():
            return {'error': 'Invoice not found'}
        
        if invoice.payment_state == 'paid':
            return {'error': 'Invoice already fully paid'}
        
        if amount <= 0:
            return {'error': 'Invalid payment amount'}
        
        if amount > invoice.amount_residual:
            amount = invoice.amount_residual
        
        journal = self._get_payment_journal(payment_method, ICP)
        if not journal:
            return {'error': 'Payment journal not configured'}
        
        try:
            payment = self._create_and_post_payment(
                partner=invoice.partner_id,
                amount=amount,
                journal=journal,
                invoice=invoice,
            )
            
            invoice.invalidate_recordset()
            
            return {
                'success': True,
                'payment_id': payment.id,
                'payment_name': payment.name,
                'invoice_id': invoice.id,
                'amount_paid': amount,
                'amount_residual': invoice.amount_residual,
                'fully_paid': invoice.payment_state == 'paid',
            }
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Payment failed: {e}")
            return {'success': False, 'error': str(e)[:200]}
    
    # ==================== HELPER METHODS ====================
    
    def _get_payment_journal(self, payment_method, ICP):
        """Get journal based on payment method."""
        journal_param_map = {
            'cash': 'clinic_staff_portal.cashier_cash_journal_id',
            'card': 'clinic_staff_portal.cashier_card_journal_id',
            'cheque': 'clinic_staff_portal.cashier_cheque_journal_id',
            'convention': 'clinic_staff_portal.cashier_convention_journal_id',
        }
        
        journal_id_str = ICP.get_param(journal_param_map.get(payment_method, journal_param_map['cash']), '')
        if not journal_id_str or not journal_id_str.isdigit():
            journal = request.env['account.journal'].sudo().search([('type', '=', 'cash')], limit=1)
        else:
            journal = request.env['account.journal'].sudo().browse(int(journal_id_str))
        
        return journal if journal.exists() else None
    
    def _create_and_post_payment(self, partner, amount, journal, invoice, is_convention=False):
        """Create payment and reconcile with specific invoice."""
        AccountPayment = request.env['account.payment'].sudo()
        
        payment_method = journal.inbound_payment_method_line_ids[:1].payment_method_id
        
        payment_vals = {
            'partner_id': partner.id,
            'amount': amount,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'journal_id': journal.id,
            'ref': f"Cashier - {invoice.name}" + (" (Convention)" if is_convention else ""),
        }
        
        if payment_method:
            payment_vals['payment_method_id'] = payment_method.id
        
        payment = AccountPayment.create(payment_vals)
        payment.action_post()
        
        # Reconcile with invoice
        self._reconcile_payment_with_invoice(payment, invoice)
        
        return payment
    
    def _reconcile_payment_with_invoice(self, payment, invoice):
        """Explicitly reconcile payment with a specific invoice."""
        payment_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
        )
        
        invoice_line = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable' and not line.reconciled
        )
        
        if payment_line and invoice_line:
            (payment_line + invoice_line).reconcile()
    
    # ==================== PHASE 4: CORRECTIONS ====================
    
    @http.route('/cbm/cashier/cancel', type='json', auth='user')
    def cancel(self, invoice_id, reason=''):
        """
        Full reversal of a paid invoice.
        
        Odoo workflow:
        1. Create CN via reversal wizard with refund_method='cancel'
           - This creates CN, posts it, and auto-reconciles with original invoice
           - Original invoice payment_state becomes 'reversed'
        2. Create outbound payments to refund the customer
           - One outbound payment per original inbound payment
           - Same journal as original payment
        
        Result:
        - Original invoice: state=posted, payment_state=reversed
        - Credit note: state=posted, payment_state=paid (reconciled)
        - Outbound payments created (cash leaving)
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Accès refusé'}
        
        try:
            invoice = request.env['account.move'].sudo().browse(invoice_id)
            if not invoice.exists():
                return {'error': 'Facture non trouvée'}
            
            if invoice.state == 'cancel':
                return {'error': 'Facture déjà annulée'}
            
            if invoice.move_type != 'out_invoice':
                return {'error': 'Ce n\'est pas une facture client'}
            
            _logger.info(f"[CBM CASHIER] Cancel invoice {invoice.name} by {request.env.user.name}")
            
            # Get original payments BEFORE reversal (we need to refund these)
            original_payments = invoice._get_reconciled_payments()
            total_paid = sum(p.amount for p in original_payments)
            
            # STEP 1: Create and post CN using 'cancel' method
            # This auto-reconciles CN with original invoice
            reversal_wizard = request.env['account.move.reversal'].sudo().with_context(
                active_model='account.move',
                active_ids=[invoice.id],
            ).create({
                'refund_method': 'cancel',  # Auto-post + auto-reconcile
                'reason': reason or 'Annulation via Caisse',
                'journal_id': invoice.journal_id.id,
            })
            
            action = reversal_wizard.reverse_moves()
            credit_note_id = action.get('res_id')
            credit_note = request.env['account.move'].sudo().browse(credit_note_id) if credit_note_id else None
            
            # STEP 2: Create outbound payments (actual cash refund to customer)
            # One payment per original payment, using same journal
            refund_payments = []
            
            for orig_payment in original_payments:
                refund = request.env['account.payment'].sudo().create({
                    'partner_id': invoice.partner_id.id,
                    'amount': orig_payment.amount,
                    'payment_type': 'outbound',  # Money going OUT
                    'partner_type': 'customer',
                    'journal_id': orig_payment.journal_id.id,
                    'ref': f"Remboursement {invoice.name} - {reason or 'Annulation'}",
                })
                refund.action_post()
                
                refund_payments.append({
                    'id': refund.id,
                    'name': refund.name,
                    'amount': refund.amount,
                    'journal': refund.journal_id.name,
                })
            
            # Log to invoice chatter
            invoice.message_post(
                body=f"<b>Annulation complète</b><br/>"
                     f"Avoir: {credit_note.name if credit_note else '-'}<br/>"
                     f"Montant remboursé: {total_paid} DA<br/>"
                     f"Raison: {reason or '-'}<br/>"
                     f"Par: {request.env.user.name}",
                message_type='notification',
            )
            
            return {
                'success': True,
                'message': f'Facture {invoice.name} annulée',
                'credit_note': credit_note.name if credit_note else None,
                'credit_note_id': credit_note.id if credit_note else None,
                'refund_payments': refund_payments,
                'total_refunded': total_paid,
            }
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Cancel failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)[:200]}
    
    @http.route('/cbm/cashier/refund', type='json', auth='user')
    def refund(self, invoice_id, mode, amount=0, reason=''):
        """
        Refund following exact Odoo 16 workflow.
        
        Modes:
        - 'total': Full reversal (refund_method='cancel') - delegates to cancel()
        - 'partial': Partial refund, RINV stays open for patient to pay later
        - 'partial_close': Partial refund + write-off remaining balance
        
        Odoo workflow:
        1. Create RINV via reversal wizard (refund_method='refund' for draft)
        2. Post RINV (it's negative, auto-reconciles with original)
        3. Register outbound payment for refund amount
        4. For partial: RINV stays open with remaining balance
        5. For partial_close: Write-off remaining on RINV
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Accès refusé'}
        
        # Convert amount to float (comes as string from frontend input)
        try:
            amount = float(amount) if amount else 0
        except (ValueError, TypeError):
            return {'error': 'Montant invalide'}
        
        try:
            invoice = request.env['account.move'].sudo().browse(invoice_id)
            
            if not invoice.exists():
                return {'error': 'Facture non trouvée'}
            
            if invoice.state != 'posted':
                return {'error': 'La facture doit être validée'}
            
            if invoice.move_type != 'out_invoice':
                return {'error': 'Ce n\'est pas une facture client'}
            
            if invoice.payment_state not in ('paid', 'in_payment', 'partial'):
                return {'error': 'La facture doit avoir au moins un paiement'}
            
            _logger.info(f"[CBM CASHIER] Refund {mode} for {invoice.name}, amount={amount}")
            
            # OUTCOME 1: Full Cancel
            if mode == 'total':
                return self.cancel(invoice_id, reason)
            
            # OUTCOME 2 & 3: Partial Refund
            if mode not in ('partial', 'partial_close'):
                return {'error': f'Mode invalide: {mode}'}
            
            if amount <= 0:
                return {'error': 'Le montant doit être supérieur à 0'}
            
            if amount > invoice.amount_total:
                return {'error': f'Le montant dépasse le total de la facture'}
            
            ICP = request.env['ir.config_parameter'].sudo()
            
            # STEP 1: Create RINV via reversal wizard (draft mode)
            reversal_wizard = request.env['account.move.reversal'].sudo().with_context(
                active_model='account.move',
                active_ids=[invoice.id],
            ).create({
                'refund_method': 'refund',  # Draft RINV
                'reason': reason or 'Remboursement',
                'journal_id': invoice.journal_id.id,
            })
            
            action = reversal_wizard.reverse_moves()
            rinv_id = action.get('res_id')
            rinv = request.env['account.move'].sudo().browse(rinv_id)
            
            if not rinv.exists():
                return {'error': 'Échec de création de l\'avoir'}
            
            # RINV is in DRAFT - different handling based on mode
            if rinv.state != 'draft':
                return {'error': f'L\'avoir n\'est pas en brouillon: {rinv.state}'}
            
            # MODE: partial_close - Add discount line to reduce total
            if mode == 'partial_close':
                # Add a discount line with negative amount
                rinv.write({
                    'invoice_line_ids': [(0, 0, {
                        'name': reason or f'Remise - {amount} DA',
                        'quantity': 1,
                        'price_unit': -amount,  # Negative = discount
                    })]
                })
            
            # Post the RINV
            rinv.action_post()
            
            # STEP 3: Register payment
            cash_journal = self._get_payment_journal('cash', ICP)
            if not cash_journal:
                return {'error': 'Journal de caisse non configuré'}
            
            rinv_total = rinv.amount_total  # After discount line if partial_close
            
            if mode == 'partial':
                # Partial: register kept amount (total - refund), RINV stays open
                kept_amount = rinv_total - amount
                payment_vals = {
                    'journal_id': cash_journal.id,
                    'payment_date': fields.Date.today(),
                    'amount': kept_amount,
                }
            else:
                # partial_close: register full reduced amount, RINV fully paid
                payment_vals = {
                    'journal_id': cash_journal.id,
                    'payment_date': fields.Date.today(),
                    'amount': rinv_total,  # Full (reduced) amount
                }
            
            # Register payment on RINV
            payment_register = request.env['account.payment.register'].sudo().with_context(
                active_model='account.move',
                active_ids=[rinv.id],
            ).create(payment_vals)
            
            payment_action = payment_register.action_create_payments()
            
            # Get created payment
            payment_id = payment_action.get('res_id') if isinstance(payment_action, dict) else None
            payment = request.env['account.payment'].sudo().browse(payment_id) if payment_id else None
            
            # Refresh states
            rinv.invalidate_recordset(['payment_state', 'amount_residual'])
            
            # Log to original invoice
            invoice.message_post(
                body=f"<b>Remboursement {'partiel (ouvert)' if mode == 'partial' else 'partiel (clôturé)'}</b><br/>"
                     f"Montant remboursé: {amount} DA<br/>"
                     f"Avoir: {rinv.name}<br/>"
                     f"Paiement: {payment.name if payment else '-'}<br/>"
                     f"Solde RINV: {rinv.amount_residual} DA<br/>"
                     f"Raison: {reason or '-'}<br/>"
                     f"Par: {request.env.user.name}",
                message_type='notification',
            )
            
            return {
                'success': True,
                'message': f'Remboursement de {amount} DA effectué',
                'rinv_id': rinv.id,
                'rinv_name': rinv.name,
                'rinv_total': rinv.amount_total,
                'rinv_residual': rinv.amount_residual,
                'rinv_payment_state': rinv.payment_state,
                'payment_id': payment.id if payment else None,
                'payment_name': payment.name if payment else None,
            }
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Refund failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)[:200]}
    
    @http.route('/cbm/cashier/get_refund_info', type='json', auth='user')
    def get_refund_info(self, invoice_id):
        """
        Get invoice info for refund modal.
        Returns available refund options based on invoice state.
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Accès refusé'}
        
        try:
            invoice = request.env['account.move'].sudo().browse(invoice_id)
            if not invoice.exists():
                return {'error': 'Facture non trouvée'}
            
            # Get payments made on this invoice
            payments = invoice._get_reconciled_payments()
            payment_info = []
            total_paid = 0
            
            for payment in payments:
                payment_info.append({
                    'id': payment.id,
                    'name': payment.name,
                    'date': payment.date.strftime('%d/%m/%Y') if payment.date else '',
                    'amount': payment.amount,
                    'journal': payment.journal_id.name,
                    'type': 'Entrée' if payment.payment_type == 'inbound' else 'Sortie',
                })
                if payment.payment_type == 'inbound':
                    total_paid += payment.amount
            
            # Get existing credit notes
            credit_notes = request.env['account.move'].sudo().search([
                ('reversed_entry_id', '=', invoice.id),
                ('move_type', '=', 'out_refund'),
            ])
            
            cn_info = []
            total_refunded = 0
            for cn in credit_notes:
                cn_info.append({
                    'id': cn.id,
                    'name': cn.name,
                    'date': cn.invoice_date.strftime('%d/%m/%Y') if cn.invoice_date else '',
                    'amount': cn.amount_total,
                    'state': cn.state,
                    'payment_state': cn.payment_state,
                })
                if cn.state == 'posted':
                    total_refunded += cn.amount_total
            
            # Determine available actions
            can_cancel = (
                invoice.state == 'posted' 
                and invoice.payment_state in ('paid', 'in_payment', 'partial')
            )
            can_partial_refund = (
                invoice.state == 'posted'
                and invoice.payment_state in ('paid', 'in_payment', 'partial')
                and (invoice.amount_total - total_refunded) > 0
            )
            
            max_refund_amount = invoice.amount_total - total_refunded
            
            return {
                'invoice_id': invoice.id,
                'invoice_name': invoice.name,
                'partner_name': invoice.partner_id.name,
                'amount_total': invoice.amount_total,
                'amount_residual': invoice.amount_residual,
                'state': invoice.state,
                'payment_state': invoice.payment_state,
                'payments': payment_info,
                'total_paid': total_paid,
                'credit_notes': cn_info,
                'total_refunded': total_refunded,
                'max_refund_amount': max_refund_amount,
                'can_cancel': can_cancel,
                'can_partial_refund': can_partial_refund,
            }
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Get refund info failed: {e}")
            return {'error': str(e)[:200]}

    @http.route('/cbm/cashier/get_status', type='json', auth='user')
    def get_status(self, invoice_id):
        """
        Get complete invoice history for status popup (red cards).
        Returns timeline of events, linked credit notes, payments, and reasons.
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Accès refusé'}
        
        try:
            invoice = request.env['account.move'].sudo().browse(invoice_id)
            if not invoice.exists():
                return {'error': 'Facture non trouvée'}
            
            # Build status info
            status = {
                'invoice_id': invoice.id,
                'invoice_name': invoice.name,
                'partner_name': invoice.partner_id.name,
                'amount_total': invoice.amount_total,
                'amount_residual': invoice.amount_residual,
                'state': invoice.state,
                'payment_state': invoice.payment_state,
                'create_date': invoice.create_date.strftime('%d/%m/%Y %H:%M') if invoice.create_date else '',
                'create_user': invoice.create_uid.name if invoice.create_uid else '',
                'is_cancelled': invoice.state == 'cancel',
                'is_reversed': invoice.payment_state == 'reversed',
                'credit_notes': [],
                'payments': [],
                'timeline': [],
            }
            
            # Get linked credit notes
            credit_notes = request.env['account.move'].sudo().search([
                ('move_type', '=', 'out_refund'),
                ('reversed_entry_id', '=', invoice.id),
            ])
            
            for cn in credit_notes:
                # Get payments on this CN
                cn_payments = cn._get_reconciled_payments()
                cn_payment_names = [p.name for p in cn_payments]
                
                status['credit_notes'].append({
                    'id': cn.id,
                    'name': cn.name,
                    'date': cn.invoice_date.strftime('%d/%m/%Y') if cn.invoice_date else '',
                    'amount': cn.amount_total,
                    'state': cn.state,
                    'payment_state': cn.payment_state,
                    'reason': cn.ref or '',
                    'payments': cn_payment_names,
                })
            
            # Get all payments (inbound and outbound)
            # Inbound = customer paid
            # Outbound = refund to customer
            all_payments = invoice._get_reconciled_payments()
            
            for payment in all_payments:
                status['payments'].append({
                    'id': payment.id,
                    'name': payment.name,
                    'date': payment.date.strftime('%d/%m/%Y') if payment.date else '',
                    'amount': payment.amount,
                    'type': 'Entrée' if payment.payment_type == 'inbound' else 'Sortie (Remboursement)',
                    'journal': payment.journal_id.name,
                    'state': payment.state,
                })
            
            # Build timeline from chatter messages
            messages = invoice.message_ids.filtered(
                lambda m: m.message_type in ('notification', 'comment') and m.body
            ).sorted('date', reverse=True)[:15]
            
            for msg in messages:
                status['timeline'].append({
                    'date': msg.date.strftime('%d/%m/%Y %H:%M') if msg.date else '',
                    'user': msg.author_id.name if msg.author_id else 'Système',
                    'body': msg.body,
                })
            
            return status
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Get status failed: {e}")
            return {'error': str(e)[:200]}
    
    # ==================== SESSION MANAGEMENT ====================
    
    @http.route('/cbm/cashier/session/current', type='json', auth='user')
    def get_current_session(self):
        """Get current user's open session, if any."""
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        Session = request.env['cashier.session'].sudo()
        return Session.get_current_session()
    
    @http.route('/cbm/cashier/session/open', type='json', auth='user')
    def open_session(self):
        """Open a new session for current user."""
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        Session = request.env['cashier.session'].sudo()
        return Session.open_new_session()
    
    @http.route('/cbm/cashier/session/summary', type='json', auth='user')
    def get_session_summary(self):
        """Get detailed session summary for Z-Report panel."""
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        Session = request.env['cashier.session'].sudo()
        session = Session.search([
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'open'),
        ], limit=1)
        
        if not session:
            return {'error': 'No open session', 'is_open': False}
        
        # Force recompute of totals
        session._compute_payment_totals()
        
        return {
            'id': session.id,
            'name': session.name,
            'is_open': True,
            'open_time': session.open_datetime.isoformat() if session.open_datetime else None,
            'total_cash': session.total_cash,
            'total_card': session.total_card,
            'total_cheque': session.total_cheque,
            'total_all': session.total_all,
            'payment_count': session.payment_count,
            'currency_symbol': session.currency_id.symbol or 'DA',
        }
    
    @http.route('/cbm/cashier/session/close', type='json', auth='user', methods=['POST'])
    def close_session(self, counted_cash=0, notes=''):
        """Close session and return Z-Report data."""
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        Session = request.env['cashier.session'].sudo()
        session = Session.search([
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'open'),
        ], limit=1)
        
        if not session:
            return {'error': 'No open session to close'}
        
        try:
            # Update counted cash and notes
            session.write({
                'counted_cash': counted_cash,
                'notes': notes,
            })
            
            # Close the session
            session.action_close()
            
            return {
                'success': True,
                'session_id': session.id,
                'session_name': session.name,
                'open_time': session.open_datetime.isoformat() if session.open_datetime else None,
                'close_time': session.close_datetime.isoformat() if session.close_datetime else None,
                'total_cash': session.total_cash,
                'total_card': session.total_card,
                'total_cheque': session.total_cheque,
                'total_all': session.total_all,
                'counted_cash': session.counted_cash,
                'difference': session.difference,
                'payment_count': session.payment_count,
            }
            
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Session close failed: {e}")
            return {'success': False, 'error': str(e)[:200]}
    
    @http.route('/cbm/cashier/session/invoices', type='json', auth='user')
    def get_session_invoices(self, session_id=None):
        """Get list of invoices for a session (for print/export).
        
        If session_id is None, uses current open session.
        Returns structured data suitable for printing or CSV export.
        """
        if not request.env.user.has_group('clinic_staff_portal.group_clinic_portal_cashier'):
            return {'error': 'Access Denied'}
        
        Session = request.env['cashier.session'].sudo()
        
        if session_id:
            session = Session.browse(session_id)
        else:
            # Get current user's most recent session (open or closed today)
            session = Session.search([
                ('user_id', '=', request.env.user.id),
            ], order='open_datetime desc', limit=1)
        
        if not session.exists():
            return {'error': 'No session found'}
        
        return session.get_invoice_list()
    
    # ==================== RECEIPT PRINTING ====================
    
    @http.route('/cbm/cashier/receipt/html/<int:invoice_id>', type='http', auth='user')
    def get_receipt_html(self, invoice_id):
        """
        Render receipt as HTML for silent iframe printing.
        Uses the POS-style receipt template from serenvale_custom_invoice_print.
        """
        invoice = request.env['account.move'].sudo().browse(invoice_id)
        if not invoice.exists():
            return request.make_response(
                '<html><body>Invoice not found</body></html>',
                headers=[('Content-Type', 'text/html')]
            )
        
        try:
            # Render the POS-style receipt template
            html = request.env['ir.qweb']._render(
                'serenvale_custom_invoice_print.report_pos_style_payment_receipt_template',
                {
                    'o': invoice,
                    'docs': invoice,
                    'lang': request.env.user.lang or 'fr_FR',
                }
            )
            return request.make_response(html, headers=[('Content-Type', 'text/html')])
        except Exception as e:
            _logger.error(f"[CBM CASHIER] Receipt render failed: {e}")
            return request.make_response(
                f'<html><body>Error: {str(e)[:100]}</body></html>',
                headers=[('Content-Type', 'text/html')]
            )

