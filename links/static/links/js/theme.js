/**
 * LinkForge Theme Manager
 * Premium dark-only theme — always locked to dark mode.
 * No light mode, no toggling. Inspired by ChatGPT's dark theme.
 */

(function() {
    'use strict';

    const html = document.documentElement;

    /**
     * Apply dark theme to the document.
     * Always forces dark mode — no light mode available.
     */
    function applyDarkTheme() {
        html.setAttribute('data-theme', 'dark');
        document.body.classList.add('dark');

        // Dispatch event for charts and other scripts
        document.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { theme: 'dark' }
        }));
    }

    // Apply immediately (blocks rendering, so no flash of light theme)
    applyDarkTheme();

    // No toggle handlers needed — we're dark-only forever.
    // Keyboard shortcut Ctrl+T repurposed: does nothing in dark-only mode.

    console.log('%c⬛ LinkForge Dark Mode', 'color: #818cf8; font-weight: bold;');

})();
