/**
 * Backend lifecycle manager.
 *
 * Spawns the Python FastAPI server as a child process (auto-start mode)
 * or connects to an external server (engineUrl in settings).
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import { BackendClient } from './client.js';
import { getVenvPython, ensureVenv } from './venv.js';
import { getVenvDir } from '../config/paths.js';

export interface BackendManagerOptions {
  /** Connect to an external engine URL instead of auto-starting */
  engineUrl?: string | null;
  /** Port for auto-started engine (default: 8741) */
  port?: number;
  /** Path to engine package for local dev install */
  enginePath?: string;
  /** Progress callback */
  onProgress?: (msg: string) => void;
}

export class BackendManager {
  private process: ChildProcess | null = null;
  private client: BackendClient | null = null;
  private port: number;
  private external: boolean;

  constructor(private options: BackendManagerOptions = {}) {
    this.port = options.port ?? 8741;
    this.external = !!options.engineUrl;
  }

  /**
   * Start or connect to the engine. Returns the client.
   */
  async start(): Promise<BackendClient> {
    const log = this.options.onProgress ?? console.log;

    if (this.options.engineUrl) {
      // External server mode
      this.client = new BackendClient(this.options.engineUrl);
      log(`Connecting to external engine at ${this.options.engineUrl}...`);
      await this.client.waitForHealth(10000);
      return this.client;
    }

    // Auto-start mode
    await ensureVenv(this.options.enginePath, log);

    const python = getVenvPython();
    log(`Starting engine on port ${this.port}...`);

    this.process = spawn(
      python,
      [
        '-m',
        'uvicorn',
        'cadforge_engine.app:create_app',
        '--factory',
        '--host',
        '127.0.0.1',
        '--port',
        String(this.port),
      ],
      {
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
          ...process.env,
          VIRTUAL_ENV: getVenvDir(),
          PATH: `${join(getVenvDir(), 'bin')}:${process.env.PATH}`,
        },
      },
    );

    // Log stderr — suppress routine uvicorn info and noisy dependency warnings
    this.process.stderr?.on('data', (data: Buffer) => {
      const line = data.toString().trim();
      if (!line) return;
      // Skip routine uvicorn info lines
      if (line.includes('INFO:')) return;
      // Skip noisy torch/numpy/transformers warnings during startup
      if (line.includes('UserWarning:') || line.includes('Disabling PyTorch')
        || line.includes('PyTorch was not found') || line.includes('compiled using NumPy')
        || line.includes('pybind11') || line.includes('downgrade to')
        || line.includes('expect that some modules') || line.includes('Traceback')
        || line.includes('File "') || line.startsWith('  ')) return;
      log(`[engine] ${line}`);
    });

    this.process.on('exit', (code) => {
      if (code !== null && code !== 0) {
        log(`[engine] Process exited with code ${code}`);
      }
      this.process = null;
    });

    // Wait for health — engine can be slow to start when loading heavy deps
    this.client = new BackendClient(`http://127.0.0.1:${this.port}`);
    await this.client.waitForHealth(60000);
    log('Engine ready.');

    return this.client;
  }

  /**
   * Get the client (must call start() first).
   */
  getClient(): BackendClient {
    if (!this.client) {
      throw new Error('Backend not started. Call start() first.');
    }
    return this.client;
  }

  /**
   * Stop the engine process (no-op for external servers).
   */
  async stop(): Promise<void> {
    if (this.process) {
      this.process.kill('SIGTERM');
      // Give it time to shut down gracefully
      await new Promise<void>((resolve) => {
        const timer = setTimeout(() => {
          this.process?.kill('SIGKILL');
          resolve();
        }, 5000);
        this.process?.on('exit', () => {
          clearTimeout(timer);
          resolve();
        });
      });
      this.process = null;
    }
  }

  /**
   * Whether the engine is running.
   */
  isRunning(): boolean {
    if (this.external) return this.client !== null;
    return this.process !== null && this.process.exitCode === null;
  }
}
