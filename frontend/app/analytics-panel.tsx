"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import {
  fetchAnalyticsChart,
  fetchAnalyticsPresets,
  fetchAnalyticsSchema,
  type AnalyticsChartConfig,
  type AnalyticsChartResult,
  type AnalyticsChartType,
  type AnalyticsPresetConfig,
  type AnalyticsSchema,
  type AnalyticsValueFormat
} from "../lib/analyticsApi";

type BuilderSortField = "value" | "label" | "count" | "sample_size";

type BuilderState = {
  presetId: string;
  dimension: string;
  metric: string;
  chartType: AnalyticsChartType;
  seasonStart: string;
  seasonEnd: string;
  minimumSampleSize: string;
  sortField: BuilderSortField;
  sortDirection: "asc" | "desc";
  limit: string;
};

const BUILDER_SORT_FIELDS: { id: BuilderSortField; label: string }[] = [
  { id: "value", label: "Metric value" },
  { id: "count", label: "Castaways" },
  { id: "sample_size", label: "Metric sample" },
  { id: "label", label: "Label" }
];

export default function AnalyticsPanel() {
  const [presets, setPresets] = useState<AnalyticsPresetConfig[]>([]);
  const [schema, setSchema] = useState<AnalyticsSchema | null>(null);
  const [builder, setBuilder] = useState<BuilderState | null>(null);
  const [result, setResult] = useState<AnalyticsChartResult | null>(null);
  const [error, setError] = useState("");
  const [validationError, setValidationError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isQuerying, setIsQuerying] = useState(false);
  const requestId = useRef(0);

  useEffect(() => {
    let active = true;

    async function loadAnalytics() {
      const [presetResponse, schemaResponse] = await Promise.all([fetchAnalyticsPresets(), fetchAnalyticsSchema()]);
      if (!active) {
        return;
      }

      if (!schemaResponse.ok) {
        setError(schemaResponse.error);
        setIsLoading(false);
        return;
      }
      if (!presetResponse.ok) {
        setError(presetResponse.error);
        setIsLoading(false);
        return;
      }

      const firstPreset = presetResponse.data.presets[0];
      if (!firstPreset) {
        setError("The analytics API did not return any chart presets.");
        setIsLoading(false);
        return;
      }

      const initialBuilder = builderFromPreset(firstPreset, schemaResponse.data);
      const initialQuery = toChartConfig(initialBuilder, schemaResponse.data);
      setSchema(schemaResponse.data);
      setPresets(presetResponse.data.presets);
      setBuilder(initialBuilder);
      setIsLoading(false);

      if ("error" in initialQuery) {
        setValidationError(initialQuery.error);
        return;
      }
      await runQuery(initialQuery.config, active);
    }

    void loadAnalytics();
    return () => {
      active = false;
    };
  }, []);

  async function runQuery(config: AnalyticsChartConfig, componentActive = true) {
    const currentRequestId = requestId.current + 1;
    requestId.current = currentRequestId;
    setError("");
    setResult(null);
    setIsQuerying(true);

    const response = await fetchAnalyticsChart(config);
    if (!componentActive || currentRequestId !== requestId.current) {
      return;
    }

    setIsQuerying(false);
    if (response.ok) {
      setResult(response.data);
      return;
    }

    setResult(null);
    setError(response.error);
  }

  function updateBuilder(patch: Partial<BuilderState>) {
    setBuilder((current) => (current ? { ...current, ...patch, presetId: "" } : current));
    setError("");
    setValidationError("");
  }

  function selectPreset(presetId: string) {
    if (!schema) {
      return;
    }
    if (!presetId) {
      updateBuilder({ presetId: "" });
      return;
    }

    const preset = presets.find((candidate) => candidate.id === presetId);
    if (!preset) {
      return;
    }

    const nextBuilder = builderFromPreset(preset, schema);
    const nextQuery = toChartConfig(nextBuilder, schema);
    setBuilder(nextBuilder);
    setError("");
    setValidationError("");
    if ("error" in nextQuery) {
      setValidationError(nextQuery.error);
      return;
    }
    void runQuery(nextQuery.config);
  }

  function submitBuilder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!schema || !builder) {
      return;
    }

    const nextQuery = toChartConfig(builder, schema);
    if ("error" in nextQuery) {
      setValidationError(nextQuery.error);
      return;
    }

    setValidationError("");
    void runQuery(nextQuery.config);
  }

  const selectedMetric = builder && schema ? schema.metrics.find((candidate) => candidate.id === builder.metric) : undefined;
  const sampleSizeApplies = selectedMetric?.format === "percent";
  const supportsSeasonRange = schema?.filters.some(
    (filter) => filter.field === "season" && filter.operators.includes("range")
  );

  return (
    <section className="section analyticsSection" id="analytics" aria-labelledby="analytics-title">
      <div className="sectionHeader">
        <div>
          <p className="eyebrow">Historical Analytics</p>
          <h2 id="analytics-title">Build a castaway comparison</h2>
        </div>
        <p className="sectionNote">Compare castaway-season records using the local workbook.</p>
      </div>

      {isLoading ? <AnalyticsLoading /> : null}
      {!isLoading && error && !builder ? <AnalyticsUnavailable error={error} /> : null}

      {!isLoading && builder && schema ? (
        <div className="analyticsWorkspace">
          <form className="analyticsBuilder" noValidate onSubmit={submitBuilder}>
            <div className="analyticsBuilderHeader">
              <div>
                <h3>Chart builder</h3>
                <p>Start with a preset or configure the comparison directly.</p>
              </div>
              <button className="analyticsRunButton" disabled={isQuerying} type="submit">
                {isQuerying ? "Updating..." : "Update chart"}
              </button>
            </div>

            <div className="analyticsControlGrid">
              <BuilderSelect id="analytics-preset" label="Preset" onChange={selectPreset} value={builder.presetId}>
                <option value="">Custom configuration</option>
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.title}</option>
                ))}
              </BuilderSelect>

              <BuilderSelect
                id="analytics-dimension"
                label="Dimension"
                onChange={(value) => updateBuilder({ dimension: value })}
                value={builder.dimension}
              >
                {schema.dimensions.map((dimension) => (
                  <option key={dimension.id} value={dimension.id}>{dimension.label}</option>
                ))}
              </BuilderSelect>

              <BuilderSelect
                id="analytics-metric"
                label="Metric"
                onChange={(value) => {
                  const nextMetric = schema.metrics.find((candidate) => candidate.id === value);
                  updateBuilder({ metric: value, minimumSampleSize: String(nextMetric?.minimum_sample_size ?? 1) });
                }}
                value={builder.metric}
              >
                {schema.metrics.map((schemaMetric) => (
                  <option key={schemaMetric.id} value={schemaMetric.id}>{schemaMetric.label}</option>
                ))}
              </BuilderSelect>

              <BuilderSelect
                id="analytics-chart-type"
                label="Chart type"
                onChange={(value) => updateBuilder({ chartType: value as AnalyticsChartType })}
                value={builder.chartType}
              >
                {schema.chart_types.map((chartType) => (
                  <option key={chartType} value={chartType}>{chartTypeLabel(chartType)}</option>
                ))}
              </BuilderSelect>

              {supportsSeasonRange ? (
                <fieldset className="analyticsRangeField">
                  <legend>Season range</legend>
                  <div>
                    <label htmlFor="analytics-season-start">From</label>
                    <input
                      id="analytics-season-start"
                      inputMode="numeric"
                      onChange={(event) => updateBuilder({ seasonStart: event.target.value })}
                      placeholder="Any"
                      type="number"
                      value={builder.seasonStart}
                    />
                  </div>
                  <div>
                    <label htmlFor="analytics-season-end">To</label>
                    <input
                      id="analytics-season-end"
                      inputMode="numeric"
                      onChange={(event) => updateBuilder({ seasonEnd: event.target.value })}
                      placeholder="Any"
                      type="number"
                      value={builder.seasonEnd}
                    />
                  </div>
                </fieldset>
              ) : null}

              <BuilderNumberInput
                id="analytics-sample-size"
                disabled={!sampleSizeApplies}
                hint={sampleSizeApplies ? "Rate metrics with fewer observations are suppressed." : "Minimum samples apply to rate metrics only."}
                label="Minimum rate sample"
                onChange={(value) => updateBuilder({ minimumSampleSize: value })}
                value={builder.minimumSampleSize}
              />

              <BuilderSelect
                id="analytics-sort-field"
                label="Sort by"
                onChange={(value) => updateBuilder({ sortField: value as BuilderSortField })}
                value={builder.sortField}
              >
                {BUILDER_SORT_FIELDS.map((field) => (
                  <option key={field.id} value={field.id}>{field.label}</option>
                ))}
              </BuilderSelect>

              <BuilderSelect
                id="analytics-sort-direction"
                label="Order"
                onChange={(value) => updateBuilder({ sortDirection: value as "asc" | "desc" })}
                value={builder.sortDirection}
              >
                <option value="desc">Highest first</option>
                <option value="asc">Lowest first</option>
              </BuilderSelect>

              <BuilderNumberInput
                id="analytics-limit"
                hint="Maximum number of grouped results to return."
                label="Result limit"
                onChange={(value) => updateBuilder({ limit: value })}
                value={builder.limit}
              />
            </div>
          </form>

          {validationError ? <p className="analyticsInlineError" role="alert">{validationError}</p> : null}
          {error ? <p className="analyticsInlineError" role="alert">{result ? `The latest request failed: ${error}` : error}</p> : null}
          {isQuerying ? <AnalyticsLoading /> : null}

          {result && !isQuerying ? (
            <AnalyticsResult chartType={builder.chartType} result={result} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function BuilderSelect({
  children,
  id,
  label,
  onChange,
  value
}: {
  children: React.ReactNode;
  id: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="analyticsSelectLabel" htmlFor={id}>
      {label}
      <select id={id} onChange={(event) => onChange(event.target.value)} value={value}>{children}</select>
    </label>
  );
}

function BuilderNumberInput({
  disabled = false,
  hint,
  id,
  label,
  onChange,
  value
}: {
  disabled?: boolean;
  hint: string;
  id: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  const hintId = `${id}-hint`;
  return (
    <label className="analyticsSelectLabel" htmlFor={id}>
      {label}
      <input aria-describedby={hintId} disabled={disabled} id={id} inputMode="numeric" min="1" onChange={(event) => onChange(event.target.value)} type="number" value={value} />
      <span className="analyticsControlHint" id={hintId}>{hint}</span>
    </label>
  );
}

function AnalyticsResult({
  chartType,
  result
}: {
  chartType: AnalyticsChartType;
  result: AnalyticsChartResult;
}) {
  const { metadata, rows } = result;
  const visibleRows = rows.filter((row) => row.value !== null);
  const showProxyNote = metadata.metric.proxy || metadata.metric.id === "social_proxy_no_votes_rate";

  return (
    <div className="analyticsResult">
      <div className="analyticsResultHeader">
        <div>
          <h3>{metadata.metric.label} by {metadata.dimension.label}</h3>
          <p>{metadata.metric.description}</p>
        </div>
        <p className="analyticsResultCount">{metadata.filtered_row_count} castaway-season records</p>
      </div>

      {showProxyNote ? (
        <aside aria-label="Social performance proxy limitation" className="analyticsProxyNote">
          <strong>Social performance proxy:</strong> this uses only castaway-season records with recorded vote activity and does not measure relationships, influence, strategic agency, or jury management.
        </aside>
      ) : null}

      {chartType === "table" ? <AnalyticsTable result={result} /> : null}
      {chartType === "horizontal_bar" ? <HorizontalBarChart result={result} visibleRows={visibleRows} /> : null}
      {chartType === "bar" ? <VerticalBarChart result={result} visibleRows={visibleRows} /> : null}

      {chartType !== "table" && metadata.suppressed_row_count > 0 ? (
        <p className="analyticsSuppressionNote">
          {metadata.suppressed_row_count} group{metadata.suppressed_row_count === 1 ? "" : "s"} did not meet the minimum sample size of {metadata.minimum_sample_size}. Choose Table to inspect them.
        </p>
      ) : null}

      {metadata.warnings.map((warning) => (
        <p className="analyticsWarning" key={warning}>{warning}</p>
      ))}
    </div>
  );
}

function HorizontalBarChart({
  result,
  visibleRows
}: {
  result: AnalyticsChartResult;
  visibleRows: AnalyticsChartResult["rows"];
}) {
  if (visibleRows.length === 0) {
    return <AnalyticsEmptyChart hasRows={result.rows.length > 0} />;
  }
  const maxValue = Math.max(...visibleRows.map((row) => row.value ?? 0), 1);

  return (
    <div className="analyticsBarChart" aria-label={`${result.metadata.metric.label} by ${result.metadata.dimension.label}`} role="list">
      {visibleRows.map((row) => {
        const value = row.value ?? 0;
        const width = Math.max(0, Math.min(100, (value / maxValue) * 100));
        return (
          <div aria-label={`${row.label}: ${formatMetric(value, result.metadata.metric.format)}`} className="analyticsBarRow" key={row.key} role="listitem">
            <div className="analyticsBarLabel" title={row.label}>{row.label}</div>
            <div aria-hidden="true" className="analyticsBarTrack"><span className="analyticsBarFill" style={{ width: `${width}%` }} /></div>
            <strong className="analyticsBarValue">{formatMetric(value, result.metadata.metric.format)}</strong>
          </div>
        );
      })}
    </div>
  );
}

function VerticalBarChart({
  result,
  visibleRows
}: {
  result: AnalyticsChartResult;
  visibleRows: AnalyticsChartResult["rows"];
}) {
  if (visibleRows.length === 0) {
    return <AnalyticsEmptyChart hasRows={result.rows.length > 0} />;
  }
  const maxValue = Math.max(...visibleRows.map((row) => row.value ?? 0), 1);

  return (
    <div className="analyticsVerticalChart" aria-label={`${result.metadata.metric.label} by ${result.metadata.dimension.label}`} role="list">
      {visibleRows.map((row) => {
        const value = row.value ?? 0;
        const height = Math.max(0, Math.min(100, (value / maxValue) * 100));
        return (
          <div aria-label={`${row.label}: ${formatMetric(value, result.metadata.metric.format)}`} className="analyticsVerticalBar" key={row.key} role="listitem">
            <strong>{formatMetric(value, result.metadata.metric.format)}</strong>
            <div aria-hidden="true" className="analyticsVerticalTrack"><span style={{ height: `${height}%` }} /></div>
            <span title={row.label}>{row.label}</span>
          </div>
        );
      })}
    </div>
  );
}

function AnalyticsEmptyChart({ hasRows }: { hasRows: boolean }) {
  return (
    <p className="analyticsEmptyChart" role="status">
      {hasRows
        ? "No groups met this metric's sample-size threshold. Choose Table to inspect the suppressed groups."
        : "No castaway-season records match this configuration. Adjust the season range or choose another comparison."}
    </p>
  );
}

function AnalyticsTable({ result }: { result: AnalyticsChartResult }) {
  const { metadata, rows } = result;
  if (rows.length === 0) {
    return <AnalyticsEmptyChart hasRows={false} />;
  }
  return (
    <div className="tableFrame analyticsTableFrame" role="region" aria-label="Analytics result table" tabIndex={0}>
      <table>
        <caption>{metadata.metric.label} by {metadata.dimension.label}</caption>
        <thead>
          <tr>
            <th scope="col">{metadata.dimension.label}</th>
            <th scope="col">{metadata.metric.label}</th>
            <th scope="col">Castaways</th>
            <th scope="col">Metric sample</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row">{row.label}</th>
              <td>{row.value === null ? row.suppressed_reason ?? "Unavailable" : formatMetric(row.value, metadata.metric.format)}</td>
              <td>{formatInteger(row.count)}</td>
              <td>{formatInteger(row.sample_size)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalyticsLoading() {
  return <p className="analyticsStatus" role="status">Loading analytics...</p>;
}

function AnalyticsUnavailable({ error }: { error: string }) {
  return (
    <div className="analyticsUnavailable" role="status">
      <h3>Analytics data unavailable</h3>
      <p>{error}</p>
    </div>
  );
}

function builderFromPreset(preset: AnalyticsPresetConfig, schema: AnalyticsSchema): BuilderState {
  const metric = schema.metrics.find((candidate) => candidate.id === preset.metric);
  const sort = preset.sort ?? { field: "value", direction: "desc" };
  return {
    presetId: preset.id,
    dimension: preset.dimension,
    metric: preset.metric,
    chartType: schema.chart_types.includes("horizontal_bar") ? "horizontal_bar" : schema.chart_types[0],
    seasonStart: "",
    seasonEnd: "",
    minimumSampleSize: String(preset.minimum_sample_size ?? metric?.minimum_sample_size ?? 1),
    sortField: isBuilderSortField(sort.field) ? sort.field : "value",
    sortDirection: sort.direction,
    limit: String(preset.limit ?? 20)
  };
}

function toChartConfig(
  builder: BuilderState,
  schema: AnalyticsSchema
): { config: AnalyticsChartConfig } | { error: string } {
  if (!schema.dimensions.some((dimension) => dimension.id === builder.dimension)) {
    return { error: "Choose a supported dimension from the analytics schema." };
  }
  if (!schema.metrics.some((metric) => metric.id === builder.metric)) {
    return { error: "Choose a supported metric from the analytics schema." };
  }
  if (!schema.chart_types.includes(builder.chartType)) {
    return { error: "Choose a chart type supported by the analytics schema." };
  }

  const minimumSampleSize = positiveInteger(builder.minimumSampleSize, "Minimum sample size");
  if (typeof minimumSampleSize === "string") {
    return { error: minimumSampleSize };
  }
  const limit = positiveInteger(builder.limit, "Result limit");
  if (typeof limit === "string") {
    return { error: limit };
  }
  if (builder.chartType === "bar" && limit > 20) {
    return { error: "Vertical bar charts support up to 20 results. Reduce the limit or choose horizontal bars or a table." };
  }

  const seasonStart = optionalSeason(builder.seasonStart, "Season start");
  if (typeof seasonStart === "string") {
    return { error: seasonStart };
  }
  const seasonEnd = optionalSeason(builder.seasonEnd, "Season end");
  if (typeof seasonEnd === "string") {
    return { error: seasonEnd };
  }
  if (seasonStart !== undefined && seasonEnd !== undefined && seasonStart > seasonEnd) {
    return { error: "Season start must be earlier than or equal to season end." };
  }

  const filters = [];
  if (seasonStart !== undefined || seasonEnd !== undefined) {
    filters.push({
      field: "season",
      operator: "range" as const,
      value: { min: seasonStart, max: seasonEnd }
    });
  }

  return {
    config: {
      dimension: builder.dimension,
      metric: builder.metric,
      filters,
      minimum_sample_size: minimumSampleSize,
      sort: { field: builder.sortField, direction: builder.sortDirection },
      limit
    }
  };
}

function positiveInteger(value: string, label: string): number | string {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return `${label} must be a whole number greater than zero.`;
  }
  return parsed;
}

function optionalSeason(value: string, label: string): number | string | undefined {
  if (!value.trim()) {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return `${label} must be a positive whole-number season.`;
  }
  return parsed;
}

function isBuilderSortField(value: string): value is BuilderSortField {
  return BUILDER_SORT_FIELDS.some((field) => field.id === value);
}

function chartTypeLabel(chartType: AnalyticsChartType): string {
  if (chartType === "bar") {
    return "Vertical bars";
  }
  if (chartType === "horizontal_bar") {
    return "Horizontal bars";
  }
  return "Table";
}

function formatMetric(value: number, format: AnalyticsValueFormat): string {
  if (format === "percent") {
    return new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 }).format(value);
  }
  if (format === "decimal") {
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
  }
  return formatInteger(value);
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}
