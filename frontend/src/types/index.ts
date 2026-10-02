// TypeScript types mirroring the backend Pydantic schemas (Phases 1-6).
// Field names are taken verbatim from the API responses — do not guess.

// ─── Auth ────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// ─── Cloud connections ───────────────────────────────────────────────────────

export type CloudProvider = "google_drive" | "s3";

export interface ConnectionStatus {
  provider: string;
  is_connected: boolean;
  account_identifier: string | null;
  connected_at: string | null;
  detail: string | null;
}

export interface GoogleConnectResponse {
  authorization_url: string;
  message: string;
}

export interface S3ConnectRequest {
  access_key_id?: string;
  secret_access_key?: string;
  region?: string;
  endpoint_url?: string;
  bucket_name?: string;
}

export interface S3ConnectResponse {
  status: string;
  provider: string;
  bucket: string;
  message: string | null;
}

// ─── Cloud files ─────────────────────────────────────────────────────────────

export interface CloudFile {
  provider: string;
  file_id: string;
  name: string;
  mime_type: string | null;
  size: number | null;
  modified_at: string | null;
  is_folder: boolean;
  parent_id: string | null;
}

// ─── Documents ───────────────────────────────────────────────────────────────

export type ProcessingStatus = "pending" | "processing" | "completed" | "failed";

export interface Document {
  id: string;
  provider: string;
  external_file_id: string;
  file_name: string;
  file_type: string;
  file_size: number | null;
  mime_type: string | null;
  source_path: string | null;
  content_hash: string | null;
  processing_status: ProcessingStatus;
  ocr_required: boolean;
  ocr_completed: boolean;
  embedding_completed: boolean;
  created_at: string;
  modified_at: string;
}

export interface DocumentListResponse {
  total: number;
  items: Document[];
}

export interface ProcessResponse {
  document_id: string;
  status: string;
  message: string;
}

export interface DocumentJob {
  job_type: string | null;
  status: string | null;
  error_message: string | null;
}

export interface DocumentStatus {
  document_id: string;
  file_name: string;
  processing_status: ProcessingStatus | null;
  ocr_required: boolean;
  ocr_completed: boolean;
  embedding_completed: boolean;
  jobs: DocumentJob[];
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  page_number: number | null;
  content: string;
  token_count: number | null;
  created_at: string;
}

export interface ChunkListResponse {
  total: number;
  items: DocumentChunk[];
}

export interface DocumentTable {
  id: string;
  page_number: number | null;
  table_index: number;
  table_data: string[][];
  row_count: number | null;
  col_count: number | null;
  created_at: string;
}

export interface TableListResponse {
  total: number;
  items: DocumentTable[];
}

// ─── AI features: shared source attribution ──────────────────────────────────

export interface FeatureSource {
  document_id: string | null;
  chunk_id: string;
  filename: string | null;
  page_number: number | null;
  score: number | null;
}

export interface SummarizeResponse {
  document_id: string;
  filename: string | null;
  summary: string;
  sources: FeatureSource[];
  provider: string | null;
}

// ─── Semantic search (Phase 4) ───────────────────────────────────────────────

export interface SearchRequest {
  query: string;
  limit?: number;
  min_score?: number;
  document_id?: string;
  mime_type?: string;
  source?: CloudProvider;
}

export interface SearchHit {
  score: number;
  chunk_id: string | null;
  chunk_index: number | null;
  page_number: number | null;
  content: string | null;
  token_count: number | null;
  document_id: string | null;
  file_name: string | null;
  mime_type: string | null;
  source: string | null;
}

export interface SearchResponse {
  query: string;
  total: number;
  results: SearchHit[];
}

// ─── RAG chat (Phase 5) ──────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
  limit?: number;
  min_score?: number;
}

export interface ChatSource {
  document_id: string | null;
  chunk_id: string;
  filename: string | null;
  page_number: number | null;
  score: number;
}

export interface ChatResponse {
  message: string;
  answer: string;
  sources: ChatSource[];
}

// ─── Multi-document analysis (Phase 6) ───────────────────────────────────────

export interface AnalysisRequest {
  document_ids: string[];
  question: string;
}

export interface AnalysisResponse {
  question: string;
  analysis: string;
  sources: FeatureSource[];
  provider: string | null;
}

// ─── Report generation (Phase 6) ─────────────────────────────────────────────

export interface ReportGenerateRequest {
  document_ids: string[];
  instruction: string;
}

export interface StructuredReport {
  executive_summary: string;
  key_findings: string;
  evidence: string;
  recommendations: string;
  conclusion: string;
}

export interface ReportResponse {
  instruction: string;
  report: StructuredReport;
  sources: FeatureSource[];
  provider: string | null;
}
