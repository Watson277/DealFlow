export interface Customer {
  id: string;
  name: string;
  code: string;
  industry: string | null;
  website: string | null;
  primary_contact_name: string | null;
  primary_contact_email: string | null;
  created_at: string;
}

export interface RFP {
  id: string;
  customer_id: string;
  title: string;
  reference_number: string | null;
  status: string;
  current_stage: string;
  priority: string;
  due_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RFPStatus {
  rfp_id: string;
  status: string;
  current_stage: string;
  stage_label: string;
  progress_percent: number;
  stage_started_at: string | null;
  elapsed_seconds: number;
  attempt: number;
  is_terminal: boolean;
  error_message: string | null;
  updated_at: string;
}

export interface KnowledgeDocument {
  id: string;
  status: string;
  original_filename: string;
  size_bytes: number;
  content_hash: string | null;
  document_version: string | null;
  knowledge_category: string | null;
  parsed_text_object_key: string | null;
  parsed_ir_object_key: string | null;
  extra_data: Record<string, unknown>;
  created_at: string;
}

export interface Requirement {
  id: string;
  requirement_key: string;
  category: string;
  requirement_text: string;
  mandatory: boolean;
  confidence: number | null;
}

export interface Capability {
  id: string;
  requirement_key: string;
  requirement_text: string;
  status: string;
  confidence: number | null;
  reason: string;
  customization_notes: string | null;
  evidence: Array<{
    id: string;
    snippet: string;
    retrieval_score: number | null;
  }>;
}

export interface Proposal {
  id: string;
  rfp_id: string;
  version: number;
  status: string;
  title: string;
  executive_summary: string | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
}
