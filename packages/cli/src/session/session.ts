/**
 * Session persistence — JSONL read/write (same format as Python).
 *
 * Stores conversation transcripts as JSONL files with a session index
 * for resume and search.
 */

import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { getCadforgeDir } from '../config/paths.js';

export interface SessionEntry {
  role: 'user' | 'assistant' | 'system';
  content: string | Record<string, unknown>[];
  timestamp: number;
  tool_use_id?: string;
  tool_result?: unknown;
  usage?: { input_tokens: number; output_tokens: number };
}

export interface SessionMetadata {
  session_id: string;
  started_at: string;
  last_active: string;
  message_count: number;
  summary: string;
  file_path: string;
}

function getSessionsDir(projectRoot: string): string {
  const d = join(getCadforgeDir(projectRoot), 'sessions');
  mkdirSync(d, { recursive: true });
  return d;
}

function generateSessionId(): string {
  const now = new Date();
  const pad = (n: number, len = 2) => String(n).padStart(len, '0');
  return `session-${now.getUTCFullYear()}-${pad(now.getUTCMonth() + 1)}-${pad(now.getUTCDate())}-${pad(now.getUTCHours())}-${pad(now.getUTCMinutes())}-${pad(now.getUTCSeconds())}`;
}

export class Session {
  readonly id: string;
  readonly projectRoot: string;
  readonly filePath: string;
  readonly entries: SessionEntry[] = [];

  constructor(projectRoot: string, id?: string) {
    this.projectRoot = projectRoot;
    this.id = id ?? generateSessionId();
    this.filePath = join(getSessionsDir(projectRoot), `${this.id}.jsonl`);
  }

  addMessage(entry: SessionEntry): void {
    this.entries.push(entry);
    this.appendToFile(entry);
  }

  addUserMessage(content: string | Record<string, unknown>[]): SessionEntry {
    const entry: SessionEntry = { role: 'user', content, timestamp: Date.now() / 1000 };
    this.addMessage(entry);
    return entry;
  }

  addAssistantMessage(
    content: string | Record<string, unknown>[],
    usage?: { input_tokens: number; output_tokens: number },
  ): SessionEntry {
    const entry: SessionEntry = { role: 'assistant', content, timestamp: Date.now() / 1000 };
    if (usage) entry.usage = usage;
    this.addMessage(entry);
    return entry;
  }

  private appendToFile(entry: SessionEntry): void {
    const dir = dirname(this.filePath);
    mkdirSync(dir, { recursive: true });
    const data: Record<string, unknown> = {
      role: entry.role,
      content: entry.content,
      timestamp: entry.timestamp,
    };
    if (entry.tool_use_id) data.tool_use_id = entry.tool_use_id;
    if (entry.tool_result !== undefined) data.tool_result = entry.tool_result;
    if (entry.usage) data.usage = entry.usage;
    appendFileSync(this.filePath, JSON.stringify(data) + '\n', 'utf-8');
  }

  load(): void {
    if (!existsSync(this.filePath)) return;
    const text = readFileSync(this.filePath, 'utf-8');
    this.entries.length = 0;
    for (const line of text.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const d = JSON.parse(trimmed) as Record<string, unknown>;
      this.entries.push({
        role: d.role as SessionEntry['role'],
        content: d.content as SessionEntry['content'],
        timestamp: (d.timestamp as number) ?? 0,
        tool_use_id: d.tool_use_id as string | undefined,
        tool_result: d.tool_result,
        usage: d.usage as SessionEntry['usage'],
      });
    }
  }

  /**
   * Get messages formatted for the Anthropic API.
   * Handles dangling tool_use blocks by injecting error tool_result blocks.
   */
  getApiMessages(): Record<string, unknown>[] {
    const apiMsgs: Record<string, unknown>[] = [];
    for (const entry of this.entries) {
      if (entry.role === 'user' || entry.role === 'assistant') {
        apiMsgs.push({ role: entry.role, content: entry.content });
      }
    }

    // Fix dangling tool_use
    if (apiMsgs.length > 0 && apiMsgs[apiMsgs.length - 1].role === 'assistant') {
      const content = apiMsgs[apiMsgs.length - 1].content;
      if (Array.isArray(content)) {
        const toolUseIds = (content as Record<string, unknown>[])
          .filter((b) => b.type === 'tool_use')
          .map((b) => b.id as string);
        if (toolUseIds.length > 0) {
          const errorResults = toolUseIds.map((id) => ({
            type: 'tool_result',
            tool_use_id: id,
            content: 'Session was interrupted before tool execution completed.',
            is_error: true,
          }));
          apiMsgs.push({ role: 'user', content: errorResults });
        }
      }
    }

    return apiMsgs;
  }

  get messageCount(): number {
    return this.entries.length;
  }

  get summary(): string {
    for (const entry of this.entries) {
      if (entry.role === 'user' && typeof entry.content === 'string') {
        const text = entry.content.slice(0, 100);
        return entry.content.length > 100 ? text + '...' : text;
      }
    }
    return '(empty session)';
  }

  toMetadata(): SessionMetadata {
    const started = this.entries.length > 0 ? this.entries[0].timestamp : Date.now() / 1000;
    const last = this.entries.length > 0 ? this.entries[this.entries.length - 1].timestamp : started;
    return {
      session_id: this.id,
      started_at: new Date(started * 1000).toISOString(),
      last_active: new Date(last * 1000).toISOString(),
      message_count: this.messageCount,
      summary: this.summary,
      file_path: this.filePath,
    };
  }
}

export class SessionIndex {
  private readonly indexPath: string;

  constructor(projectRoot: string) {
    const sessionsDir = getSessionsDir(projectRoot);
    this.indexPath = join(sessionsDir, 'sessions-index.json');
  }

  private loadIndex(): SessionMetadata[] {
    if (!existsSync(this.indexPath)) return [];
    try {
      return JSON.parse(readFileSync(this.indexPath, 'utf-8')) as SessionMetadata[];
    } catch {
      return [];
    }
  }

  private saveIndex(entries: SessionMetadata[]): void {
    const dir = dirname(this.indexPath);
    mkdirSync(dir, { recursive: true });
    writeFileSync(this.indexPath, JSON.stringify(entries, null, 2) + '\n', 'utf-8');
  }

  update(session: Session): void {
    const entries = this.loadIndex();
    const metadata = session.toMetadata();
    const idx = entries.findIndex((e) => e.session_id === metadata.session_id);
    if (idx >= 0) {
      entries[idx] = metadata;
    } else {
      entries.push(metadata);
    }
    this.saveIndex(entries);
  }

  listSessions(limit = 20): SessionMetadata[] {
    const entries = this.loadIndex();
    entries.sort((a, b) => b.last_active.localeCompare(a.last_active));
    return entries.slice(0, limit);
  }

  getLatest(): SessionMetadata | null {
    const entries = this.listSessions(1);
    return entries.length > 0 ? entries[0] : null;
  }

  getById(sessionId: string): SessionMetadata | null {
    const entries = this.loadIndex();
    return entries.find((e) => e.session_id === sessionId) ?? null;
  }
}
