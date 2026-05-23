import { apiDelete, apiGet, apiPatch, apiPost } from './client';

// ---------------------------------------------------------------------------
// Backend schema types (Phase 7 — Visual Thinking Canvas)
// ---------------------------------------------------------------------------

export type CanvasItemType = 'note' | 'group' | 'text';
export type CanvasEdgeStyle = 'default' | 'dashed' | 'bold';

export interface CanvasOut {
  id: string;
  title: string;
  description: string | null;
  viewport_x: number;
  viewport_y: number;
  viewport_zoom: number;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface CanvasItemOut {
  id: string;
  canvas_id: string;
  note_id: string | null;
  item_type: CanvasItemType;
  position_x: number;
  position_y: number;
  width: number | null;
  height: number | null;
  color: string | null;
  label: string | null;
  z_index: number;
  version: number;
  last_known_title: string | null;
  note_title: string | null;
  note_summary: string | null;
  note_content: string | null;
  created_at: string;
  updated_at: string;
}

export interface CanvasEdgeOut {
  id: string;
  canvas_id: string;
  source_item_id: string;
  target_item_id: string;
  label: string | null;
  style: CanvasEdgeStyle;
  created_at: string;
}

export interface CanvasDetailOut extends CanvasOut {
  items: CanvasItemOut[];
  edges: CanvasEdgeOut[];
}

export interface CanvasListResponse {
  items: CanvasOut[];
  total: number;
}

export interface CanvasCreate {
  title?: string;
  description?: string;
}

export interface CanvasUpdate {
  title?: string;
  description?: string;
  viewport_x?: number;
  viewport_y?: number;
  viewport_zoom?: number;
}

export interface CanvasItemCreate {
  note_id?: string;
  item_type: CanvasItemType;
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
  color?: string;
  label?: string;
  z_index?: number;
}

export interface CanvasItemUpdate {
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
  color?: string;
  label?: string;
  z_index?: number;
  version: number;
}

export interface BatchItemEntry {
  id: string;
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
  z_index?: number;
  version: number;
}

export interface CanvasEdgeCreate {
  source_item_id: string;
  target_item_id: string;
  label?: string;
  style?: CanvasEdgeStyle;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function listCanvases(): Promise<CanvasListResponse> {
  return apiGet<CanvasListResponse>('/api/canvases');
}

export async function createCanvas(data: CanvasCreate = {}): Promise<CanvasOut> {
  return apiPost<CanvasOut>('/api/canvases', data);
}

export async function getCanvas(id: string): Promise<CanvasDetailOut> {
  return apiGet<CanvasDetailOut>(`/api/canvases/${id}`);
}

export async function updateCanvas(id: string, patch: CanvasUpdate): Promise<CanvasOut> {
  return apiPatch<CanvasOut>(`/api/canvases/${id}`, patch);
}

export async function deleteCanvas(id: string): Promise<void> {
  return apiDelete(`/api/canvases/${id}`);
}

export async function addCanvasItem(
  canvasId: string,
  item: CanvasItemCreate,
): Promise<CanvasItemOut> {
  return apiPost<CanvasItemOut>(`/api/canvases/${canvasId}/items`, item);
}

export async function updateCanvasItem(
  canvasId: string,
  itemId: string,
  patch: CanvasItemUpdate,
): Promise<CanvasItemOut> {
  return apiPatch<CanvasItemOut>(`/api/canvases/${canvasId}/items/${itemId}`, patch);
}

export async function batchUpdateItems(
  canvasId: string,
  items: BatchItemEntry[],
): Promise<CanvasItemOut[]> {
  const resp = await apiPost<{ items: CanvasItemOut[] }>(`/api/canvases/${canvasId}/items/batch`, { items });
  return resp.items;
}

export async function deleteCanvasItem(canvasId: string, itemId: string): Promise<void> {
  return apiDelete(`/api/canvases/${canvasId}/items/${itemId}`);
}

export async function addCanvasEdge(
  canvasId: string,
  edge: CanvasEdgeCreate,
): Promise<CanvasEdgeOut> {
  return apiPost<CanvasEdgeOut>(`/api/canvases/${canvasId}/edges`, edge);
}

export async function deleteCanvasEdge(canvasId: string, edgeId: string): Promise<void> {
  return apiDelete(`/api/canvases/${canvasId}/edges/${edgeId}`);
}

export async function autoLayoutCanvas(canvasId: string): Promise<CanvasItemOut[]> {
  const resp = await apiPost<{ items: CanvasItemOut[] }>(`/api/canvases/${canvasId}/auto-layout`, {});
  return resp.items;
}
