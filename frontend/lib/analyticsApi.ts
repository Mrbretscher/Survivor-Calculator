export type AnalyticsApiResult<T> =
  | { ok: true; data: T }
  | {
      ok: false;
      reason: AnalyticsApiFailureReason;
      error: string;
      status?: number;
    };

export type AnalyticsApiFailureReason =
  | "bad_request"
  | "unavailable"
  | "invalid_data"
  | "http_error"
  | "network"
  | "invalid_response";

export type AnalyticsChartType = "bar" | "horizontal_bar" | "table";

export type AnalyticsFilterOperator =
  | "equals"
  | "not_equals"
  | "in"
  | "not_in"
  | "range"
  | "is_true"
  | "is_false";

export type AnalyticsSortDirection = "asc" | "desc";

export type AnalyticsValueFormat = "integer" | "decimal" | "percent";

export type AnalyticsDatasetSchema = {
  id: string;
  grain: string;
  row_count: number;
};

export type AnalyticsDimensionSchema = {
  id: string;
  label: string;
  column: string;
  labels: Record<string, string>;
};

export type AnalyticsMetricSchema = {
  id: string;
  label: string;
  format: AnalyticsValueFormat;
  minimum_sample_size: number;
  proxy: boolean;
  description: string;
  warning: string | null;
};

export type AnalyticsFilterSchema = {
  field: string;
  operators: AnalyticsFilterOperator[];
};

export type AnalyticsSchema = {
  dataset: AnalyticsDatasetSchema;
  dimensions: AnalyticsDimensionSchema[];
  metrics: AnalyticsMetricSchema[];
  filters: AnalyticsFilterSchema[];
  chart_types: AnalyticsChartType[];
};

export type AnalyticsRangeFilterValue = {
  min?: number;
  max?: number;
};

export type AnalyticsFilter =
  | {
      field: string;
      operator: "equals" | "not_equals";
      value: string | number | boolean | null;
    }
  | {
      field: string;
      operator: "in" | "not_in";
      value: Array<string | number | boolean | null>;
    }
  | {
      field: string;
      operator: "range";
      value: AnalyticsRangeFilterValue;
    }
  | {
      field: string;
      operator: "is_true" | "is_false";
    };

export type AnalyticsSort = {
  field: "label" | "value" | "count" | "sample_size" | string;
  direction: AnalyticsSortDirection;
};

export type AnalyticsChartConfig = {
  dimension: string;
  metric: string;
  filters?: AnalyticsFilter[];
  sort?: AnalyticsSort;
  limit?: number;
  minimum_sample_size?: number;
};

export type AnalyticsPresetConfig = AnalyticsChartConfig & {
  id: string;
  title: string;
};

export type AnalyticsPresets = {
  presets: AnalyticsPresetConfig[];
};

export type AnalyticsChartMetricMetadata = {
  id: string;
  label: string;
  format: AnalyticsValueFormat;
  proxy: boolean;
  description: string;
};

export type AnalyticsChartDimensionMetadata = {
  id: string;
  label: string;
};

export type AnalyticsChartMetadata = {
  dimension: AnalyticsChartDimensionMetadata;
  metric: AnalyticsChartMetricMetadata;
  total_row_count: number;
  filtered_row_count: number;
  returned_row_count: number;
  minimum_sample_size: number;
  suppressed_row_count: number;
  warnings: string[];
};

export type AnalyticsChartResultRow = {
  key: string;
  label: string;
  value: number | null;
  count: number;
  sample_size: number;
  eligible: boolean;
  suppressed_reason: string | null;
};

export type AnalyticsChartResult = {
  metadata: AnalyticsChartMetadata;
  rows: AnalyticsChartResultRow[];
};

type AnalyticsFetchOptions = {
  apiBase?: string;
  revalidate?: number;
};

type ApiErrorPayload = {
  error?: unknown;
};

export const DEFAULT_ANALYTICS_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function fetchAnalyticsSchema(
  options: AnalyticsFetchOptions = {}
): Promise<AnalyticsApiResult<AnalyticsSchema>> {
  return fetchAnalyticsJson<AnalyticsSchema>("/api/analytics/schema", { method: "GET" }, options);
}

export function fetchAnalyticsPresets(
  options: AnalyticsFetchOptions = {}
): Promise<AnalyticsApiResult<AnalyticsPresets>> {
  return fetchAnalyticsJson<AnalyticsPresets>("/api/analytics/presets", { method: "GET" }, options);
}

export function fetchAnalyticsChart(
  config: AnalyticsChartConfig,
  options: AnalyticsFetchOptions = {}
): Promise<AnalyticsApiResult<AnalyticsChartResult>> {
  return fetchAnalyticsJson<AnalyticsChartResult>(
    "/api/analytics/query",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config)
    },
    options
  );
}

async function fetchAnalyticsJson<T>(
  path: string,
  init: RequestInit,
  options: AnalyticsFetchOptions
): Promise<AnalyticsApiResult<T>> {
  const apiBase = options.apiBase ?? DEFAULT_ANALYTICS_API_BASE;
  const requestInit: RequestInit & { next?: { revalidate?: number } } = {
    ...init,
    next: { revalidate: options.revalidate ?? 60 }
  };

  try {
    const response = await fetch(`${apiBase}${path}`, requestInit);
    if (!response.ok) {
      return {
        ok: false,
        reason: reasonForStatus(response.status),
        status: response.status,
        error: await errorMessage(response)
      };
    }
    try {
      return { ok: true, data: (await response.json()) as T };
    } catch {
      return {
        ok: false,
        reason: "invalid_response",
        status: response.status,
        error: "Analytics API returned an invalid JSON response."
      };
    }
  } catch {
    return {
      ok: false,
      reason: "network",
      error: `Could not reach the analytics API at ${apiBase}.`
    };
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiErrorPayload;
    return typeof payload.error === "string" && payload.error
      ? payload.error
      : `Analytics API request failed with status ${response.status}.`;
  } catch {
    return `Analytics API request failed with status ${response.status}.`;
  }
}

function reasonForStatus(status: number): AnalyticsApiFailureReason {
  if (status === 400) {
    return "bad_request";
  }
  if (status === 503) {
    return "unavailable";
  }
  if (status === 500) {
    return "invalid_data";
  }
  return "http_error";
}
