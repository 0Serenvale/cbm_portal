# -*- coding: utf-8 -*-
"""
Kiosk Access Log Model

Tracks user access to CBM Portal with:
- IP address (identify workstation)
- Screen resolution (for UI/UX optimization)
- User agent (browser info)
- Workstation link (physical location registry)
"""
from datetime import timedelta
from odoo import models, fields, api


class KioskAccessLog(models.Model):
    _name = 'cbm.kiosk.access.log'
    _description = 'CBM Kiosk Access Log'
    _order = 'create_date desc'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        index=True
    )
    cashier_session_id = fields.Many2one(
        'cashier.session',
        string='Cashier Session',
        readonly=True,
        help='Active cashier session at time of access, if any'
    )
    workstation_id = fields.Many2one(
        'clinic.workstation',
        string='Workstation',
        readonly=True,
        index=True,
        help='Auto-matched by IP address'
    )

    # Device info
    ip_address = fields.Char(string='IP Address', readonly=True, index=True)
    screen_width = fields.Integer(string='Screen Width', readonly=True)
    screen_height = fields.Integer(string='Screen Height', readonly=True)
    user_agent = fields.Char(string='User Agent', readonly=True)

    # Computed display field
    resolution = fields.Char(
        string='Resolution',
        compute='_compute_resolution',
        store=True
    )

    @api.depends('screen_width', 'screen_height')
    def _compute_resolution(self):
        for rec in self:
            if rec.screen_width and rec.screen_height:
                rec.resolution = f'{rec.screen_width}x{rec.screen_height}'
            else:
                rec.resolution = 'Unknown'

    @api.model
    def log_access(self, screen_width=0, screen_height=0, user_agent=''):
        """
        Create access log entry. IP is captured from request context.
        Called from CBM Kiosk JS on each portal load.
        Returns workstation info + dual-session warning.
        """
        from odoo.http import request

        ip_address = ''
        if request and hasattr(request, 'httprequest'):
            ip_address = request.httprequest.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            if not ip_address:
                ip_address = request.httprequest.remote_addr or ''

        # Match or auto-create workstation
        Workstation = self.env['clinic.workstation']
        ws = Workstation.get_or_create_by_ip(ip_address)

        # Check for active cashier session
        CashierSession = self.env['cashier.session']
        active_session = CashierSession.search([
            ('user_id', '=', self.env.user.id),
            ('state', '=', 'open')
        ], limit=1)

        log_id = self.create({
            'user_id': self.env.user.id,
            'cashier_session_id': active_session.id if active_session else False,
            'workstation_id': ws.id if ws else False,
            'ip_address': ip_address,
            'screen_width': screen_width,
            'screen_height': screen_height,
            'user_agent': user_agent[:500] if user_agent else '',
        }).id

        # Dual-session check: other IPs for this user in last 10 minutes
        dual_warning = ''
        cutoff = fields.Datetime.now() - timedelta(minutes=10)
        other_logs = self.sudo().search([
            ('user_id', '=', self.env.user.id),
            ('create_date', '>=', cutoff),
            ('ip_address', '!=', ip_address),
            ('ip_address', '!=', False),
        ])
        other_ips = list(set(other_logs.mapped('ip_address')))
        if other_ips:
            dual_warning = 'Connecté depuis %d emplacement(s)' % (len(other_ips) + 1)

        return {
            'success': True,
            'log_id': log_id,
            'workstation': {
                'ip': ip_address,
                'location': ws.location_name or '',
                'name': ws.name or '',
                'is_configured': ws.is_configured if ws else False,
            },
            'dual_session_warning': dual_warning,
        }
