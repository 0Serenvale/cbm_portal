/** @odoo-module **/
/**
 * InventoryCount Component - Physical Inventory Counting for CBM Portal
 * Mobile-first inline editing with barcode scanner auto-add
 * - Scan barcode → auto-adds product row to table
 * - Edit qty inline → auto-saves on change
 * - All data pre-loaded from database, user only edits quantity
 */

import { Component, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class InventoryCount extends Component {
    static template = "clinic_staff_portal.InventoryCount";

    setup() {
        this.rpc = useService("rpc");
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

            // Lines (all data pre-loaded from DB)
            linesLoading: false,
            lines: [],  // [{id, product_id, product_name, lot_id, lot_name, expiry_date, qty_counted, qty_system, uom_name, barcode}]

            // Barcode input & camera
            barcodeLoading: false,
            cameraOpen: false,
            cameraStream: null,

            // Lot disambiguation (multiple products with same lot)
            lotSearchResults: [],
            lotSearchModalOpen: false,
            selectedLotProduct: null,

            // Table search
            tableSearchQuery: '',

            // Inline editing state
            editingLineId: null,  // line_id currently being edited
            editingLineQty: '',   // temp qty value during edit
            savingLineId: null,   // line_id being saved

            // Delete confirmation
            deleteConfirmLineId: null,
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

            // Focus barcode input
            setTimeout(() => {
                if (this.barcodeInputRef.el) {
                    this.barcodeInputRef.el.focus();
                }
            }, 100);

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
    // BARCODE SCANNING
    // ============================================================

    onBarcodeInputChange(event) {
        // Allow manual typing combined with hardware scanners
        // (some mobile scanners send input without Enter key)
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
            this.state.barcodeLoading = true;

            const result = await this.rpc('/cbm/inventory/search_barcode', {
                barcode: barcode,
                location_id: this.state.locationId,
            });

            this.state.barcodeLoading = false;

            if (!result.found) {
                if (this.props.showToast) {
                    this.props.showToast(_t("Produit non trouvé"), 'warning');
                }
                event.target.value = '';
                // Re-focus for next scan
                setTimeout(() => event.target.focus(), 100);
                return;
            }

            // Each scan creates a NEW row (no deduplication)
            // User can delete accidental double-scans manually
            // This allows staff to record exact counting flow
            await this.addLineFromBarcode(result);

            event.target.value = '';
            // Re-focus for next scan
            setTimeout(() => event.target.focus(), 100);

        } catch (error) {
            console.error("[INVENTORY] Barcode scan failed:", error);
            this.state.barcodeLoading = false;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur lors du scan"), 'danger');
            }
        }
    }

    async addLineFromBarcode(product) {
        // Create new line with qty=1
        try {
            const result = await this.rpc('/cbm/inventory/save_line', {
                session_id: this.state.sessionId,
                product_id: product.id,
                lot_id: product.lot_id || false,
                expiry_date: product.expiry_date || false,
                qty_counted: 1,
                note: '',
                line_id: false,  // Create new
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur lors de l'ajout"), 'danger');
                }
                return;
            }

            // Reload lines to get new row
            await this.loadLines();

            // Auto-focus qty field of newly added product
            setTimeout(() => {
                const newLine = this.state.lines.find(l => l.product_id === product.id);
                if (newLine) {
                    this.onQtyStartEdit(newLine.id, newLine.qty_counted);
                }
            }, 50);

        } catch (error) {
            console.error("[INVENTORY] Add line from barcode failed:", error);
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
        }
    }

    // ============================================================
    // INLINE QTY EDITING & AUTO-SAVE
    // ============================================================

    onQtyStartEdit(lineId, currentQty) {
        this.state.editingLineId = lineId;
        this.state.editingLineQty = currentQty.toString();

        // Auto-focus input after next render
        setTimeout(() => {
            const input = document.querySelector(`input[data-line-id="${lineId}"]`);
            if (input) {
                input.focus();
                input.select();
            }
        }, 10);
    }

    onQtyChange(event) {
        this.state.editingLineQty = event.target.value;
    }

    async onQtyBlur(lineId) {
        // Save when user leaves qty field
        await this.saveQtyInline(lineId);
    }

    async saveQtyInline(lineId) {
        if (!lineId || !this.state.sessionId) {
            this.state.editingLineId = null;
            return;
        }

        const line = this.state.lines.find(l => l.id === lineId);
        if (!line) {
            this.state.editingLineId = null;
            return;
        }

        const newQty = parseFloat(this.state.editingLineQty);
        if (isNaN(newQty) || newQty < 0) {
            if (this.props.showToast) {
                this.props.showToast(_t("Quantité invalide"), 'warning');
            }
            this.state.editingLineId = null;
            return;
        }

        try {
            this.state.savingLineId = lineId;

            const result = await this.rpc('/cbm/inventory/save_line', {
                session_id: this.state.sessionId,
                product_id: line.product_id,
                lot_id: line.lot_id || false,
                expiry_date: line.expiry_date || false,
                qty_counted: newQty,
                note: line.note || '',
                line_id: lineId,
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur lors de l'enregistrement"), 'danger');
                }
                this.state.savingLineId = null;
                this.state.editingLineId = null;
                return;
            }

            console.log('[INVENTORY] Line saved:', lineId, 'qty=', newQty);

            // Update local state
            line.qty_counted = newQty;

            // Close edit mode
            this.state.editingLineId = null;
            this.state.savingLineId = null;

            // Keep focus on barcode for next scan
            if (this.barcodeInputRef.el) {
                this.barcodeInputRef.el.focus();
            }

        } catch (error) {
            console.error("[INVENTORY] Save qty failed:", error);
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
            this.state.savingLineId = null;
            this.state.editingLineId = null;
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

    // ============================================================
    // MOBILE CAMERA BARCODE SCANNING
    // ============================================================

    async openCamera() {
        try {
            this.state.cameraOpen = true;

            // Request camera access
            const constraints = {
                video: {
                    facingMode: 'environment',  // Back camera
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
                audio: false,
            };

            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            this.state.cameraStream = stream;

            // Start camera in video element
            setTimeout(() => {
                const video = document.querySelector('.cbm_camera_video');
                if (video) {
                    video.srcObject = stream;
                    // Start barcode detection loop
                    this.startBarcodeDetection(video);
                }
            }, 100);

        } catch (error) {
            console.error("[INVENTORY] Camera access error:", error);
            if (this.props.showToast) {
                if (error.name === 'NotAllowedError') {
                    this.props.showToast(_t("Accès à la caméra refusé"), 'danger');
                } else if (error.name === 'NotFoundError') {
                    this.props.showToast(_t("Caméra non trouvée"), 'danger');
                } else {
                    this.props.showToast(_t("Erreur caméra"), 'danger');
                }
            }
            this.state.cameraOpen = false;
        }
    }

    closeCamera() {
        if (this.state.cameraStream) {
            this.state.cameraStream.getTracks().forEach(track => track.stop());
            this.state.cameraStream = null;
        }
        this.state.cameraOpen = false;
        this.cameraDetectionInterval = null;

        // Re-focus barcode input
        if (this.barcodeInputRef.el) {
            setTimeout(() => this.barcodeInputRef.el.focus(), 100);
        }
    }

    startBarcodeDetection(video) {
        // Simple barcode detection using canvas + decoder
        // For production, use a library like QuaggaJS or jsQR
        // This is a placeholder that shows the pattern
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        this.cameraDetectionInterval = setInterval(() => {
            if (!this.state.cameraOpen || !video.videoWidth) {
                return;
            }

            try {
                // Draw video frame to canvas
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                ctx.drawImage(video, 0, 0);

                // Get image data for barcode detection
                // TODO: Integrate with barcode library (QuaggaJS, jsQR, or ZXing)
                // For now, just show camera is running
                console.log('[INVENTORY] Camera scanning...', {
                    width: canvas.width,
                    height: canvas.height,
                });

            } catch (error) {
                console.error("[INVENTORY] Barcode detection error:", error);
            }
        }, 500);
    }

    // Process barcode from camera (called by barcode library)
    async processCameraBarcode(barcode) {
        if (!barcode || !this.state.cameraOpen) {
            return;
        }

        console.log('[INVENTORY] Camera barcode detected:', barcode);

        // Close camera
        this.closeCamera();

        // Process as regular barcode scan
        this.state.barcodeLoading = true;

        try {
            const result = await this.rpc('/cbm/inventory/search_barcode', {
                barcode: barcode,
                location_id: this.state.locationId,
            });

            this.state.barcodeLoading = false;

            if (!result.found) {
                if (this.props.showToast) {
                    this.props.showToast(_t("Produit non trouvé"), 'warning');
                }
                return;
            }

            await this.addLineFromBarcode(result);

        } catch (error) {
            console.error("[INVENTORY] Camera barcode processing failed:", error);
            this.state.barcodeLoading = false;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur lors du scan caméra"), 'danger');
            }
        }
    }

    // ============================================================
    // LOT NUMBER SEARCH (Multiple Products Same Lot)
    // ============================================================

    async searchByLot(lotName) {
        if (!lotName || !lotName.trim()) {
            return;
        }

        try {
            this.state.barcodeLoading = true;

            const results = await this.rpc('/cbm/inventory/search_lot', {
                lot_name: lotName.trim(),
                location_id: this.state.locationId,
            });

            this.state.barcodeLoading = false;

            if (!results || results.length === 0) {
                if (this.props.showToast) {
                    this.props.showToast(_t("Lot non trouvé"), 'warning');
                }
                return;
            }

            if (results.length === 1) {
                // Only one product with this lot - add directly
                await this.addLineFromBarcode(results[0]);
            } else {
                // Multiple products with same lot - show disambiguation modal
                this.state.lotSearchResults = results;
                this.state.lotSearchModalOpen = true;
                console.log('[INVENTORY] Found', results.length, 'products with lot', lotName);
            }

        } catch (error) {
            console.error("[INVENTORY] Lot search failed:", error);
            this.state.barcodeLoading = false;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur lors de la recherche"), 'danger');
            }
        }
    }

    selectLotProduct(product) {
        this.state.selectedLotProduct = product;
    }

    async confirmLotSelection() {
        if (!this.state.selectedLotProduct) {
            return;
        }

        const product = this.state.selectedLotProduct;
        this.closeLotSearchModal();

        await this.addLineFromBarcode(product);
    }

    closeLotSearchModal() {
        this.state.lotSearchModalOpen = false;
        this.state.lotSearchResults = [];
        this.state.selectedLotProduct = null;

        // Re-focus barcode input
        if (this.barcodeInputRef.el) {
            setTimeout(() => this.barcodeInputRef.el.focus(), 100);
        }
    }

    // ============================================================
    // TABLE SEARCH
    // ============================================================

    onTableSearchChange(event) {
        this.state.tableSearchQuery = event.target.value.toLowerCase();
    }

    clearTableSearch() {
        this.state.tableSearchQuery = '';
    }

    getFilteredLines() {
        if (!this.state.tableSearchQuery) {
            return this.state.lines;
        }

        const query = this.state.tableSearchQuery;
        return this.state.lines.filter(line => {
            const productName = (line.product_name || '').toLowerCase();
            const lotName = (line.lot_name || '').toLowerCase();
            const barcode = (line.barcode || '').toLowerCase();

            return (
                productName.includes(query) ||
                lotName.includes(query) ||
                barcode.includes(query)
            );
        });
    }
}

InventoryCount.props = {
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
};
