export interface KnowledgeBase {
  id: string;
  user_id: string;
  name: string;
  slug: string;
  root_path?: string;
  description: string | null;
  is_shared: boolean;
  source_count: number;
  wiki_page_count: number;
  owner_email: string | null;
  owner_name: string | null;
  workspace_id: string | null;
  workspace_slug: string | null;
  workspace_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface Favorite {
  kb_id: string;
  created_at: string;
}

export interface SpaceInfo {
  id: string;
  name: string;
  slug: string;
  root_path: string;
  description: string;
  wiki_page_count: number;
  source_count: number;
}

export interface Document {
  id: string;
  knowledge_base_id: string;
  user_id: string;
  filename: string;
  title: string | null;
  path: string;
  file_type: string;
  file_size: number;
  status: string;
  page_count: number | null;
  content: string | null;
  tags: string[];
  date: string | null;
  metadata: Record<string, unknown> | null;
  error_message: string | null;
  url: string | null;
  version: number;
  document_number: number | null;
  sort_order: number | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export type DocumentListItem = Omit<Document, "content">;

export type PropertyType =
  | "text"
  | "number"
  | "date"
  | "checkbox"
  | "select"
  | "url";

export interface TypedProperty {
  type: PropertyType;
  value: string | number | boolean | null;
  options?: string[];
}

export type PropertyMap = Record<string, TypedProperty>;

export interface WikiNode {
  title: string;
  path?: string;
  docNumber?: number | null;
  docId?: string | null;
  children?: WikiNode[];
}

export interface WikiSubsection {
  id: string;
  title: string;
}

export interface HistoryVersion {
  id: string;
  document_id: string;
  user_id: string | null;
  version: number;
  content_length: number;
  created_at: string;
}

export interface LatexTemplate {
  id: string;
  name: string;
  display_name: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  created_by: string;
  member_count: number;
  wiki_count: number;
  is_member: boolean;
  created_at: string;
  updated_at: string;
}
