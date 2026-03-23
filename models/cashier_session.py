# -*- coding: utf-8 -*-
"""
Cashier Session Model

Tracks per-user cashier work sessions for Z-Report functionality.
Each session records:
- Open/close timestamps
- Cash reconciliation (counted vs expected)
- Payment totals by method (computed from payments during session)
"""
from odoo import models, fields, api
from odoo.exceptions import UserError


class CashierSession(models.Model):
    _name = 'cashier.session'
    _description = 'Cashier Work Session'
    _order = 'open_datetime desc'
    
    name = fields.Char(string='Reference', readonly=True, copy=False)
    user_id = fields.Many2one(
        'res.users', 
        string='Cashier',
        required=True, 
        default=lambda self: self.env.user,
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )
    
    # Timestamps
    open_datetime = fields.Datetime(
        string='Opened At',
        default=fields.Datetime.now,
        readonly=True
    )
    close_datetime = fields.Datetime(
        string='Closed At',
        readonly=True
    )
    
    # State
    state = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed')
    ], default='open', string='Status', readonly=True)
    
    # Cash reconciliation
    counted_cash = fields.Monetary(
        string='Counted Cash',
        help='Actual cash counted at end of session'
    )
    notes = fields.Text(string='Notes')
    
    # Computed payment totals
    total_cash = fields.Monetary(
        string='Cash Payments',
        compute='_compute_payment_totals',
        store=True
    )
    total_card = fields.Monetary(
        string='Card Payments',
        compute='_compute_payment_totals',
        store=True
    )
    total_cheque = fields.Monetary(
        string='Cheque Payments',
        compute='_compute_payment_totals',
        store=True
    )
    total_all = fields.Monetary(
        string='Total Payments',
        compute='_compute_payment_totals',
        store=True
    )
    payment_count = fields.Integer(
        string='Transaction Count',
        compute='_compute_payment_totals',
        store=True
    )
    
    # Difference for reconciliation
    difference = fields.Monetary(
        string='Difference',
        compute='_compute_difference',
        help='Counted cash minus expected cash'
    )
    
    # Linked invoices (computed from payments during session)
    invoice_ids = fields.Many2many(
        'account.move',
        string='Invoices',
        compute='_compute_session_invoices',
        store=False,
        help='Invoices paid during this session'
    )
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_session_invoices',
    )
    
    @api.model
    def create(self, vals):
        if not vals.get('name'):
            vals['name'] = self.env['ir.sequence'].next_by_code('cashier.session') or 'New'
        return super().create(vals)
    
    @api.depends('open_datetime', 'close_datetime', 'state', 'user_id')
    def _compute_payment_totals(self):
        """Sum payments created by this user during session timeframe."""
        Payment = self.env['account.payment']
        ICP = self.env['ir.config_parameter'].sudo()
        
        # Get configured journal IDs (must match keys in controller)
        cash_journal_id = int(ICP.get_param('clinic_staff_portal.cashier_cash_journal_id', '0'))
        card_journal_id = int(ICP.get_param('clinic_staff_portal.cashier_card_journal_id', '0'))
        cheque_journal_id = int(ICP.get_param('clinic_staff_portal.cashier_cheque_journal_id', '0'))
        
        for session in self:
            domain = [
                ('create_uid', '=', session.user_id.id),
                ('state', '=', 'posted'),
                ('payment_type', '=', 'inbound'),
                ('create_date', '>=', session.open_datetime),
            ]
            if session.close_datetime:
                domain.append(('create_date', '<=', session.close_datetime))
            
            payments = Payment.search(domain)
            
            # If journals are configured, filter by them. Otherwise count all as cash.
            if cash_journal_id or card_journal_id or cheque_journal_id:
                session.total_cash = sum(
                    p.amount for p in payments if p.journal_id.id == cash_journal_id
                )
                session.total_card = sum(
                    p.amount for p in payments if p.journal_id.id == card_journal_id
                )
                session.total_cheque = sum(
                    p.amount for p in payments if p.journal_id.id == cheque_journal_id
                )
            else:
                # No journals configured - count all payments as "cash" for simplicity
                session.total_cash = sum(p.amount for p in payments)
                session.total_card = 0
                session.total_cheque = 0
            
            session.total_all = session.total_cash + session.total_card + session.total_cheque
            session.payment_count = len(payments)
    
    @api.depends('counted_cash', 'total_cash')
    def _compute_difference(self):
        for session in self:
            if session.counted_cash:
                session.difference = session.counted_cash - session.total_cash
            else:
                session.difference = 0.0
    
    def _compute_session_invoices(self):
        """Find invoices that were paid during this session timeframe."""
        Payment = self.env['account.payment']
        
        for session in self:
            domain = [
                ('create_uid', '=', session.user_id.id),
                ('state', '=', 'posted'),
                ('payment_type', '=', 'inbound'),
                ('create_date', '>=', session.open_datetime),
            ]
            if session.close_datetime:
                domain.append(('create_date', '<=', session.close_datetime))
            
            payments = Payment.search(domain)
            
            # Get unique invoices from payment reconciliations
            invoices = self.env['account.move']
            for payment in payments:
                # Get invoice from payment's reconciled lines
                reconciled_invoices = payment.reconciled_invoice_ids
                if reconciled_invoices:
                    invoices |= reconciled_invoices.filtered(
                        lambda inv: inv.move_type == 'out_invoice'
                    )
            
            session.invoice_ids = invoices
            session.invoice_count = len(invoices)
    
    def action_close(self):
        """Close the session. Only the session owner can close."""
        self.ensure_one()
        if self.user_id != self.env.user:
            raise UserError("Seul le propriétaire de la session peut la fermer.")
        if self.state == 'closed':
            raise UserError("Cette session est déjà fermée.")

        self.write({
            'close_datetime': fields.Datetime.now(),
            'state': 'closed',
        })
        # Trigger recompute of totals with final close_datetime
        self._compute_payment_totals()
        return True

    def action_force_close(self):
        """Force-close the session. Available to managers regardless of ownership."""
        self.ensure_one()
        if self.state == 'closed':
            raise UserError("Cette session est déjà fermée.")

        self.write({
            'close_datetime': fields.Datetime.now(),
            'state': 'closed',
        })
        self._compute_payment_totals()
        return True

    @api.model
    def _cron_close_stale_sessions(self):
        """Cron: close all sessions that are still open from a previous day."""
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        stale = self.search([
            ('state', '=', 'open'),
            ('open_datetime', '<', today_start),
        ])
        for session in stale:
            session.write({
                'close_datetime': today_start,
                'state': 'closed',
            })
            session._compute_payment_totals()
    
    @api.model
    def get_current_session(self):
        """Get the current user's open session, if any.

        Auto-closes stale sessions (opened before today).
        """
        session = self.search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'open'),
        ], limit=1)
        if session:
            # Auto-close if session was opened before today (stale session)
            today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if session.open_datetime and session.open_datetime < today_start:
                # Session is from a previous day - auto-close it
                session.write({
                    'close_datetime': fields.Datetime.now(),
                    'state': 'closed',
                })
                session._compute_payment_totals()
                return {'is_open': False, 'auto_closed': True}

            # Force recompute to get latest payment totals
            session._compute_payment_totals()
            return {
                'id': session.id,
                'name': session.name,
                'is_open': True,
                'open_time': session.open_datetime.isoformat() if session.open_datetime else None,
                'running_total': session.total_all,
                'payment_count': session.payment_count,
            }
        return {'is_open': False}
    
    @api.model
    def open_new_session(self):
        """Open a new session for current user. Close any existing open sessions first."""
        # Close any stale open sessions for this user
        stale = self.search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'open'),
        ])
        for s in stale:
            s.action_close()
        
        # Create new session
        session = self.create({})
        return session.get_current_session()
    
    def get_invoice_list(self):
        """Return structured list of invoices for export/print."""
        self.ensure_one()
        self._compute_session_invoices()
        
        result = []
        for inv in self.invoice_ids:
            result.append({
                'id': inv.id,
                'name': inv.name,
                'partner_name': inv.partner_id.name or '',
                'partner_ref': inv.partner_id.ref or '',
                'amount_total': inv.amount_total,
                'amount_residual': inv.amount_residual,
                'payment_state': inv.payment_state,
                'invoice_date': inv.invoice_date.strftime('%d/%m/%Y') if inv.invoice_date else '',
                'cashier': self.user_id.name,
            })
        
        return {
            'session_name': self.name,
            'cashier': self.user_id.name,
            'open_time': self.open_datetime.strftime('%d/%m/%Y %H:%M') if self.open_datetime else '',
            'close_time': self.close_datetime.strftime('%d/%m/%Y %H:%M') if self.close_datetime else '',
            'invoice_count': len(result),
            'total_amount': sum(inv['amount_total'] for inv in result),
            'invoices': result,
        }
    
    def action_view_invoices(self):
        """Open list of invoices paid during this session."""
        self.ensure_one()
        self._compute_session_invoices()
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Factures - {self.name}',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'create': False},
        }
    
    def action_print_invoices(self):
        """Print PDF report of session invoices."""
        self.ensure_one()
        return self.env.ref('clinic_staff_portal.action_report_cashier_session_invoices').report_action(self)
