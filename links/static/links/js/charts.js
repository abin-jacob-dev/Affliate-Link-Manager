/**
 * LinkForge - Chart.js Integration
 * Monochrome dark chart theme — always dark mode.
 * Uses grayscale/white color scheme matching the ChatGPT-style UI.
 */

(function() {
    'use strict';

    // Monochrome color scheme
    const COLORS = {
        primary: '#A1A1AA',        // zinc-400
        primaryLight: '#D4D4D8',   // zinc-300
        primaryBg: 'rgba(161, 161, 170, 0.08)',
        pointBorder: '#0A0A0A',    // match bg-primary
        gray: '#71717A',           // zinc-500
        grayLighter: '#52525B',    // zinc-600
    };

    // Chart accent palette (subdued grays)
    const CHART_ACCENTS = [
        '#A1A1AA',  // zinc-400
        '#D4D4D8',  // zinc-300
        '#71717A',  // zinc-500
        '#52525B',  // zinc-600
        '#3F3F46',  // zinc-700
        '#E4E4E7',  // zinc-200
        '#27272A',  // zinc-800
        '#18181B',  // zinc-900
    ];

    // Default chart configuration
    Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#71717A';
    Chart.defaults.plugins.legend.labels.usePointStyle = true;

    /**
     * Initialize the main clicks line chart (always dark mode).
     */
    function initClicksChart(canvas, labels, data) {
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const gridColor = 'rgba(255, 255, 255, 0.06)';
        const textColor = '#71717A';

        new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Clicks',
                    data: data,
                    borderColor: COLORS.primary,
                    backgroundColor: function(context) {
                        const chart = context.chart;
                        const {ctx, chartArea} = chart;
                        if (!chartArea) return COLORS.primaryBg;
                        const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                        gradient.addColorStop(0, 'rgba(161, 161, 170, 0.15)');
                        gradient.addColorStop(1, 'rgba(161, 161, 170, 0)');
                        return gradient;
                    },
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointBackgroundColor: COLORS.primary,
                    pointBorderColor: COLORS.pointBorder,
                    pointBorderWidth: 2,
                    pointHoverRadius: 6,
                    pointHoverBackgroundColor: COLORS.primary,
                    pointHoverBorderColor: COLORS.pointBorder,
                    pointHoverBorderWidth: 3,
                    borderWidth: 2.5,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        backgroundColor: '#212121',
                        titleColor: '#EDEDED',
                        bodyColor: '#A1A1AA',
                        borderColor: 'rgba(255, 255, 255, 0.10)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        displayColors: false,
                        callbacks: {
                            title: function(items) {
                                return items[0].label;
                            },
                            label: function(context) {
                                return `Clicks: ${context.parsed.y}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: gridColor,
                            drawBorder: false,
                        },
                        ticks: {
                            color: textColor,
                            maxTicksLimit: 10,
                            maxRotation: 0,
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: gridColor,
                            drawBorder: false,
                        },
                        ticks: {
                            color: textColor,
                            precision: 0,
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index',
                }
            }
        });
    }

    /**
     * Initialize a pie/doughnut chart for breakdowns (always dark mode).
     */
    function initPieChart(canvas, data, labelKey) {
        if (!canvas || !data || !data.length) return;

        const ctx = canvas.getContext('2d');
        const textColor = '#71717A';

        const labels = data.map(item => item[labelKey] || 'Unknown');
        const values = data.map(item => item.count);
        const backgroundColors = CHART_ACCENTS.slice(0, labels.length);

        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: backgroundColors,
                    borderColor: '#0A0A0A',
                    borderWidth: 3,
                    hoverOffset: 6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: textColor,
                            padding: 12,
                            usePointStyle: true,
                            pointStyle: 'circle',
                            font: {
                                size: 11,
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#212121',
                        titleColor: '#EDEDED',
                        bodyColor: '#A1A1AA',
                        borderColor: 'rgba(255, 255, 255, 0.10)',
                        borderWidth: 1,
                        padding: 12,
                        cornerRadius: 8,
                        callbacks: {
                            label: function(context) {
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? Math.round((context.parsed / total) * 100) : 0;
                                return `${context.label}: ${context.parsed} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    // Make chart functions globally available
    window.initClicksChart = initClicksChart;
    window.initPieChart = initPieChart;

})();
