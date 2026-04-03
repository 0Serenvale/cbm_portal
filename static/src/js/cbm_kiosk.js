/** @odoo-module **/
/**
 * CBM Kiosk - Main Client Action
 *
 * Single-page application (SPA) for clinic staff.
 * States: home → request/consumption_menu → consumption_patient/consumption_department → consumption_products → success
 */

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { TimeOffForm, TimeoffRequests } from "../components/timeoff/timeoff";
import { DocumentsViewer } from "../components/documents/documents";
import { AccountabilityDashboard } from "../components/accountability/accountability";
import { InventoryCount } from "../components/inventory/inventory";
import { InventoryBanner } from "../components/inventory/inventory_banner";

class CBMKiosk extends Component {
    static template = "clinic_staff_portal.CBMKiosk";
    static components = { TimeOffForm, TimeoffRequests, DocumentsViewer, AccountabilityDashboard, InventoryCount, InventoryBanner };
    
    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        this.searchInputRef = useRef("searchInput");
        this.barcodeInputRef = useRef("barcodeInput");
        this.patientSearchRef = useRef("patientSearchInput");

        this.state = useState({
            // UI State
            currentState: "home",
            loading: true,
            error: null,

            // Custom toast notifications
            toasts: [],

            // Confirmation modal
            confirmModal: null,
            
            // User Context
            userContext: null,
            operationTypes: [],
            
            // Selected operation
            selectedOpType: null,
            
            // Patient (for billable)
            selectedPatient: null,
            patientSearchQuery: "",
            patientResults: [],
            patientLoading: false,

            // Department (for non-patient consumptions)
            selectedDepartment: null,
            departmentList: [],
            departmentLoading: false,

            // Products
            productSearchQuery: "",
            productResults: [],
            productLoading: false,
            selectedProducts: [],
            removedProducts: [],  // Pre-loaded products that were removed (for returns)
            selectedResultIndex: -1,  // For keyboard navigation

            // Quick Pick (patient consumption only)
            quickPick: {
                enabled: false,
                locationName: '',
                products: [],
                clickCounts: {},  // {product_id: pending_click_count}
            },
            quickPickTimer: null,  // Timer for 500ms auto-submit delay

            // Alert Banner (unified for all notifications)
            showAlertBanner: false,
            alertBannerMessage: "",
            alertBannerType: "warning", // warning, error, info, success

            // Prescription (Bahmni drug orders)
            prescriptionLines: [],         // {prescription_line_id, product_id, product_name, qty_prescribed, qty_applied, qty_remaining, qty_to_apply, provider_name, ...}
            prescriptionConsumables: [],    // Nurse-added non-drug items [{id, name, qty, ...}]
            rxConsumableSearchQuery: "",
            rxConsumableResults: [],
            rxSelectedResultIndex: -1,
            rxActiveTab: 'prescription',   // 'prescription' | 'consumables'

            // Custom Tiles (from tile manager)
            customTiles: [],
            
            // Pending Approvals (for sidebar)
            pendingApprovals: {
                show_sidebar: true,
                is_admin: false,
                is_location_responsable: false,
                is_po_approver: false,
                my_requests_count: 0,
                to_approve_count: 0,
                my_receptions_count: 0,
                pending_po_count: 0,
                responsible_location_ids: [],
                transfer_status: 'ok',
                request_status: 'ok',
                consumption_status: 'ok',
            },
            
            // Financial Dashboard (for executives)
            financials: {
                is_executive: false,
                total_at_risk: 0,
                pending_count: 0,
                currency_symbol: 'CFA',
            },
            // financialDepartments moved to AccountabilityDashboard component
            
            // Brain Suggestions (smart replenishment)
            brainStatus: {
                has_suggestions: false,
                suggestion_count: 0,
                critical_count: 0,
                warning_count: 0,
                user_location_type: 'none',
                picking_type_id: 0,
            },
            
            // Replenishment Dashboard
            replenishmentItems: [],
            selectedReplenishmentIds: [],
            replenishmentLocationType: 'none',
            replenishmentSubmitting: false,
            
            // PO Creation (CBM Portal Procurement)
            poVendors: [],
            poVendorSearchQuery: '',
            poVendorSelectedIndex: -1,
            poSelectedVendorId: null,
            poSelectedVendorName: '',
            poProductSearchQuery: '',
            poProductResults: [],
            poProductLoading: false,
            
            // PO Tracking Page (Purchase Dashboard)
            poList: [],
            poListAll: [],  // Unfiltered list for client-side filtering
            poListLoading: false,
            poStats: {
                draft_count: 0,
                to_approve_count: 0,
                reception_count: 0,
            },
            poFilterState: 'all',  // 'all', 'draft', 'to approve', 'purchase', 'cancel', 'reception'
            poFilterSearch: '',
            poFilterDateFrom: '',
            poFilterDateTo: '',
            
            // PO Edit (full page state: 'po_edit')
            currentPO: null,
            poLines: [],
            poEditLoading: false,
            poEditReadOnly: false,  // true when viewing non-draft PO
            poEditProductSearch: '',
            poEditProductResults: [],
            availableTaxes: [],
            
            // PO Create (dedicated page state: 'po_create')
            poCreate: {
                vendor_id: null,
                vendor_name: '',
                reference: '',  // Vendor invoice reference (optional, unique per vendor if provided)
                lines: [],      // [{product_id, product_name, product_code, qty, price, tax_ids, subtotal}]
                total: 0,
                loading: false,
                submitting: false,
            },
            poCreateProductSearch: '',
            poCreateProductResults: [],
            poCreateProductLoading: false,
            poCreateSelectedIndex: -1,

            

            // Reception (Phase 3)
            receptionMode: 'list',  // 'list' | 'detail'
            pendingReceptions: [],
            receptionsLoading: false,
            currentReception: null,
            receptionLines: [],
            showCompletedReceptions: false,
            receptionSuccess: false,  // Success overlay flag
            receptionSuccessMessage: '',
            

            // Compliance lock (managed by DocumentsViewer component via callback)
            isComplianceLocked: false,

            // History
            historyItems: [],
            historyOffset: 0,
            historyLimit: 40,
            historyHasMore: true,
            historyLoading: false,

            
            // Modal
            showModal: false,
            modalData: null,
            
            // Success
            successMessage: "",
            
            // Maintenance Request
            maintenanceDescription: "",
            equipmentSearchQuery: "",
            equipmentResults: [],
            selectedEquipment: null,
            equipmentLoading: false,

            // Time Off History (for suivi page - form handled by TimeOffForm component)
            timeoffHistory: [],
            timeoffHistoryLoading: false,
            historyActiveTab: 'transfers',

            // Cashier
            hasCashierAccess: false,
            cashierSearchQuery: "",
            cashierSearchResults: [],
            cashierSelectedDocument: null,
            cashierLoading: false,
            workspaceLoading: false,  // Separate loading for workspace to avoid table flicker
            
            // Cashier Payment Modal (Blue cards - validation)
            showCashierPayModal: false,

            // Sorting State
            sortState: {
                listName: null,
                column: null,
                direction: 'asc'
            },
            sortDirections: {},  // For PO Create lines sorting
            cashierPaymentMethod: 'cash',
            cashierPaymentAmount: 0,  // For partial payments
            cashierSplitPreview: null,
            cashierValidating: false,
            cashierConventionEnabled: false,  // Toggle: Sans/Avec Convention
            cashierConventions: [],  // Available conventions (pricelists with coverage > 0)
            cashierSelectedConventionId: null,  // Selected convention pricelist ID
            
            // Cashier Pay Remainder Modal (Orange cards)
            showPayRemainderModal: false,
            payRemainderInvoice: null,
            payRemainderAmount: 0,
            payRemainderMethod: 'cash',
            payRemainderProcessing: false,
            
            // Phase 4: Cancel Confirmation Modal
            showCancelModal: false,
            cancelInvoice: null,
            cancelReason: '',
            cancelProcessing: false,
            
            // Phase 4: Refund Wizard Modal
            showRefundWizard: false,
            refundInvoice: null,
            refundMode: 'total',  // 'total', 'partial', 'partial_close'
            refundAmount: 0,
            refundReason: '',
            refundProcessing: false,
            
            // Phase 4: Status Modal (red cards)
            showStatusModal: false,
            statusData: null,
            statusLoading: false,
            
            // ====== PHASE 5: CASHIER SPLIT VIEW WORKSTATION ======
            cashierMode: 'dashboard',  // 'dashboard' | 'workspace' | 'session'
            cashierFilter: 'all',      // 'all' | 'draft' | 'unpaid' | 'paid'
            cashierSelectedId: null,    // ID of selected row
            cashierSession: { is_open: false, running_total: 0, payment_count: 0 },
            cashierPollingInterval: null,
            cashierPaymentSuccess: false,   // Show success overlay
            cashierChangeDue: 0,
            cashierSuccessInvoiceId: null,
            cashierLightMode: localStorage.getItem('cbm_cashier_theme') === 'light',  // Theme preference

            // Undo toast state
            cashierUndoToast: null,  // { message, timeoutId }

            // Document details for workspace panel
            cashierDocumentLines: [],           // Product lines to display
            cashierDocumentConvention: null,    // Convention name if any
            cashierDocumentConventionPct: 0,    // Convention % coverage

            // Kiosk theme preference (separate from cashier)
            kioskDarkMode: localStorage.getItem('cbm_kiosk_theme') === 'dark',

            // Deletion confirmation modal (consumption returns)
            showDeletionModal: false,
            deletionConfirmItems: null,  // [{product_name, qty_removed, ...}]
            deletionMessage: '',

            // Workstation info (from log_access response)
            workstationIp: '',
            workstationLocation: '',
            workstationName: '',
            activityStatus: 'active',  // 'active' | 'idle'
            dualSessionWarning: '',

            // Dashboard recent activity feed
            recentActivity: [],

            // Inventory Session (for inventory counting)
            inventorySession: null,  // Populated on goToInventory()
        });
        
        onWillStart(async () => {
            await this.loadUserContext();
            await this.loadCustomTiles();
            await this.loadPendingApprovals();
            await this.loadFinancials();
            await this.loadBrainStatus();
            await this.checkCashierAccess();
            // Log kiosk access (IP, screen resolution) - fire and forget
            this.logKioskAccess();
            // Load recent activity for dashboard sidebar - fire and forget
            this.loadRecentActivity();
        });
        
        // Keyboard navigation for cashier table
        this._onKeyDown = this._onKeyDown.bind(this);

        // Activity status tracking
        this._lastLocalActivity = Date.now();
        this._activityCheckInterval = null;
        this._onLocalActivity = () => { this._lastLocalActivity = Date.now(); this.state.activityStatus = 'active'; };
        const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "scroll", "touchstart", "click", "input", "change", "focusin"];

        onMounted(() => {
            document.addEventListener('keydown', this._onKeyDown);
            for (const evt of ACTIVITY_EVENTS) {
                document.addEventListener(evt, this._onLocalActivity, { passive: true });
            }
            this._activityCheckInterval = setInterval(() => {
                const idle = Date.now() - this._lastLocalActivity > 60000;
                this.state.activityStatus = idle ? 'idle' : 'active';
            }, 30000);
        });

        onWillUnmount(() => {
            document.removeEventListener('keydown', this._onKeyDown);
            for (const evt of ACTIVITY_EVENTS) {
                document.removeEventListener(evt, this._onLocalActivity);
            }
            if (this._activityCheckInterval) clearInterval(this._activityCheckInterval);
        });
    }

    async loadRecentActivity() {
        try {
            const items = await this.rpc('/cbm/get_history', { limit: 5 });
            this.state.recentActivity = (items || []).map(p => ({
                name: p.name,
                state: p.state,
                portal_behavior: p.portal_behavior,
                create_date: p.create_date,
                partner_name: p.partner_name || false,
            }));
        } catch (e) {
            // Non-blocking — dashboard still works without recent activity
            this.state.recentActivity = [];
        }
    }

    _formatRelativeTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        const diffMs = Date.now() - date.getTime();
        const diffMin = Math.floor(diffMs / 60000);
        if (diffMin < 1) return 'À l\'instant';
        if (diffMin < 60) return `Il y a ${diffMin} min`;
        const diffH = Math.floor(diffMin / 60);
        if (diffH < 24) return `Il y a ${diffH}h`;
        if (diffH < 48) return 'Hier';
        return `Il y a ${Math.floor(diffH / 24)}j`;
    }

    _recentDotClass(state) {
        if (state === 'done') return 'dot_done';
        if (['assigned', 'confirmed', 'waiting'].includes(state)) return 'dot_pending';
        if (state === 'cancel') return 'dot_cancel';
        return 'dot_draft';
    }

    // Custom toast notification system
    showToast(message, type = 'info', duration = 4000) {
        const id = Date.now();
        const toast = { id, message, type };
        this.state.toasts = [...this.state.toasts, toast];

        // Auto-dismiss (except errors)
        if (type !== 'danger') {
            setTimeout(() => this.dismissToast(id), duration);
        }
    }

    dismissToast(id) {
        this.state.toasts = this.state.toasts.filter(t => t.id !== id);
    }

    // Confirmation modal system
    async showConfirm(title, message, type = 'info', confirmText = 'Confirmer') {
        return new Promise((resolve) => {
            this.state.confirmModal = {
                title,
                message,
                type,
                confirmText,
                resolve
            };
        });
    }

    confirmAction() {
        if (this.state.confirmModal && this.state.confirmModal.resolve) {
            this.state.confirmModal.resolve(true);
            this.state.confirmModal = null;
        }
    }

    cancelConfirm() {
        if (this.state.confirmModal && this.state.confirmModal.resolve) {
            this.state.confirmModal.resolve(false);
            this.state.confirmModal = null;
        }
    }

    _onKeyDown(ev) {
        // Only handle when in cashier state
        if (this.state.currentState !== 'cashier') return;
        if (this.state.cashierPaymentSuccess) return;
        
        const results = this.filteredCashierResults || [];
        if (results.length === 0) return;
        
        // Find current index
        let currentIndex = results.findIndex(doc => doc.id === this.state.cashierSelectedId);
        
        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            const newIndex = currentIndex < results.length - 1 ? currentIndex + 1 : 0;
            this.selectCashierRow(results[newIndex]);
            this._scrollToSelectedRow();
        } else if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            const newIndex = currentIndex > 0 ? currentIndex - 1 : results.length - 1;
            this.selectCashierRow(results[newIndex]);
            this._scrollToSelectedRow();
        } else if (ev.key === 'Escape') {
            ev.preventDefault();
            this.closeCashierWorkspace();
        }
    }
    
    _scrollToSelectedRow() {
        setTimeout(() => {
            const selectedRow = document.querySelector('.cbm_cashier_row.selected');
            if (selectedRow) {
                selectedRow.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }, 10);
    }
    
    // ==================== DATA LOADING ====================
    
    async loadUserContext() {
        try {
            this.state.loading = true;
            const result = await this.rpc("/cbm/get_user_context", {});
            this.state.userContext = result;
            this.state.operationTypes = result.operation_types || [];
            this.state.loading = false;
            
            // NOTE: Fullscreen kiosk mode is now handled by kiosk_body_class.js
            // which runs earlier to prevent navbar flash in Firefox.
            // No need to add the class here anymore.
        } catch (error) {
            this.state.error = _t("Failed to load user context");
            this.state.loading = false;
        }
    }
    
    async loadCustomTiles() {
        try {
            const result = await this.rpc("/cbm/get_custom_tiles", {});
            this.state.customTiles = result || [];
        } catch (error) {
            // Fail silently - custom tiles are optional
            this.state.customTiles = [];
        }
    }
    
    /**
     * Log kiosk access for analytics (IP, screen resolution).
     * Also populates workstation info + dual-session warning.
     */
    logKioskAccess() {
        this.rpc("/cbm/log_access", {
            screen_width: window.screen.width,
            screen_height: window.screen.height,
            user_agent: navigator.userAgent,
        }).then((result) => {
            if (result && result.workstation) {
                this.state.workstationIp = result.workstation.ip || '';
                this.state.workstationLocation = result.workstation.location || '';
                this.state.workstationName = result.workstation.name || '';
            }
            if (result && result.dual_session_warning) {
                this.state.dualSessionWarning = result.dual_session_warning;
            }
        }).catch(() => {
            // Fail silently - logging is non-critical
        });
    }
    
    async loadPendingApprovals() {
        try {
            const result = await this.rpc("/cbm/get_pending_approvals", {});
            console.log('[CBM DEBUG] pendingApprovals result:', result);
            this.state.pendingApprovals = result || {
                show_sidebar: true,
                is_admin: false,
                my_requests_count: 0,
                to_approve_count: 0,
                my_receptions_count: 0,
                pending_po_count: 0,
                responsible_location_ids: [],
                transfer_status: 'ok',
                request_status: 'ok',
                consumption_status: 'ok',
            };
        } catch (error) {
            // Fail silently - approvals sidebar is optional
            this.state.pendingApprovals = {
                show_sidebar: true,
                is_admin: false,
                my_requests_count: 0,
                to_approve_count: 0,
                my_receptions_count: 0,
                pending_po_count: 0,
                responsible_location_ids: [],
                transfer_status: 'ok',
                request_status: 'ok',
                consumption_status: 'ok',
            };
        }
    }
    
    async loadFinancials() {
        try {
            const result = await this.rpc("/cbm/financial_summary", {});
            this.state.financials = result || {
                is_executive: false,
                total_at_risk: 0,
                pending_count: 0,
                currency_symbol: 'CFA',
            };
        } catch (error) {
            // Fail silently - financials are optional
            this.state.financials = {
                is_executive: false,
                total_at_risk: 0,
                pending_count: 0,
                currency_symbol: 'CFA',
            };
        }
    }
    
    async loadBrainStatus() {
        try {
            const result = await this.rpc("/cbm/brain/get_user_status", {});
            this.state.brainStatus = result || {
                has_suggestions: false,
                suggestion_count: 0,
                critical_count: 0,
                warning_count: 0,
                user_location_type: 'none',
                picking_type_id: 0,
            };
        } catch (error) {
            // Fail silently - brain integration is optional
            this.state.brainStatus = {
                has_suggestions: false,
                suggestion_count: 0,
                critical_count: 0,
                warning_count: 0,
                user_location_type: 'none',
                picking_type_id: 0,
            };
        }
    }
    
    async openBrainSuggestions() {
        // Navigate to Replenishment Dashboard
        this.state.loading = true;
        try {
            const result = await this.rpc("/cbm/brain/get_replenishment_list", { limit: 50 });
            this.state.replenishmentItems = result.items || [];
            this.state.replenishmentLocationType = result.location_type || 'none';
            this.state.selectedReplenishmentIds = [];  // Reset selection
            this.state.currentState = 'replenishment';
        } catch (error) {
            this.showToast(_t("Erreur lors du chargement des suggestions"), 'danger');
        }
        this.state.loading = false;
    }

    /**
     * Smart back button for replenishment page
     * - Reception users: return to Purchase Dashboard
     * - Ward users: return to Home
     */
    goBackFromReplenishment() {
        if (this.state.replenishmentLocationType === 'reception') {
            // Reception user - return to Purchase Dashboard
            this.goToPOList();
        } else {
            // Ward user - return to Home
            this.goHome();
        }
    }
    
    toggleReplenishmentItem(item) {
        const idx = this.state.selectedReplenishmentIds.indexOf(item.id);
        if (idx > -1) {
            this.state.selectedReplenishmentIds.splice(idx, 1);
        } else {
            this.state.selectedReplenishmentIds.push(item.id);
        }
    }
    
    isReplenishmentSelected(item) {
        return this.state.selectedReplenishmentIds.includes(item.id);
    }
    
    selectAllReplenishment() {
        this.state.selectedReplenishmentIds = this.state.replenishmentItems.map(i => i.id);
    }
    
    deselectAllReplenishment() {
        this.state.selectedReplenishmentIds = [];
    }
    
    updateReplenishmentQty(item, event) {
        const newQty = parseFloat(event.target.value);
        if (newQty && newQty > 0) {
            item.suggested_qty = newQty;
        }
    }
    
    async submitReplenishment() {
        const selectedItems = this.state.replenishmentItems
            .filter(i => this.state.selectedReplenishmentIds.includes(i.id))
            .map(i => ({ id: i.id, qty: i.suggested_qty }));
        
        if (selectedItems.length === 0) {
            this.showToast(_t("Sélectionnez au moins un produit"), 'warning');
            return;
        }

        this.state.replenishmentSubmitting = true;
        
        try {
            let result;
            if (this.state.replenishmentLocationType === 'reception') {
                // Main stock - create draft PO
                result = await this.rpc("/cbm/brain/create_draft_po_from_selection", { items: selectedItems });
            } else {
                // Ward - create internal request
                result = await this.rpc("/cbm/brain/create_request_from_selection", { items: selectedItems });
            }
            
            if (result.success) {
                this.showToast(result.message, 'success');

                // Remove submitted items from list
                this.state.replenishmentItems = this.state.replenishmentItems.filter(
                    i => !this.state.selectedReplenishmentIds.includes(i.id)
                );
                this.state.selectedReplenishmentIds = [];
                
                // Update brain status count
                this.state.brainStatus.suggestion_count = this.state.replenishmentItems.length;
                this.state.brainStatus.has_suggestions = this.state.replenishmentItems.length > 0;
                
                // If no items left, go home
                if (this.state.replenishmentItems.length === 0) {
                    this.goHome();
                }
            } else {
                this.showToast(result.error || _t("Erreur"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur lors de la soumission"), 'danger');
        }

        this.state.replenishmentSubmitting = false;
    }
    
    // ==================== PO CREATION (CBM Portal Procurement) ====================
    
    async loadVendors(query = '') {
        try {
            const result = await this.rpc("/cbm/purchase/get_vendors", { query, limit: 50 });
            this.state.poVendors = result || [];
            this.state.poVendorSelectedIndex = -1;  // Reset selection on new search
        } catch (error) {
            this.showToast(_t("Erreur chargement fournisseurs"), 'danger');
        }
    }
    
    onVendorSearchInput(event) {
        const query = event.target.value;
        this.state.poVendorSearchQuery = query;
        if (query.length >= 2) {
            this.loadVendors(query);
        } else if (query.length === 0) {
            this.loadVendors();  // Load all
        }
    }
    
    onVendorSearchBlur() {
        // Delay to allow click on dropdown item to register first
        setTimeout(() => {
            this.state.poVendors = [];
            this.state.poVendorSelectedIndex = -1;
        }, 200);
    }

    /**
     * Handle keyboard navigation in vendor search dropdown
     */
    onVendorSearchKeydown(ev) {
        const vendors = this.state.poVendors;

        switch (ev.key) {
            case 'ArrowDown':
                ev.preventDefault();
                if (vendors.length) {
                    this.state.poVendorSelectedIndex = Math.min(
                        this.state.poVendorSelectedIndex + 1,
                        vendors.length - 1
                    );
                }
                break;
            case 'ArrowUp':
                ev.preventDefault();
                this.state.poVendorSelectedIndex = Math.max(
                    this.state.poVendorSelectedIndex - 1,
                    0
                );
                break;
            case 'Enter':
                ev.preventDefault();
                if (this.state.poVendorSelectedIndex >= 0 && this.state.poVendorSelectedIndex < vendors.length) {
                    this.setPOCreateVendor(vendors[this.state.poVendorSelectedIndex]);
                } else if (vendors.length === 1) {
                    // Auto-select if only one result
                    this.setPOCreateVendor(vendors[0]);
                } else if (vendors.length === 0 && this.state.poVendorSearchQuery.length >= 2) {
                    // No results - create new vendor
                    this.createVendorAndSetPOCreate(this.state.poVendorSearchQuery);
                }
                break;
            case 'Escape':
                this.state.poVendors = [];
                this.state.poVendorSelectedIndex = -1;
                break;
        }
    }

    selectVendor(vendor) {
        this.state.poSelectedVendorId = vendor.id;
        this.state.poSelectedVendorName = vendor.name;
        this.state.poVendorSearchQuery = '';
        this.state.poVendors = [];  // Clear dropdown
    }
    
    clearVendor() {
        this.state.poSelectedVendorId = null;
        this.state.poSelectedVendorName = '';
    }
    
    async createVendorAndSelect(name) {
        if (!name || name.trim().length < 2) {
            this.showToast(_t("Nom du fournisseur trop court"), 'warning');
            return;
        }

        try {
            const result = await this.rpc("/cbm/purchase/create_vendor", { name: name.trim() });
            if (result.success) {
                // Auto-select the created vendor
                this.state.poSelectedVendorId = result.vendor_id;
                this.state.poSelectedVendorName = result.vendor_name;
                this.state.poVendorSearchQuery = '';
                this.state.poVendors = [];
                this.showToast(_t("Fournisseur créé: ") + result.vendor_name, 'success');
            } else {
                this.showToast(result.error || _t("Erreur création fournisseur"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur création fournisseur"), 'danger');
        }
    }

    
    onProductSearchBlur() {
        // Delay to allow click on dropdown item to register first
        setTimeout(() => {
            this.state.poProductResults = [];
        }, 200);
    }
    

    async searchPOProducts(event) {
        const query = event.target.value;
        this.state.poProductSearchQuery = query;
        
        if (query.length < 2) {
            this.state.poProductResults = [];
            return;
        }
        
        try {
            this.state.poProductLoading = true;
            const result = await this.rpc("/cbm/search_products", {
                query,
                purchase_mode: true,
                limit: 20
            });
            this.state.poProductResults = result || [];
            this.state.poProductLoading = false;
        } catch (error) {
            this.state.poProductLoading = false;
        }
    }
    
    addPOProductToList(product) {
        // Check if already in list
        const existing = this.state.replenishmentItems.find(
            i => i.product_id === product.id
        );
        
        if (existing) {
            // Just select it
            if (!this.state.selectedReplenishmentIds.includes(existing.id)) {
                this.state.selectedReplenishmentIds.push(existing.id);
            }
            this.showToast(_t("Produit déjà dans la liste"), 'info');
        } else {
            // Add new item at top (unshift for kiosk behavior)
            const newItem = {
                id: `new_${Date.now()}_${product.id}`,
                product_id: product.id,
                product_name: product.name || product.display_name,
                suggested_qty: 1,
                current_stock: product.current_stock || 0,
                location_name: product.location_name || '',
                price: product.standard_price || 0,
                uom_name: product.uom_po_name || product.uom_name || 'Unité',
                uom_id: product.uom_po_id || product.uom_id,
                severity: 'info',
                is_new: true,
            };


            this.state.replenishmentItems.unshift(newItem);
            this.state.selectedReplenishmentIds.push(newItem.id);
        }
        
        // Clear search
        this.state.poProductSearchQuery = '';
        this.state.poProductResults = [];
    }
    
    updateReplenishmentPrice(item, event) {
        const newPrice = parseFloat(event.target.value);
        if (!isNaN(newPrice) && newPrice >= 0) {
            item.price = newPrice;
        }
    }
    
    async createProductAndAdd(name) {
        if (!name || name.trim().length < 2) {
            this.showToast(_t("Nom du produit trop court"), 'warning');
            return;
        }

        try {
            const result = await this.rpc("/cbm/purchase/create_product", { name: name.trim() });
            if (result.success) {
                // Add to list
                const newItem = {
                    id: `new_${Date.now()}_${result.product_id}`,
                    product_id: result.product_id,
                    product_name: result.product_name,
                    suggested_qty: 1,
                    price: 0,
                    uom_name: 'Unité',
                    severity: 'info',
                    is_new: true,
                };
                this.state.replenishmentItems.unshift(newItem);
                this.state.selectedReplenishmentIds.push(newItem.id);
                this.showToast(_t("Produit créé: ") + result.product_name, 'success');
            } else {
                this.showToast(result.error || _t("Erreur création produit"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur création produit"), 'danger');
        }
        
        // Clear search
        this.state.poProductSearchQuery = '';
        this.state.poProductResults = [];
    }
    
    async submitPOWithVendor() {
        if (!this.state.poSelectedVendorId) {
            this.showToast(_t("Sélectionnez un fournisseur"), 'warning');
            return;
        }

        const selectedItems = this.state.replenishmentItems.filter(
            i => this.state.selectedReplenishmentIds.includes(i.id)
        );

        if (selectedItems.length === 0) {
            this.showToast(_t("Sélectionnez au moins un produit"), 'warning');
            return;
        }

        const lines = selectedItems.map(item => ({
            product_id: item.product_id,
            qty: item.suggested_qty,
            price: item.price || 0,
            uom_id: item.uom_id || null,
        }));

        this.state.replenishmentSubmitting = true;

        try {
            const result = await this.rpc("/cbm/purchase/create_po", {
                vendor_id: this.state.poSelectedVendorId,
                lines
            });

            if (result.success) {
                this.showToast(result.message, 'success');

                // Clear selected items
                this.state.replenishmentItems = this.state.replenishmentItems.filter(
                    i => !this.state.selectedReplenishmentIds.includes(i.id)
                );
                this.state.selectedReplenishmentIds = [];
                this.clearVendor();

                // Go to PO list or home
                this.goToPOList();
            } else {
                this.showToast(result.error || _t("Erreur"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur lors de la création"), 'danger');
        }

        this.state.replenishmentSubmitting = false;
    }
    
    // ==================== PO LIST (Tracking Page) ====================
    
    async goToPOList() {
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();
        this.state.poListLoading = true;
        this.state.currentState = 'po_list';

        try {
            const result = await this.rpc("/cbm/purchase/get_my_pos", { limit: 50 });

            // Handle new response format with stats
            if (result.pos) {
                this.state.poListAll = result.pos;
                this.state.poList = result.pos;  // Start with unfiltered
                this.state.poStats = result.stats || {
                    draft_count: 0,
                    to_approve_count: 0,
                    reception_count: 0,
                };
            } else {
                // Legacy format fallback
                this.state.poListAll = result || [];
                this.state.poList = result || [];
            }

            // Apply filters if any are set
            this.applyPOFilters();
        } catch (error) {
            this.showToast(_t("Erreur chargement bons de commande"), 'danger');
        }

        this.state.poListLoading = false;
    }

    /**
     * Apply filters to PO list (client-side filtering)
     */
    applyPOFilters() {
        let filtered = [...this.state.poListAll];

        // Filter by state
        if (this.state.poFilterState && this.state.poFilterState !== 'all') {
            if (this.state.poFilterState === 'reception') {
                // Special filter: show only POs that can be received
                filtered = filtered.filter(po => po.can_receive === true);
            } else {
                filtered = filtered.filter(po => po.state === this.state.poFilterState);
            }
        }

        // Filter by search (BC number, reference, vendor)
        if (this.state.poFilterSearch) {
            const search = this.state.poFilterSearch.toLowerCase();
            filtered = filtered.filter(po =>
                po.name.toLowerCase().includes(search) ||
                (po.reference && po.reference.toLowerCase().includes(search)) ||
                po.vendor_name.toLowerCase().includes(search)
            );
        }

        // Filter by date range
        if (this.state.poFilterDateFrom || this.state.poFilterDateTo) {
            filtered = filtered.filter(po => {
                if (!po.date) return false;

                // Parse DD/MM/YYYY to compare
                const [day, month, year] = po.date.split('/');
                const poDate = new Date(year, month - 1, day);

                if (this.state.poFilterDateFrom) {
                    const fromDate = new Date(this.state.poFilterDateFrom);
                    if (poDate < fromDate) return false;
                }

                if (this.state.poFilterDateTo) {
                    const toDate = new Date(this.state.poFilterDateTo);
                    if (poDate > toDate) return false;
                }

                return true;
            });
        }

        this.state.poList = filtered;
    }

    /**
     * Update filter state
     */
    updatePOFilter(filterType, value) {
        if (filterType === 'state') {
            this.state.poFilterState = value;
        } else if (filterType === 'search') {
            this.state.poFilterSearch = value;
        } else if (filterType === 'dateFrom') {
            this.state.poFilterDateFrom = value;
        } else if (filterType === 'dateTo') {
            this.state.poFilterDateTo = value;
        }

        this.applyPOFilters();
    }

    /**
     * Clear all filters
     */
    clearPOFilters() {
        this.state.poFilterState = 'all';
        this.state.poFilterSearch = '';
        this.state.poFilterDateFrom = '';
        this.state.poFilterDateTo = '';
        this.applyPOFilters();
    }

    getPOStateClass(state) {
        switch(state) {
            case 'draft':
                return 'status-secondary';  // Gray - draft
            case 'sent':
            case 'to approve':
                return 'status-warning';  // Yellow - waiting for approval
            case 'purchase':
            case 'done':
                return 'status-success';  // Green - approved
            case 'cancel':
                return 'status-danger';   // Red - cancelled
            default:
                return 'status-secondary';
        }
    }
    

    async goToReception(po) {
        if (!po.can_receive || !po.picking_id) {
            this.showToast(_t("Pas de réception disponible"), 'warning');
            return;
        }

        // Open reception detail for this picking
        await this.openReceptionDetail(po.picking_id);
    }
    
    // ==================== PO EDIT WORKFLOW ====================
    
    async editPO(po) {
        // Navigate to full page PO edit (editable mode)
        this.state.poEditReadOnly = false;
        this.state.poEditLoading = true;
        this.state.currentState = 'po_edit';
        this.state.currentPO = po;
        this.state.poEditProductSearch = '';
        this.state.poEditProductResults = [];

        try {
            // Load PO details and available taxes in parallel
            const [poResult, taxResult] = await Promise.all([
                this.rpc("/cbm/purchase/get_po_details", { po_id: po.id }),
                this.rpc("/cbm/purchase/get_purchase_taxes", {}),
            ]);

            if (poResult.success) {
                this.state.currentPO = poResult.po;
                this.state.poLines = poResult.lines;
            } else {
                this.showToast(poResult.error || _t("Erreur chargement BC"), 'danger');
                this.closePOEdit();
            }

            if (taxResult.success) {
                this.state.availableTaxes = taxResult.taxes;
            }
        } catch (error) {
            this.showToast(_t("Erreur chargement BC"), 'danger');
            this.closePOEdit();
        }

        this.state.poEditLoading = false;
    }

    async viewPO(po) {
        // Navigate to full page PO view (read-only mode for non-draft POs)
        this.state.poEditReadOnly = true;
        this.state.poEditLoading = true;
        this.state.currentState = 'po_edit';
        this.state.currentPO = po;
        this.state.poEditProductSearch = '';
        this.state.poEditProductResults = [];

        try {
            const poResult = await this.rpc("/cbm/purchase/get_po_details", { po_id: po.id });

            if (poResult.success) {
                this.state.currentPO = poResult.po;
                this.state.poLines = poResult.lines;
            } else {
                this.showToast(poResult.error || _t("Erreur chargement BC"), 'danger');
                this.closePOEdit();
            }
        } catch (error) {
            this.showToast(_t("Erreur chargement BC"), 'danger');
            this.closePOEdit();
        }

        this.state.poEditLoading = false;
    }

    async validateDraftPO(po) {
        const confirmed = await this.showConfirm(
            'Valider le bon de commande',
            `Envoyer le bon de commande ${po.name} pour approbation?`,
            'info',
            'Valider'
        );

        if (!confirmed) return;

        try {
            const result = await this.rpc("/cbm/purchase/confirm_po", { po_id: po.id });

            if (result.success) {
                this.showToast(`BC ${po.name} validé avec succès`, 'success');
                await this.loadPOList();
            } else {
                this.showToast(result.error || _t("Erreur validation"), 'danger');
            }
        } catch (error) {
            console.error("Validate PO failed:", error);
            this.showToast(_t("Erreur validation BC"), 'danger');
        }
    }

    async deleteDraftPO(po) {
        const confirmed = await this.showConfirm(
            'Supprimer le bon de commande',
            `Supprimer définitivement le bon de commande ${po.name}? Cette action est irréversible.`,
            'danger',
            'Supprimer'
        );

        if (!confirmed) return;

        try {
            const result = await this.rpc("/cbm/purchase/delete_po", { po_id: po.id });

            if (result.success) {
                this.showToast(`BC ${po.name} supprimé`, 'success');
                await this.loadPOList();
            } else {
                this.showToast(result.error || _t("Erreur suppression"), 'danger');
            }
        } catch (error) {
            console.error("Delete PO failed:", error);
            this.showToast(_t("Erreur suppression BC"), 'danger');
        }
    }

    closePOEdit() {
        // Return to PO list
        this.state.currentPO = null;
        this.state.poLines = [];
        this.state.poEditReadOnly = false;
        this.state.poEditProductSearch = '';
        this.state.poEditProductResults = [];
        this.goToPOList();
    }
    
    async updatePOLineField(lineId, field, event) {
        const value = event.target.value;
        
        try {
            const result = await this.rpc("/cbm/purchase/update_po_line", {
                line_id: lineId,
                field: field,
                value: value
            });
            
            if (result.success) {
                // Update local state
                const lineIndex = this.state.poLines.findIndex(l => l.id === lineId);
                if (lineIndex !== -1) {
                    this.state.poLines[lineIndex].qty = result.line.qty;
                    this.state.poLines[lineIndex].price = result.line.price;
                    this.state.poLines[lineIndex].subtotal = result.line.subtotal;
                }
                if (this.state.currentPO) {
                    this.state.currentPO.amount_total = result.po_total;
                }
                // Also update in main PO list
                const poIndex = this.state.poList.findIndex(p => p.id === this.state.currentPO.id);
                if (poIndex !== -1) {
                    this.state.poList[poIndex].amount_total = result.po_total;
                }
            } else {
                this.showToast(result.error || _t("Erreur mise à jour"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur mise à jour"), 'danger');
        }
    }

    async updatePOLineTax(lineId, event) {
        // Get selected tax ID from single select
        const value = event.target.value;
        const taxIds = value ? [parseInt(value)] : [];

        try {
            const result = await this.rpc("/cbm/purchase/update_po_line", {
                line_id: lineId,
                field: 'taxes_id',
                value: taxIds
            });

            if (result.success) {
                const lineIndex = this.state.poLines.findIndex(l => l.id === lineId);
                if (lineIndex !== -1) {
                    this.state.poLines[lineIndex].taxes = result.line.taxes;
                    this.state.poLines[lineIndex].tax_ids = result.line.tax_ids;
                    this.state.poLines[lineIndex].subtotal = result.line.subtotal;
                }
                if (this.state.currentPO) {
                    this.state.currentPO.amount_total = result.po_total;
                }
            } else {
                this.showToast(result.error || _t("Erreur mise à jour TVA"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur mise à jour TVA"), 'danger');
        }
    }

    async searchProductForPO(event) {
        const query = event.target.value;
        this.state.poEditProductSearch = query;

        if (query.length < 2) {
            this.state.poEditProductResults = [];
            return;
        }

        try {
            // Use CBM Portal endpoint with purchase_mode
            const result = await this.rpc("/cbm/search_products", {
                query,
                purchase_mode: true,
                limit: 10
            });
            this.state.poEditProductResults = result || [];
        } catch (error) {
            this.state.poEditProductResults = [];
        }
    }
    
    onPOEditProductSearchBlur() {
        setTimeout(() => {
            this.state.poEditProductResults = [];
        }, 200);
    }
    
    async addProductToPO(product) {
        if (!this.state.currentPO) return;
        
        try {
            const result = await this.rpc("/cbm/purchase/add_po_line", {
                po_id: this.state.currentPO.id,
                product_id: product.id,
                qty: 1,
                price: product.standard_price || 0
            });
            
            if (result.success) {
                this.state.poLines.push(result.line);
                this.state.currentPO.amount_total = result.po_total;
                // Update main list
                const poIndex = this.state.poList.findIndex(p => p.id === this.state.currentPO.id);
                if (poIndex !== -1) {
                    this.state.poList[poIndex].amount_total = result.po_total;
                    this.state.poList[poIndex].line_count = this.state.poLines.length;
                }
                this.state.poEditProductSearch = '';
                this.state.poEditProductResults = [];
                this.showToast(_t("Produit ajouté"), 'success');
            } else {
                this.showToast(result.error || _t("Erreur ajout produit"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur ajout produit"), 'danger');
        }
    }

    async createProductAndAddToPO(name) {
        if (!name || name.trim().length < 2) {
            this.showToast(_t("Nom du produit trop court"), 'warning');
            return;
        }
        
        if (!this.state.currentPO) return;
        
        try {
            // First create the product
            const createResult = await this.rpc("/cbm/purchase/create_product", { name: name.trim() });

            if (!createResult.success) {
                this.showToast(createResult.error || _t("Erreur création produit"), 'danger');
                return;
            }

            // Then add it to the PO
            const addResult = await this.rpc("/cbm/purchase/add_po_line", {
                po_id: this.state.currentPO.id,
                product_id: createResult.product_id,
                qty: 1,
                price: 0
            });

            if (addResult.success) {
                this.state.poLines.push(addResult.line);
                this.state.currentPO.amount_total = addResult.po_total;
                // Update main list
                const poIndex = this.state.poList.findIndex(p => p.id === this.state.currentPO.id);
                if (poIndex !== -1) {
                    this.state.poList[poIndex].amount_total = addResult.po_total;
                    this.state.poList[poIndex].line_count = this.state.poLines.length;
                }
                this.state.poEditProductSearch = '';
                this.state.poEditProductResults = [];
                this.showToast(_t("Produit créé et ajouté: ") + createResult.product_name, 'success');
            } else {
                this.showToast(addResult.error || _t("Erreur ajout produit"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur création produit"), 'danger');
        }
    }

    async removePOLine(lineId) {
        try {
            const result = await this.rpc("/cbm/purchase/remove_po_line", { line_id: lineId });

            if (result.success) {
                this.state.poLines = this.state.poLines.filter(l => l.id !== lineId);
                this.state.currentPO.amount_total = result.po_total;
                // Update main list
                const poIndex = this.state.poList.findIndex(p => p.id === this.state.currentPO.id);
                if (poIndex !== -1) {
                    this.state.poList[poIndex].amount_total = result.po_total;
                    this.state.poList[poIndex].line_count = this.state.poLines.length;
                }
            } else {
                this.showToast(result.error || _t("Erreur suppression"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur suppression"), 'danger');
        }
    }
    
    async updatePOVendor(event) {
        const vendorId = parseInt(event.target.value);
        if (!vendorId || !this.state.currentPO) return;
        
        try {
            const result = await this.rpc("/cbm/purchase/update_po_vendor", {
                po_id: this.state.currentPO.id,
                vendor_id: vendorId
            });
            
            if (result.success) {
                this.state.currentPO.vendor_id = result.vendor_id;
                this.state.currentPO.vendor_name = result.vendor_name;
                // Update main list
                const poIndex = this.state.poList.findIndex(p => p.id === this.state.currentPO.id);
                if (poIndex !== -1) {
                    this.state.poList[poIndex].vendor_name = result.vendor_name;
                }
            } else {
                this.showToast(result.error || _t("Erreur changement fournisseur"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur changement fournisseur"), 'danger');
        }
    }

    // ==================== RECEPTION WORKFLOW (Phase 3) ====================

    /**
     * Navigate to PO list filtered to show only receivable POs
     * Now uses the purchase dashboard with reception filter instead of separate page
     */
    async goToReceptions() {
        await this.goToPOList();
        // Apply reception filter after loading
        this.updatePOFilter('state', 'reception');
    }
    
    async openReceptionDetail(pickingId) {
        this.state.receptionsLoading = true;

        try {
            const result = await this.rpc("/cbm/purchase/get_reception_details", { picking_id: pickingId });

            if (result.success) {
                this.state.currentReception = result.picking;
                this.state.receptionLines = result.lines.map(line => {
                    // Convert ISO date (YYYY-MM-DD) to MM/YY for display
                    let expiryDisplay = '';
                    let expiryISO = '';
                    if (line.expiration_date) {
                        // Parse ISO date: "2025-07-01" -> "07/25"
                        const match = line.expiration_date.match(/^(\d{4})-(\d{2})-/);
                        if (match) {
                            const year = match[1].slice(-2);  // Last 2 digits of year
                            const month = match[2];
                            expiryDisplay = `${month}/${year}`;
                            expiryISO = line.expiration_date.split('T')[0];  // Strip time if present
                        }
                    }

                    return {
                        ...line,
                        // Initialize editable fields
                        qty_done_input: line.qty_done || line.expected_qty,
                        lot_name_input: line.lot_name || '',
                        expiration_date_input: expiryDisplay,  // MM/YY format for display
                        expiration_date_iso: expiryISO,         // YYYY-MM-DD for backend
                        price_input: line.price_unit || 0,
                    };
                });
                this.state.currentState = 'receptions';
                this.state.receptionMode = 'detail';
            } else {
                this.showToast(result.error || _t("Erreur"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur chargement détails réception"), 'danger');
        }

        this.state.receptionsLoading = false;
    }
    
    updateReceptionLineQty(line, event) {
        const qty = parseFloat(event.target.value);
        if (!isNaN(qty) && qty >= 0) {
            line.qty_done_input = qty;
        }
    }
    
    updateReceptionLineLot(line, event) {
        line.lot_name_input = event.target.value;
    }

    updateReceptionLinePrice(line, event) {
        const price = parseFloat(event.target.value);
        if (!isNaN(price) && price >= 0) {
            line.price_input = price;
        }
    }

    /**
     * Format expiry date input as user types (MM/YY format)
     * Auto-adds "/" after 2 digits
     */
    formatExpiryDateInput(line, event) {
        let value = event.target.value.replace(/[^\d]/g, '');  // Remove non-digits
        if (value.length >= 2) {
            value = value.substring(0, 2) + '/' + value.substring(2, 4);
        }
        event.target.value = value;
        line.expiration_date_input = value;
    }

    /**
     * Convert MM/YY to full date (YYYY-MM-DD) for backend
     * 07/25 -> 2025-07-01
     */
    updateReceptionLineExpiry(line, event) {
        const value = event.target.value;
        line.expiration_date_input = value;

        // Convert MM/YY to ISO date for backend
        if (value && value.includes('/')) {
            const [month, year] = value.split('/');
            if (month && year && month.length === 2 && year.length === 2) {
                const fullYear = parseInt(year) < 50 ? `20${year}` : `19${year}`;
                line.expiration_date_iso = `${fullYear}-${month}-01`;
            }
        }
    }
    
    async validateReception() {
        if (!this.state.currentReception) {
            return;
        }
        
        // Prepare lines data
        // Use expiration_date_iso (converted from MM/YY) if available
        const lines = this.state.receptionLines.map(line => ({
            move_line_id: line.id,
            qty_done: line.qty_done_input || 0,
            lot_name: line.lot_name_input || '',
            expiration_date: line.expiration_date_iso || line.expiration_date_input || '',
            price_unit: line.price_input || 0,
        }));
        
        // Check that at least one line has qty
        const hasQty = lines.some(l => l.qty_done > 0);
        if (!hasQty) {
            this.showToast(_t("Entrez au moins une quantité reçue"), 'warning');
            return;
        }

        this.state.receptionsLoading = true;

        try {
            const result = await this.rpc("/cbm/purchase/validate_reception", {
                picking_id: this.state.currentReception.id,
                lines
            });

            if (result.success) {
                // Show success overlay
                this.state.receptionsLoading = false;
                this.state.receptionSuccess = true;
                this.state.receptionSuccessMessage = result.bill_name
                    ? `Réception validée - Facture: ${result.bill_name}`
                    : 'Réception validée avec succès';

                // Auto-navigate back to PO dashboard after delay
                setTimeout(async () => {
                    this.state.receptionSuccess = false;
                    await this.goToPOList();
                }, 2500);
            } else {
                this.showToast(result.error || _t("Erreur validation"), 'danger');
                this.state.receptionsLoading = false;
            }
        } catch (error) {
            this.showToast(_t("Erreur validation réception"), 'danger');
            this.state.receptionsLoading = false;
        }
    }
    

    cancelReceptionDetail() {
        // Go back to PO dashboard instead of empty reception list
        this.goToPOList();
    }

    async toggleCompletedReceptions() {
        this.state.showCompletedReceptions = !this.state.showCompletedReceptions;
        // Reload reception list with new filter
        await this.loadPendingReceptions();
    }

    async loadPendingReceptions() {
        this.state.receptionsLoading = true;
        try {
            const result = await this.rpc("/cbm/purchase/get_pending_receptions", {
                limit: 50,
                include_done: this.state.showCompletedReceptions
            });
            this.state.pendingReceptions = result.pickings || [];
        } catch (error) {
            console.error("Failed to load receptions:", error);
            this.showToast(_t("Erreur lors du chargement"), 'danger');
        }
        this.state.receptionsLoading = false;
    }

    async openCorrectionFromDashboard(po) {
        // Open correction form for a PO from the purchase dashboard
        // Uses the done_picking_id from the PO data
        if (!po.done_picking_id) {
            this.showToast(_t("Aucune réception validée"), 'warning');
            return;
        }
        await this.openCorrectionForm({ id: po.done_picking_id });
    }

    async openCorrectionForm(picking) {
        // Load original reception data for correction
        this.state.receptionsLoading = true;

        try {
            const result = await this.rpc("/cbm/purchase/get_reception_details", {
                picking_id: picking.id
            });

            if (result.success) {
                this.state.currentReception = {
                    ...result.picking,
                    is_correction: true,
                    original_picking_id: picking.id,
                };

                // Pre-fill lines with original data
                this.state.receptionLines = result.lines.map(line => {
                    // Convert ISO date (YYYY-MM-DD) to MM/YY for display
                    let expiryDisplay = '';
                    let expiryISO = '';
                    if (line.expiration_date) {
                        const match = line.expiration_date.match(/^(\d{4})-(\d{2})-/);
                        if (match) {
                            const year = match[1].slice(-2);
                            const month = match[2];
                            expiryDisplay = `${month}/${year}`;
                            expiryISO = line.expiration_date.split('T')[0];
                        }
                    }

                    return {
                        ...line,
                        qty_done_input: line.qty_done || line.expected_qty,
                        lot_name_input: line.lot_name || '',
                        expiration_date_input: expiryDisplay,
                        expiration_date_iso: expiryISO,
                        price_input: line.price_unit || 0,
                        original_qty: line.qty_done || line.expected_qty,
                    };
                });

                this.state.currentState = 'receptions';
                this.state.receptionMode = 'detail';
            } else {
                this.showToast(result.error || _t("Erreur"), 'danger');
            }
        } catch (error) {
            console.error("Failed to load correction form:", error);
            this.showToast(_t("Erreur chargement correction"), 'danger');
        }

        this.state.receptionsLoading = false;
    }

    async validateCorrection() {
        if (!this.state.currentReception || !this.state.currentReception.is_correction) {
            return;
        }

        this.state.receptionsLoading = true;

        const corrections = this.state.receptionLines.map(line => ({
            move_line_id: line.id,
            product_id: line.product_id,
            original_qty: line.original_qty,
            new_qty: line.qty_done_input || 0,
            lot_name: line.lot_name_input || '',
            expiration_date: line.expiration_date_iso || '',
            price_unit: line.price_input || 0,
        }));

        try {
            const result = await this.rpc("/cbm/purchase/correct_reception", {
                picking_id: this.state.currentReception.original_picking_id,
                corrections: corrections,
            });

            if (result.success) {
                this.showToast(result.message, 'success');

                // Show operations performed
                if (result.operations && result.operations.length > 0) {
                    const ops = result.operations.join(', ');
                    this.showToast(`Opérations: ${ops}`, 'info');
                }

                // Return to reception list
                this.goToPOList();
            } else {
                this.showToast(result.error, 'danger');
            }
        } catch (error) {
            console.error("Correction failed:", error);
            this.showToast(_t("Erreur correction"), 'danger');
        }

        this.state.receptionsLoading = false;
    }

    async autoGenerateLots() {
        // Call backend which uses product_barcode module's lot generation
        if (!this.state.currentReception) {
            return;
        }
        
        this.state.receptionsLoading = true;
        
        try {
            const result = await this.rpc("/cbm/purchase/generate_lots", {
                picking_id: this.state.currentReception.id
            });
            
            if (result.success) {
                // Update lines with new lot data
                this.state.receptionLines = result.lines.map(line => {
                    // Convert ISO date to MM/YY for display
                    let expiryDisplay = '';
                    let expiryISO = '';
                    if (line.expiration_date) {
                        const match = line.expiration_date.match(/^(\d{4})-(\d{2})-/);
                        if (match) {
                            const year = match[1].slice(-2);
                            const month = match[2];
                            expiryDisplay = `${month}/${year}`;
                            expiryISO = line.expiration_date.split('T')[0];
                        }
                    }

                    return {
                        ...line,
                        qty_done_input: line.qty_done || line.expected_qty,
                        lot_name_input: line.lot_name || '',
                        expiration_date_input: expiryDisplay,
                        expiration_date_iso: expiryISO,
                        price_input: line.price_unit || 0,
                    };
                });
                this.showToast(result.message || _t("Lots générés"), 'success');
            } else {
                this.showToast(result.error || _t("Erreur génération lots"), 'danger');
            }
        } catch (error) {
            this.showToast(_t("Erreur génération lots"), 'danger');
        }

        this.state.receptionsLoading = false;
    }


    goToFinancialDashboard() {
        // Dashboard logic is now in AccountabilityDashboard component
        this.state.currentState = 'financial';
    }

    async loadHistory(loadMore = false) {
        try {
            if (loadMore) {
                this.state.historyLoading = true;
            } else {
                this.state.loading = true;
                this.state.historyOffset = 0;
                this.state.historyItems = [];
            }

            const result = await this.rpc("/cbm/get_history", {
                limit: this.state.historyLimit,
                offset: this.state.historyOffset
            });

            if (loadMore) {
                this.state.historyItems = [...this.state.historyItems, ...result];
            } else {
                this.state.historyItems = result;
            }

            this.state.historyHasMore = result.length === this.state.historyLimit;
            this.state.historyOffset += result.length;

            this.state.loading = false;
            this.state.historyLoading = false;
        } catch (error) {
            this.state.error = _t("Failed to load history");
            this.state.loading = false;
            this.state.historyLoading = false;
        }
    }

    async loadMoreHistory() {
        if (this.state.historyLoading || !this.state.historyHasMore) {
            return;
        }
        await this.loadHistory(true);
    }
    
    // ==================== UTILITIES ====================

    /**
     * Convert icon name to CSS class format.
     * Handles multiple formats:
     * - "fa-cube" -> "cube" (FontAwesome prefix)
     * - "calendar-days" -> "calendar_days" (Heroicons hyphen-case)
     * - "wrench-screwdriver" -> "wrench_screwdriver"
     */
    getIconClass(iconName) {
        if (!iconName) return 'cube';
        // Strip fa- prefix if present (legacy FontAwesome format)
        let name = iconName.replace(/^fa-/, '');
        // Convert hyphens to underscores
        return name.replace(/-/g, '_');
    }

    // ==================== NAVIGATION ====================

    goHome() {
        this.state.currentState = "home";
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();
        this.resetMaintenanceState();
        this.loadCustomTiles();  // Refresh tile pending counts
        this.loadPendingApprovals();  // Refresh approvals sidebar
    }
    
    // ==================== TABLE SORTING ====================
    
    /**
     * Sort a list by column. Toggles direction if same column clicked.
     * @param {string} listName - State property name (e.g., 'poList', 'poLines', 'historyItems')
     * @param {string} column - Column/field name to sort by
     */
    sortList(listName, column) {
        const currentSort = this.state.sortState;
        let newDirection = 'asc';
        
        // Toggle direction if same column
        if (currentSort.listName === listName && currentSort.column === column) {
            newDirection = currentSort.direction === 'asc' ? 'desc' : 'asc';
        }
        
        // Update sort state
        this.state.sortState = {
            listName,
            column,
            direction: newDirection
        };
        
        // Get the list to sort
        const list = this.state[listName];
        if (!Array.isArray(list)) return;
        
        // Sort the list
        const sorted = [...list].sort((a, b) => {
            let valA = a[column];
            let valB = b[column];
            
            // Handle null/undefined
            if (valA == null) valA = '';
            if (valB == null) valB = '';
            
            // Handle dates (ISO string format)
            if (typeof valA === 'string' && valA.match(/^\d{4}-\d{2}-\d{2}/)) {
                valA = new Date(valA);
                valB = new Date(valB);
            }
            
            // Handle numbers
            if (typeof valA === 'number' && typeof valB === 'number') {
                return newDirection === 'asc' ? valA - valB : valB - valA;
            }
            
            // Handle strings
            const strA = String(valA).toLowerCase();
            const strB = String(valB).toLowerCase();
            if (newDirection === 'asc') {
                return strA.localeCompare(strB);
            } else {
                return strB.localeCompare(strA);
            }
        });
        
        this.state[listName] = sorted;
    }
    
    /**
     * Get sort class for a column header
     * @param {string} listName - State property name
     * @param {string} column - Column name
     * @returns {string} CSS class: 'sortable', 'sortable sort-asc', or 'sortable sort-desc'
     */
    getSortClass(listName, column) {
        const sort = this.state.sortState;
        if (sort.listName === listName && sort.column === column) {
            return `sortable sort-${sort.direction}`;
        }
        return 'sortable';
    }

    // ==================== PO CREATE PAGE ====================
    
    /**
     * Load available purchase taxes
     */
    async loadPurchaseTaxes() {
        try {
            const result = await this.rpc("/cbm/purchase/get_purchase_taxes", {});
            if (result.success) {
                this.state.availableTaxes = result.taxes || [];
            }
        } catch (error) {
            console.error("Error loading purchase taxes:", error);
        }
    }
    
    /**
     * Navigate to PO Create page
     * @param {Array} prefillProducts - Optional array of products to pre-fill (from Réapprovisionnement)
     */
    goToPOCreate(prefillProducts = []) {
        // Reset state
        this.state.poCreate = {
            vendor_id: null,
            vendor_name: '',
            reference: '',
            lines: [],
            total: 0,
            loading: false,
            submitting: false,
        };
        this.state.poCreateProductSearch = '';
        this.state.poCreateProductResults = [];
        
        // Pre-fill products if provided (from Réapprovisionnement)
        if (prefillProducts && prefillProducts.length > 0) {
            for (const p of prefillProducts) {
                this.addPOCreateLine({
                    id: p.product_id,
                    display_name: p.product_name,
                    default_code: p.product_code || '',
                    standard_price: p.price || 0,
                });
                // Update qty if provided
                const lastLine = this.state.poCreate.lines[this.state.poCreate.lines.length - 1];
                if (p.qty && lastLine) {
                    lastLine.qty = p.qty;
                    this.recalcPOCreateTotal();
                }
            }
        }
        
        // Load taxes if not already loaded
        if (this.state.availableTaxes.length === 0) {
            this.loadPurchaseTaxes();
        }
        
        this.state.currentState = 'po_create';
    }
    
    /**
     * Navigate to PO Create from Replenishment with selected items
     */
    goToPOCreateFromReplenishment() {
        // Collect selected items from replenishment
        const selectedItems = this.state.replenishmentItems.filter(item => 
            this.state.selectedReplenishmentIds.includes(item.id)
        );
        
        if (selectedItems.length === 0) {
            this.showToast(_t("Sélectionnez au moins un produit"), 'warning');
            return;
        }

        // Convert to prefill format
        const prefillProducts = selectedItems.map(item => ({
            product_id: item.product_id,
            product_name: item.product_name,
            product_code: item.default_code || '',
            qty: item.suggested_qty || 1,
            price: item.price || item.standard_price || 0,
        }));
        
        // Navigate to PO Create with pre-filled products
        this.goToPOCreate(prefillProducts);
    }
    
    /**
     * Set vendor for PO create
     */
    setPOCreateVendor(vendor) {
        this.state.poCreate.vendor_id = vendor.id;
        this.state.poCreate.vendor_name = vendor.name;
        this.state.poVendorSearchQuery = vendor.name;
        this.state.poVendors = [];
    }
    
    /**
     * Search vendors for PO create (wrapper for loadVendors)
     */
    searchVendors(query) {
        this.state.poVendorSearchQuery = query;
        if (query.length >= 2) {
            this.loadVendors(query);
        } else if (query.length === 0) {
            this.loadVendors();
        } else {
            this.state.poVendors = [];
        }
    }
    
    /**
     * Create vendor and set it for PO create
     */
    async createVendorAndSetPOCreate(name) {
        if (!name || name.trim().length < 2) {
            this.showToast(_t("Nom du fournisseur trop court"), 'warning');
            return;
        }

        try {
            const result = await this.rpc("/cbm/purchase/create_vendor", { name: name.trim() });
            if (result.success) {
                this.setPOCreateVendor({ id: result.vendor_id, name: result.vendor_name });
                this.showToast(_t("Fournisseur créé"), 'success');
            } else {
                this.showToast(result.error || _t("Erreur création fournisseur"), 'danger');
            }
        } catch (error) {
            console.error("Error creating vendor:", error);
            this.showToast(_t("Erreur création fournisseur"), 'danger');
        }
    }
    
    /**
     * Create product and add to PO create lines
     */
    async createProductAndAddToCreate(name) {
        if (!name || name.trim().length < 2) {
            this.showToast(_t("Nom du produit trop court"), 'warning');
            return;
        }

        try {
            const result = await this.rpc("/cbm/purchase/create_product", { name: name.trim() });
            if (result.success) {
                // Add the created product to PO create lines
                this.addPOCreateLine({
                    id: result.product_id,
                    name: result.product_name,
                    display_name: result.product_name,
                    default_code: '',
                    standard_price: 0,
                });
                this.showToast(_t("Produit créé et ajouté"), 'success');
            } else {
                this.showToast(result.error || _t("Erreur création produit"), 'danger');
            }
        } catch (error) {
            console.error("Error creating product:", error);
            this.showToast(_t("Erreur création produit"), 'danger');
        }
    }
    
    /**
     * Handle product search input for PO create (event handler)
     */
    onPOCreateProductSearch(ev) {
        const query = ev.target.value;
        this.state.poCreateProductSearch = query;
        this.searchPOCreateProducts(query);
    }
    
    /**
     * Handle product search blur for PO create (event handler)
     */
    onPOCreateProductBlur() {
        setTimeout(() => {
            this.state.poCreateProductResults = [];
            this.state.poCreateSelectedIndex = -1;
        }, 200);
    }
    
    /**
     * Handle keyboard navigation in PO create product search
     */
    onPOCreateProductKeydown(ev) {
        const results = this.state.poCreateProductResults;
        if (!results.length) return;
        
        switch (ev.key) {
            case 'ArrowDown':
                ev.preventDefault();
                this.state.poCreateSelectedIndex = Math.min(
                    this.state.poCreateSelectedIndex + 1, 
                    results.length - 1
                );
                break;
            case 'ArrowUp':
                ev.preventDefault();
                this.state.poCreateSelectedIndex = Math.max(
                    this.state.poCreateSelectedIndex - 1, 
                    0
                );
                break;
            case 'Enter':
                ev.preventDefault();
                if (this.state.poCreateSelectedIndex >= 0 && this.state.poCreateSelectedIndex < results.length) {
                    this.addPOCreateLine(results[this.state.poCreateSelectedIndex]);
                }
                break;
            case 'Escape':
                this.state.poCreateProductResults = [];
                this.state.poCreateSelectedIndex = -1;
                break;
        }
    }
    
    /**
     * Clear vendor selection in PO create
     */
    clearPOCreateVendor() {
        this.state.poCreate.vendor_id = null;
        this.state.poCreate.vendor_name = '';
        this.state.poVendorSearchQuery = '';
        this.state.poVendors = [];
    }
    
    /**
     * Sort PO create lines
     */
    sortPOCreateLines(field) {
        const sortKey = `poCreateLines_${field}`;
        const currentDir = this.state.sortDirections[sortKey] || 'asc';
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';
        this.state.sortDirections[sortKey] = newDir;

        this.state.poCreate.lines.sort((a, b) => {
            let aVal = a[field];
            let bVal = b[field];

            // Handle strings
            if (typeof aVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }

            if (aVal < bVal) return newDir === 'asc' ? -1 : 1;
            if (aVal > bVal) return newDir === 'asc' ? 1 : -1;
            return 0;
        });
    }

    sortReceptionLines(field) {
        const sortKey = `receptionLines_${field}`;
        const currentDir = this.state.sortDirections[sortKey] || 'asc';
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';
        this.state.sortDirections[sortKey] = newDir;

        // Calculate subtotal for sorting if needed
        const getVal = (line, f) => {
            if (f === 'subtotal') {
                return (line.qty_done_input || 0) * (line.price_input || 0);
            }
            return line[f];
        };

        this.state.receptionLines = [...this.state.receptionLines].sort((a, b) => {
            let aVal = getVal(a, field);
            let bVal = getVal(b, field);

            if (typeof aVal === 'string') {
                aVal = aVal.toLowerCase();
                bVal = bVal.toLowerCase();
            }

            if (aVal < bVal) return newDir === 'asc' ? -1 : 1;
            if (aVal > bVal) return newDir === 'asc' ? 1 : -1;
            return 0;
        });
    }
    
    /**
     * Search products for PO create
     */
    async searchPOCreateProducts(query) {
        if (!query || query.length < 2) {
            this.state.poCreateProductResults = [];
            return;
        }
        
        this.state.poCreateProductLoading = true;
        try {
            const result = await this.rpc("/cbm/search_products", {
                query: query,
                purchase_mode: true,
                limit: 15,
            });
            this.state.poCreateProductResults = result || [];
        } catch (error) {
            console.error("Error searching products:", error);
            this.state.poCreateProductResults = [];
        }
        this.state.poCreateProductLoading = false;
    }
    
    /**
     * Add product to PO create lines
     */
    async addPOCreateLine(product) {
        // Check if already exists
        const existingIndex = this.state.poCreate.lines.findIndex(l => l.product_id === product.id);
        if (existingIndex >= 0) {
            // Update existing line - create new array for reactivity
            const updatedLines = [...this.state.poCreate.lines];
            updatedLines[existingIndex] = {
                ...updatedLines[existingIndex],
                qty: updatedLines[existingIndex].qty + 1,
                subtotal: (updatedLines[existingIndex].qty + 1) * updatedLines[existingIndex].price,
            };
            this.state.poCreate.lines = updatedLines;
        } else {
            // Fetch available UoMs for this product
            let available_uoms = [];
            try {
                const uomResult = await this.rpc("/cbm/purchase/get_product_purchase_uoms", {
                    product_id: product.id
                });
                if (uomResult.success) {
                    available_uoms = uomResult.uoms;
                }
            } catch (e) {
                console.error("Failed to load UoMs:", e);
                // Continue with default UoM if fetch fails
            }

            // Add new line - create new array for reactivity
            this.state.poCreate.lines = [
                ...this.state.poCreate.lines,
                {
                    product_id: product.id,
                    product_name: product.display_name || product.name,
                    product_code: product.default_code || '',
                    uom_id: product.uom_po_id || null,
                    uom_name: product.uom_po_name || product.uom_name || 'Unité',
                    available_uoms: available_uoms,
                    qty: 1,
                    price: product.standard_price || 0,
                    tax_ids: [],
                    subtotal: product.standard_price || 0,
                }
            ];
        }

        this.recalcPOCreateTotal();
        this.state.poCreateProductSearch = '';
        this.state.poCreateProductResults = [];
    }
    
    /**
     * Handle qty change event in PO create
     */
    onPOCreateQtyChange(ev) {
        const index = parseInt(ev.target.dataset.index);
        this.updatePOCreateLine(index, 'qty', ev.target.value);
    }
    
    /**
     * Handle price change event in PO create
     */
    onPOCreatePriceChange(ev) {
        const index = parseInt(ev.target.dataset.index);
        this.updatePOCreateLine(index, 'price', ev.target.value);
    }

    onPOCreateUomChange(ev) {
        const index = parseInt(ev.target.dataset.index);
        const newUomId = parseInt(ev.target.value);
        const line = this.state.poCreate.lines[index];

        // Find UoM details from available_uoms
        const uom = line.available_uoms?.find(u => u.id === newUomId);
        if (uom) {
            const updatedLines = [...this.state.poCreate.lines];
            updatedLines[index] = {
                ...updatedLines[index],
                uom_id: newUomId,
                uom_name: uom.name,
            };
            this.state.poCreate.lines = updatedLines;
        }
    }

    /**
     * Handle tax change event in PO create
     */
    onPOCreateTaxChange(ev) {
        const index = parseInt(ev.target.dataset.index);
        const taxId = ev.target.value ? [parseInt(ev.target.value)] : [];
        this.updatePOCreateLine(index, 'tax_ids', taxId);
    }
    
    /**
     * Update PO create line field
     */
    updatePOCreateLine(index, field, value) {
        const line = this.state.poCreate.lines[index];
        if (!line) return;
        
        // Create updated line with new values
        let updatedLine = { ...line };
        
        if (field === 'qty') {
            updatedLine.qty = Math.max(0, parseFloat(value) || 0);
        } else if (field === 'price') {
            updatedLine.price = Math.max(0, parseFloat(value) || 0);
        } else if (field === 'tax_ids') {
            updatedLine.tax_ids = value;
        }
        
        updatedLine.subtotal = updatedLine.qty * updatedLine.price;
        
        // Create new array for reactivity
        const updatedLines = [...this.state.poCreate.lines];
        updatedLines[index] = updatedLine;
        this.state.poCreate.lines = updatedLines;
        
        this.recalcPOCreateTotal();
    }
    
    /**
     * Remove line from PO create
     */
    removePOCreateLine(index) {
        // Create new array for reactivity (don't mutate with splice)
        this.state.poCreate.lines = this.state.poCreate.lines.filter((_, i) => i !== index);
        this.recalcPOCreateTotal();
    }
    
    /**
     * Recalculate PO create total
     */
    recalcPOCreateTotal() {
        this.state.poCreate.total = this.state.poCreate.lines.reduce(
            (sum, line) => sum + (line.subtotal || 0), 0
        );
    }
    
    /**
     * Save PO as draft
     */
    async savePODraft() {
        const pc = this.state.poCreate;

        if (!pc.vendor_id) {
            this.showToast("Veuillez sélectionner un fournisseur", 'warning');
            return;
        }
        if (pc.lines.length === 0) {
            this.showToast("Ajoutez au moins un produit", 'warning');
            return;
        }

        pc.submitting = true;
        try {
            const result = await this.rpc("/cbm/purchase/create_po_full", {
                vendor_id: pc.vendor_id,
                reference: (pc.reference || '').trim(),
                lines: pc.lines.map(l => ({
                    product_id: l.product_id,
                    qty: l.qty,
                    price: l.price,
                    tax_ids: l.tax_ids || [],
                    uom_id: l.uom_id || null,
                })),
            });

            if (result.success) {
                this.showToast(`BC ${result.po_name} créé en brouillon`, 'success');
                // Go to PO list
                this.goToPOList();
            } else {
                this.showToast(result.error || "Erreur de création", 'danger');
            }
        } catch (error) {
            console.error("Error creating PO:", error);
            this.showToast("Erreur de création du BC", 'danger');
        }
        pc.submitting = false;
    }

    /**
     * Submit PO for approval (create + confirm in one step)
     */
    async submitPOForApproval() {
        const pc = this.state.poCreate;

        if (!pc.vendor_id) {
            this.showToast("Veuillez sélectionner un fournisseur", 'warning');
            return;
        }
        if (pc.lines.length === 0) {
            this.showToast("Ajoutez au moins un produit", 'warning');
            return;
        }

        pc.submitting = true;

        try {
            // Atomic operation - create and submit in one transaction
            const result = await this.rpc("/cbm/purchase/create_and_submit_po", {
                vendor_id: pc.vendor_id,
                reference: (pc.reference || '').trim(),
                lines: pc.lines.map(l => ({
                    product_id: l.product_id,
                    qty: l.qty,
                    price: l.price,
                    tax_ids: l.tax_ids || [],
                    uom_id: l.uom_id || null,
                })),
            });

            if (result.success) {
                if (result.state === 'to approve') {
                    // Approval required - show info message (orange)
                    this.showToast(`BC ${result.po_name} envoyé pour approbation. Merci!`, 'info');
                } else {
                    // Directly confirmed
                    this.showToast(`BC ${result.po_name} confirmé`, 'success');
                }
                // Go to PO list
                this.goToPOList();
            } else {
                // Complete failure
                this.showToast(result.error || "Erreur de création du BC", 'danger');
            }
        } catch (error) {
            console.error("Error submitting PO:", error);
            this.showToast("Erreur de création du BC", 'danger');
        }
        pc.submitting = false;
    }

    
    goToRequest() {
        const requestOp = this.state.operationTypes.find(
            op => op.portal_category === "request"
        );
        if (requestOp) {
            this.state.selectedOpType = requestOp;
        }
        
        // Check for pending Brain suggestions
        const brainSuggestions = window.__brainPendingSuggestions || [];
        if (brainSuggestions.length > 0) {
            // Convert and inject brain suggestions into products
            this.state.selectedProducts = brainSuggestions.map(s => ({
                id: s.product_id,
                name: s.product_name,
                qty: s.suggested_qty || 1,
                uom_name: '',
                qty_available: s.current_stock || 0,
                lot_id: false,
                lot_name: false,
                hoarding_status: 'ok',
                ward_qty: 0,
                hoarding_message: '',
                _brain_insight_id: s.insight_id,
            }));
            window.__brainPendingSuggestions = [];  // Clear after use
        }
        
        this.state.currentState = "request";
    }
    
    goToConsumptionMenu() {
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();
        this.state.selectedOpType = null;
        this.state.currentState = "consumption_menu";
    }
    
    showBlockedNotification() {
        const pending = this.state.pendingApprovals;
        const myRequests = pending.my_requests_count || 0;
        this.showToast(
            `Accès temporairement bloqué. Vous avez ${myRequests} demande(s) en attente de validation. Veuillez contacter le responsable (Pharmacie/Magasin) pour valider vos transferts.`,
            'danger'
        );
    }
    
    goToHistory() {
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();
        this.state.historyActiveTab = 'transfers';
        this.loadHistory();
        this.loadTimeOffHistory();
        this.state.currentState = "history";
    }

    // ==================== DOCUMENTS ====================

    async goToDocuments() {
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();
        this.state.currentState = "documents";
    }

    onComplianceLockChange(locked) {
        this.state.isComplianceLocked = locked;
    }

    goBack() {
        if (this.state.currentState === "request") {
            this.goHome();
        } else if (this.state.currentState === "consumption_products") {
            if (this.state.selectedPatient) {
                this.state.currentState = "consumption_patient";
            } else if (this.state.selectedDepartment) {
                this.state.currentState = "consumption_department";
            } else {
                this.goToConsumptionMenu();
            }
        } else {
            this.goHome();
        }
    }

    modifyPatient() {
        // Clear patient selection and products, return to patient selection screen
        const wasPrescription = this.state.currentState === 'prescription_products';
        this.resetPatientState();
        this.resetProductState();
        if (wasPrescription) {
            this.resetPrescriptionState();
            this.state.currentState = "prescription_patient";
        } else {
            this.state.currentState = "consumption_patient";
        }
        this.focusPatientSearch();
    }

    modifyDepartment() {
        // Clear department selection and products, return to department selection screen
        this.resetDepartmentState();
        this.resetProductState();
        this.state.currentState = "consumption_department";
    }
    
    async selectConsumptionOpType(opType) {
        // Reset all state when switching operation types
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();

        this.state.selectedOpType = opType;

        if (opType.portal_requires_patient) {
            this.state.currentState = "consumption_patient";
            this.focusPatientSearch();
        } else if (opType.portal_requires_department) {
            // Load department list
            await this.loadDepartmentList();
            this.state.currentState = "consumption_department";
        } else {
            this.state.currentState = "consumption_products";
            // Auto-focus barcode input for immediate scanning
            this.focusBarcodeInput();
        }
    }
    
    async confirmPatient() {
        if (!this.state.selectedPatient) {
            this.showToast(_t("Please select a patient"), 'warning');
            return;
        }

        // Get source location for stock availability check
        const locationId = this.state.selectedOpType?.default_location_src_id ||
                          this.state.userContext?.ward_location_id;

        // Load existing draft quotation lines into cart
        try {
            const response = await this.rpc("/cbm/get_patient_draft_quotation", {
                patient_id: this.state.selectedPatient.id,
                location_id: locationId || false,
            });

            // FIX Issue #2: Store linked SO ID to prevent jumping between multiple SOs
            // Response format: {sale_order_id, sale_order_name, lines} or legacy array format
            const draftLines = response.lines || response;  // Handle both new and legacy format
            if (response.sale_order_id) {
                this.state.linkedSaleOrderId = response.sale_order_id;
                this.state.linkedSaleOrderName = response.sale_order_name;
                console.log('[CBM] Linked to SO:', response.sale_order_name, '(ID:', response.sale_order_id, ')');
            }

            // Pre-populate cart with existing quotation lines
            for (const line of draftLines) {
                // Check if product already in cart (shouldn't happen, but defensive)
                const existing = this.state.selectedProducts.find(p => p.id === line.product_id);
                if (!existing) {
                    const productEntry = {
                        id: line.product_id,
                        name: line.product_name,
                        qty: line.qty,
                        originalQty: line.qty,  // Track original qty for delta calculation
                        uom_name: line.uom_name,
                        qty_available: line.qty_available,  // Stock at user's location
                        // FIX: Use lot from user's location (backend now returns location-specific lot)
                        lot_id: line.lot_id || false,
                        lot_name: line.lot_name || false,  // FIX: Was hardcoded to false, now uses backend value
                        hoarding_status: null,
                        ward_qty: 0,
                        hoarding_message: '',
                        stockStatus: 'ok',
                        order_line_id: line.order_line_id,  // Track which order line this came from
                    };

                    this.state.selectedProducts.unshift(productEntry);

                    // Update stock status based on qty vs available
                    this.updateProductStockStatus(productEntry);
                }
            }

            // Update stock alert banner if any pre-loaded products have issues
            this.updateStockAlertBanner();

        } catch (error) {
            // Non-blocking - if fetching draft fails, just continue without pre-populating
            console.warn('[CBM] Failed to load draft quotation:', error);
        }

        this.state.currentState = "consumption_products";

        // Load quick picks for patient consumption (billable flow)
        if (this.state.selectedOpType?.portal_category === 'consumption_billable') {
            await this.loadQuickPicks();
        }

        // Auto-focus barcode input for immediate scanning
        this.focusBarcodeInput();
    }

    // ==================== QUICK PICK ====================

    async loadQuickPicks() {
        /**
         * Load quick pick products for the user's ward location.
         * Only shown for patient consumption (billable) flow.
         */
        const locationId = this.state.selectedOpType?.default_location_src_id ||
                          this.state.userContext?.ward_id;

        if (!locationId) {
            this.state.quickPick.enabled = false;
            return;
        }

        try {
            const result = await this.rpc('/cbm/get_quick_picks', {
                location_id: locationId,
            });

            if (result.enabled && result.products.length > 0) {
                this.state.quickPick.enabled = true;
                this.state.quickPick.locationName = result.location_name || '';
                this.state.quickPick.products = result.products;
                this.state.quickPick.clickCounts = {};
            } else {
                this.state.quickPick.enabled = false;
            }
        } catch (error) {
            console.warn('[CBM] Failed to load quick picks:', error);
            this.state.quickPick.enabled = false;
        }
    }

    onQuickPickClick(productId) {
        /**
         * Handle quick pick button click.
         * Each click increments counter. After 500ms of no additional clicks, adds to cart.
         *
         * Example: Click 3 times rapidly → Counter shows "+3" → After 500ms silence → Adds 3 units to cart
         */
        // Increment click counter
        const currentCount = this.state.quickPick.clickCounts[productId] || 0;
        this.state.quickPick.clickCounts[productId] = currentCount + 1;

        // Clear existing timer for this product
        if (this.quickPickTimers && this.quickPickTimers[productId]) {
            clearTimeout(this.quickPickTimers[productId]);
        }

        // Initialize timer storage if needed
        if (!this.quickPickTimers) {
            this.quickPickTimers = {};
        }

        // Set new timer - after 500ms of no additional clicks, add accumulated qty to cart
        this.quickPickTimers[productId] = setTimeout(() => {
            this.addQuickPickToCart(productId);
        }, 500);
    }

    addQuickPickToCart(productId) {
        /**
         * Add quick pick product to cart (selectedProducts) with accumulated quantity.
         * The user still needs to click "Valider" to submit the consumption.
         */
        const qty = this.state.quickPick.clickCounts[productId] || 1;
        const product = this.state.quickPick.products.find(p => p.id === productId);

        if (!product) return;

        // Check if already in cart
        const existing = this.state.selectedProducts.find(p => p.id === productId);

        if (existing) {
            // Increment existing qty
            existing.qty += qty;
        } else {
            // Add new product to cart
            const newProduct = {
                id: product.id,
                name: product.name,
                qty: qty,
                uom_name: product.uom_name,
                qty_available: product.qty_available,
                lot_id: false,
                lot_name: false,
                tracking: product.tracking,
                hoarding_status: null,
                ward_qty: 0,
                hoarding_message: '',
                stockStatus: product.qty_available > 0 ? 'ok' : 'warning',
            };
            this.state.selectedProducts.unshift(newProduct);
        }

        // Reset counter and show brief confirmation
        this.state.quickPick.clickCounts[productId] = 0;

        // Update stock alert banner
        this.updateStockAlertBanner();

        // Show toast notification
        this.showToast(
            _t("Added %s x %s to cart", qty, product.short_name),
            'success'
        );
    }

    // ==================== PRODUCT SEARCH ====================
    
    async onProductSearch(event) {
        const query = event.target.value;
        this.state.productSearchQuery = query;
        
        if (query.length < 2) {
            this.state.productResults = [];
            return;
        }
        
        await this.searchProducts(query);
    }
    
    async searchProducts(query) {
        // Determine location to search products from:
        // - Consumption: use the operation type's SOURCE location (where stock comes from)
        // - Request: use the operation type's source (pharmacy) or fallback to user's pharmacy setting
        const isConsumption = this.state.selectedOpType?.portal_behavior === 'billable' ||
                              this.state.selectedOpType?.portal_behavior === 'internal' ||
                              this.state.selectedOpType?.portal_requires_patient;
        
        let locationId;
        if (isConsumption) {
            // Consumption: search stock at the OPERATION TYPE's source location
            // This handles pharmacy consumption (pharmacist), ward consumption (nurse), etc.
            locationId = this.state.selectedOpType?.default_location_src_id;
            if (!locationId) {
                // Fallback to user's ward if operation type has no source
                locationId = this.state.userContext?.ward_id;
            }
            if (!locationId) {
                this.showToast(_t("No source location configured for this operation. Contact admin."), 'danger');
                return;
            }
        } else {
            // Request: search stock at operation type's source (pharmacy)
            locationId = this.state.selectedOpType?.default_location_src_id || 
                        this.state.userContext?.pharmacy_location_id;
        }
        
        if (!locationId) {
            this.showToast(_t("No source location configured"), 'warning');
            return;
        }
        
        try {
            this.state.productLoading = true;
            const result = await this.rpc("/cbm/search_products", {
                query: query,
                location_id: locationId,
                limit: 10,
            });
            this.state.productResults = result;
            this.state.productLoading = false;
        } catch (error) {
            this.state.productLoading = false;
        }
    }
    
    async onBarcodeInput(event) {
        if (event.key === "Enter") {
            const barcode = event.target.value.trim();
            if (barcode) {
                await this.searchBarcode(barcode);
                event.target.value = "";
            }
        }
    }
    
    async searchBarcode(barcode) {
        const locationId = this.state.selectedOpType?.default_location_src_id ||
                          this.state.userContext?.pharmacy_location_id;

        try {
            const result = await this.rpc("/cbm/search_barcode", {
                barcode: barcode,
                location_id: locationId,
            });

            if (result.found) {
                if (this.state.currentState === 'prescription_products') {
                    this.addPrescriptionConsumable(result);
                } else {
                    this.addOrIncrementProduct(result);
                }
            } else {
                this.showToast(result.error || _t("Product not found"), 'warning');
            }
        } catch (error) {
            this.showToast(_t("Barcode search failed"), 'danger');
        }
    }
    
    addProduct(product) {
        this.addOrIncrementProduct(product);
        this.state.productSearchQuery = "";
        this.state.productResults = [];
        this.state.selectedResultIndex = -1;
        // Re-focus search input
        this.focusSearchInput();
    }
    
    focusSearchInput() {
        // Focus the search input after a short delay to let DOM update
        setTimeout(() => {
            const input = this.searchInputRef.el;
            if (input) {
                input.focus();
            }
        }, 50);
    }
    
    focusPatientSearch() {
        // Focus the patient search input after a short delay to let DOM update
        setTimeout(() => {
            const input = this.patientSearchRef.el;
            if (input) {
                input.focus();
            }
        }, 100);
    }

    focusBarcodeInput() {
        // Focus the barcode input after a short delay to let DOM update
        setTimeout(() => {
            const input = this.barcodeInputRef.el;
            if (input) {
                input.focus();
            }
        }, 100);
    }
    
    onSearchKeydown(event) {
        const results = this.state.productResults;
        if (!results.length) return;
        
        switch (event.key) {
            case "ArrowDown":
                event.preventDefault();
                this.state.selectedResultIndex = Math.min(
                    this.state.selectedResultIndex + 1,
                    results.length - 1
                );
                this.scrollToSelectedItem();
                break;
            case "ArrowUp":
                event.preventDefault();
                this.state.selectedResultIndex = Math.max(
                    this.state.selectedResultIndex - 1,
                    -1
                );
                this.scrollToSelectedItem();
                break;
            case "Enter":
                event.preventDefault();
                if (this.state.selectedResultIndex >= 0) {
                    this.addProduct(results[this.state.selectedResultIndex]);
                }
                break;
            case "Escape":
                this.state.productResults = [];
                this.state.selectedResultIndex = -1;
                break;
        }
    }
    
    scrollToSelectedItem() {
        setTimeout(() => {
            const selected = document.querySelector('.cbm_search_item.selected');
            if (selected) {
                selected.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }, 10);
    }
    
    async addOrIncrementProduct(product) {
        const existing = this.state.selectedProducts.find(p => p.id === product.id);
        
        if (existing) {
            existing.qty += 1;
        } else {
            // Check hoarding status before adding (for REQUEST mode only)
            let hoarding_status = 'ok';
            let ward_qty = 0;
            let hoarding_message = '';
            
            // Only check for request behavior (when user is requesting from pharmacy)
            const isRequest = this.state.selectedOpType?.portal_behavior === 'request';
            const destLocationId = this.state.userContext?.ward_id;
            
            if (isRequest && destLocationId) {
                try {
                    const check = await this.rpc("/cbm/check_hoarding", {
                        product_id: product.id,
                        destination_location_id: destLocationId,
                    });
                    hoarding_status = check.status || 'ok';
                    ward_qty = check.trusted_qty || 0;
                    hoarding_message = check.message || '';
                } catch (e) {
                    // Fail silently - hoarding check is optional
                }
            }
            
            const productEntry = {
                id: product.id,
                name: product.name || product.display_name,
                qty: 1,
                uom_name: product.uom_name,
                qty_available: product.qty_available,
                // Lot info (from auto-FEFO selection or barcode scan)
                lot_id: product.lot_id || false,
                lot_name: product.lot_name || false,
                // Hoarding fields
                hoarding_status: hoarding_status,
                ward_qty: ward_qty,
                hoarding_message: hoarding_message,
                // Stock status (will be updated below)
                stockStatus: 'ok',
            };

            this.state.selectedProducts.unshift(productEntry);

            // Update stock status based on requested qty vs available
            this.updateProductStockStatus(productEntry);
        }

        // Update stock alert banner
        this.updateStockAlertBanner();
    }
    
    incrementProduct(product) {
        product.qty += 1;
        this.updateProductStockStatus(product);
        this.updateStockAlertBanner();
    }

    decrementProduct(product) {
        if (product.qty > 1) {
            product.qty -= 1;
            this.updateProductStockStatus(product);
            this.updateStockAlertBanner();
        } else {
            this.removeProduct(product);
        }
    }

    onQtyChange(product, event) {
        const newQty = parseInt(event.target.value, 10);
        if (newQty && newQty > 0) {
            product.qty = newQty;
        } else {
            product.qty = 1;
            event.target.value = 1;
        }
        this.updateProductStockStatus(product);
        this.updateStockAlertBanner();
    }

    updateProductStockStatus(product) {
        // SAFETY CHECK: Only run stock checks for products with qty_available field
        // This prevents errors for service products or products without stock tracking
        if (product.qty_available === undefined || product.qty_available === null) {
            product.stockStatus = 'ok';  // Skip stock checking for non-stockable products
            return;
        }

        // Re-evaluate stock status based on requested quantity vs available
        // FIX: For pre-loaded items, only check the DELTA (additional qty needed), not total
        // The original qty was already consumed, so we only need stock for the increase
        const qtyToConsume = product.originalQty
            ? Math.max(0, product.qty - product.originalQty)  // Delta for pre-loaded items
            : product.qty;  // Full qty for new items

        if (product.qty_available === 0 && qtyToConsume > 0) {
            product.stockStatus = 'critical';  // No stock at all and need some
        } else if (qtyToConsume > product.qty_available) {
            product.stockStatus = 'critical';  // Requested more than available
        } else if (product.qty_available < 1 && qtyToConsume > 0) {
            product.stockStatus = 'warning';   // Very low stock (fractional)
        } else {
            product.stockStatus = 'ok';        // Sufficient stock (or no additional needed)
        }
    }

    
    removeProduct(product) {
        const index = this.state.selectedProducts.indexOf(product);
        if (index > -1) {
            // If this was a pre-loaded product from ledger (has originalQty), track for return
            // order_line_id is no longer required - originalQty alone marks a pre-loaded item
            if (product.originalQty) {
                this.state.removedProducts.push({
                    id: product.id,
                    qty: 0,  // Reduced to 0
                    originalQty: product.originalQty,
                    order_line_id: product.order_line_id || false,
                    lot_id: product.lot_id || false,
                });
            }
            this.state.selectedProducts.splice(index, 1);
        }
        // Update stock alert banner after removal
        this.updateStockAlertBanner();
    }

    updateStockAlertBanner() {
        // Check if any selected products have stock issues
        const criticalProducts = this.state.selectedProducts.filter(p => p.stockStatus === 'critical');
        const warningProducts = this.state.selectedProducts.filter(p => p.stockStatus === 'warning');

        if (criticalProducts.length > 0) {
            // Critical: over-consumption
            const productNames = criticalProducts.map(p => p.name).slice(0, 3).join(', ');
            const moreCount = criticalProducts.length > 3 ? ` (+${criticalProducts.length - 3})` : '';
            this.showAlertBanner(
                ` ${_t('INSUFFICIENT STOCK')}: ${productNames}${moreCount}. ${_t('Reduce quantities or contact pharmacy.')}`,
                'error'
            );
        } else if (warningProducts.length > 0) {
            // Warning: low stock
            const productNames = warningProducts.map(p => p.name).slice(0, 3).join(', ');
            const moreCount = warningProducts.length > 3 ? ` (+${warningProducts.length - 3})` : '';
            this.showAlertBanner(
                ` ${_t('Limited stock for')}: ${productNames}${moreCount}. ${_t('You can continue - admin has been notified.')}`,
                'warning'
            );
        } else {
            this.hideAlertBanner();
        }
    }

    showAlertBanner(message, type = 'warning') {
        this.state.showAlertBanner = true;
        this.state.alertBannerMessage = message;
        this.state.alertBannerType = type;
    }

    hideAlertBanner() {
        this.state.showAlertBanner = false;
        this.state.alertBannerMessage = '';
    }
    
    // ==================== PATIENT SEARCH ====================
    
    async onPatientSearch(event) {
        const query = event.target.value;
        this.state.patientSearchQuery = query;
        
        if (query.length < 2) {
            this.state.patientResults = [];
            return;
        }
        
        try {
            this.state.patientLoading = true;
            const result = await this.rpc("/cbm/search_patients", {
                query: query,
                limit: 10,
            });
            this.state.patientResults = result;
            this.state.patientLoading = false;
        } catch (error) {
            this.state.patientLoading = false;
        }
    }
    
    async onPatientBarcodeKeydown(event) {
        // Detect barcode scan: Enter key pressed
        if (event.key === "Enter") {
            const barcode = event.target.value.trim();
            if (barcode && barcode.length >= 3) {
                event.preventDefault();
                await this.searchPatientBarcode(barcode);
            }
        }
    }
    
    async searchPatientBarcode(barcode) {
        // Use exact match endpoint for patient barcode (CBM ID)
        try {
            this.state.patientLoading = true;
            const result = await this.rpc("/cbm/search_patient_barcode", {
                barcode: barcode,
            });
            
            if (result.found) {
                // Auto-select the patient
                this.selectPatient(result);
                this.showToast(
                    _t("Patient selected: ") + result.name,
                    'success'
                );
            } else {
                // Fall back to regular search
                this.showToast(
                    result.error || _t("Patient not found. Try manual search."),
                    'warning'
                );
            }
            this.state.patientLoading = false;
        } catch (error) {
            this.showToast(_t("Barcode search failed"), 'danger');
            this.state.patientLoading = false;
        }
    }
    
    selectPatient(patient) {
        this.state.selectedPatient = patient;
        // Clear search results and query to hide the dropdown
        this.state.patientResults = [];
        this.state.patientSearchQuery = '';  // Clear the query to prevent list reappearing
    }

    // ==================== DEPARTMENT SELECTION ====================

    async loadDepartmentList() {
        try {
            this.state.departmentLoading = true;
            const departments = await this.rpc("/cbm/get_department_partners", {});
            this.state.departmentList = departments;
            this.state.departmentLoading = false;
        } catch (error) {
            this.showToast(_t("Failed to load departments"), 'danger');
            this.state.departmentLoading = false;
        }
    }

    selectDepartment(department) {
        this.state.selectedDepartment = department;
    }

    confirmDepartment() {
        if (!this.state.selectedDepartment) {
            this.showToast(_t("Please select a department"), 'warning');
            return;
        }
        this.state.currentState = "consumption_products";
        // Auto-focus barcode input for immediate scanning
        this.focusBarcodeInput();
    }

    // ==================== SUBMIT ====================
    
    async submitRequest() {
        // CRITICAL: Prevent double submission
        if (this.state.loading) {
            console.warn('[CBM] Submit already in progress, ignoring duplicate request');
            return;
        }

        if (!this.state.selectedProducts.length) {
            this.showToast(_t("Please add at least one product"), 'warning');
            return;
        }

        // Check for hard-blocked items (hoarding policy)
        const blockedItems = this.state.selectedProducts.filter(p => p.hoarding_status === 'blocked');
        if (blockedItems.length > 0) {
            const names = blockedItems.map(p => p.name).join(', ');
            this.showToast(
                _t("Remove blocked items first: ") + names,
                'danger'
            );
            return;
        }

        const lines = this.state.selectedProducts.map(p => ({
            product_id: p.id,
            qty: p.qty,
        }));

        try {
            // Set loading IMMEDIATELY to block duplicate submissions
            this.state.loading = true;
            const result = await this.rpc("/cbm/submit_request", {
                picking_type_id: this.state.selectedOpType?.id,
                lines: lines,
            });
            
            if (result.success) {
                // Mark brain insights as executed if any
                const brainInsightIds = this.state.selectedProducts
                    .filter(p => p._brain_insight_id)
                    .map(p => p._brain_insight_id);
                if (brainInsightIds.length > 0) {
                    try {
                        await this.rpc("/cbm/brain/mark_executed", { insight_ids: brainInsightIds });
                    } catch (e) {
                        console.warn('[Brain] Failed to mark insights as executed', e);
                    }
                }
                
                this.showSuccess(result.message);
            } else {
                this.state.loading = false;

                // ALWAYS show errors in banner (more visible than toast)
                this.showAlertBanner(result.error, 'error');

                // Also show toast for backup
                this.showToast(result.error, 'danger');
            }
        } catch (error) {
            this.state.loading = false;
            this.showAlertBanner(_t("Erreur lors de la soumission. Veuillez réessayer."), 'error');
            this.showToast(_t("Failed to submit request"), 'danger');
        }
    }
    
    async submitConsumption(confirmDeletion = false) {
        // CRITICAL: Prevent double submission
        if (this.state.loading) {
            console.warn('[CBM] Submit already in progress, ignoring duplicate consumption');
            return;
        }

        // Allow submit if there are products OR removed products (returns)
        if (!this.state.selectedProducts.length && !this.state.removedProducts.length) {
            this.showToast(_t("Please add at least one product"), 'warning');
            return;
        }

        if (this.state.selectedOpType?.portal_requires_patient && !this.state.selectedPatient) {
            this.showToast(_t("Please select a patient"), 'warning');
            return;
        }

        if (this.state.selectedOpType?.portal_requires_department && !this.state.selectedDepartment) {
            this.showToast(_t("Please select a department"), 'warning');
            return;
        }

        // Combine selected products with removed products (for returns)
        const lines = this.state.selectedProducts.map(p => ({
            product_id: p.id,
            qty: p.qty,
            original_qty: p.originalQty || false,  // Original qty for delta calculation (returns)
            lot_id: p.lot_id || false,  // Pass lot from barcode scan
            order_line_id: p.order_line_id || false,  // Pass order line ID if pre-loaded from draft
        }));

        // Add removed products (qty=0) so backend knows to return and delete SO line
        for (const removed of this.state.removedProducts) {
            lines.push({
                product_id: removed.id,
                qty: 0,
                original_qty: removed.originalQty,
                lot_id: removed.lot_id || false,
                order_line_id: removed.order_line_id,
            });
        }

        try {
            // Set loading IMMEDIATELY to block duplicate submissions
            this.state.loading = true;
            const result = await this.rpc("/cbm/submit_consumption", {
                picking_type_id: this.state.selectedOpType?.id,
                patient_id: this.state.selectedPatient?.id || false,
                department_id: this.state.selectedDepartment?.id || false,
                lines: lines,
                // FIX Issue #2: Pass linked SO ID to prevent jumping between multiple SOs
                sale_order_id: this.state.linkedSaleOrderId || false,
                // Pass confirmation flag for deletions
                confirm_deletion: confirmDeletion,
            });

            if (result.success) {
                if (result.open_confirm_wizard && result.wizard_action) {
                    this.action.doAction(result.wizard_action);
                } else {
                    this.showSuccess(result.message);
                }
            } else if (result.requires_confirmation) {
                // Show deletion confirmation dialog
                this.state.loading = false;
                this.showDeletionConfirmation(result.deletion_items);
            } else {
                this.state.loading = false;

                // ALWAYS show errors in banner (more visible than toast)
                const bannerType = result.banner_type || 'error';
                this.showAlertBanner(result.error, bannerType);

                // Also show toast for backup (users familiar with it)
                this.showToast(result.error, 'danger');
            }
        } catch (error) {
            this.state.loading = false;
            this.showAlertBanner(_t("Erreur lors de la soumission. Veuillez réessayer."), 'error');
            this.showToast(_t("Failed to submit consumption"), 'danger');
        }
    }

    showDeletionConfirmation(deletionItems) {
        this.state.deletionConfirmItems = deletionItems;
        this.state.showDeletionModal = true;
    }

    confirmDeletion() {
        // User confirmed - resubmit with confirmation flag
        this.state.showDeletionModal = false;
        this.state.deletionConfirmItems = null;
        this.submitConsumption(true);
    }

    cancelDeletion() {
        // User cancelled - close modal, do nothing
        this.state.showDeletionModal = false;
        this.state.deletionConfirmItems = null;
        this.showToast(_t("Suppression annulée"), 'info');
    }

    // ==================== PRESCRIPTION FLOW ====================

    goToPrescription() {
        this.resetPatientState();
        this.resetPrescriptionState();
        this.state.currentState = 'prescription_patient';
        // Use the first patient consumption op type (for stock location resolution)
        const patientOps = this.consumptionOpTypes.filter(op => op.portal_requires_patient);
        if (patientOps.length > 0) {
            this.state.selectedOpType = patientOps[0];
        }
    }

    resetPrescriptionState() {
        this.state.prescriptionLines = [];
        this.state.prescriptionConsumables = [];
        this.state.rxConsumableSearchQuery = "";
        this.state.rxConsumableResults = [];
        this.state.rxSelectedResultIndex = -1;
        this.state.rxActiveTab = 'prescription';
    }

    async confirmPrescriptionPatient() {
        if (!this.state.selectedPatient) return;
        this.state.loading = true;

        try {
            // Determine user's location from the selected op type
            const locationId = this.state.selectedOpType?.default_location_src_id;

            const result = await this.rpc("/cbm/get_patient_prescriptions", {
                patient_id: this.state.selectedPatient.id,
                location_id: locationId || false,
            });

            // Set prescription lines with qty_to_apply initialized to 0
            this.state.prescriptionLines = (result.lines || []).map(line => ({
                ...line,
                qty_to_apply: 0,
            }));

            this.state.currentState = 'prescription_products';
            this.focusBarcodeInput();

        } catch (error) {
            console.error('[CBM Prescription] Failed to load prescriptions:', error);
            this.showToast(_t("Erreur lors du chargement des prescriptions"), 'danger');
        } finally {
            this.state.loading = false;
        }
    }

    incrementPrescriptionLine(line) {
        if (line.qty_to_apply < line.qty_remaining) {
            line.qty_to_apply = (line.qty_to_apply || 0) + 1;
        }
    }

    decrementPrescriptionLine(line) {
        if (line.qty_to_apply > 0) {
            line.qty_to_apply -= 1;
        }
    }

    onPrescriptionQtyChange(line, ev) {
        let val = parseFloat(ev.target.value) || 0;
        if (val < 0) val = 0;
        if (val > line.qty_remaining) val = line.qty_remaining;
        line.qty_to_apply = val;
        ev.target.value = val;
    }

    // --- Consumable search (non-drug) ---

    async onPrescriptionConsumableSearch(ev) {
        const query = ev.target.value.trim();
        this.state.rxConsumableSearchQuery = query;
        this.state.rxSelectedResultIndex = -1;

        if (query.length < 2) {
            this.state.rxConsumableResults = [];
            return;
        }

        try {
            const locationId = this.state.selectedOpType?.default_location_src_id;
            const result = await this.rpc("/cbm/search_products_non_drug", {
                query: query,
                location_id: locationId || false,
                limit: 20,
            });
            this.state.rxConsumableResults = result || [];
        } catch (error) {
            console.error('[CBM Prescription] Consumable search error:', error);
            this.state.rxConsumableResults = [];
        }
    }

    onRxSearchKeydown(ev) {
        const results = this.state.rxConsumableResults;
        if (!results.length) return;

        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            this.state.rxSelectedResultIndex = Math.min(
                this.state.rxSelectedResultIndex + 1, results.length - 1
            );
        } else if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            this.state.rxSelectedResultIndex = Math.max(
                this.state.rxSelectedResultIndex - 1, 0
            );
        } else if (ev.key === 'Enter') {
            ev.preventDefault();
            const idx = this.state.rxSelectedResultIndex;
            if (idx >= 0 && idx < results.length) {
                this.addPrescriptionConsumable(results[idx]);
            } else if (results.length === 1) {
                this.addPrescriptionConsumable(results[0]);
            }
        }
    }

    addPrescriptionConsumable(product) {
        const existing = this.state.prescriptionConsumables.find(p => p.id === product.id);
        if (existing) {
            existing.qty += 1;
        } else {
            this.state.prescriptionConsumables.push({
                id: product.id,
                name: product.display_name || product.name,
                qty: 1,
                uom_name: product.uom_name,
                lot_id: product.lot_id || false,
                qty_available: product.qty_available,
            });
        }
        this.state.rxConsumableSearchQuery = "";
        this.state.rxConsumableResults = [];
        this.state.rxActiveTab = 'consumables';
    }

    incrementPrescriptionConsumable(product) {
        product.qty += 1;
    }

    decrementPrescriptionConsumable(product) {
        if (product.qty > 1) {
            product.qty -= 1;
        }
    }

    onPrescriptionConsumableQtyChange(product, ev) {
        let val = parseInt(ev.target.value) || 1;
        if (val < 1) val = 1;
        product.qty = val;
    }

    removePrescriptionConsumable(product) {
        const index = this.state.prescriptionConsumables.indexOf(product);
        if (index >= 0) {
            this.state.prescriptionConsumables.splice(index, 1);
        }
    }

    // --- Submit prescription ---

    async submitPrescription(confirmDeletion = false) {
        if (this.state.loading) return;

        const prescriptionLines = this.state.prescriptionLines
            .filter(l => l.qty_to_apply > 0)
            .map(l => ({
                prescription_line_id: l.prescription_line_id,
                qty_applied: l.qty_to_apply,
                lot_id: l.lot_id || false,
            }));

        const consumableLines = this.state.prescriptionConsumables.map(p => ({
            product_id: p.id,
            qty: p.qty,
            lot_id: p.lot_id || false,
        }));

        if (!prescriptionLines.length && !consumableLines.length) {
            this.showToast(_t("Veuillez ajouter au moins un produit ou appliquer une quantité"), 'warning');
            return;
        }

        try {
            this.state.loading = true;
            console.log('[RX SUBMIT] Sending:', {
                picking_type_id: this.state.selectedOpType?.id,
                patient_id: this.state.selectedPatient?.id,
                prescription_lines: prescriptionLines,
                consumable_lines: consumableLines,
                opType: this.state.selectedOpType?.name,
            });
            const result = await this.rpc("/cbm/submit_prescription_consumption", {
                picking_type_id: this.state.selectedOpType?.id,
                patient_id: this.state.selectedPatient?.id || false,
                prescription_lines: prescriptionLines,
                consumable_lines: consumableLines,
                confirm_deletion: confirmDeletion,
            });
            console.log('[RX SUBMIT] Result:', result);

            if (result.success) {
                this.showSuccess(result.message);
            } else if (result.requires_confirmation) {
                this.state.loading = false;
                this.showDeletionConfirmation(result.deletion_items);
            } else {
                this.state.loading = false;
                this.showAlertBanner(result.error, result.banner_type || 'error');
                this.showToast(result.error, 'danger');
            }
        } catch (error) {
            this.state.loading = false;
            console.error('[RX SUBMIT] Exception:', error, error?.message, error?.data);
            this.showAlertBanner(_t("Erreur lors de la soumission. Veuillez réessayer."), 'error');
            this.showToast(_t("Échec de la soumission de la prescription"), 'danger');
        }
    }

    showSuccess(message) {
        this.state.successMessage = message;
        this.state.currentState = "success";
        this.state.loading = false;
        this.resetDepartmentState();  // Reset department selection on success

        setTimeout(() => {
            this.goHome();
        }, 3000);
    }
    
    // ==================== HELPERS ====================
    
    resetProductState() {
        this.state.productSearchQuery = "";
        this.state.productResults = [];
        this.state.selectedProducts = [];
        this.state.removedProducts = [];
        // FIX Issue #2: Clear linked SO when resetting cart
        this.state.linkedSaleOrderId = null;
        this.state.linkedSaleOrderName = null;
        this.hideAlertBanner();
    }
    
    resetPatientState() {
        this.state.selectedPatient = null;
        this.state.patientSearchQuery = "";
        this.state.patientResults = [];
    }

    resetDepartmentState() {
        this.state.selectedDepartment = null;
        this.state.departmentList = [];
    }
    
    get consumptionOpTypes() {
        return this.state.operationTypes.filter(
            op => op.portal_category && op.portal_category !== "request"
        );
    }
    
    get hasRequestOpType() {
        return this.state.operationTypes.some(op => op.portal_category === "request");
    }
    
    get hasConsumptionOpTypes() {
        return this.consumptionOpTypes.length > 0;
    }

    get hasPatientConsumptionOpTypes() {
        return this.consumptionOpTypes.some(op => op.portal_requires_patient);
    }

    /** Unique provider names for grouping prescription lines in the template */
    get prescriptionProviders() {
        const providers = new Set();
        for (const line of this.state.prescriptionLines) {
            providers.add(line.provider_name || '');
        }
        return [...providers];
    }

    getStatusClass(state) {
        const classes = {
            'draft': 'bg-secondary',
            'waiting': 'bg-warning',
            'confirmed': 'bg-info',
            'assigned': 'bg-info',
            'done': 'bg-success',
            'cancel': 'bg-danger',
        };
        return classes[state] || 'bg-secondary';
    }
    
    formatDate(isoDate) {
        if (!isoDate) return "";
        const date = new Date(isoDate);
        return date.toLocaleDateString() + " " + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }
    
    openHistoryDetail(item) {
        this.fetchPickingDetail(item.id);
    }
    
    async fetchPickingDetail(pickingId) {
        try {
            this.state.loading = true;
            const result = await this.rpc("/cbm/get_picking_detail", { picking_id: pickingId });
            
            if (result.error) {
                this.showToast(result.error, 'warning');
                this.state.loading = false;
                return;
            }

            this.state.modalData = result;
            this.state.showModal = true;
            this.state.loading = false;
        } catch (error) {
            this.showToast(_t("Failed to load details"), 'danger');
            this.state.loading = false;
        }
    }
    
    openCustomTile(tile) {
        // Intercept maintenance tile - route to internal form instead of Odoo action
        if (tile.icon === 'wrench-screwdriver' || tile.name.toLowerCase().includes('maintenance')) {
            this.goToMaintenance();
            return;
        }

        // Intercept time off tile - route to internal form instead of Odoo action
        if (tile.icon === 'calendar-days' || tile.name.toLowerCase().includes('congé')) {
            this.goToTimeOff();
            return;
        }

        // Intercept inventory tile - route to inventory counting component
        if (tile.icon === 'clipboard-document-list' || tile.name.toLowerCase().includes('inventaire')) {
            this.goToInventory();
            return;
        }

        // Handle client actions (Discuss, etc.) - open in new tab
        if (tile.type === 'client_action' && tile.client_action_tag) {
            // Build URL for client action and open in new tab
            const baseUrl = window.location.origin;
            const actionUrl = `${baseUrl}/web#action=${tile.client_action_tag}`;
            window.open(actionUrl, '_blank');
            return;
        }

        // Open other custom action tiles normally
        if (tile.action_id) {
            this.action.doAction(tile.action_id);
        }
    }
    
    openMyRequests() {
        // Open filtered view of user's own pending requests
        const isAdmin = this.state.pendingApprovals?.is_admin;
        
        let domain;
        if (isAdmin) {
            // Admin sees ALL portal requests
            domain = [
                ['is_portal_request', '=', true],
                ['state', 'not in', ['done', 'cancel']],
            ];
        } else {
            // Regular user sees only their own requests
            domain = [
                ['portal_requester_id', '=', this.state.userContext?.user_id || false],
                ['state', 'not in', ['done', 'cancel']],
            ];
        }
        
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Mes Demandes',
            res_model: 'stock.picking',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            context: {},
        });
    }
    
    openToApprove() {
        // Open filtered view of transfers needing user's approval
        const isAdmin = this.state.pendingApprovals?.is_admin;
        
        const domain = [['approval_state', '=', 'pending']];
        if (!isAdmin) {
            domain.push(['approver_ids', 'in', this.state.userContext?.user_id || false]);
        }
        
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'À Valider',
            res_model: 'stock.picking',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            context: {},
        });
    }
    
    openPendingPO() {
        // Open filtered view of pending PO approvals
        // DRH/Executives/Admin see ALL pending, others see only where they are approver
        const isDRHOrExecOrAdmin = this.state.pendingApprovals?.is_drh || 
                                   this.state.pendingApprovals?.is_executive ||
                                   this.state.userContext?.is_admin;
        
        const domain = [['state', '=', 'to approve']];
        if (!isDRHOrExecOrAdmin) {
            domain.push(['bracket_approver_ids', 'in', this.state.userContext?.user_id || false]);
        }
        
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Pending PO Approvals',
            res_model: 'purchase.order',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            context: {},
        });
    }
    
    openMyReceptions() {
        // Open filtered view of user's pending receptions
        // Uses same filter as count: user's allowed incoming operation types
        const isAdmin = this.state.pendingApprovals?.is_admin;
        const opTypeIds = this.state.pendingApprovals?.user_incoming_op_type_ids || [];
        
        let domain = [
            ['picking_type_code', '=', 'incoming'],
            ['state', 'in', ['assigned', 'confirmed']],
        ];
        
        // Non-admin: filter by their incoming operation types
        if (!isAdmin && opTypeIds.length > 0) {
            domain.push(['picking_type_id', 'in', opTypeIds]);
        }
        
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Réceptions',
            res_model: 'stock.picking',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            context: {},
        });
    }
    
    openStockDiscrepancies() {
        // Open filtered view of pending stock discrepancy alerts
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Stock Discrepancy Alerts',
            res_model: 'clinic.stock.discrepancy',
            view_mode: 'tree,form',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                ['state', '=', 'pending'],
            ],
            context: {},
        });
    }
    
    // ==================== MAINTENANCE REQUEST ====================
    
    openMaintenanceList() {
        // Open the Odoo maintenance request list view
        this.action.doAction('maintenance.hr_equipment_request_action');
    }
    
    goToMaintenance() {
        // Navigate to maintenance request form
        this.state.currentState = 'maintenance';
        this.state.selectedEquipment = null;
        this.state.maintenanceDescription = '';
        this.state.equipmentSearchQuery = '';
        this.state.equipmentResults = [];
        // Don't auto-load equipment list - user must search
    }
    
    async searchEquipment(query) {
        try {
            this.state.equipmentLoading = true;
            const result = await this.rpc('/cbm/get_equipment', {
                query: query,
                limit: 20,
            });
            this.state.equipmentResults = result || [];
            this.state.equipmentLoading = false;
        } catch (error) {
            console.error('Equipment search error:', error);
            this.showToast(_t('Erreur lors de la recherche d\'équipement'), 'warning');
            this.state.equipmentLoading = false;
            this.state.equipmentResults = [];
        }
    }
    
    async onEquipmentSearch(event) {
        const query = event.target.value;
        this.state.equipmentSearchQuery = query;
        await this.searchEquipment(query);
    }
    
    selectEquipment(equipment) {
        this.state.selectedEquipment = equipment;
        this.state.equipmentResults = [];
        this.state.equipmentSearchQuery = equipment.name;
    }
    
    clearEquipment() {
        this.state.selectedEquipment = null;
        this.state.equipmentSearchQuery = '';
        this.searchEquipment('');
    }

    onMaintenanceDescriptionInput(event) {
        this.state.maintenanceDescription = event.target.value;
    }

    async submitMaintenance() {
        if (!this.state.selectedEquipment) {
            this.showToast(_t('Veuillez sélectionner un équipement'), 'warning');
            return;
        }

        try {
            this.state.loading = true;
            const result = await this.rpc('/cbm/submit_maintenance', {
                equipment_id: this.state.selectedEquipment.id,
                description: this.state.maintenanceDescription || '',
            });

            if (result.success) {
                this.showSuccess(_t('Demande créée: ') + result.request_name);
            } else {
                this.showToast(result.error || _t('Erreur lors de la création'), 'danger');
                this.state.loading = false;
            }
        } catch (error) {
            this.showToast(_t('Échec de la création de la demande'), 'danger');
            this.state.loading = false;
        }
    }

    resetMaintenanceState() {
        this.state.selectedEquipment = null;
        this.state.maintenanceDescription = '';
        this.state.equipmentSearchQuery = '';
        this.state.equipmentResults = [];
    }

    // ==================== TIME OFF (form handled by TimeOffForm component) ====================

    goToTimeOff() {
        this.state.currentState = 'timeoff';
        // Form is self-contained in TimeOffForm component
    }

    goToTimeoffRequests() {
        this.state.currentState = 'timeoff_requests';
    }

    goToInventory() {
        this.state.currentState = 'inventory';
        // Session is self-contained in InventoryCount component
    }

    async loadTimeOffHistory() {
        try {
            this.state.timeoffHistoryLoading = true;

            const result = await this.rpc('/cbm/get_timeoff_history', {});
            this.state.timeoffHistory = result || [];

            this.state.timeoffHistoryLoading = false;
        } catch (error) {
            console.error('Failed to load time off history:', error);
            this.state.timeoffHistoryLoading = false;
        }
    }

    setHistoryTab(tab) {
        this.state.historyActiveTab = tab;
    }

    printTimeOffFromHistory(leaveId) {
        if (leaveId) {
            window.open('/cbm/timeoff/get_pdf/' + leaveId, '_blank');
        }
    }

    getTimeOffStatusClass(state) {
        const statusMap = {
            'draft': 'draft',
            'confirm': 'waiting',
            'validate1': 'waiting',
            'validate': 'done',
            'refuse': 'cancel',
        };
        return statusMap[state] || 'draft';
    }

    getTimeOffStatusLabel(state) {
        const labelMap = {
            'draft': _t('Brouillon'),
            'confirm': _t('En attente'),
            'validate1': _t('Première validation'),
            'validate': _t('Validé'),
            'refuse': _t('Refusé'),
        };
        return labelMap[state] || state;
    }

    // ==================== CASHIER MODULE ====================
    
    async checkCashierAccess() {
        try {
            const result = await this.rpc('/cbm/cashier/check_access', {});
            this.state.hasCashierAccess = result.has_access || false;
        } catch (error) {
            this.state.hasCashierAccess = false;
        }
    }
    
    goToCashier() {
        this.resetProductState();
        this.resetPatientState();
        this.resetDepartmentState();
        this.state.currentState = 'cashier';
        this.resetCashierState();
        this.loadCashierSession();
        this.startCashierPolling();
    }
    
    resetCashierState() {
        this.state.cashierSearchQuery = '';
        this.state.cashierSearchResults = [];
        this.state.cashierSelectedDocument = null;
        this.state.cashierLoading = false;
        // Split-view state reset
        this.state.cashierMode = 'dashboard';
        this.state.cashierFilter = 'all';
        this.state.cashierSelectedId = null;
        this.state.cashierPaymentSuccess = false;
        this.state.cashierChangeDue = 0;
        this.state.cashierSuccessInvoiceId = null;
        // Clear any pending undo
        if (this.state.cashierUndoToast?.timeoutId) {
            clearTimeout(this.state.cashierUndoToast.timeoutId);
        }
        this.state.cashierUndoToast = null;
    }
    
    async loadCashierSession() {
        try {
            const result = await this.rpc('/cbm/cashier/session/current', {});
            
            // Auto-open session if none exists
            if (!result.is_open) {
                const newSession = await this.rpc('/cbm/cashier/session/open', {});
                this.state.cashierSession = newSession;
            } else {
                this.state.cashierSession = result;
            }
        } catch (error) {
            this.state.cashierSession = { is_open: false, running_total: 0, payment_count: 0 };
        }
    }
    
    startCashierPolling() {
        // Clear existing interval
        if (this.state.cashierPollingInterval) {
            clearInterval(this.state.cashierPollingInterval);
        }
        // Poll every 5 seconds
        this.state.cashierPollingInterval = setInterval(() => {
            this.pollCashierList();
        }, 5000);
        // Initial load
        this.pollCashierList();
    }
    
    stopCashierPolling() {
        if (this.state.cashierPollingInterval) {
            clearInterval(this.state.cashierPollingInterval);
            this.state.cashierPollingInterval = null;
        }
    }
    
    async pollCashierList() {
        // Only poll if in dashboard or workspace mode
        if (this.state.currentState !== 'cashier') {
            this.stopCashierPolling();
            return;
        }
        
        try {
            const result = await this.rpc('/cbm/cashier/search', {
                query: this.state.cashierSearchQuery || '',
                limit: 50,
            });
            const newResults = result.results || [];
            const oldIds = new Set(this.state.cashierSearchResults.map(r => r.id + '_' + r.type));
            
            // Mark new items for animation
            for (const item of newResults) {
                const key = item.id + '_' + item.type;
                if (!oldIds.has(key)) {
                    item.isNew = true;
                    setTimeout(() => { item.isNew = false; }, 2000);
                }
            }
            
            this.state.cashierSearchResults = newResults;
            
            // Preserve selection
            if (this.state.cashierSelectedId) {
                const stillExists = newResults.find(
                    r => r.id === this.state.cashierSelectedId && r.type === this.state.cashierSelectedDocument?.type
                );
                if (!stillExists) {
                    // Selected item removed, close workspace
                    this.closeCashierWorkspace();
                }
            }
        } catch (error) {
            // Silent fail for polling
        }
    }
    
    // ==================== SPLIT-VIEW ROW SELECTION ====================
    
    selectCashierRow(doc) {
        if (this.state.cashierPaymentSuccess) return;  // Prevent selection during success overlay
        
        // Preserve scroll position before state change
        const listPanel = document.querySelector('.cbm_cashier_list_panel');
        const scrollTop = listPanel ? listPanel.scrollTop : 0;
        
        this.state.cashierSelectedId = doc.id;
        this.state.cashierSelectedDocument = doc;
        this.state.cashierMode = 'workspace';
        
        // Restore scroll position after DOM updates (use timeout for reliability)
        setTimeout(() => {
            const panel = document.querySelector('.cbm_cashier_list_panel');
            if (panel) {
                panel.scrollTop = scrollTop;
            }
        }, 50);
        
        // Load payment form data INLINE (not as popup modal)
        if (doc.color === 'blue') {
            this.loadInlineValidationData(doc);
        } else if (doc.color === 'orange' || doc.color === 'green' || doc.color === 'red') {
            // Orange, green, red are all invoices - load invoice details
            this.loadInlinePaymentData(doc);
        }
    }
    
    async loadInlineValidationData(doc) {
        // Load split preview, lines, and conventions for inline display
        try {
            // Use workspaceLoading to avoid hiding the table
            this.state.workspaceLoading = true;
            
            const pricelistResult = await this.rpc('/cbm/cashier/get_pricelists', {});
            const allPricelists = pricelistResult.pricelists || [];
            this.state.cashierConventions = allPricelists.filter(pl => pl.is_convention);
            
            const splitResult = await this.rpc('/cbm/cashier/get_split', {
                order_id: doc.id,
            });
            
            this.state.cashierSplitPreview = splitResult;
            this.state.cashierPaymentAmount = splitResult.patient_share || splitResult.amount_total || 0;
            this.state.cashierConventionEnabled = false;
            this.state.cashierSelectedConventionId = null;
            this.state.cashierPaymentMethod = 'cash';
            
            // Store lines for display (from order lines in split result)
            this.state.cashierDocumentLines = splitResult.lines || [];
            this.state.cashierDocumentConvention = splitResult.convention_name || null;
            this.state.cashierDocumentConventionPct = splitResult.convention_pct || 0;
            
            this.state.workspaceLoading = false;
        } catch (error) {
            this.state.workspaceLoading = false;
            this.showToast(_t('Erreur lors du chargement'), 'danger');
        }
    }

    async loadInlinePaymentData(doc) {
        // Load invoice info with lines for inline display
        try {
            // Use workspaceLoading to avoid hiding the table
            this.state.workspaceLoading = true;
            
            const result = await this.rpc('/cbm/cashier/get_invoice_info', {
                invoice_id: doc.id,
            });
            
            this.state.payRemainderInvoice = result;
            this.state.payRemainderAmount = result.amount_residual || 0;
            this.state.payRemainderMethod = 'cash';
            this.state.cashierPaymentMethod = 'cash';
            
            // Store lines for display
            console.log('[CASHIER DEBUG] get_invoice_info result:', result);
            console.log('[CASHIER DEBUG] lines:', result.lines);
            this.state.cashierDocumentLines = result.lines || [];
            this.state.cashierDocumentConvention = result.convention_name || null;
            this.state.cashierDocumentConventionPct = result.convention_pct || 0;
            this.state.cashierPaymentAmount = result.amount_residual || 0;
            
            this.state.workspaceLoading = false;
        } catch (error) {
            this.state.workspaceLoading = false;
            this.showToast(_t('Erreur lors du chargement'), 'danger');
        }
    }

    // Inline payment execution (replaces modal buttons)
    async executeInlinePayment() {
        const doc = this.state.cashierSelectedDocument;
        if (!doc) return;
        
        try {
            this.state.cashierValidating = true;
            
            let result;
            if (doc.type === 'quotation' || doc.color === 'blue') {
                result = await this.rpc('/cbm/cashier/validate', {
                    order_id: doc.id,
                    payment_method: this.state.cashierPaymentMethod,
                    amount: this.state.cashierPaymentAmount,  // Pass partial payment amount
                    pricelist_id: this.state.cashierConventionEnabled ? this.state.cashierSelectedConventionId : null,
                });
            } else {
                result = await this.rpc('/cbm/cashier/pay', {
                    invoice_id: doc.id,
                    amount: this.state.payRemainderAmount || this.state.payRemainderInvoice?.amount_residual,
                    payment_method: this.state.payRemainderMethod || 'cash',
                });
            }
            
            this.state.cashierValidating = false;
            
            if (result.success) {
                this.state.cashierPaymentSuccess = true;
                this.state.cashierChangeDue = 0;
                this.state.cashierSuccessInvoiceId = result.invoice_id;
                
                // Immediately refresh the list (so devis becomes invoice/paid)
                await this.pollCashierList();
                
                // Refresh session totals
                this.loadCashierSession();
                
                // Auto-print receipt (only once)
                this.printReceiptSilent(result.invoice_id);
                
                // Auto-reset after 5 seconds (increased from 3s for better UX)
                setTimeout(() => {
                    if (this.state.cashierPaymentSuccess) {
                        this.closeCashierWorkspace();
                        this.pollCashierList();
                    }
                }, 5000);
            } else {
                this.showToast(result.error || _t('Erreur de paiement'), 'danger');
            }
        } catch (error) {
            this.state.cashierValidating = false;
            this.showToast(_t('Erreur de paiement'), 'danger');
        }
    }

    closeCashierWorkspace() {
        this.state.cashierSelectedId = null;
        this.state.cashierSelectedDocument = null;
        this.state.cashierMode = 'dashboard';
        this.state.cashierPaymentSuccess = false;
        this.state.showCashierPayModal = false;
        this.state.showPayRemainderModal = false;
    }
    
    // ==================== QUICK ACTIONS ====================
    
    async quickPay(doc, ev) {
        ev.stopPropagation();  // Prevent row selection
        
        if (doc.color !== 'blue' && doc.color !== 'orange') return;
        
        try {
            this.state.cashierLoading = true;
            
            let result;
            if (doc.type === 'quotation') {
                // Validate quotation with full payment
                result = await this.rpc('/cbm/cashier/validate', {
                    order_id: doc.id,
                    payment_method: 'cash',
                });
            } else {
                // Pay remaining on invoice
                result = await this.rpc('/cbm/cashier/pay', {
                    invoice_id: doc.id,
                    amount: doc.amount_residual,
                    payment_method: 'cash',
                });
            }
            
            this.state.cashierLoading = false;
            
            if (result.success) {
                // Show success and print
                this.state.cashierPaymentSuccess = true;
                this.state.cashierChangeDue = 0;  // Quick pay = exact amount
                this.state.cashierSuccessInvoiceId = result.invoice_id;
                this.state.cashierMode = 'workspace';
                this.state.cashierSelectedId = doc.id;
                this.state.cashierSelectedDocument = doc;
                
                // Silent print
                this.printReceiptSilent(result.invoice_id);
                
                // Auto-reset after 5 seconds
                setTimeout(() => {
                    if (this.state.cashierPaymentSuccess) {
                        this.closeCashierWorkspace();
                        this.pollCashierList();  // Refresh list
                    }
                }, 5000);
            } else {
                this.showToast(result.error || _t('Erreur de paiement'), 'danger');
            }
        } catch (error) {
            this.state.cashierLoading = false;
            this.showToast(_t('Erreur de paiement'), 'danger');
        }
    }

    quickCancel(doc, ev) {
        ev.stopPropagation();  // Prevent row selection
        
        // Show undo toast for 5 seconds
        const timeoutId = setTimeout(() => {
            // Execute cancel
            this.executeCancelAfterUndo(doc);
        }, 5000);
        
        this.state.cashierUndoToast = {
            message: `Annulation de ${doc.name}...`,
            timeoutId: timeoutId,
            docId: doc.id,
        };
    }
    
    quickRefund(doc, ev) {
        ev.stopPropagation();  // Prevent row selection

        // Set mode FIRST, then select document
        this.state.cashierMode = 'refund';
        this.state.cashierSelectedId = doc.id;
        this.state.cashierSelectedDocument = doc;

        // Load refund info
        this.loadRefundInfo(doc.id);
    }
    
    async loadRefundInfo(invoiceId) {
        try {
            this.state.workspaceLoading = true;
            const result = await this.rpc('/cbm/cashier/get_refund_info', { invoice_id: invoiceId });

            if (result.error) {
                this.showToast(result.error, 'danger');
                this.state.workspaceLoading = false;
                return;
            }

            this.state.refundInfo = result;
            this.state.refundAmount = result.max_refund_amount || 0;
            this.state.refundMode = 'total';
            this.state.refundReason = '';
            this.state.workspaceLoading = false;
        } catch (error) {
            this.state.workspaceLoading = false;
            this.showToast(_t('Erreur lors du chargement'), 'danger');
        }
    }

    async executeInlineRefund() {
        if (!this.state.cashierSelectedDocument || !this.state.refundAmount) return;
        
        try {
            this.state.cashierValidating = true;
            
            const result = await this.rpc('/cbm/cashier/refund', {
                invoice_id: this.state.cashierSelectedDocument.id,
                mode: this.state.refundMode,
                amount: this.state.refundAmount,
                reason: this.state.refundReason || 'Remboursement client',
            });
            
            this.state.cashierValidating = false;
            
            if (result.error) {
                this.showToast(result.error, 'danger');
                return;
            }

            // Show success overlay (same as payment success)
            this.state.cashierPaymentSuccess = true;
            this.state.cashierChangeDue = 0;
            this.state.cashierSuccessInvoiceId = result.credit_note_id || null;

            // Refresh list immediately
            await this.pollCashierList();

            // Refresh session totals
            this.loadCashierSession();

            // Auto-close after 5 seconds (same as payment)
            setTimeout(() => {
                if (this.state.cashierPaymentSuccess) {
                    this.closeCashierWorkspace();
                    this.pollCashierList();
                }
            }, 5000);
        } catch (error) {
            this.state.cashierValidating = false;
            this.showToast(_t('Erreur lors du remboursement'), 'danger');
        }
    }

    undoCancel() {
        if (this.state.cashierUndoToast?.timeoutId) {
            clearTimeout(this.state.cashierUndoToast.timeoutId);
        }
        this.state.cashierUndoToast = null;
        this.showToast(_t('Annulation annulée'), 'info');
    }
    
    async executeCancelAfterUndo(doc) {
        this.state.cashierUndoToast = null;
        
        try {
            const result = await this.rpc('/cbm/cashier/cancel', {
                invoice_id: doc.id,
                reason: 'Annulation depuis caisse',
            });
            
            if (result.success) {
                this.showToast(result.message || _t('Facture annulée'), 'success');
                this.pollCashierList();  // Refresh
            } else {
                this.showToast(result.error || _t('Erreur'), 'danger');
            }
        } catch (error) {
            this.showToast(_t('Erreur lors de l\'annulation'), 'danger');
        }
    }
    
    // ==================== THEME TOGGLE ====================

    toggleKioskTheme() {
        this.state.kioskDarkMode = !this.state.kioskDarkMode;
        localStorage.setItem('cbm_kiosk_theme', this.state.kioskDarkMode ? 'dark' : 'light');
    }

    toggleTheme() {
        this.state.cashierLightMode = !this.state.cashierLightMode;
        localStorage.setItem('cbm_cashier_theme', this.state.cashierLightMode ? 'light' : 'dark');
    }

    // ==================== SESSION WIDGET ====================
    
    async toggleSessionPanel() {
        if (!this.state.cashierSession?.is_open) {
            // Open new session
            try {
                const result = await this.rpc('/cbm/cashier/session/open', {});
                this.state.cashierSession = result;
                this.showToast(_t('Session ouverte'), 'success');
            } catch (error) {
                this.showToast(_t('Erreur ouverture session'), 'danger');
            }
        } else {
            // Show session summary panel
            this.state.cashierMode = 'session';
            await this.refreshSessionSummary();
        }
    }
    
    async refreshSessionSummary() {
        try {
            const result = await this.rpc('/cbm/cashier/session/summary', {});
            if (!result.error) {
                this.state.cashierSession = result;
            }
        } catch (error) {
            // Silent
        }
    }
    
    onCountedCashInput(ev) {
        this.state.cashierSession.counted_cash = parseFloat(ev.target.value) || 0;
    }
    
    async closeSession() {
        try {
            this.state.cashierLoading = true;
            const result = await this.rpc('/cbm/cashier/session/close', {
                counted_cash: this.state.cashierSession.counted_cash || 0,
                notes: '',
            });
            
            this.state.cashierLoading = false;
            
            if (result.success) {
                // Print Z-Report (use existing print mechanism)
                this.showToast(
                    _t('Session fermée. Écart: ') + result.difference + ' DA',
                    'info'
                );
                this.state.cashierSession = { is_open: false };
                this.state.cashierMode = 'dashboard';
            } else {
                this.showToast(result.error || _t('Erreur'), 'danger');
            }
        } catch (error) {
            this.state.cashierLoading = false;
            this.showToast(_t('Erreur fermeture session'), 'danger');
        }
    }
    
    // ==================== SILENT PRINTING ====================
    
    printReceiptSilent(invoiceId) {
        // Prevent duplicate prints
        if (this._printingInvoiceId === invoiceId) {
            console.log('[CASHIER] Skipping duplicate print for invoice', invoiceId);
            return;
        }
        this._printingInvoiceId = invoiceId;
        
        // Remove old iframe to ensure clean state
        let oldIframe = document.getElementById('cbm-print-iframe');
        if (oldIframe) {
            oldIframe.remove();
        }
        
        // Create hidden iframe - the receipt template has its own auto-print script
        // that calls window.print() on load, so we just need to load the page
        const iframe = document.createElement('iframe');
        iframe.id = 'cbm-print-iframe';
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
        
        // Reset flag after delay to allow future prints
        setTimeout(() => {
            this._printingInvoiceId = null;
        }, 3000);
        
        iframe.src = `/cbm/cashier/receipt/html/${invoiceId}`;
    }
    
    reprintReceipt() {
        if (this.state.cashierSuccessInvoiceId) {
            this.printReceiptSilent(this.state.cashierSuccessInvoiceId);
        }
    }
    
    // ==================== FILTER PILLS ====================
    
    setCashierFilter(filter) {
        this.state.cashierFilter = filter;
        // TODO: Apply filter to cashierSearchResults or modify search query
    }
    
    get filteredCashierResults() {
        const results = this.state.cashierSearchResults || [];
        const filter = this.state.cashierFilter;
        
        if (filter === 'all') return results;
        if (filter === 'draft') return results.filter(r => r.color === 'blue');
        if (filter === 'unpaid') return results.filter(r => r.color === 'orange');
        if (filter === 'paid') return results.filter(r => r.color === 'green');
        return results;
    }
    
    onCashierSearchInput(ev) {
        this.state.cashierSearchQuery = ev.target.value;
        // Debounce search
        clearTimeout(this._cashierSearchTimeout);
        this._cashierSearchTimeout = setTimeout(() => {
            this.searchCashier(this.state.cashierSearchQuery);
        }, 300);
    }
    
    async searchCashier(query) {
        if (query.length < 2) {
            this.state.cashierSearchResults = [];
            return;
        }
        
        try {
            this.state.cashierLoading = true;
            const result = await this.rpc('/cbm/cashier/search', {
                query: query,
                limit: 20,
            });
            this.state.cashierSearchResults = result.results || [];
            this.state.cashierLoading = false;
        } catch (error) {
            this.state.cashierSearchResults = [];
            this.state.cashierLoading = false;
            this.showToast(_t('Erreur de recherche'), 'danger');
        }
    }

    async selectCashierDocument(doc) {
        this.state.cashierSelectedDocument = doc;

        // Handle based on document color/type
        if (doc.color === 'blue') {
            // Quotation - show validation modal
            await this.showValidationModal(doc);
        } else if (doc.color === 'orange') {
            // Unpaid invoice - show pay remainder modal
            await this.showPayRemainderModal(doc);
        } else if (doc.color === 'green') {
            // Paid invoice - print receipt
            this.printReceipt(doc.id);
        } else if (doc.color === 'red') {
            // Cancelled - show status
            this.showToast(_t('Affichage statut - À venir'), 'info');
        }
    }

    async showValidationModal(doc) {
        try {
            this.state.cashierLoading = true;

            // Load available conventions (pricelists with convention_pct > 0)
            const pricelistResult = await this.rpc('/cbm/cashier/get_pricelists', {});
            const allPricelists = pricelistResult.pricelists || [];
            this.state.cashierConventions = allPricelists.filter(pl => pl.is_convention);

            // Get split preview (no convention by default)
            const splitResult = await this.rpc('/cbm/cashier/get_split', {
                order_id: doc.id,
            });

            this.state.cashierSplitPreview = splitResult;
            this.state.cashierPaymentAmount = splitResult.amount_total || 0;
            this.state.cashierConventionEnabled = false;  // Default: no convention
            this.state.cashierSelectedConventionId = null;
            this.state.showCashierPayModal = true;
            this.state.cashierPaymentMethod = 'cash';
            this.state.cashierLoading = false;
        } catch (error) {
            this.state.cashierLoading = false;
            this.showToast(_t('Erreur lors du chargement'), 'danger');
        }
    }
    
    toggleConvention() {
        this.state.cashierConventionEnabled = !this.state.cashierConventionEnabled;
        
        if (!this.state.cashierConventionEnabled) {
            // Disabled convention - reset to no split
            this.state.cashierSelectedConventionId = null;
            this.refreshSplitPreview(null);
        } else if (this.state.cashierConventions.length > 0) {
            // Enabled convention - auto-select first one
            const firstConvention = this.state.cashierConventions[0];
            this.state.cashierSelectedConventionId = firstConvention.id;
            this.refreshSplitPreview(firstConvention.id);
        }
    }
    
    async onConventionChange(ev) {
        const conventionId = parseInt(ev.target.value) || null;
        this.state.cashierSelectedConventionId = conventionId;
        await this.refreshSplitPreview(conventionId);
    }
    
    async refreshSplitPreview(conventionId) {
        if (!this.state.cashierSelectedDocument) return;
        
        const splitResult = await this.rpc('/cbm/cashier/get_split', {
            order_id: this.state.cashierSelectedDocument.id,
            pricelist_id: conventionId,
        });
        this.state.cashierSplitPreview = splitResult;
        // Update payment amount to patient share when convention is active
        this.state.cashierPaymentAmount = splitResult.patient_share || splitResult.amount_total || 0;
    }
    
    onPaymentMethodChange(ev) {
        this.state.cashierPaymentMethod = ev.target.value;
    }
    
    onPaymentAmountChange(ev) {
        const value = parseFloat(ev.target.value) || 0;
        const max = this.state.cashierSplitPreview?.amount_total || 0;
        this.state.cashierPaymentAmount = Math.min(Math.max(0, value), max);
    }
    
    async confirmValidation() {
        if (!this.state.cashierSelectedDocument) return;
        
        try {
            this.state.cashierValidating = true;
            
            const result = await this.rpc('/cbm/cashier/validate', {
                order_id: this.state.cashierSelectedDocument.id,
                payment_method: this.state.cashierPaymentMethod,
                amount: this.state.cashierPaymentAmount,
                pricelist_id: this.state.cashierSelectedConventionId,
            });
            
            this.state.cashierValidating = false;
            
            if (result.success) {
                this.closeCashierPayModal();
                this.showSuccess(_t('Facture validée: ') + result.invoice_name);
                
                // Refresh search results
                if (this.state.cashierSearchQuery) {
                    await this.searchCashier(this.state.cashierSearchQuery);
                }
                
                // Print receipt after validation (silent)
                this.printReceiptSilent(result.invoice_id);
            } else {
                this.showToast(result.error || _t('Échec de la validation'), 'danger');
            }
        } catch (error) {
            this.state.cashierValidating = false;
            this.showToast(_t('Erreur lors de la validation'), 'danger');
        }
    }

    closeCashierPayModal() {
        this.state.showCashierPayModal = false;
        this.state.cashierSplitPreview = null;
        this.state.cashierSelectedDocument = null;
    }
    
    printReceipt(invoiceId) {
        // Open receipt as HTML (for thermal printer auto-print)
        const url = `/report/html/serenvale_custom_invoice_print.report_pos_style_payment_receipt/${invoiceId}`;
        window.open(url, '_blank');
    }
    
    // =============================================
    // PHASE 3: Orange Card - Pay Remainder
    // =============================================
    
    async showPayRemainderModal(doc) {
        try {
            this.state.cashierLoading = true;
            
            // Get invoice info from backend
            const invoiceInfo = await this.rpc('/cbm/cashier/get_invoice_info', {
                invoice_id: doc.id,
            });
            
            if (invoiceInfo.error) {
                this.showToast(invoiceInfo.error, 'danger');
                this.state.cashierLoading = false;
                return;
            }

            this.state.payRemainderInvoice = invoiceInfo;
            this.state.payRemainderAmount = invoiceInfo.amount_residual;
            this.state.payRemainderMethod = 'cash';
            this.state.showPayRemainderModal = true;
            this.state.cashierLoading = false;
        } catch (error) {
            this.state.cashierLoading = false;
            this.showToast(_t('Erreur lors du chargement'), 'danger');
        }
    }

    onPayRemainderAmountChange(ev) {
        const val = parseFloat(ev.target.value) || 0;
        const max = this.state.payRemainderInvoice?.amount_residual || 0;
        this.state.payRemainderAmount = Math.min(Math.max(0, val), max);
    }
    
    onPayRemainderMethodChange(ev) {
        this.state.payRemainderMethod = ev.target.value;
    }
    
    async confirmPayRemainder() {
        if (!this.state.payRemainderInvoice) return;
        if (this.state.payRemainderAmount <= 0) {
            this.showToast(_t('Montant invalide'), 'warning');
            return;
        }

        try {
            this.state.payRemainderProcessing = true;

            const result = await this.rpc('/cbm/cashier/pay', {
                invoice_id: this.state.payRemainderInvoice.invoice_id,
                amount: this.state.payRemainderAmount,
                payment_method: this.state.payRemainderMethod,
            });

            this.state.payRemainderProcessing = false;

            if (result.success) {
                const invoiceId = this.state.payRemainderInvoice?.invoice_id;
                const amountPaid = this.state.payRemainderAmount;

                // Show notification IMMEDIATELY before any state changes
                // This ensures notification appears on current screen, not a future page
                this.showToast(
                    _t('Paiement effectué: ') + amountPaid.toLocaleString('fr-DZ') + ' DA',
                    'success'
                );

                // Now close modal and navigate
                this.closePayRemainderModal();

                if (result.fully_paid) {
                    this.showSuccess(_t('Facture entièrement payée!'));
                } else {
                    this.showSuccess(_t('Paiement enregistré - Reste: ') + result.amount_residual.toLocaleString('fr-DZ') + ' DA');
                }

                // Print receipt after EVERY payment
                if (invoiceId) this.printReceipt(invoiceId);

                // Refresh search results
                if (this.state.cashierSearchQuery) {
                    await this.searchCashier(this.state.cashierSearchQuery);
                }
            } else {
                this.showToast(result.error || _t('Échec du paiement'), 'danger');
            }
        } catch (error) {
            this.state.payRemainderProcessing = false;
            this.showToast(_t('Erreur lors du paiement'), 'danger');
        }
    }
    
    closePayRemainderModal() {
        this.state.showPayRemainderModal = false;
        this.state.payRemainderInvoice = null;
        this.state.payRemainderAmount = 0;
        this.state.cashierSelectedDocument = null;
    }
    
    closeModal() {
        this.state.showModal = false;
        this.state.modalData = null;
    }
    
    // =============================================
    // PHASE 4: CORRECTIONS (Cancel, Refund, Status)
    // =============================================
    
    // Show cancel confirmation modal
    confirmCancel(doc) {
        this.state.cancelInvoice = doc;
        this.state.cancelReason = '';
        this.state.showCancelModal = true;
    }
    
    closeCancelModal() {
        this.state.showCancelModal = false;
        this.state.cancelInvoice = null;
        this.state.cancelReason = '';
        this.state.cancelProcessing = false;
    }
    
    onCancelReasonInput(ev) {
        this.state.cancelReason = ev.target.value;
    }
    
    async executeCancel() {
        if (!this.state.cancelInvoice) return;
        
        try {
            this.state.cancelProcessing = true;
            
            const result = await this.rpc('/cbm/cashier/cancel', {
                invoice_id: this.state.cancelInvoice.id,
                reason: this.state.cancelReason || '',
            });
            
            this.state.cancelProcessing = false;
            
            if (result.success) {
                this.closeCancelModal();
                this.showToast(result.message, 'success');

                // Refresh search results
                if (this.state.cashierSearchQuery) {
                    await this.searchCashier(this.state.cashierSearchQuery);
                }
            } else {
                this.showToast(result.error || _t('Échec de l\'annulation'), 'danger');
            }
        } catch (error) {
            this.state.cancelProcessing = false;
            this.showToast(_t('Erreur lors de l\'annulation'), 'danger');
        }
    }

    // Open refund wizard for green cards
    openRefundWizard(doc) {
        this.state.refundInvoice = doc;
        this.state.refundMode = 'total';
        this.state.refundAmount = doc.amount_total || 0;
        this.state.refundReason = '';
        this.state.showRefundWizard = true;
    }
    
    closeRefundWizard() {
        this.state.showRefundWizard = false;
        this.state.refundInvoice = null;
        this.state.refundMode = 'total';
        this.state.refundAmount = 0;
        this.state.refundReason = '';
        this.state.refundProcessing = false;
    }
    
    onRefundModeChange(ev) {
        this.state.refundMode = ev.target.value;
        // Pre-fill amount based on mode
        if (this.state.refundMode === 'total' && this.state.refundInvoice) {
            this.state.refundAmount = this.state.refundInvoice.amount_total || 0;
        }
    }
    
    onRefundAmountInput(ev) {
        this.state.refundAmount = parseFloat(ev.target.value) || 0;
    }
    
    onRefundReasonInput(ev) {
        this.state.refundReason = ev.target.value;
    }
    
    async executeRefund() {
        if (!this.state.refundInvoice) return;
        
        // Validate
        if (!this.state.refundReason.trim()) {
            this.showToast(_t('La raison est obligatoire'), 'warning');
            return;
        }

        if (this.state.refundMode !== 'total' && this.state.refundAmount <= 0) {
            this.showToast(_t('Le montant doit être supérieur à 0'), 'warning');
            return;
        }
        
        try {
            this.state.refundProcessing = true;
            
            const result = await this.rpc('/cbm/cashier/refund', {
                invoice_id: this.state.refundInvoice.id,
                mode: this.state.refundMode,
                amount: this.state.refundAmount,
                reason: this.state.refundReason,
            });
            
            this.state.refundProcessing = false;
            
            if (result.success) {
                this.closeRefundWizard();
                this.showToast(result.message, 'success');

                // Refresh search results
                if (this.state.cashierSearchQuery) {
                    await this.searchCashier(this.state.cashierSearchQuery);
                }
            } else {
                this.showToast(result.error || _t('Échec du remboursement'), 'danger');
            }
        } catch (error) {
            this.state.refundProcessing = false;
            this.showToast(_t('Erreur lors du remboursement'), 'danger');
        }
    }

    // Show status popup for red cards
    async showStatus(doc) {
        try {
            this.state.statusLoading = true;
            this.state.showStatusModal = true;

            const result = await this.rpc('/cbm/cashier/get_status', {
                invoice_id: doc.id,
            });

            this.state.statusLoading = false;

            if (result.error) {
                this.showToast(result.error, 'danger');
                this.state.showStatusModal = false;
                return;
            }

            this.state.statusData = result;
        } catch (error) {
            this.state.statusLoading = false;
            this.state.showStatusModal = false;
            this.showToast(_t('Erreur lors du chargement du statut'), 'danger');
        }
    }
    
    closeStatusModal() {
        this.state.showStatusModal = false;
        this.state.statusData = null;
    }
}

// REGISTER THE CLIENT ACTION
registry.category("actions").add("cbm_kiosk_action", CBMKiosk);