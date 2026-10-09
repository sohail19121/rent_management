import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { formatDate, deserializeDate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useChart } from "@web/core/utils/chart_hook";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { formatFloat, formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/** Reads a chart color token from the dashboard root, so light and dark mode each get their own steps. */
function cssVar(name) {
    const root = document.querySelector(".o_rent_dashboard") || document.body;
    return getComputedStyle(root).getPropertyValue(name).trim();
}

/**
 * A chart with its title, an optional legend, and a table view of the same numbers.
 * Props: chart = { title, subtitle, kind: "bar" | "hbar", labels, series: [{ label, values, color }],
 *                  format: "monetary" | "number", unit, currencyId }
 */
export class RentChartCard extends Component {
    static template = "rent_management.RentChartCard";

    props = useProps({ chart: t.object() });

    setup() {
        this.state = proxy({ showTable: false });
        this.chart = useChart(() => this.chartConfig());
    }

    formatValue(value, compact = false) {
        const chart = this.props.chart;
        if (chart.format === "monetary") {
            // Axis ticks: compact and without decimals ("$ 200k"), tooltips and tables: exact.
            return formatMonetary(value, {
                currencyId: chart.currencyId,
                humanReadable: compact,
                ...(compact ? { digits: [16, 0] } : {}),
            });
        }
        const number = formatFloat(value, { digits: [16, compact ? 0 : 2], humanReadable: compact });
        return chart.unit ? `${number} ${chart.unit}` : number;
    }

    toggleTable() {
        this.state.showTable = !this.state.showTable;
    }

    chartConfig() {
        const chart = this.props.chart;
        const horizontal = chart.kind === "hbar";
        const grid = cssVar("--o-rent-grid");
        const muted = cssVar("--o-rent-text-muted");
        const surface = cssVar("--o-rent-surface");
        const valueAxis = {
            beginAtZero: true,
            border: { display: false },
            grid: { color: grid, lineWidth: 1, drawTicks: false },
            ticks: {
                color: muted,
                padding: 6,
                maxTicksLimit: horizontal ? 3 : 5,
                maxRotation: 0,
                callback: (value) => this.formatValue(value, true),
            },
        };
        const categoryAxis = {
            border: { color: grid },
            grid: { display: false },
            ticks: { color: muted, padding: 4, autoSkip: !horizontal, maxRotation: 0 },
        };
        return {
            type: "bar",
            data: {
                labels: chart.labels,
                datasets: chart.series.map((serie) => ({
                    label: serie.label,
                    data: serie.values,
                    backgroundColor: cssVar(serie.color),
                    hoverBackgroundColor: cssVar(serie.color),
                    // Thin marks with rounded data ends; the 2px surface border gives the gap between bars.
                    borderRadius: 4,
                    borderSkipped: "start",
                    borderWidth: 1,
                    borderColor: surface,
                    maxBarThickness: horizontal ? 18 : 22,
                    categoryPercentage: 0.7,
                    barPercentage: 0.9,
                })),
            },
            options: {
                indexAxis: horizontal ? "y" : "x",
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: "index", intersect: false },
                scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
                plugins: {
                    legend: {
                        display: chart.series.length > 1,
                        position: "top",
                        align: "end",
                        labels: { color: muted, boxWidth: 10, boxHeight: 10, useBorderRadius: true, borderRadius: 2 },
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${this.formatValue(ctx.parsed[horizontal ? "x" : "y"])}`,
                        },
                    },
                },
            },
        };
    }
}

/** 12-point trend line: muted history, accent dot on the current period. */
export class RentSparkline extends Component {
    static template = "rent_management.RentSparkline";

    props = useProps({
        values: t.array(),
        label: t.string(),
        width: t.number().optional(160),
        height: t.number().optional(36),
    });

    geometry() {
        const { values, width, height } = this.props;
        if (!values || values.length < 2 || !values.some((v) => v)) {
            return null;
        }
        const max = Math.max(...values, 0);
        const min = Math.min(...values, 0);
        const span = max - min || 1;
        const pad = 3;
        const points = values.map((v, i) => [
            pad + (i * (width - 2 * pad)) / (values.length - 1),
            pad + (height - 2 * pad) * (1 - (v - min) / span),
        ]);
        const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
        const last = points.at(-1);
        return {
            viewBox: `0 0 ${width} ${height}`,
            line,
            area: `${line} L${last[0].toFixed(1)},${height} L${points[0][0].toFixed(1)},${height} Z`,
            x: last[0],
            y: last[1],
        };
    }
}

/** Card title with its icon badge and an optional "View all" link. */
export class RentCardHeader extends Component {
    static template = "rent_management.RentCardHeader";

    props = useProps({
        title: t.string(),
        icon: t.string(),
        variant: t.string().optional("primary"),
        subtitle: t.string().optional(""),
        action: t.or([t.object(), t.boolean()]).optional(false),
    });

    setup() {
        this.actionService = useService("action");
    }

    viewAll() {
        if (this.props.action) {
            this.actionService.doAction(this.props.action);
        }
    }
}

export class RentDashboard extends Component {
    static template = "rent_management.RentDashboard";
    static components = { RentCardHeader, RentChartCard, RentSparkline };

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periods = [
            ["this_month", _t("This Month")],
            ["last_month", _t("Last Month")],
            ["this_quarter", _t("This Quarter")],
            ["this_year", _t("This Year")],
            ["last_12_months", _t("Last 12 Months")],
        ];
        this.state = proxy({ data: null, period: "this_month", propertyId: false, loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("rent.property", "get_dashboard_data", [], {
            period: this.state.period,
            property_id: this.state.propertyId,
        });
        this.state.loading = false;
    }

    setPeriod(period) {
        this.state.period = period;
        this.load();
    }

    onPropertyChange(ev) {
        this.state.propertyId = parseInt(ev.target.value) || false;
        this.load();
    }

    // Formatting ---------------------------------------------------------------

    money(value) {
        return formatMonetary(value, { currencyId: this.state.data.currency_id });
    }

    number(value, digits = 0) {
        return formatFloat(value, { digits: [16, digits] });
    }

    date(value) {
        return value ? formatDate(deserializeDate(value)) : "";
    }

    kpiValue(kpi) {
        if (kpi.format === "monetary") {
            return this.money(kpi.value);
        }
        if (kpi.format === "percent") {
            return `${this.number(kpi.value, 1)} %`;
        }
        return this.number(kpi.value);
    }

    /** Auto-compact value for tiles (12.9K, $ 4.2M); the exact value goes in the title. */
    kpiCompact(kpi) {
        if (kpi.format === "monetary") {
            const big = Math.abs(kpi.value) >= 100000;
            return formatMonetary(kpi.value, {
                currencyId: this.state.data.currency_id,
                humanReadable: big,
                digits: [16, big ? 1 : 0],
            });
        }
        return this.kpiValue(kpi);
    }

    // KPI layout ---------------------------------------------------------------

    allKpis() {
        return this.state.data.sections.flatMap((section) => section.kpis);
    }

    kpi(key) {
        return this.allKpis().find((kpi) => kpi.key === key);
    }

    hero() {
        return this.allKpis().find((kpi) => kpi.placement === "hero");
    }

    highlights() {
        return this.allKpis().filter((kpi) => kpi.placement === "highlight");
    }

    tiles() {
        return this.allKpis().filter((kpi) => kpi.placement === "tile");
    }

    previousLabel() {
        return {
            this_month: _t("vs last month"),
            last_month: _t("vs the month before"),
            this_quarter: _t("vs last quarter"),
            this_year: _t("vs last year"),
            last_12_months: _t("vs the 12 months before"),
        }[this.state.data.period.key];
    }

    /** Signed change vs the previous period; its color says whether that direction is good. */
    delta(kpi) {
        if (kpi.previous === null || kpi.previous === undefined) {
            return null;
        }
        const { value, previous } = kpi;
        if (!previous) {
            return value ? { text: _t("New"), direction: "up", good: kpi.up_is_good } : null;
        }
        const pct = ((value - previous) / Math.abs(previous)) * 100;
        const direction = Math.abs(pct) < 0.05 ? "flat" : pct > 0 ? "up" : "down";
        return {
            text: `${pct > 0 ? "+" : ""}${this.number(pct, 1)} %`,
            direction,
            good: direction === "flat" ? null : (direction === "up") === kpi.up_is_good,
        };
    }

    deltaIcon(delta) {
        return { up: "arrow_upward", down: "arrow_downward", flat: "remove" }[delta.direction];
    }

    clampPct(value) {
        return Math.max(0, Math.min(value || 0, 100));
    }

    collectionRate() {
        return this.kpi("collection_rate").value;
    }

    greeting() {
        const hour = new Date().getHours();
        const name = (user.name || "").split(" ")[0];
        if (hour < 12) {
            return _t("Good morning, %s", name);
        }
        if (hour < 17) {
            return _t("Good afternoon, %s", name);
        }
        return _t("Good evening, %s", name);
    }

    initials(name) {
        return (name || "?")
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0].toUpperCase())
            .join("");
    }

    periodLabel() {
        const period = this.state.data.period;
        return `${this.date(period.date_from)} - ${this.date(period.date_to)}`;
    }

    // Charts -------------------------------------------------------------------

    collectionChart() {
        const monthly = this.state.data.monthly;
        return {
            title: _t("Billed vs Collected"),
            subtitle: _t("Last 12 months"),
            kind: "bar",
            labels: monthly.labels,
            series: [
                { label: _t("Billed"), values: monthly.billed, color: "--o-rent-series-1" },
                { label: _t("Collected"), values: monthly.collected, color: "--o-rent-series-2" },
            ],
            format: "monetary",
            currencyId: this.state.data.currency_id,
        };
    }

    incomeChart() {
        const mix = this.state.data.income_mix;
        return {
            title: _t("Income by Type"),
            subtitle: this.periodLabel(),
            kind: "hbar",
            labels: mix.map((row) => row.label),
            series: [{ label: _t("Amount"), values: mix.map((row) => row.value), color: "--o-rent-series-1" }],
            format: "monetary",
            currencyId: this.state.data.currency_id,
        };
    }

    electricityChart() {
        const monthly = this.state.data.monthly;
        return {
            title: _t("Electricity Consumption"),
            subtitle: _t("Last 12 months, confirmed readings"),
            kind: "bar",
            labels: monthly.labels,
            series: [{ label: _t("Consumption"), values: monthly.kwh, color: "--o-rent-series-1" }],
            format: "number",
            unit: "kWh",
        };
    }

    // Navigation ---------------------------------------------------------------

    openAction(action) {
        if (action) {
            this.action.doAction(action);
        }
    }

    openRecord(model, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
        });
    }

    openList(name, model, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            domain,
            views: [[false, "list"], [false, "form"]],
        });
    }

    propertyFilterDomain() {
        return this.state.propertyId ? [["property_id", "=", this.state.propertyId]] : [];
    }
}

registry.category("actions").add("rent_management.dashboard", RentDashboard);
