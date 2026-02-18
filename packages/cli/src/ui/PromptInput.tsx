/**
 * Prompt input — custom text input using Ink's useInput.
 * Supports typing, backspace, cursor movement (left/right), enter to submit.
 * Multi-line via backslash continuation. Disabled while agent is processing.
 */

import React, { useState, useCallback } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { InteractionMode } from '../agent/modes.js';
import { MODE_COLORS, modePromptPrefix } from '../agent/modes.js';

interface PromptInputProps {
  mode: InteractionMode;
  isProcessing: boolean;
  onSubmit: (text: string) => void;
}

export function PromptInput({ mode, isProcessing, onSubmit }: PromptInputProps): React.ReactElement {
  const { isRawModeSupported } = useStdin();
  const [value, setValue] = useState('');
  const [cursor, setCursor] = useState(0);
  const [continuation, setContinuation] = useState<string[]>([]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;

    // Backslash continuation
    if (trimmed.endsWith('\\')) {
      setContinuation((prev) => [...prev, trimmed.slice(0, -1)]);
      setValue('');
      setCursor(0);
      return;
    }

    const fullInput = continuation.length > 0
      ? [...continuation, trimmed].join('\n')
      : trimmed;

    setValue('');
    setCursor(0);
    setContinuation([]);
    onSubmit(fullInput);
  }, [value, continuation, onSubmit]);

  useInput((input, key) => {
    if (isProcessing) return;

    if (key.return) {
      handleSubmit();
      return;
    }

    if (key.backspace || key.delete) {
      if (cursor > 0) {
        setValue((v) => v.slice(0, cursor - 1) + v.slice(cursor));
        setCursor((c) => c - 1);
      }
      return;
    }

    if (key.leftArrow) {
      setCursor((c) => Math.max(0, c - 1));
      return;
    }

    if (key.rightArrow) {
      setCursor((c) => Math.min(value.length, c + 1));
      return;
    }

    // Home / End
    if (key.ctrl && input === 'a') {
      setCursor(0);
      return;
    }
    if (key.ctrl && input === 'e') {
      setCursor(value.length);
      return;
    }

    // Kill line (Ctrl+K)
    if (key.ctrl && input === 'k') {
      setValue((v) => v.slice(0, cursor));
      return;
    }

    // Clear input (Ctrl+U)
    if (key.ctrl && input === 'u') {
      setValue('');
      setCursor(0);
      return;
    }

    // Ignore other control sequences
    if (key.ctrl || key.meta || key.escape) return;
    if (key.upArrow || key.downArrow) return;
    if (key.tab) return;

    // Regular character input
    if (input) {
      setValue((v) => v.slice(0, cursor) + input + v.slice(cursor));
      setCursor((c) => c + input.length);
    }
  }, { isActive: isRawModeSupported && !isProcessing });

  const prefix = modePromptPrefix(mode);
  const modeColor = MODE_COLORS[mode];

  if (isProcessing) {
    return (
      <Box>
        <Text color={modeColor} dimColor>{prefix}</Text>
      </Box>
    );
  }

  // Render cursor inline
  const before = value.slice(0, cursor);
  const cursorChar = value[cursor] ?? ' ';
  const after = value.slice(cursor + 1);

  return (
    <Box flexDirection="column">
      {continuation.length > 0 && (
        <Box marginLeft={2}>
          <Text dimColor>{continuation.map((l) => l + '\\').join('\n')}</Text>
        </Box>
      )}
      <Box>
        <Text color={modeColor} bold>{prefix}</Text>
        <Text>{before}</Text>
        <Text inverse>{cursorChar}</Text>
        <Text>{after}</Text>
      </Box>
    </Box>
  );
}
