/** @odoo-module **/
/**
 * InventoryCount Component - Physical Inventory Counting for CBM Portal
 * Allows staff to count stock, search products by barcode/name, and view/edit lines
 */

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class InventoryCount extends Component {
    static template = "clinic_staff_portal.InventoryCount";

    setup() {
        this.rpc = useService("rpc");
        this.searchInputRef = useRef("searchInput");
        this.barcodeInputRef = useRef("barcodeInput");

        this.state = useState({
            // Session
            sessionLoading: true,
            sessionFound: false,
            sessionId: null,
            sessionName: '',
            locationId: null,
            locationName: '',
            teamId: null,
            teamName: '',

            // Lines
            linesLoading: false,
            lines: [],  // [{id, product_id, product_name, lot_id, lot_name, expiry_date, qty_counted, uom_name, note}]

            // Search
            searchQuery: '',
            searchResults: [],
            searchLoading: false,
            selectedResultIndex: -1,
            searchDropdownOpen: false,

            // Add/Edit form
            editingLine: null,  // {product_id, product_name, lot_id, lot_name, expiry_date, qty_counted, note, uom_name} or null
            editingLineId: null,  // line_id if updating, null if creating

            // Submission
            savingLine: false,
            deleteConfirmLineId: null,  // line_id pending deletion
        });

        this.loadSession();
    }

    // ============================================================
    // SESSION LOADING
    // ============================================================

    async loadSession() {
        try {
            this.state.sessionLoading = true;

            const result = await this.rpc('/cbm/inventory/get_session', {});

            if (!result.found) {
                this.state.sessionFound = false;
                this.state.sessionLoading = false;
                return;
            }

            this.state.sessionFound = true;
            this.state.sessionId = result.session_id;
            this.state.sessionName = result.session_name;
            this.state.locationId = result.location_id;
            this.state.locationName = result.location_name;
            this.state.teamId = result.team_id;
            this.state.teamName = result.team_name;

            console.log('[INVENTORY] Session loaded:', {
                sessionId: this.state.sessionId,
                teamId: this.state.teamId,
                teamName: this.state.teamName,
            });

            await this.loadLines();
            this.state.sessionLoading = false;

        } catch (error) {
            console.error("[INVENTORY] Failed to load session:", error);
            this.state.sessionFound = false;
            this.state.sessionLoading = false;
        }
    }

    // ============================================================
    // LINES MANAGEMENT
    // ============================================================

    async loadLines() {
        if (!this.state.sessionId) {
            return;
        }

        try {
            this.state.linesLoading = true;

            const result = await this.rpc('/cbm/inventory/get_lines', {
                session_id: this.state.sessionId,
            });

            this.state.lines = result || [];
            console.log('[INVENTORY] Lines loaded:', this.state.lines.length);
            this.state.linesLoading = false;

        } catch (error) {
            console.error("[INVENTORY] Failed to load lines:", error);
            this.state.linesLoading = false;
        }
    }

    // ============================================================
    // SEARCH & PRODUCT SELECTION
    // ============================================================

    async onSearchInput(event) {
        const query = event.target.value || '';
        this.state.searchQuery = query;
        this.state.selectedResultIndex = -1;

        if (!query.trim()) {
            this.state.searchResults = [];
            this.state.searchDropdownOpen = false;
            return;
        }

        try {
            this.state.searchLoading = true;
            this.state.searchDropdownOpen = true;

            const results = await this.rpc('/cbm/inventory/search_product', {
                query: query,
                location_id: this.state.locationId,
                limit: 10,
            });

            this.state.searchResults = results || [];
            console.log('[INVENTORY] Search results:', this.state.searchResults.length);
            this.state.searchLoading = false;

        } catch (error) {
            console.error("[INVENTORY] Search failed:", error);
            this.state.searchLoading = false;
            this.state.searchResults = [];
        }
    }

    async onBarcodeInput(event) {
        if (event.key !== 'Enter') {
            return;
        }

        const barcode = event.target.value || '';
        if (!barcode.trim()) {
            return;
        }

        try {
            this.state.searchLoading = true;

            const result = await this.rpc('/cbm/inventory/search_barcode', {
                barcode: barcode,
                location_id: this.state.locationId,
            });

            this.state.searchLoading = false;

            if (!result.found) {
                if (this.props.showToast) {
                    this.props.showToast(_t("Produit non trouvé"), 'warning');
                }
                event.target.value = '';
                return;
            }

            // Found product - open form for this product
            this.selectProduct({
                id: result.id,
                name: result.name,
                barcode: barcode,
                uom_name: result.uom_name,
                qty_system: result.qty_system,
            });

            event.target.value = '';

        } catch (error) {
            console.error("[INVENTORY] Barcode search failed:", error);
            this.state.searchLoading = false;
        }
    }

    onSearchKeydown(event) {
        const filtered = this.state.searchResults;

        if (event.key === 'ArrowDown') {
            event.preventDefault();
            this.state.selectedResultIndex = Math.min(
                this.state.selectedResultIndex + 1,
                filtered.length - 1
            );
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            this.state.selectedResultIndex = Math.max(
                this.state.selectedResultIndex - 1,
                -1
            );
        } else if (event.key === 'Enter') {
            event.preventDefault();
            if (this.state.selectedResultIndex >= 0 &&
                this.state.selectedResultIndex < filtered.length) {
                const selected = filtered[this.state.selectedResultIndex];
                this.selectProduct(selected);
            }
        } else if (event.key === 'Escape') {
            event.preventDefault();
            this.state.searchDropdownOpen = false;
            this.state.searchQuery = '';
            this.state.searchResults = [];
            this.state.selectedResultIndex = -1;
        }
    }

    selectProduct(product) {
        // Clear search
        this.state.searchQuery = '';
        this.state.searchResults = [];
        this.state.selectedResultIndex = -1;
        this.state.searchDropdownOpen = false;

        // Open form for this product
        this.state.editingLine = {
            product_id: product.id,
            product_name: product.name,
            lot_id: null,
            lot_name: '',
            expiry_date: null,
            qty_counted: '',
            note: '',
            uom_name: product.uom_name || 'U',
            qty_system: product.qty_system || 0,
        };
        this.state.editingLineId = null;
    }

    // ============================================================
    // LINE EDIT/SAVE
    // ============================================================

    editLine(line) {
        // Copy line for editing
        this.state.editingLine = {
            product_id: line.product_id,
            product_name: line.product_name,
            lot_id: line.lot_id,
            lot_name: line.lot_name,
            expiry_date: line.expiry_date,
            qty_counted: line.qty_counted.toString(),
            note: line.note,
            uom_name: line.uom_name,
        };
        this.state.editingLineId = line.id;
    }

    onEditFormInput(field, event) {
        if (!this.state.editingLine) {
            return;
        }
        const value = event.target.value;
        this.state.editingLine[field] = value;
    }

    cancelEdit() {
        this.state.editingLine = null;
        this.state.editingLineId = null;
    }

    async saveLine() {
        if (!this.state.editingLine || !this.state.sessionId) {
            return;
        }

        const qtyCountedVal = parseFloat(this.state.editingLine.qty_counted);
        if (isNaN(qtyCountedVal) || qtyCountedVal < 0) {
            if (this.props.showToast) {
                this.props.showToast(_t("Quantité invalide"), 'warning');
            }
            return;
        }

        try {
            this.state.savingLine = true;

            const result = await this.rpc('/cbm/inventory/save_line', {
                session_id: this.state.sessionId,
                product_id: this.state.editingLine.product_id,
                lot_id: this.state.editingLine.lot_id || false,
                expiry_date: this.state.editingLine.expiry_date || false,
                qty_counted: qtyCountedVal,
                note: this.state.editingLine.note || '',
                line_id: this.state.editingLineId || false,
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur lors de l'enregistrement"), 'danger');
                }
                this.state.savingLine = false;
                return;
            }

            // Success - reload lines
            if (this.props.showToast) {
                this.props.showToast(_t("Ligne enregistrée"), 'success');
            }

            this.state.editingLine = null;
            this.state.editingLineId = null;
            this.state.savingLine = false;

            await this.loadLines();

        } catch (error) {
            console.error("[INVENTORY] Save line failed:", error);
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
            this.state.savingLine = false;
        }
    }

    // ============================================================
    // DELETE LINE
    // ============================================================

    confirmDelete(lineId) {
        this.state.deleteConfirmLineId = lineId;
    }

    cancelDelete() {
        this.state.deleteConfirmLineId = null;
    }

    async deleteLine() {
        const lineId = this.state.deleteConfirmLineId;
        if (!lineId) {
            return;
        }

        try {
            const result = await this.rpc('/cbm/inventory/delete_line', {
                line_id: lineId,
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur lors de la suppression"), 'danger');
                }
                this.state.deleteConfirmLineId = null;
                return;
            }

            if (this.props.showToast) {
                this.props.showToast(_t("Ligne supprimée"), 'success');
            }

            this.state.deleteConfirmLineId = null;
            await this.loadLines();

        } catch (error) {
            console.error("[INVENTORY] Delete line failed:", error);
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
            this.state.deleteConfirmLineId = null;
        }
    }

    // ============================================================
    // PDF PRINT & NAVIGATION
    // ============================================================

    printTeamPDF() {
        if (this.state.sessionId) {
            window.open('/cbm/inventory/team_pdf/' + this.state.sessionId, '_blank');
        }
    }

    goHome() {
        this.props.onNavigateHome();
    }
}

InventoryCount.props = {
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
};
