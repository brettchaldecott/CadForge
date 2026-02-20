/**
 * HTTP + SSE client for the Python CadForge Engine API.
 */

import type {
  HealthResponse,
  CadQueryRequest,
  CadQueryResponse,
  MeshAnalyzeRequest,
  MeshAnalysisResponse,
  PreviewRequest,
  PreviewResponse,
  ExportRequest,
  ExportResponse,
  VaultSearchRequest,
  VaultSearchResponse,
  VaultIndexRequest,
  VaultIndexResponse,
  CadSubagentRequest,
  SSEEvent,
} from '@cadforge/shared';

export class BackendClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Make a request to the engine API.
   */
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const init: RequestInit = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }

    const response = await fetch(url, init);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Engine API error ${response.status}: ${text}`);
    }
    return (await response.json()) as T;
  }

  // ── Health ──

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/health');
  }

  /**
   * Wait for the engine to become healthy, with timeout.
   */
  async waitForHealth(timeoutMs: number = 30000): Promise<HealthResponse> {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        return await this.health();
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
    throw new Error(`Engine did not become healthy within ${timeoutMs}ms`);
  }

  // ── CadQuery ──

  async executeCadQuery(req: CadQueryRequest): Promise<CadQueryResponse> {
    return this.request<CadQueryResponse>('POST', '/tools/cadquery', req);
  }

  // ── Mesh ──

  async analyzeMesh(req: MeshAnalyzeRequest): Promise<MeshAnalysisResponse> {
    return this.request<MeshAnalysisResponse>('POST', '/tools/mesh', req);
  }

  async preview(req: PreviewRequest): Promise<PreviewResponse> {
    return this.request<PreviewResponse>('POST', '/tools/preview', req);
  }

  // ── Export ──

  async exportModel(req: ExportRequest): Promise<ExportResponse> {
    return this.request<ExportResponse>('POST', '/tools/export', req);
  }

  // ── Vault ──

  async searchVault(req: VaultSearchRequest): Promise<VaultSearchResponse> {
    return this.request<VaultSearchResponse>('POST', '/vault/search', req);
  }

  async indexVault(req: VaultIndexRequest): Promise<VaultIndexResponse> {
    return this.request<VaultIndexResponse>('POST', '/vault/index', req);
  }

  // ── CAD Subagent ──

  /**
   * Stream a CAD subagent session via SSE.
   * Parses the SSE wire format and calls onSSEEvent for each event.
   * Returns the final output from the 'completion' event.
   */
  async streamCadSubagent(
    req: CadSubagentRequest,
    onSSEEvent: (event: SSEEvent) => void,
  ): Promise<{ success: boolean; output: string; error?: string }> {
    const url = `${this.baseUrl}/subagent/cad`;
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });

    if (!response.ok) {
      const text = await response.text();
      return { success: false, output: '', error: `Engine API error ${response.status}: ${text}` };
    }

    if (!response.body) {
      return { success: false, output: '', error: 'No response body from SSE endpoint' };
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalOutput = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';  // Keep incomplete line in buffer

        let currentEvent = '';
        let currentData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            currentData = line.slice(6);
          } else if (line === '' && currentEvent) {
            // End of SSE event (blank line)
            try {
              const data = JSON.parse(currentData) as Record<string, unknown>;
              const sseEvent: SSEEvent = {
                event: currentEvent as SSEEvent['event'],
                data,
              };
              onSSEEvent(sseEvent);

              if (currentEvent === 'completion') {
                finalOutput = (data.text as string) ?? '';
              }
            } catch {
              // Skip malformed events
            }
            currentEvent = '';
            currentData = '';
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return { success: true, output: finalOutput };
  }

  // ── Generic tool dispatch ──

  /**
   * Route a tool call to the appropriate engine endpoint.
   */
  async callTool(toolName: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    switch (toolName) {
      case 'ExecuteCadQuery':
        return this.request('POST', '/tools/cadquery', input);
      case 'AnalyzeMesh':
        return this.request('POST', '/tools/mesh', input);
      case 'ShowPreview':
        return this.request('POST', '/tools/preview', input);
      case 'ExportModel':
        return this.request('POST', '/tools/export', input);
      case 'SearchVault':
        return this.request('POST', '/vault/search', input);
      default:
        return { success: false, error: `Unknown remote tool: ${toolName}` };
    }
  }
}
