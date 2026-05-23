/**
 * useCanvasUndoRedo — client-side command stack for canvas position changes.
 *
 * V1 limitation: tracks position (move) changes only. Add/delete are not
 * undoable; that requires a more complex reverse-operation model and is
 * deferred per Phase 7 PR D scope.
 */

import { useRef } from 'react';

export interface MoveCommand {
  type: 'move';
  itemId: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

export interface UndoRedoApi {
  push: (cmd: MoveCommand) => void;
  undo: () => MoveCommand | null;
  redo: () => MoveCommand | null;
  clear: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
}

export function createUndoRedoStack(): UndoRedoApi {
  const undoStack: MoveCommand[] = [];
  const redoStack: MoveCommand[] = [];

  return {
    push(cmd) {
      undoStack.push(cmd);
      redoStack.length = 0;
    },
    undo() {
      const cmd = undoStack.pop();
      if (!cmd) return null;
      redoStack.push(cmd);
      // Return the reverse move so the caller can apply it.
      return {
        type: 'move',
        itemId: cmd.itemId,
        fromX: cmd.toX,
        fromY: cmd.toY,
        toX: cmd.fromX,
        toY: cmd.fromY,
      };
    },
    redo() {
      const cmd = redoStack.pop();
      if (!cmd) return null;
      undoStack.push(cmd);
      return cmd;
    },
    clear() {
      undoStack.length = 0;
      redoStack.length = 0;
    },
    canUndo() {
      return undoStack.length > 0;
    },
    canRedo() {
      return redoStack.length > 0;
    },
  };
}

export function useCanvasUndoRedo(): UndoRedoApi {
  const ref = useRef<UndoRedoApi | null>(null);
  if (!ref.current) {
    ref.current = createUndoRedoStack();
  }
  return ref.current;
}
