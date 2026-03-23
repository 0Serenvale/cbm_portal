/** @odoo-module **/
/**
 * TimeOff Component - Extracted from CBMKiosk
 * Handles leave request form
 */

import { Component, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class TimeOffForm extends Component {
    static template = "clinic_staff_portal.TimeOffForm";
    
    setup() {
        this.rpc = useService("rpc");
        // Refs to read actual DOM values at submit time
        this.dateInputRef = useRef("dateInput");
        this.daysInputRef = useRef("daysInput");
        this.employeeSearchInputRef = useRef("employeeSearchInput");
        
        this.state = useState({
            timeoffLeaveTypes: [],
            timeoffEmployees: [],
            timeoffIsResponsable: false,
            timeoffCurrentEmployeeId: null,
            timeoffSelectedEmployeeId: null,
            timeoffSelectedLeaveTypeId: null,
            timeoffDateFrom: this.getTodayDate(),
            timeoffNumberOfDays: 1,
            timeoffReason: '',
            timeoffLoading: false,
            timeoffSubmitting: false,
            timeoffSuccess: false,
            timeoffSuccessMessage: '',
            timeoffEmployeeDropdownOpen: false,
            timeoffEmployeeSearch: '',
            timeoffHighlightedEmployeeIndex: -1,
        });
        
        this.loadTimeOffData();
    }
    
    getTodayDate() {
        return new Date().toISOString().split('T')[0];
    }
    
    async loadTimeOffData() {
        try {
            this.state.timeoffLoading = true;
            
            const [leaveTypes, employeeData] = await Promise.all([
                this.rpc('/cbm/get_timeoff_types', {}),
                this.rpc('/cbm/get_timeoff_employees', {})
            ]);
            
            this.state.timeoffLeaveTypes = leaveTypes || [];
            this.state.timeoffEmployees = employeeData.employees || [];
            this.state.timeoffIsResponsable = employeeData.is_responsable || false;
            this.state.timeoffCurrentEmployeeId = employeeData.current_employee_id || null;
            
            // Default to current employee
            if (this.state.timeoffCurrentEmployeeId) {
                this.state.timeoffSelectedEmployeeId = this.state.timeoffCurrentEmployeeId;
            }
            
            // Default to first leave type
            if (this.state.timeoffLeaveTypes.length > 0) {
                this.state.timeoffSelectedLeaveTypeId = this.state.timeoffLeaveTypes[0].id;
            }
            
            this.state.timeoffLoading = false;
        } catch (error) {
            console.error("Failed to load timeoff data:", error);
            this.state.timeoffLoading = false;
        }
    }
    
    toggleEmployeeDropdown() {
        this.state.timeoffEmployeeDropdownOpen = !this.state.timeoffEmployeeDropdownOpen;
        if (this.state.timeoffEmployeeDropdownOpen) {
            // Reset search and focus input
            this.state.timeoffEmployeeSearch = '';
            this.state.timeoffHighlightedEmployeeIndex = -1;
            setTimeout(() => {
                if (this.employeeSearchInputRef.el) {
                    this.employeeSearchInputRef.el.focus();
                }
            }, 50);
        }
    }
    
    onTimeOffEmployeeSelect(employeeId) {
        this.state.timeoffSelectedEmployeeId = employeeId;
        this.state.timeoffEmployeeDropdownOpen = false;
        this.state.timeoffEmployeeSearch = '';
        this.state.timeoffHighlightedEmployeeIndex = -1;
    }
    
    getFilteredEmployees() {
        const search = this.state.timeoffEmployeeSearch.toLowerCase().trim();
        if (!search) {
            return this.state.timeoffEmployees;
        }
        return this.state.timeoffEmployees.filter(emp => 
            emp.name.toLowerCase().includes(search)
        );
    }
    
    onEmployeeSearch() {
        // Reset highlighted index when search changes
        this.state.timeoffHighlightedEmployeeIndex = -1;
    }
    
    onEmployeeSearchKeydown(ev) {
        const filtered = this.getFilteredEmployees();
        
        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            this.state.timeoffHighlightedEmployeeIndex = 
                Math.min(this.state.timeoffHighlightedEmployeeIndex + 1, filtered.length - 1);
        } else if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            this.state.timeoffHighlightedEmployeeIndex = 
                Math.max(this.state.timeoffHighlightedEmployeeIndex - 1, -1);
        } else if (ev.key === 'Enter') {
            ev.preventDefault();
            if (this.state.timeoffHighlightedEmployeeIndex >= 0 && 
                this.state.timeoffHighlightedEmployeeIndex < filtered.length) {
                const selected = filtered[this.state.timeoffHighlightedEmployeeIndex];
                this.onTimeOffEmployeeSelect(selected.id);
            }
        } else if (ev.key === 'Escape') {
            ev.preventDefault();
            this.state.timeoffEmployeeDropdownOpen = false;
            this.state.timeoffEmployeeSearch = '';
            this.state.timeoffHighlightedEmployeeIndex = -1;
        }
    }
    
    onTimeOffLeaveTypeChange(event) {
        this.state.timeoffSelectedLeaveTypeId = parseInt(event.target.value) || null;
    }
    
    onTimeOffDateChange(event) {
        this.state.timeoffDateFrom = event.target.value;
    }

    onTimeOffDaysChange(event) {
        const value = parseFloat(event.target.value) || 0;
        this.state.timeoffNumberOfDays = Math.max(0.5, value);
    }
    
    onTimeOffReasonInput(event) {
        this.state.timeoffReason = event.target.value;
    }
    
    getSelectedEmployeeName() {
        const emp = this.state.timeoffEmployees.find(
            e => e.id === this.state.timeoffSelectedEmployeeId
        );
        return emp ? emp.name : _t('Sélectionner...');
    }
    
    isTimeOffFormValid() {
        return (
            this.state.timeoffSelectedEmployeeId &&
            this.state.timeoffSelectedLeaveTypeId &&
            this.state.timeoffDateFrom &&
            this.state.timeoffNumberOfDays > 0
        );
    }
    
    async submitTimeOff() {
        if (!this.isTimeOffFormValid()) {
            return;
        }
        
        try {
            this.state.timeoffSubmitting = true;
            
            // CRITICAL: Read values directly from the DOM inputs instead of state.
            // Date inputs don't reliably fire input/change events in all browsers,
            // so state may still hold the initial (today) value.
            const dateFromDOM = this.dateInputRef.el ? this.dateInputRef.el.value : null;
            const daysFromDOM = this.daysInputRef.el ? parseFloat(this.daysInputRef.el.value) : null;
            
            const dateFrom = dateFromDOM || this.state.timeoffDateFrom;
            const numberOfDays = daysFromDOM || this.state.timeoffNumberOfDays;
            
            console.log('[TIMEOFF] Submitting:', {
                date_from_DOM: dateFromDOM,
                date_from_state: this.state.timeoffDateFrom,
                date_from_used: dateFrom,
                days_DOM: daysFromDOM,
                days_state: this.state.timeoffNumberOfDays,
                days_used: numberOfDays,
            });
            
            const result = await this.rpc('/cbm/submit_timeoff', {
                holiday_status_id: this.state.timeoffSelectedLeaveTypeId,
                employee_id: this.state.timeoffSelectedEmployeeId,
                request_date_from: dateFrom,
                number_of_days: numberOfDays,
                name: this.state.timeoffReason || '',
            });
            
            if (result.success === false) {
                console.error("[TIMEOFF] Backend error:", result.error);
                if (this.props.showToast) {
                    this.props.showToast(
                        result.error || _t("Erreur lors de la création de la demande"),
                        'danger'
                    );
                }
                this.state.timeoffSubmitting = false;
                return;
            }
            
            this.state.timeoffSuccess = true;
            this.state.timeoffSuccessMessage = result.request_name || _t('Demande créée avec succès');
            this.state.timeoffSubmitting = false;
            
        } catch (error) {
            console.error("[TIMEOFF] Failed to submit:", error);
            if (this.props.showToast) {
                this.props.showToast(
                    _t("Erreur de connexion, veuillez réessayer"),
                    'danger'
                );
            }
            this.state.timeoffSubmitting = false;
        }
    }
    
    goHome() {
        this.props.onNavigateHome();
    }
}

TimeOffForm.props = {
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
};