/** @odoo-module **/
/**
 * InventoryCount Component - Physical Inventory Counting for CBM Portal
 * Mobile-first inline editing with barcode scanner auto-add
 * - Scan barcode → auto-adds product row to table
 * - Edit qty inline → auto-saves on change
 * - All data pre-loaded from database, user only edits quantity
 */

import { Component, useState, useRef, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class InventoryCount extends Component {
    static template = "clinic_staff_portal.InventoryCount";

    setup() {
        this.rpc = useService("rpc");
        this.barcodeInputRef = useRef("barcodeInput");
        this.productSearchInputRef = useRef("productSearchInput");
        this.tableFilterRef = useRef("tableFilter");
        this.cameraVideoRef = useRef("cameraVideo");
        this._searchDebounce = null;
        this._barcodeDebounce = null;
        this._cameraDetectionInterval = null;

        this.state = useState({
            // Session
            sessionLoading: true,
            sessionFound: false,
            sessionId: null,
            sessionName: '',
            sessionState: '',
            locationId: null,
            locationName: '',
            teamId: null,
            teamName: '',
            userSubmitted: false,
            lineCount: 0,
            productCount: 0,

            // Lines
            linesLoading: false,
            lines: [],

            // Barcode input
            barcodeLoading: false,
            barcodeSearchLoading: false,
            barcodeSearchResults: [],
            selectedBarcodeIndex: -1,

            // Camera
            cameraOpen: false,
            cameraSupported: typeof BarcodeDetector !== 'undefined',

            // Product name search (dropdown)
            productSearchLoading: false,
            productSearchResults: [],
            selectedSearchIndex: -1,

            // Lot picker dropdown — fixed-position anchored to button rect
            lotPickerOpenLineId: null,
            lotPickerProduct: null,
            lotPickerLots: [],
            lotPickerLoading: false,
            lotPickerQuery: '',
            lotPickerRect: null,   // {top, left, width, flipUp}

            // Table search
            tableSearchQuery: '',

            // Inline editing
            savingLineId: null,
            editingExpiryLineId: null,
            editingExpiryValue: '',

            // Done modal
            doneModalOpen: false,
            submittingFinal: false,
            recounting: false,

            // Delete confirmation
            deleteConfirmLineId: null,
        });

        // Attach camera stream after OWL renders the video element
        useEffect(() => {
            if (this.state.cameraOpen && this._pendingStream) {
                const video = this.cameraVideoRef.el;
                if (video) {
                    const stream = this._pendingStream;
                    this._pendingStream = null;
                    video.srcObject = stream;
                    this._cameraStream = stream;
                    video.play().then(() => {
                        this._startBarcodeDetection(video);
                    }).catch(err => {
                        console.error("[INVENTORY] video.play() rejected:", err);
                        this.closeCamera();
                    });
                }
            }
        }, () => [this.state.cameraOpen]);

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
            this.state.sessionState = result.session_state || 'active';
            this.state.locationId = result.location_id;
            this.state.locationName = result.location_name;
            this.state.teamId = result.team_id;
            this.state.teamName = result.team_name;
            this.state.userSubmitted = result.user_submitted || false;
            this.state.lineCount = result.line_count || 0;
            this.state.productCount = result.product_count || 0;

            // Only load lines and focus input if user hasn't submitted
            if (!this.state.userSubmitted) {
                await this.loadLines();
            }
            this.state.sessionLoading = false;

            if (!this.state.userSubmitted) {
                setTimeout(() => {
                    if (this.barcodeInputRef.el) {
                        this.barcodeInputRef.el.focus();
                    }
                }, 100);
            }

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
        if (!this.state.sessionId) return;
        try {
            this.state.linesLoading = true;
            const result = await this.rpc('/cbm/inventory/get_lines', {
                session_id: this.state.sessionId,
            });
            this.state.lines = result || [];
            this.state.linesLoading = false;
        } catch (error) {
            console.error("[INVENTORY] Failed to load lines:", error);
            this.state.linesLoading = false;
        }
    }

    // ============================================================
    // BARCODE / LOT SEARCH (with dropdown)
    // ============================================================

    onBarcodeInputChange(event) {
        const value = event.target.value || '';
        if (this._barcodeDebounce) {
            clearTimeout(this._barcodeDebounce);
        }

        // Clear dropdown if empty
        if (!value.trim() || value.length < 2) {
            this.state.barcodeSearchResults = [];
            this.state.selectedBarcodeIndex = -1;
            return;
        }

        // Debounce search for lot/barcode dropdown
        this._barcodeDebounce = setTimeout(() => {
            this._doBarcodeSearch(value.trim());
        }, 300);
    }

    async _doBarcodeSearch(query) {
        try {
            this.state.barcodeSearchLoading = true;

            // Search both by barcode (product) and by lot name
            const [barcodeResults, lotResults] = await Promise.all([
                this.rpc('/cbm/inventory/search_product', {
                    query: query,
                    location_id: this.state.locationId,
                    limit: 5,
                }),
                this.rpc('/cbm/inventory/search_lot', {
                    lot_name: query,
                    location_id: this.state.locationId,
                    limit: 10,
                }),
            ]);

            // Merge results: lots first (more specific), then products without lots
            const merged = [];
            const seenKeys = new Set();

            for (const item of (lotResults || [])) {
                const key = item.id + '_' + (item.lot_id || 0);
                if (!seenKeys.has(key)) {
                    seenKeys.add(key);
                    merged.push(item);
                }
            }

            for (const item of (barcodeResults || [])) {
                // Only add if not already covered by lot results
                const key = item.id + '_0';
                if (!seenKeys.has(key)) {
                    seenKeys.add(key);
                    merged.push(item);
                }
            }

            this.state.barcodeSearchResults = merged;
            this.state.selectedBarcodeIndex = -1;
            this.state.barcodeSearchLoading = false;

        } catch (error) {
            console.error("[INVENTORY] Barcode search failed:", error);
            this.state.barcodeSearchLoading = false;
        }
    }

    onBarcodeKeydown(event) {
        const results = this.state.barcodeSearchResults;

        if (event.key === 'ArrowDown' && results.length) {
            event.preventDefault();
            this.state.selectedBarcodeIndex = Math.min(
                this.state.selectedBarcodeIndex + 1,
                results.length - 1
            );
        } else if (event.key === 'ArrowUp' && results.length) {
            event.preventDefault();
            this.state.selectedBarcodeIndex = Math.max(
                this.state.selectedBarcodeIndex - 1, 0
            );
        } else if (event.key === 'Enter') {
            event.preventDefault();
            const idx = this.state.selectedBarcodeIndex;
            if (idx >= 0 && idx < results.length) {
                this.selectBarcodeResult(results[idx]);
            } else if (results.length === 1) {
                // Auto-select single result on Enter
                this.selectBarcodeResult(results[0]);
            } else {
                // Fallback: exact barcode match via shared endpoint
                this._exactBarcodeSearch(event.target.value);
            }
        } else if (event.key === 'Escape') {
            this.state.barcodeSearchResults = [];
            this.state.selectedBarcodeIndex = -1;
        }
    }

    async _exactBarcodeSearch(barcode) {
        if (!barcode || !barcode.trim()) return;
        try {
            this.state.barcodeLoading = true;
            const result = await this.rpc('/cbm/search_barcode', {
                barcode: barcode.trim(),
                location_id: this.state.locationId,
            });
            this.state.barcodeLoading = false;

            if (!result.found) {
                if (this.props.showToast) {
                    this.props.showToast(_t("Produit non trouvé"), 'warning');
                }
                return;
            }

            await this._addProductLine({
                id: result.id,
                name: result.name,
                barcode: result.barcode,
                uom_name: result.uom_name,
                lot_id: result.lot_id,
                lot_name: result.lot_name || '',
                expiry_date: false,
                tracking: 'none',  // Already resolved by barcode
            });
            this._clearBarcodeInput();

        } catch (error) {
            console.error("[INVENTORY] Exact barcode search failed:", error);
            this.state.barcodeLoading = false;
        }
    }

    async selectBarcodeResult(item) {
        this.state.barcodeSearchResults = [];
        this.state.selectedBarcodeIndex = -1;

        // Always add directly — lot assigned inline from the table row
        await this._addProductLine({
            id: item.id,
            name: item.name,
            uom_name: item.uom_name,
            lot_id: item.lot_id || false,
            lot_name: item.lot_name || '',
            expiry_date: item.expiry_date || false,
            tracking: item.tracking || 'none',
        });
        this._clearBarcodeInput();
    }

    _clearBarcodeInput() {
        if (this.barcodeInputRef.el) {
            this.barcodeInputRef.el.value = '';
            setTimeout(() => this.barcodeInputRef.el.focus(), 100);
        }
    }

    // ============================================================
    // PRODUCT NAME SEARCH (with dropdown)
    // ============================================================

    onProductSearch(event) {
        const query = event.target.value;
        if (this._searchDebounce) {
            clearTimeout(this._searchDebounce);
        }
        if (!query || query.length < 2) {
            this.state.productSearchResults = [];
            this.state.selectedSearchIndex = -1;
            return;
        }
        this._searchDebounce = setTimeout(() => {
            this._doProductSearch(query);
        }, 300);
    }

    async _doProductSearch(query) {
        try {
            this.state.productSearchLoading = true;
            const results = await this.rpc('/cbm/inventory/search_product', {
                query: query,
                location_id: this.state.locationId,
                limit: 10,
            });
            this.state.productSearchResults = results || [];
            this.state.selectedSearchIndex = -1;
            this.state.productSearchLoading = false;
        } catch (error) {
            console.error("[INVENTORY] Product search failed:", error);
            this.state.productSearchLoading = false;
        }
    }

    onProductSearchKeydown(event) {
        const results = this.state.productSearchResults;
        if (!results.length) return;

        if (event.key === 'ArrowDown') {
            event.preventDefault();
            this.state.selectedSearchIndex = Math.min(
                this.state.selectedSearchIndex + 1,
                results.length - 1
            );
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            this.state.selectedSearchIndex = Math.max(
                this.state.selectedSearchIndex - 1, 0
            );
        } else if (event.key === 'Enter') {
            event.preventDefault();
            const idx = this.state.selectedSearchIndex;
            if (idx >= 0 && idx < results.length) {
                this.selectSearchProduct(results[idx]);
            }
        } else if (event.key === 'Escape') {
            this.state.productSearchResults = [];
            this.state.selectedSearchIndex = -1;
        }
    }

    async selectSearchProduct(product) {
        this.state.productSearchResults = [];
        this.state.selectedSearchIndex = -1;
        if (this.productSearchInputRef.el) {
            this.productSearchInputRef.el.value = '';
        }

        // Always add directly — lot is assigned inline from the table row
        await this._addProductLine({
            id: product.id,
            name: product.name,
            uom_name: product.uom_name,
            lot_id: false,
            lot_name: '',
            expiry_date: false,
            tracking: product.tracking || 'none',
        });
    }

    // ============================================================
    // LOT PICKER DROPDOWN (used for both new lines and editing existing)
    // ============================================================

    async _openLotPicker(product) {
        try {
            this.state.lotPickerProduct = product;
            this.state.lotPickerLots = [];
            this.state.lotPickerLoading = true;
            this.state.lotPickerOpenLineId = 'new';
            this.state.lotPickerQuery = '';

            const lots = await this.rpc('/cbm/inventory/get_product_lots', {
                product_id: product.id,
                location_id: this.state.locationId,
            });

            this.state.lotPickerLots = lots || [];
            this.state.lotPickerLoading = false;

        } catch (error) {
            console.error("[INVENTORY] Failed to load lots:", error);
            this.state.lotPickerOpenLineId = null;
            this.state.lotPickerLoading = false;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur lors du chargement des lots"), 'danger');
            }
        }
    }

    async startEditLot(line, event) {
        if (event) event.stopPropagation();

        // Toggle off if already open for this line
        if (this.state.lotPickerOpenLineId === line.id) {
            this.closeLotPicker();
            return;
        }

        // Capture button position for fixed-position dropdown
        let rect = null;
        if (event && event.currentTarget) {
            const btnRect = event.currentTarget.getBoundingClientRect();
            const menuHeight = 280; // max-height of menu
            const spaceBelow = window.innerHeight - btnRect.bottom;
            const flipUp = spaceBelow < menuHeight && btnRect.top > menuHeight;
            rect = {
                top: flipUp ? btnRect.top : btnRect.bottom,
                left: btnRect.left,
                width: Math.max(btnRect.width, 260),
                flipUp,
            };
        }

        try {
            this.state.lotPickerProduct = {
                id: line.product_id,
                name: line.product_name,
                uom_name: line.uom_name,
            };
            this.state.lotPickerLots = [];
            this.state.lotPickerLoading = true;
            this.state.lotPickerOpenLineId = line.id;
            this.state.lotPickerQuery = '';
            this.state.lotPickerRect = rect;

            const lots = await this.rpc('/cbm/inventory/get_product_lots', {
                product_id: line.product_id,
                location_id: this.state.locationId,
            });

            this.state.lotPickerLots = lots || [];
            this.state.lotPickerLoading = false;

        } catch (error) {
            console.error("[INVENTORY] Failed to load lots for edit:", error);
            this.state.lotPickerOpenLineId = null;
            this.state.lotPickerLoading = false;
            this.state.lotPickerRect = null;
        }
    }

    closeLotPicker() {
        this.state.lotPickerOpenLineId = null;
        this.state.lotPickerProduct = null;
        this.state.lotPickerLots = [];
        this.state.lotPickerLoading = false;
        this.state.lotPickerQuery = '';
        this.state.lotPickerRect = null;
    }

    onLotPickerSearch(event) {
        this.state.lotPickerQuery = (event.target.value || '').toLowerCase();
    }

    getFilteredLots() {
        if (!this.state.lotPickerQuery) {
            return this.state.lotPickerLots;
        }
        const q = this.state.lotPickerQuery;
        return this.state.lotPickerLots.filter(lot => {
            return (lot.lot_name || '').toLowerCase().includes(q)
                || (lot.expiry_date || '').toLowerCase().includes(q);
        });
    }

    async selectLot(lot) {
        const product = this.state.lotPickerProduct;
        const editLineId = this.state.lotPickerOpenLineId;
        if (!product) return;

        this.closeLotPicker();

        if (editLineId && editLineId !== 'new') {
            // Edit mode — update existing line's lot
            const line = this.state.lines.find(l => l.id === editLineId);
            if (!line) return;

            try {
                const result = await this.rpc('/cbm/inventory/save_line', {
                    session_id: this.state.sessionId,
                    product_id: line.product_id,
                    lot_id: lot.lot_id || false,
                    expiry_date: lot.expiry_date || line.expiry_date || false,
                    qty_counted: line.qty_counted,
                    note: line.note || '',
                    line_id: editLineId,
                });

                if (result.success) {
                    await this.loadLines();
                }
            } catch (error) {
                console.error("[INVENTORY] Update lot failed:", error);
            }
        } else {
            // New line mode
            await this._addProductLine({
                id: product.id,
                name: product.name,
                uom_name: product.uom_name,
                lot_id: lot.lot_id || false,
                lot_name: lot.lot_name || '',
                expiry_date: lot.expiry_date || false,
                tracking: product.tracking || 'lot',
            });
        }
    }

    // ============================================================
    // ADD PRODUCT LINE (shared by all search flows)
    // ============================================================

    async _addProductLine(product) {
        try {
            const result = await this.rpc('/cbm/inventory/save_line', {
                session_id: this.state.sessionId,
                product_id: product.id,
                lot_id: product.lot_id || false,
                expiry_date: product.expiry_date || false,
                qty_counted: 1,
                note: '',
                line_id: false,
            });

            if (!result.success) {
                console.error("[INVENTORY] save_line rejected:", result.error);
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur lors de l'ajout"), 'danger');
                }
                return;
            }

            await this.loadLines();

        } catch (error) {
            console.error("[INVENTORY] Add line failed (exception):", error);
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
        }
    }

    // ============================================================
    // INLINE QTY EDITING (always-visible input, no click-to-edit)
    // ============================================================

    async onQtyChanged(lineId, rawValue) {
        const newQty = parseFloat(rawValue);
        if (isNaN(newQty) || newQty < 0) {
            if (this.props.showToast) {
                this.props.showToast(_t("Quantité invalide"), 'warning');
            }
            return;
        }

        const line = this.state.lines.find(l => l.id === lineId);
        if (!line) return;

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
                    this.props.showToast(result.error || _t("Erreur"), 'danger');
                }
            } else {
                // Reload lines to ensure OWL reactive proxy reflects the change
                await this.loadLines();
            }

            this.state.savingLineId = null;

        } catch (error) {
            console.error("[INVENTORY] Save qty failed:", error);
            this.state.savingLineId = null;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
        }
    }

    // ============================================================
    // INLINE EXPIRY DATE EDITING
    // ============================================================

    startEditExpiry(lineId, currentValue) {
        this.state.editingExpiryLineId = lineId;
        this.state.editingExpiryValue = currentValue || '';
    }

    onExpiryChange(event) {
        this.state.editingExpiryValue = event.target.value;
    }

    async saveExpiry(lineId) {
        const line = this.state.lines.find(l => l.id === lineId);
        if (!line) {
            this.state.editingExpiryLineId = null;
            return;
        }

        const newExpiry = this.state.editingExpiryValue || false;

        try {
            const result = await this.rpc('/cbm/inventory/save_line', {
                session_id: this.state.sessionId,
                product_id: line.product_id,
                lot_id: line.lot_id || false,
                expiry_date: newExpiry,
                qty_counted: line.qty_counted,
                note: line.note || '',
                line_id: lineId,
            });

            if (result.success) {
                await this.loadLines();
            }

        } catch (error) {
            console.error("[INVENTORY] Save expiry failed:", error);
        }

        this.state.editingExpiryLineId = null;
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
        if (!lineId) return;

        try {
            const result = await this.rpc('/cbm/inventory/delete_line', {
                line_id: lineId,
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur"), 'danger');
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
            this.state.deleteConfirmLineId = null;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
        }
    }

    // ============================================================
    // PDF & NAVIGATION
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
    // CAMERA BARCODE SCANNING (native BarcodeDetector API)
    // ============================================================

    async openCamera() {
        // Guard: prevent double-tap creating orphaned stream
        if (this._cameraStream) return;

        if (!this.state.cameraSupported) {
            if (this.props.showToast) {
                this.props.showToast(_t("Scan caméra non supporté sur ce navigateur (utilisez Chrome)"), 'warning');
            }
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
                audio: false,
            });

            // Store stream temporarily; useEffect will attach it once video element is rendered
            this._pendingStream = stream;
            this.state.cameraOpen = true;  // Triggers OWL render → useEffect fires

        } catch (error) {
            console.error("[INVENTORY] Camera access error:", error);
            this.state.cameraOpen = false;
            if (this.props.showToast) {
                // TypeError on non-HTTPS means the API is blocked by browser security policy
                const isHttps = window.location.protocol === 'https:' || window.location.hostname === 'localhost';
                if (!isHttps && error instanceof TypeError) {
                    this.props.showToast(_t("Caméra nécessite HTTPS"), 'danger');
                } else {
                    this.props.showToast(_t("Accès caméra refusé"), 'warning');
                }
            }
        }
    }

    closeCamera() {
        // Stop stream tracks
        if (this._cameraStream) {
            this._cameraStream.getTracks().forEach(track => track.stop());
            this._cameraStream = null;
        }
        // Stop detection loop
        if (this._cameraDetectionInterval) {
            clearInterval(this._cameraDetectionInterval);
            this._cameraDetectionInterval = null;
        }
        this.state.cameraOpen = false;
        // Refocus barcode input
        setTimeout(() => {
            if (this.barcodeInputRef.el) this.barcodeInputRef.el.focus();
        }, 100);
    }

    _startBarcodeDetection(video) {
        const detector = new BarcodeDetector({
            formats: ['qr_code', 'code_128', 'ean_13', 'ean_8', 'code_39', 'code_93', 'itf', 'data_matrix'],
        });

        let detecting = false;  // Guard against overlapping async callbacks
        this._cameraDetectionInterval = setInterval(async () => {
            if (!this.state.cameraOpen || !video.videoWidth) return;
            if (detecting) return;
            detecting = true;
            try {
                const barcodes = await detector.detect(video);
                if (barcodes.length > 0 && this.state.cameraOpen) {
                    const raw = barcodes[0].rawValue;
                    this.closeCamera();
                    await this._exactBarcodeSearch(raw);
                }
            } catch (error) {
                // Detection errors are expected on blank frames — ignore
            } finally {
                detecting = false;
            }
        }, 400);
    }

    // ============================================================
    // DONE MODAL
    // ============================================================

    openDoneModal() {
        this.state.doneModalOpen = true;
    }

    cancelDoneModal() {
        this.state.doneModalOpen = false;
    }

    async submitFinal() {
        if (!this.state.sessionId) return;
        try {
            this.state.submittingFinal = true;
            const result = await this.rpc('/cbm/inventory/submit', {
                session_id: this.state.sessionId,
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur"), 'danger');
                }
                this.state.submittingFinal = false;
                return;
            }

            if (this.props.showToast) {
                this.props.showToast(_t("Comptage enregistré avec succès"), 'success');
            }

            // Transition to status page instead of navigating home
            this.state.submittingFinal = false;
            this.state.doneModalOpen = false;
            this.state.userSubmitted = true;
            this.state.lineCount = this.state.lines.length;
            this.state.productCount = new Set(this.state.lines.map(l => l.product_id)).size;

            if (result.all_submitted) {
                this.state.sessionState = 'pending_approval';
            }

        } catch (error) {
            console.error("[INVENTORY] Submit failed:", error);
            this.state.submittingFinal = false;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
        }
    }

    async startRecount() {
        if (!this.state.sessionId) return;
        try {
            this.state.recounting = true;
            const result = await this.rpc('/cbm/inventory/recount', {
                session_id: this.state.sessionId,
            });

            if (!result.success) {
                if (this.props.showToast) {
                    this.props.showToast(result.error || _t("Erreur"), 'danger');
                }
                this.state.recounting = false;
                return;
            }

            if (this.props.showToast) {
                this.props.showToast(_t("Comptage réinitialisé"), 'success');
            }

            this.state.lines = [];
            this.state.recounting = false;
            this.state.doneModalOpen = false;
            await this.loadLines();

            setTimeout(() => {
                if (this.barcodeInputRef.el) this.barcodeInputRef.el.focus();
            }, 100);

        } catch (error) {
            console.error("[INVENTORY] Recount failed:", error);
            this.state.recounting = false;
            if (this.props.showToast) {
                this.props.showToast(_t("Erreur de connexion"), 'danger');
            }
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
        if (this.tableFilterRef.el) {
            this.tableFilterRef.el.value = '';
        }
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
            return productName.includes(query) || lotName.includes(query) || barcode.includes(query);
        });
    }
}

InventoryCount.props = {
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
};
