/** @odoo-module **/
/**
 * DocumentsViewer Component - Extracted from CBMKiosk
 * Handles documents browsing, PDF viewer, acknowledgement, and compliance lock.
 */

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class DocumentsViewer extends Component {
    static template = "clinic_staff_portal.DocumentsViewer";

    setup() {
        this.rpc = useService("rpc");

        this.state = useState({
            documents: {
                categories: [],
                is_admin: false,
                total_count: 0,
            },
            documentsLoading: false,
            pdfViewerOpen: false,
            pdfViewerDoc: null,
            // Type-to-confirm acknowledgement
            ackTypedName: '',
            ackExpectedName: '',
            ackError: '',
            // Compliance lock
            isComplianceLocked: false,
        });

        onWillStart(async () => {
            await this.checkPendingAcknowledgements();
        });

        onWillUpdateProps((nextProps) => {
            if (nextProps.currentState === 'documents' && this.props.currentState !== 'documents') {
                this.loadDocuments();
            }
        });
    }

    // ==================== DOCUMENTS ====================

    async loadDocuments() {
        this.state.documentsLoading = true;
        try {
            const result = await this.rpc('/cbm/documents/list', {});
            this.state.documents = result;
        } catch (error) {
            this.showToast(_t("Erreur chargement documents"), 'danger');
            this.state.documents = { categories: [], is_admin: false, total_count: 0 };
        }
        this.state.documentsLoading = false;
    }

    openDocument(doc) {
        if (doc.resource_type === 'pdf' && doc.url) {
            this.state.pdfViewerDoc = doc;
            this.state.pdfViewerOpen = true;
        } else if (doc.url) {
            window.open(doc.url, '_blank');
        }
    }

    closePdfViewer() {
        if (this.state.isComplianceLocked && this.state.pdfViewerDoc?.requires_acknowledgement && !this.state.pdfViewerDoc?.is_acknowledged) {
            this.showToast(_t("Vous devez signer ce document pour continuer"), 'warning');
            return;
        }
        this.state.pdfViewerOpen = false;
        this.state.pdfViewerDoc = null;
        this.state.ackTypedName = '';
        this.state.ackError = '';
    }

    async acknowledgeDocument(doc) {
        const typedName = (this.state.ackTypedName || '').trim();
        if (!typedName) {
            this.state.ackError = _t("Veuillez saisir votre nom complet.");
            return;
        }
        if (typedName.toLowerCase() !== this.state.ackExpectedName.toLowerCase()) {
            this.state.ackError = _t("Le nom saisi ne correspond pas.");
            return;
        }
        this.state.ackError = '';
        try {
            const result = await this.rpc('/cbm/documents/acknowledge', {
                document_id: doc.id,
                typed_name: typedName,
                user_agent: navigator.userAgent || '',
            });
            if (result.success) {
                this.state.ackTypedName = '';
                this.state.ackError = '';
                this.closePdfViewer();
                this.showToast(_t("Document accepté"), 'success');
                await this.checkPendingAcknowledgements();
            } else {
                this.state.ackError = result.error || _t("Erreur");
            }
        } catch (error) {
            this.state.ackError = _t("Erreur lors de l'acceptation");
        }
    }

    onAckNameInput(ev) {
        this.state.ackTypedName = ev.target.value;
        this.state.ackError = '';
    }

    async checkPendingAcknowledgements() {
        try {
            const config = await this.rpc('/cbm/session/config', {});
            if (config) {
                this.state.isComplianceLocked = config.is_compliance_locked || false;
                this.state.ackExpectedName = config.user_display_name || '';
                this.props.onComplianceLockChange(this.state.isComplianceLocked);
            }

            const result = await this.rpc('/cbm/documents/list', {});
            if (!result || !result.categories) return;
            for (const cat of result.categories) {
                for (const doc of cat.documents) {
                    if (doc.requires_acknowledgement && !doc.is_acknowledged && doc.is_targeted && doc.resource_type === 'pdf' && doc.url) {
                        this.state.pdfViewerDoc = doc;
                        this.state.pdfViewerOpen = true;
                        this.state.ackTypedName = '';
                        this.state.ackError = '';
                        return;
                    }
                }
            }
            this.state.isComplianceLocked = false;
            this.props.onComplianceLockChange(false);
        } catch (error) {
            console.warn("Failed to check pending acknowledgements", error);
        }
    }

    // ==================== HELPERS ====================

    showToast(message, type) {
        if (this.props.showToast) {
            this.props.showToast(message, type);
        }
    }

    goHome() {
        this.props.onNavigateHome();
    }

}

DocumentsViewer.props = {
    currentState: String,
    onNavigateHome: Function,
    showToast: { type: Function, optional: true },
    onComplianceLockChange: { type: Function, optional: true },
};
