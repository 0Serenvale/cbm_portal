# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ClinicWorkstation(models.Model):
    _name = 'clinic.workstation'
    _description = 'Clinic Workstation Registry'
    _order = 'location_name, name'
    _rec_name = 'name'

    name = fields.Char(string='Post Name', required=True, index=True)
    ip_address = fields.Char(string='IP Address', required=True, index=True)
    location_name = fields.Char(string='Physical Location',
                                help='e.g. Floor 5, Reception, Pharmacy')
    assigned_employee_id = fields.Many2one('hr.employee', string='Assigned Employee')
    assigned_user_id = fields.Many2one('res.users', string='Assigned User')
    is_configured = fields.Boolean(string='Configured', default=False,
                                   help='Set to True once admin fills in details')
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')
    last_seen = fields.Datetime(string='Last Seen', readonly=True)

    _sql_constraints = [
        ('ip_address_unique', 'UNIQUE(ip_address)',
         'A workstation with this IP address already exists.'),
    ]

    @api.model
    def get_or_create_by_ip(self, ip_address):
        """Find workstation by IP or auto-create an unconfigured one."""
        if not ip_address:
            return self.browse()
        ws = self.sudo().search([('ip_address', '=', ip_address)], limit=1)
        if not ws:
            ws = self.sudo().create({
                'name': '[Auto] %s' % ip_address,
                'ip_address': ip_address,
                'is_configured': False,
            })
        ws.sudo().write({'last_seen': fields.Datetime.now()})
        return ws
