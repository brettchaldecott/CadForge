/**
 * Protocol types for Node CLI ↔ Python Engine communication.
 * Mirrors the Pydantic models in cadforge_engine.models.
 */

// ── Health ──

export interface HealthResponse {
  status: string;
  version: string;
  capabilities: string[];
}

// ── CadQuery ──

export interface CadQueryRequest {
  code: string;
  output_name?: string;
  format?: 'stl' | 'step';
  project_root: string;
}

export interface CadQueryResponse {
  success: boolean;
  stdout?: string;
  stderr?: string;
  error?: string | null;
  output_path?: string | null;
  script_path?: string | null;
  message?: string | null;
}

// ── Mesh ──

export interface MeshAnalyzeRequest {
  path: string;
  project_root: string;
}

export interface MeshAnalysisResponse {
  success: boolean;
  error?: string | null;
  file_path?: string | null;
  is_watertight?: boolean | null;
  volume_mm3?: number | null;
  volume_cm3?: number | null;
  surface_area_mm2?: number | null;
  triangle_count?: number | null;
  vertex_count?: number | null;
  bounding_box?: Record<string, number> | null;
  center_of_mass?: number[] | null;
  issues?: string[] | null;
}

// ── Preview ──

export interface PreviewRequest {
  path: string;
  color?: string;
  background?: string;
}

export interface PreviewResponse {
  success: boolean;
  message?: string | null;
  error?: string | null;
}

// ── Export ──

export interface ExportRequest {
  source: string;
  format?: 'stl' | 'step' | '3mf';
  name?: string;
  project_root: string;
}

export interface ExportResponse {
  success: boolean;
  output_path?: string | null;
  message?: string | null;
  error?: string | null;
}

// ── Vault ──

export interface VaultSearchRequest {
  query: string;
  tags?: string[];
  limit?: number;
  project_root: string;
}

export interface VaultSearchResult {
  file_path: string;
  section: string;
  content: string;
  score: number;
  tags: string[];
}

export interface VaultSearchResponse {
  success: boolean;
  query: string;
  results: VaultSearchResult[];
  note?: string | null;
  error?: string | null;
}

export interface VaultIndexRequest {
  project_root: string;
  incremental?: boolean;
}

export interface VaultIndexResponse {
  success: boolean;
  files_indexed?: number;
  chunks_created?: number;
  files_deleted?: number;
  backend?: string | null;
  error?: string | null;
}

// ── CAD Subagent ──

import type { ProviderType } from './config.js';

export interface CadSubagentProviderConfig {
  provider: ProviderType;
  api_key?: string | null;
  auth_token?: string | null;
  base_url?: string | null;
  aws_region?: string | null;
  aws_profile?: string | null;
}

export interface CadSubagentRequest {
  prompt: string;
  context: string;
  project_root: string;
  /** @deprecated Use provider_config instead */
  auth?: { api_key?: string | null; auth_token?: string | null };
  provider_config?: CadSubagentProviderConfig;
  model?: string;
  max_tokens?: number;
}

// ── SSE Events (CAD subagent) ──

export type SSEEventType =
  | 'status'
  | 'text_delta'
  | 'tool_use_start'
  | 'tool_result'
  | 'completion'
  | 'done';

export interface SSEEvent {
  event: SSEEventType;
  data: Record<string, unknown>;
}
