# -*- coding: utf-8 -*-
"""
Time Off Request Controller for CBM Portal.

Allows staff to request time off through the kiosk interface.
Location responsables can request for themselves and their team.
"""
import logging
import math
from odoo import http, fields, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class TimeOffController(http.Controller):
    """Controller for time off requests in CBM Portal."""

    # ========================================
    # TIME OFF ENDPOINTS
    # ========================================

    @http.route('/cbm/get_timeoff_types', type='json', auth='user')
    def get_timeoff_types(self):
        """Return available time off types (holiday status).

        Uses sudo() to bypass access restrictions - all users can see leave types.
        """
        try:
            HolidayStatus = request.env['hr.leave.type'].sudo()

            # Get active leave types that allow requests
            leave_types = HolidayStatus.search([
                ('active', '=', True),
            ], order='sequence, name')

            return [{
                'id': lt.id,
                'name': lt.name,
                'display_name': lt.display_name,
            } for lt in leave_types]
        except Exception as e:
            _logger.error("Error in get_timeoff_types: %s", str(e))
            return []

    @http.route('/cbm/get_timeoff_employees', type='json', auth='user')
    def get_timeoff_employees(self):
        """Return employees for location responsables and DRH.

        - Location responsables can see employees in their locations.
        - DRH (configured in settings) can see ALL employees.
        Returns user's own employee record plus team members.
        """
        try:
            user = request.env.user
            Employee = request.env['hr.employee'].sudo()
            Location = request.env['stock.location'].sudo()
            ICP = request.env['ir.config_parameter'].sudo()

            # Get current user's employee record
            current_employee = Employee.search([
                ('user_id', '=', user.id),
                ('active', '=', True),
            ], limit=1)

            # Check if user is a location responsable
            responsible_locations = Location.search([
                ('responsible_user_ids', 'in', user.id),
            ])
            is_location_responsable = bool(responsible_locations)

            # Check if user is DRH (from CBM Portal settings)
            drh_id_str = ICP.get_param('clinic_staff_portal.drh_user_id', '')
            is_drh = drh_id_str and str(user.id) == drh_id_str

            # Check if user is admin (Settings group)
            is_admin = user.has_group('base.group_system')

            is_responsable = is_location_responsable or is_drh or is_admin

            _logger.info(
                "[CBM TIMEOFF] User %s - is_admin=%s, is_drh=%s, is_location_responsable=%s, "
                "responsible_locations=%s",
                user.name, is_admin, is_drh, is_location_responsable,
                responsible_locations.ids if responsible_locations else []
            )

            employees = []

            if current_employee:
                # Always include current user's employee
                employees.append({
                    'id': current_employee.id,
                    'name': current_employee.name,
                    'display_name': current_employee.display_name,
                    'is_self': True,
                })

            if is_drh or is_admin:
                # DRH or Admin sees ALL active employees
                all_employees = Employee.search([
                    ('active', '=', True),
                ], order='name')

                _logger.info("[CBM TIMEOFF] Admin/DRH loading %d employees", len(all_employees))

                for emp in all_employees:
                    if current_employee and emp.id == current_employee.id:
                        continue  # Already added as 'self'
                    employees.append({
                        'id': emp.id,
                        'name': emp.name,
                        'display_name': emp.display_name,
                        'is_self': False,
                    })

            elif is_location_responsable:
                # Get all employees from responsible locations
                # employee_ids_1 field from stock.location
                location_employee_ids = set()
                for loc in responsible_locations:
                    if hasattr(loc, 'employee_ids_1') and loc.employee_ids_1:
                        location_employee_ids.update(loc.employee_ids_1.ids)

                _logger.info(
                    "[CBM TIMEOFF] Location responsable found %d employees in %d locations",
                    len(location_employee_ids), len(responsible_locations)
                )

                if location_employee_ids:
                    # Exclude current employee (already added)
                    if current_employee:
                        location_employee_ids.discard(current_employee.id)

                    team_employees = Employee.browse(list(location_employee_ids)).filtered(
                        lambda e: e.active
                    )

                    for emp in team_employees.sorted(key=lambda e: e.name):
                        employees.append({
                            'id': emp.id,
                            'name': emp.name,
                            'display_name': emp.display_name,
                            'is_self': False,
                        })

            _logger.info(
                "[CBM TIMEOFF] Returning %d employees to user %s (is_responsable=%s)",
                len(employees), user.name, is_responsable
            )

            return {
                'is_responsable': is_responsable,
                'employees': employees,
                'current_employee_id': current_employee.id if current_employee else False,
            }
        except Exception as e:
            _logger.error("Error in get_timeoff_employees: %s", str(e))
            return {
                'is_responsable': False,
                'employees': [],
                'current_employee_id': False,
            }

    @http.route('/cbm/submit_timeoff', type='json', auth='user')
    def submit_timeoff(self, holiday_status_id, employee_id, request_date_from,
                       number_of_days, name=''):
        """Create a time off request.

        Uses sudo() in the action to bypass permissions while keeping
        the request traceable to the actual user via chatter.

        Args:
            holiday_status_id: ID of hr.leave.type
            employee_id: ID of hr.employee
            request_date_from: Start date (YYYY-MM-DD)
            number_of_days: Number of days requested
            name: Optional description/reason
        """
        user = request.env.user
        HolidayRequest = request.env['hr.leave']
        Employee = request.env['hr.employee'].sudo()
        HolidayStatus = request.env['hr.leave.type'].sudo()
        Location = request.env['stock.location'].sudo()
        ICP = request.env['ir.config_parameter'].sudo()

        # Validate leave type exists
        leave_type = HolidayStatus.browse(holiday_status_id)
        if not leave_type.exists():
            return {'success': False, 'error': _('Type de congé non trouvé')}

        # Validate employee
        employee = Employee.browse(employee_id)
        if not employee.exists():
            return {'success': False, 'error': _('Employé non trouvé')}

        # Check authorization: user can only request for self, team, or if DRH
        current_employee = Employee.search([
            ('user_id', '=', user.id),
            ('active', '=', True),
        ], limit=1)

        is_self = current_employee and employee.id == current_employee.id

        # Check if user is admin (Settings group)
        is_admin = user.has_group('base.group_system')

        # Check if user is DRH (from CBM Portal settings)
        drh_id_str = ICP.get_param('clinic_staff_portal.drh_user_id', '')
        is_drh = drh_id_str and str(user.id) == drh_id_str

        # Check if user is location responsable
        responsible_locations = Location.search([
            ('responsible_user_ids', 'in', user.id),
        ])
        is_location_responsable = bool(responsible_locations)

        # Authorization: allow if self, admin, DRH, or responsable
        if not is_self and not is_admin and not is_drh and not is_location_responsable:
            return {
                'success': False,
                'error': _("Vous n'êtes pas autorisé à demander un congé pour cet employé")
            }

        # If responsable (not admin/DRH), verify employee is in their locations
        if is_location_responsable and not is_admin and not is_drh and not is_self:
            allowed_employee_ids = set()
            for loc in responsible_locations:
                if hasattr(loc, 'employee_ids_1') and loc.employee_ids_1:
                    allowed_employee_ids.update(loc.employee_ids_1.ids)

            if allowed_employee_ids and employee.id not in allowed_employee_ids:
                return {
                    'success': False,
                    'error': _("Cet employé n'est pas dans vos emplacements")
                }


        try:
            from datetime import datetime, timedelta

            _logger.info(
                "[CBM TIMEOFF] Request params: date_from=%s, number_of_days=%s",
                request_date_from, number_of_days
            )

            start_date = datetime.strptime(request_date_from, '%Y-%m-%d').date()
            num_days = float(number_of_days)

            # Calculate end date (inclusive)
            if num_days <= 1:
                end_date = start_date
            else:
                days_delta = math.ceil(num_days) - 1
                end_date = start_date + timedelta(days=days_delta)

            _logger.info(
                "[CBM TIMEOFF] Calculated: start=%s, end=%s",
                start_date, end_date
            )

            # Build vals - ONLY pass what the user entered.
            # Let Odoo's standard compute fields handle date_from/date_to/number_of_days.
            vals = {
                'holiday_status_id': holiday_status_id,
                'holiday_type': 'employee',  # Required: indicates employee-specific request
                'employee_id': employee_id,
                'request_date_from': start_date,
                'request_date_to': end_date,
                'name': name or _('Demande via portail CBM'),
            }

            # Half-day handling
            if num_days == 0.5:
                vals['request_unit_half'] = True
                vals['request_date_from_period'] = 'am'

            # Create leave request - Odoo will compute date_from/date_to/number_of_days
            leave_request = HolidayRequest.sudo().create(vals)

            # CRITICAL: Force Odoo to recompute date_from/date_to/number_of_days
            # by triggering the onchange. Writing the same value forces recomputation.
            leave_request.sudo().write({
                'request_date_from': start_date,
                'request_date_to': end_date,
            })

            # Refresh the record to get updated computed fields (display_name, number_of_days)
            leave_request.invalidate_recordset()
            leave_request = leave_request.sudo().browse(leave_request.id)

            # Post a message to track who actually submitted
            if not is_self:
                role = _('DRH') if is_drh else _('responsable')
                leave_request.message_post(
                    body=_("Demande créée par %s (%s) pour %s") % (
                        user.name, role, employee.name
                    ),
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                )

            _logger.info(
                "[CBM TIMEOFF] Created leave request %s for employee %s by user %s",
                leave_request.name or leave_request.id,
                employee.name,
                user.name
            )

            return {
                'success': True,
                'request_id': leave_request.id,
                'request_name': leave_request.display_name or _('Demande de congé créée'),
            }
        except Exception as e:
            _logger.error("[CBM TIMEOFF] Failed to create request: %s", str(e))
            return {'success': False, 'error': str(e)[:200]}

    @http.route('/cbm/get_timeoff_history', type='json', auth='user')
    def get_timeoff_history(self, limit=30):
        """Get time off request history for the current user.

        Returns leave requests for the current user's employee record,
        plus requests made by user as a responsable for their team.
        """
        try:
            user = request.env.user
            HolidayRequest = request.env['hr.leave'].sudo()
            Employee = request.env['hr.employee'].sudo()
            Location = request.env['stock.location'].sudo()

            # Get current user's employee record
            current_employee = Employee.search([
                ('user_id', '=', user.id),
                ('active', '=', True),
            ], limit=1)

            if not current_employee:
                return []

            # Get all employee IDs to include (self + team if responsable)
            employee_ids = {current_employee.id}

            # Check if user is a location responsable
            responsible_locations = Location.search([
                ('responsible_user_ids', 'in', user.id),
            ])

            if responsible_locations:
                for loc in responsible_locations:
                    if hasattr(loc, 'employee_ids_1') and loc.employee_ids_1:
                        employee_ids.update(loc.employee_ids_1.ids)

            # Fetch leave requests
            leaves = HolidayRequest.search([
                ('employee_id', 'in', list(employee_ids)),
            ], order='create_date desc', limit=limit)

            result = []
            for leave in leaves:
                result.append({
                    'id': leave.id,
                    'name': leave.name or '',
                    'employee_name': leave.employee_id.name if leave.employee_id else '',
                    'employee_id': leave.employee_id.id if leave.employee_id else False,
                    'is_self': leave.employee_id.id == current_employee.id if leave.employee_id else False,
                    'leave_type': leave.holiday_status_id.name if leave.holiday_status_id else '',
                    'date_from': str(leave.request_date_from) if leave.request_date_from else '',
                    'date_to': str(leave.request_date_to) if leave.request_date_to else '',
                    'number_of_days': leave.number_of_days_display or leave.number_of_days or 0,
                    'state': leave.state,
                    'state_display': dict(leave._fields['state'].selection).get(leave.state, leave.state),
                    'create_date': leave.create_date.isoformat() if leave.create_date else '',
                })

            return result
        except Exception as e:
            _logger.error("Error in get_timeoff_history: %s", str(e))
            return []

    @http.route('/cbm/timeoff/get_pdf/<int:leave_id>', type='http', auth='user')
    def get_timeoff_pdf(self, leave_id, **kwargs):
        """Génère et retourne le PDF d'une demande de congé.

        Seul l'employé concerné, un responsable de sa localisation, le DRH
        ou un administrateur système peut télécharger le PDF.
        """
        try:
            user = request.env.user
            Leave = request.env['hr.leave'].sudo()
            leave = Leave.browse(leave_id)

            if not leave.exists():
                return request.make_response(
                    "Demande introuvable.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')]
                )

            # Vérification d'accès : employé concerné, responsable, DRH, ou admin
            current_employee = request.env['hr.employee'].sudo().search(
                [('user_id', '=', user.id), ('active', '=', True)], limit=1
            )
            ICP = request.env['ir.config_parameter'].sudo()
            drh_id_str = ICP.get_param('clinic_staff_portal.drh_user_id', '')
            is_drh = bool(drh_id_str) and str(user.id) == drh_id_str.strip()
            is_system_admin = user.has_group('base.group_system')
            is_owner = (
                current_employee
                and leave.employee_id
                and leave.employee_id.id == current_employee.id
            )

            # Check if user is responsable for the leave employee's location
            is_responsable = False
            if leave.employee_id and not is_owner and not is_drh and not is_system_admin:
                Location = request.env['stock.location'].sudo()
                responsible_locations = Location.search(
                    [('responsible_user_ids', 'in', user.id)]
                )
                if responsible_locations:
                    allowed_employee_ids = set()
                    for loc in responsible_locations:
                        if hasattr(loc, 'employee_ids_1') and loc.employee_ids_1:
                            allowed_employee_ids.update(loc.employee_ids_1.ids)
                    is_responsable = leave.employee_id.id in allowed_employee_ids

            if not is_owner and not is_drh and not is_system_admin and not is_responsable:
                return request.make_response(
                    "Accès refusé.",
                    headers=[('Content-Type', 'text/plain; charset=utf-8')],
                    status=403
                )

            report = request.env.ref(
                'clinic_staff_portal.action_report_timeoff_request'
            ).sudo()
            pdf_content, _ = report._render_qweb_pdf(
                report.report_name, [leave_id]
            )

            filename = 'Conge_%s.pdf' % (leave.name or str(leave_id)).replace('/', '_')
            return request.make_response(
                pdf_content,
                headers=[
                    ('Content-Type', 'application/pdf'),
                    ('Content-Disposition', 'attachment; filename="%s"' % filename),
                    ('Content-Length', len(pdf_content)),
                ]
            )

        except Exception as e:
            _logger.error("CBM Timeoff: Erreur génération PDF pour congé %s: %s",
                          leave_id, str(e), exc_info=True)
            return request.make_response(
                "Erreur lors de la génération du PDF.",
                headers=[('Content-Type', 'text/plain; charset=utf-8')]
            )
