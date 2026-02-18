/**
 * Auto-venv creation and pip install for the Python engine.
 *
 * On first run, finds python3, creates a venv at ~/.cadforge/.venv/,
 * and pip-installs cadforge-engine[all].
 */

import { execSync, execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { getVenvDir } from '../config/paths.js';

/**
 * Find a usable python3 binary.
 */
function findPython(): string {
  for (const name of ['python3', 'python']) {
    try {
      const version = execSync(`${name} --version`, {
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      }).trim();
      // Require Python 3.10+
      const match = version.match(/Python (\d+)\.(\d+)/);
      if (match) {
        const major = parseInt(match[1], 10);
        const minor = parseInt(match[2], 10);
        if (major === 3 && minor >= 10) return name;
      }
    } catch {
      // not found, try next
    }
  }
  throw new Error(
    'Python 3.10+ not found. Install Python from https://python.org or use conda.',
  );
}

/**
 * Get the path to the pip binary inside the venv.
 */
function getVenvPip(venvDir: string): string {
  return join(venvDir, 'bin', 'pip');
}

/**
 * Get the path to the python binary inside the venv.
 */
export function getVenvPython(venvDir?: string): string {
  const d = venvDir ?? getVenvDir();
  return join(d, 'bin', 'python');
}

/**
 * Check if the venv exists and has the engine installed.
 */
export function isVenvReady(): boolean {
  const venvDir = getVenvDir();
  const pip = getVenvPip(venvDir);
  if (!existsSync(pip)) return false;

  try {
    const output = execFileSync(pip, ['show', 'cadforge-engine'], {
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return output.includes('cadforge-engine');
  } catch {
    return false;
  }
}

/**
 * Create the venv and install the engine.
 * This is called on first run if the venv doesn't exist.
 *
 * @param enginePath - Path to the engine package directory (for local dev install)
 * @param onProgress - Callback for progress messages
 */
export async function ensureVenv(
  enginePath?: string,
  onProgress?: (msg: string) => void,
): Promise<void> {
  if (isVenvReady()) return;

  const venvDir = getVenvDir();
  const log = onProgress ?? console.log;

  // Step 1: Find python
  log('Finding Python 3.10+...');
  const python = findPython();
  log(`Using ${python}`);

  // Step 2: Create venv
  if (!existsSync(join(venvDir, 'bin', 'python'))) {
    log('Creating Python virtual environment...');
    execSync(`${python} -m venv "${venvDir}"`, { stdio: 'inherit' });
  }

  // Step 3: Upgrade pip
  const pip = getVenvPip(venvDir);
  log('Upgrading pip...');
  execFileSync(pip, ['install', '--upgrade', 'pip'], { stdio: 'inherit' });

  // Step 4: Install engine
  if (enginePath) {
    // Local development: install from source
    log('Installing cadforge-engine from local source...');
    execFileSync(pip, ['install', '-e', `${enginePath}[all]`], {
      stdio: 'inherit',
    });
  } else {
    // Production: install from PyPI
    log('Installing cadforge-engine...');
    execFileSync(pip, ['install', 'cadforge-engine[all]'], {
      stdio: 'inherit',
    });
  }

  log('Python engine ready.');
}
