/** @odoo-module **/
/**
 * TimeOff Component - Extracted from CBMKiosk
 * Handles leave request form
 */

import { Component, useState, useRef, onMounted } from "@odoo/owl";
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
            timeoffSuccessLeaveId: null,
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
            this.state.timeoffSuccessLeaveId = result.request_id || null;
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
    
    printTimeOff() {
        if (this.state.timeoffSuccessLeaveId) {
            window.open('/cbm/timeoff/get_pdf/' + this.state.timeoffSuccessLeaveId, '_blank');
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

// ============================================================
// TimeoffRequests – management view for responsables
// ============================================================

export class TimeoffRequests extends Component {
    static template = "clinic_staff_portal.TimeoffRequests";

    setup() {
        this.rpc = useService("rpc");
        this.filterBarRef = useRef("filterBar");
        this.state = useState({
            leaves: [],
            loading: false,
            filter: 'all',          // 'all' | 'pending' | 'validate' | 'refuse'
            actionInProgress: null, // leave_id currently being acted on
        });
        this.loadLeaves();
        onMounted(() => this._snapIndicator());
    }

    // ---- helpers ----

    toTitleCase(name) {
        if (!name) return '';
        return name.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
    }

    getInitials(name) {
        if (!name) return '?';
        const parts = name.trim().split(/\s+/);
        if (parts.length === 1) return parts[0][0].toUpperCase();
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }

    // ---- filter pill sliding indicator ----

    setFilter(value) {
        this.state.filter = value;
        // after OWL re-renders, snap indicator to active chip
        setTimeout(() => this._snapIndicator(), 0);
    }

    hoverPill(btn) {
        const bar = this.filterBarRef.el;
        if (!bar) return;
        const indicator = bar.querySelector('.cbm_filter_pill_indicator');
        if (!indicator) return;
        const barRect = bar.getBoundingClientRect();
        const btnRect = btn.getBoundingClientRect();
        indicator.style.width  = btnRect.width  + 'px';
        indicator.style.height = btnRect.height + 'px';
        indicator.style.transform = `translateX(${btnRect.left - barRect.left - 4}px)`;
        indicator.classList.add('visible');
    }

    _snapIndicator() {
        const bar = this.filterBarRef.el;
        if (!bar) return;
        const active = bar.querySelector('.cbm_filter_chip.active');
        if (!active) return;
        this.hoverPill(active);
    }

    async loadLeaves() {
        try {
            this.state.loading = true;
            const result = await this.rpc('/cbm/timeoff_requests/get_all', {});
            if (result.success === false) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t('Erreur de chargement'), 'danger');
                }
                this.state.leaves = [];
            } else {
                this.state.leaves = result.leaves || [];
            }
        } catch (error) {
            console.error('[TIMEOFF REQUESTS] load error:', error);
            if (this.props.showToast) {
                this.props.showToast(_t('Erreur de connexion'), 'danger');
            }
        } finally {
            this.state.loading = false;
        }
    }

    async approveLeave(leaveId) {
        this.state.actionInProgress = leaveId;
        try {
            const result = await this.rpc('/cbm/timeoff_requests/approve', { leave_id: leaveId });
            if (result.success) {
                if (this.props.showToast) {
                    this.props.showToast(_t('Demande approuvée'), 'success');
                }
                await this.loadLeaves();
            } else {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t('Erreur lors de l\'approbation'), 'danger');
                }
            }
        } catch (error) {
            console.error('[TIMEOFF REQUESTS] approve error:', error);
            if (this.props.showToast) {
                this.props.showToast(_t('Erreur de connexion'), 'danger');
            }
        } finally {
            this.state.actionInProgress = null;
        }
    }

    async refuseLeave(leaveId) {
        this.state.actionInProgress = leaveId;
        try {
            const result = await this.rpc('/cbm/timeoff_requests/refuse', { leave_id: leaveId });
            if (result.success) {
                if (this.props.showToast) {
                    this.props.showToast(_t('Demande refusée'), 'success');
                }
                await this.loadLeaves();
            } else {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t('Erreur lors du refus'), 'danger');
                }
            }
        } catch (error) {
            console.error('[TIMEOFF REQUESTS] refuse error:', error);
            if (this.props.showToast) {
                this.props.showToast(_t('Erreur de connexion'), 'danger');
            }
        } finally {
            this.state.actionInProgress = null;
        }
    }

    printLeave(leaveId) {
        window.open('/cbm/timeoff/get_pdf/' + leaveId, '_blank');
    }

    get filteredLeaves() {
        const f = this.state.filter;
        if (f === 'all') return this.state.leaves;
        if (f === 'pending') return this.state.leaves.filter(l => ['draft', 'confirm', 'validate1'].includes(l.state));
        if (f === 'validate') return this.state.leaves.filter(l => l.state === 'validate');
        if (f === 'refuse') return this.state.leaves.filter(l => l.state === 'refuse');
        return this.state.leaves;
    }

    getStateClass(state) {
        if (['draft', 'confirm', 'validate1'].includes(state)) return 'state-pending';
        if (state === 'validate') return 'state-validate';
        if (state === 'refuse') return 'state-refuse';
        return 'state-draft';
    }

    getStateBadgeClass(state) {
        const map = {
            draft: 'cbm_badge_warning',
            confirm: 'cbm_badge_warning',
            validate1: 'cbm_badge_info',
            validate: 'cbm_badge_success',
            refuse: 'cbm_badge_danger',
        };
        return map[state] || 'cbm_badge_secondary';
    }

    getStateLabel(state) {
        const map = {
            draft: _t('Brouillon'),
            confirm: _t('En attente'),
            validate1: _t('Validation partielle'),
            validate: _t('Approuvé'),
            refuse: _t('Refusé'),
        };
        return map[state] || state;
    }

    canApprove(state) {
        return ['draft', 'confirm', 'validate1'].includes(state);
    }

    canRefuse(state) {
        return ['draft', 'confirm', 'validate1', 'validate'].includes(state);
    }

    goHome() {
        this.props.onNavigateHome();
    }
}

TimeoffRequests.props = {
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
};