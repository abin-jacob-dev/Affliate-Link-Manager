/**
 * LinkForge - Main Application JavaScript
 * Handles clipboard, modals, interactions, and global UI behaviors.
 * Monochrome ChatGPT-style dark theme.
 */

(function() {
    'use strict';

    // ============================================
    // Toast Notifications
    // ============================================
    const Toast = {
        container: null,

        init: function() {
            this.container = document.getElementById('toast-container');
            if (!this.container) {
                this.container = document.createElement('div');
                this.container.id = 'toast-container';
                this.container.className = 'fixed bottom-4 right-4 z-50 space-y-3';
                document.body.appendChild(this.container);
            }

            // Auto-dismiss existing toasts with transition
            document.querySelectorAll('#toast-container > [role="alert"]').forEach(toast => {
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.style.transition = 'opacity 0.2s ease, transform 0.25s ease';
                        toast.style.opacity = '0';
                        toast.style.transform = 'translateY(10px) scale(0.97)';
                        setTimeout(() => toast.remove(), 280);
                    }
                }, 4000);
            });
        },

        show: function(message, type) {
            type = type || 'info';
            
            const iconMap = {
                success: 'iconoir-check-circle',
                error: 'iconoir-xmark-circle',
                info: 'iconoir-info-circle'
            };
            
            const colorMap = {
                success: 'text-[#22C55E]',
                error: 'text-[#EF4444]',
                info: 'text-[#3B82F6]'
            };

            if (!this.container) this.init();

            const toast = document.createElement('div');
            toast.className = 'min-w-[320px] p-4 rounded-xl border bg-[#212121] shadow-lg backdrop-blur-xl';
            toast.setAttribute('role', 'alert');
            toast.style.cssText = `
                animation: slideUp 0.25s ease-out forwards;
            `;
            const iconClass = iconMap[type] || iconMap.info;
            const colorClass = colorMap[type] || colorMap.info;
            toast.innerHTML = `
                <div class="flex items-center gap-3">
                    <i class="${iconClass} ${colorClass} text-lg flex-shrink-0"></i>
                    <p class="text-sm font-medium text-[#EDEDED] flex-1">${message}</p>
                    <button onclick="dismissToast(this)" class="text-[#71717A] hover:text-[#EDEDED] transition-colors flex-shrink-0">
                        <i class="iconoir-xmark text-base"></i>
                    </button>
                </div>
            `;

            this.container.appendChild(toast);

            // Auto dismiss with smooth fade downward
            setTimeout(() => {
                toast.style.transition = 'opacity 0.2s ease, transform 0.25s ease';
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(10px) scale(0.97)';
                setTimeout(() => toast.remove(), 280);
            }, 4000);
        }
    };

    // ============================================
    // Clipboard Manager
    // ============================================
    const Clipboard = {
        copy: async function(text, showToast = true) {
            try {
                await navigator.clipboard.writeText(text);
                if (showToast) {
                    Toast.show('Copied to clipboard', 'success');
                }
                return true;
            } catch (err) {
                // Fallback for older browsers
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                try {
                    document.execCommand('copy');
                    if (showToast) {
                        Toast.show('Copied to clipboard', 'success');
                    }
                    return true;
                } catch (e) {
                    if (showToast) {
                        Toast.show('Failed to copy', 'error');
                    }
                    return false;
                } finally {
                    document.body.removeChild(textarea);
                }
            }
        }
    };

    // ============================================
    // Row Click-to-Copy Handler
    // ============================================
    function initClickableRows() {
        document.querySelectorAll('.link-row, .link-card').forEach(el => {
            el.addEventListener('click', function(e) {
                // Don't copy if clicking inside action zone or analytics link
                if (e.target.closest('.action-zone') || e.target.closest('.analytics-link') || e.target.closest('a')) return;
                
                const text = this.dataset.clipboard;
                if (!text) return;
                
                copyText(text);
            });
        });
    }

    /**
     * Copy text with polished visual feedback:
     * - Floating "Copied" badge near click position
     * - Subtle green border accent on the row
     * - Professional toast notification
     */
    function copyText(text) {
        navigator.clipboard.writeText(text).then(() => {
            window.Toast?.show('Copied to clipboard', 'success');
        }).catch(() => {
            window.Toast?.show('Failed to copy', 'error');
        });
    }

    // ============================================
    // Keyboard Shortcuts
    // ============================================
    const Shortcuts = {
        init: function() {
            document.addEventListener('keydown', function(e) {
                // Don't trigger shortcuts when typing in inputs
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                    return;
                }

                // Ctrl/Cmd + N - Create new link
                if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
                    e.preventDefault();
                    const createLink = document.querySelector('a[href*="create"]');
                    if (createLink) {
                        window.location.href = createLink.href;
                    }
                }
                
                // Ctrl/Cmd + D - Go to Dashboard
                if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
                    e.preventDefault();
                    const dashboardLink = document.querySelector('a[href*="dashboard"]');
                    if (dashboardLink) {
                        window.location.href = dashboardLink.href;
                    }
                }
            });
        }
    };

    // ============================================
    // Confirm Dialog
    // ============================================
    window.confirmDelete = function(linkId, linkName) {
        const modal = document.getElementById('delete-modal');
        if (modal) {
            document.getElementById('delete-link-name').textContent = linkName;
            document.getElementById('delete-form').action = '/delete/' + linkId + '/';
            modal.classList.remove('hidden');
            modal.style.animation = 'scaleIn 0.2s ease-out';
        }
    };

    window.closeDeleteModal = function() {
        const modal = document.getElementById('delete-modal');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.animation = '';
        }
    };

    // Close modals with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeDeleteModal();
        }
    });

    // ============================================
    // Pagination & Search Enhancements
    // (Sorting is handled server-side in dashboard inline script)
    // ============================================
    function initTableSorting() {
        // Server-side sorting is handled in the dashboard template's inline script.
        // This is a no-op placeholder to avoid errors.
    }

    // ============================================
    // Live URL Preview
    // ============================================
    function initUrlPreview() {
        const urlInput = document.getElementById('destination_url');
        const previewContainer = document.getElementById('url-preview');

        if (urlInput) {
            urlInput.addEventListener('input', function() {
                if (previewContainer) {
                    previewContainer.textContent = this.value || 'No URL entered';
                }
            });
        }
    }

    // ============================================
    // Premium Icon Animations
    // ============================================
    function initIconAnimations() {
        // Animate premium icon containers with staggered entrance
        document.querySelectorAll('.premium-icon').forEach((icon, i) => {
            if (!icon.closest('.animate-icon')) {
                icon.classList.add('premium-icon-entrance');
                icon.style.animationDelay = `${i * 0.05}s`;
            }
        });
        
        // Enhanced hover: scale + gentle glow via class-based CSS
        // The CSS handles all hover effects (scale, glow, border)
        // This JS adds the entrance animation on scroll reveal
    }

    // ============================================
    // Initialize Everything
    // ============================================
    document.addEventListener('DOMContentLoaded', function() {
        Toast.init();
        Shortcuts.init();
        initTableSorting();
        initUrlPreview();
        initClickableRows();
        initIconAnimations();

        // Copy buttons with premium visual feedback
        document.querySelectorAll('.copy-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const text = this.dataset.clipboard;
                if (text) {
                    Clipboard.copy(text, false);
                    // Monochrome visual feedback on button
                    const icon = this.querySelector('i');
                    if (icon) {
                        const originalClass = icon.className;
                        icon.className = 'iconoir-check text-[#22C55E]';
                        setTimeout(() => {
                            icon.className = originalClass;
                        }, 1500);
                    }
                    // Show toast after brief delay
                    setTimeout(() => {
                        window.Toast?.show('Copied to clipboard', 'success');
                    }, 100);
                }
            });
        });
        
        // Add subtle entrance animation to table rows
        document.querySelectorAll('.link-row').forEach((row, i) => {
            row.style.animation = `fadeIn 0.3s ease-out ${i * 0.03}s both`;
        });
        
        // Add entrance animation to mobile cards
        document.querySelectorAll('.link-card').forEach((card, i) => {
            card.style.animation = `fadeIn 0.3s ease-out ${i * 0.05}s both`;
        });
    });

    // Global dismiss toast with smooth fade-out
    window.dismissToast = function(btn) {
        const toast = btn.closest('[role="alert"]');
        if (!toast) return;
        toast.style.transition = 'opacity 0.2s ease, transform 0.25s ease';
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px) scale(0.97)';
        setTimeout(function() { toast.remove(); }, 280);
    };

    // Make utilities globally available
    window.Toast = Toast;
    window.Clipboard = Clipboard;

})();
