/**
 * canvas-keyboard.test.ts — Phase 7 PR D
 *
 * Tests for the client-side undo/redo command stack used by CanvasEditorPage.
 */

import { describe, it, expect } from 'vitest';
import { createUndoRedoStack, type MoveCommand } from '../hooks/useCanvasUndoRedo';

function move(itemId: string, fromX: number, fromY: number, toX: number, toY: number): MoveCommand {
  return { type: 'move', itemId, fromX, fromY, toX, toY };
}

describe('canvas undo/redo stack', () => {
  it('push + undo returns the reverse move and restores previous position', () => {
    const s = createUndoRedoStack();
    s.push(move('a', 0, 0, 100, 50));
    expect(s.canUndo()).toBe(true);
    const reversed = s.undo();
    expect(reversed).not.toBeNull();
    expect(reversed!.itemId).toBe('a');
    // The reverse should travel back from (100,50) to (0,0).
    expect(reversed!.fromX).toBe(100);
    expect(reversed!.fromY).toBe(50);
    expect(reversed!.toX).toBe(0);
    expect(reversed!.toY).toBe(0);
  });

  it('push + undo + redo restores the new position', () => {
    const s = createUndoRedoStack();
    s.push(move('a', 0, 0, 100, 50));
    s.undo();
    expect(s.canRedo()).toBe(true);
    const redone = s.redo();
    expect(redone).not.toBeNull();
    expect(redone!.itemId).toBe('a');
    expect(redone!.toX).toBe(100);
    expect(redone!.toY).toBe(50);
  });

  it('empty undo stack: undo() returns null', () => {
    const s = createUndoRedoStack();
    expect(s.canUndo()).toBe(false);
    expect(s.undo()).toBeNull();
  });

  it('empty redo stack: redo() returns null', () => {
    const s = createUndoRedoStack();
    expect(s.canRedo()).toBe(false);
    expect(s.redo()).toBeNull();
  });

  it('new push after undo clears the redo stack', () => {
    const s = createUndoRedoStack();
    s.push(move('a', 0, 0, 10, 10));
    s.undo();
    expect(s.canRedo()).toBe(true);
    s.push(move('b', 0, 0, 5, 5));
    expect(s.canRedo()).toBe(false);
  });

  it('multiple pushes undo in LIFO order', () => {
    const s = createUndoRedoStack();
    s.push(move('a', 0, 0, 10, 0));
    s.push(move('b', 0, 0, 20, 0));
    const first = s.undo();
    expect(first!.itemId).toBe('b');
    const second = s.undo();
    expect(second!.itemId).toBe('a');
  });

  it('clear() empties both stacks', () => {
    const s = createUndoRedoStack();
    s.push(move('a', 0, 0, 10, 10));
    s.undo();
    s.clear();
    expect(s.canUndo()).toBe(false);
    expect(s.canRedo()).toBe(false);
  });
});
