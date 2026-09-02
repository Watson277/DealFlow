import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  Building2,
  Check,
  ChevronRight,
  CircleGauge,
  FileCheck2,
  FileText,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { api } from "./api";
import { MarkdownPreview } from "./MarkdownPreview";
import type {
  Capability,
  Customer,
  KnowledgeDocument,
  Proposal,
  Requirement,
  RFP,
  RFPStatus,
} from "./types";

type View = "overview" | "rfps" | "knowledge" | "customers";
type Panel = "rfp" | "knowledge" | "customer" | null;
type DetailTab = "requirements" | "capabilities" | "proposal";

const statusText: Record<string, string> = {
  QUEUED: "等待处理",
  PROCESSING: "处理中",
  REVIEW_PENDING: "待审核",
  APPROVED: "已通过",
  FAILED: "失败",
  READY: "可用",
  UPLOADED: "已上传",
  CHANGES_REQUESTED: "等待修改",
  SUPPORTED: "支持",
  PARTIALLY_SUPPORTED: "部分支持",
  UNSUPPORTED: "不支持",
  NEED_REVIEW: "需确认",
  ENTERPRISE_ONLY: "仅企业版",
  REQUIRES_CUSTOMIZATION: "需定制",
};

const navItems = [
  { id: "overview" as const, label: "总览", icon: LayoutDashboard },
  { id: "rfps" as const, label: "RFP 工作台", icon: FileText },
  { id: "knowledge" as const, label: "企业知识库", icon: BookOpen },
  { id: "customers" as const, label: "客户管理", icon: Building2 },
];

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`,
  );
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`status status-${value.toLowerCase()}`}>
      {statusText[value] ?? value}
    </span>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <FileText size={22} />
      </div>
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("overview");
  const [panel, setPanel] = useState<Panel>(null);
  const [rfps, setRfps] = useState<RFP[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [knowledge, setKnowledge] = useState<KnowledgeDocument[]>([]);
  const [statuses, setStatuses] = useState<Record<string, RFPStatus>>({});
  const [selectedRFP, setSelectedRFP] = useState<RFP | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("requirements");
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const refreshing = useRef(false);
  const dataVersion = useRef(0);
  const deleting = useRef(false);
  const loadedDetailId = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    const version = dataVersion.current;
    try {
      const [rfpPage, customerPage, knowledgePage] = await Promise.all([
        api.rfps(),
        api.customers(),
        api.knowledge(),
      ]);
      if (version !== dataVersion.current) return;
      setRfps(rfpPage.items);
      setSelectedRFP((current) =>
        current
          ? (rfpPage.items.find((item) => item.id === current.id) ?? null)
          : null,
      );
      setCustomers(customerPage.items);
      setKnowledge(knowledgePage.items);
      const nextStatuses = await Promise.all(
        rfpPage.items.map(
          async (item) => [item.id, await api.status(item.id)] as const,
        ),
      );
      if (version !== dataVersion.current) return;
      setStatuses(Object.fromEntries(nextStatuses));
      setRefreshVersion((value) => value + 1);
    } catch (reason) {
      if (version === dataVersion.current)
        setError(reason instanceof Error ? reason.message : "数据加载失败");
    } finally {
      refreshing.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) void loadAll();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadAll]);

  const selectedId = selectedRFP?.id;
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    if (loadedDetailId.current !== selectedId) setDetailLoading(true);
    const load = async () => {
      try {
        const [requirementPage, capabilityPage, proposalPage] =
          await Promise.all([
            api.requirements(selectedId),
            api.capabilities(selectedId),
            api.proposals(selectedId),
          ]);
        const latest = proposalPage.items[0];
        const nextMarkdown = latest ? await api.markdown(latest.id) : "";
        if (cancelled) return;
        setRequirements(requirementPage.items);
        setCapabilities(capabilityPage.items);
        setProposals(proposalPage.items);
        setMarkdown(nextMarkdown);
        loadedDetailId.current = selectedId;
      } catch (reason) {
        if (!cancelled)
          setError(
            reason instanceof Error ? reason.message : "RFP 详情加载失败",
          );
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshVersion]);

  const openRFP = useCallback((rfp: RFP, tab: DetailTab = "requirements") => {
    loadedDetailId.current = null;
    setSelectedRFP(rfp);
    setDetailTab(tab);
    setView("rfps");
    setRequirements([]);
    setCapabilities([]);
    setProposals([]);
    setMarkdown("");
  }, []);

  const runAction = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      setNotice(success);
      setPanel(null);
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  const deleteItem = async (kind: "rfp" | "customer" | "knowledge", id: string, name: string) => {
    if (busy || deleting.current) return;
    const labels = { rfp: "任务", customer: "客户", knowledge: "知识库文档" };
    const details = {
      rfp: "任务及关联方案将从工作台移除，不再进入后续阶段。当前阶段无法保证即时停止，模型调用可能仍会完成，但结果不会保存。",
      customer: "有关联任务时不能删除，请先删除该客户的全部任务。客户编码仍保留，不能重复使用。",
      knowledge: "文档将从知识库移除，向量索引将删除，不再用于后续检索；已有方案和证据不变。正在索引的文档需等待完成。",
    };
    if (!window.confirm(`确认删除${labels[kind]}“${name}”？\n\n${details[kind]}\n\n底层记录和原始文件保留，界面暂不提供恢复入口。`)) return;
    deleting.current = true;
    setBusy(true);
    setError(null);
    try {
      if (kind === "rfp") await api.deleteRFP(id);
      else if (kind === "customer") await api.deleteCustomer(id);
      else await api.deleteKnowledge(id);
      // Discard polling responses fetched before this deletion completed.
      dataVersion.current += 1;
      if (kind === "rfp") {
        setRfps((items) => items.filter((item) => item.id !== id));
        setSelectedRFP((item) => item?.id === id ? null : item);
        setStatuses((items) => {
          const next = { ...items };
          delete next[id];
          return next;
        });
      } else if (kind === "customer") {
        setCustomers((items) => items.filter((item) => item.id !== id));
      } else {
        setKnowledge((items) => items.filter((item) => item.id !== id));
      }
      setNotice(`${labels[kind]}已删除`);
      await loadAll();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除失败，请重试");
    } finally {
      deleting.current = false;
      setBusy(false);
    }
  };

  const filteredRFPs = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase();
    if (!keyword) return rfps;
    return rfps.filter((item) =>
      `${item.title} ${item.reference_number ?? ""}`
        .toLocaleLowerCase()
        .includes(keyword),
    );
  }, [rfps, search]);

  const activeCount = Object.values(statuses).filter(
    (item) => item.status === "PROCESSING" || item.status === "QUEUED",
  ).length;
  const reviewCount = rfps.filter(
    (item) => item.status === "REVIEW_PENDING",
  ).length;
  const latestProposal = proposals[0];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Sparkles size={19} />
          </div>
          <div>
            <strong>DealFlow</strong>
            <span>Proposal Intelligence</span>
          </div>
        </div>
        <nav>
          <p className="nav-label">工作空间</p>
          {navItems.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => {
                setView(id);
                setSelectedRFP(null);
              }}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === "rfps" && reviewCount > 0 && <em>{reviewCount}</em>}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="system-dot" />
          <div>
            <strong>自动化流程</strong>
            <span>
              {activeCount ? `${activeCount} 个任务运行中` : "当前空闲"}
            </span>
          </div>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <span className="eyebrow">
              DEALFLOW / {navItems.find((item) => item.id === view)?.label}
            </span>
            <h1>
              {selectedRFP
                ? selectedRFP.title
                : navItems.find((item) => item.id === view)?.label}
            </h1>
          </div>
          <div className="top-actions">
            <button
              className="icon-button"
              aria-label="刷新"
              onClick={() => void loadAll()}
            >
              <RefreshCw size={18} />
            </button>
            <button className="primary" onClick={() => setPanel("rfp")}>
              <Plus size={17} />
              新建 RFP
            </button>
          </div>
        </header>

        {error && (
          <div className="alert error">
            <AlertCircle size={18} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="alert success">
            <Check size={18} />
            <span>{notice}</span>
            <button onClick={() => setNotice(null)}>
              <X size={16} />
            </button>
          </div>
        )}

        <div className="content">
          {loading ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              正在连接 DealFlow…
            </div>
          ) : null}

          {!loading && view === "overview" && (
            <>
              <section className="hero-card">
                <div>
                  <span className="hero-kicker">
                    <Sparkles size={15} /> 智能投标工作流
                  </span>
                  <h2>
                    从客户文档到可审核方案，
                    <br />
                    让每一步都有依据。
                  </h2>
                  <p>需求抽取、企业能力匹配与方案生成在同一条工作流中完成。</p>
                  <button
                    className="hero-button"
                    onClick={() => setPanel("rfp")}
                  >
                    开始处理 RFP <ArrowRight size={17} />
                  </button>
                </div>
                <div className="workflow-orbit">
                  <div className="orbit-center">
                    <Sparkles size={28} />
                  </div>
                  <span className="orbit-node node-a">需求</span>
                  <span className="orbit-node node-b">能力</span>
                  <span className="orbit-node node-c">方案</span>
                </div>
              </section>

              <section className="metric-grid">
                <article>
                  <div className="metric-icon blue">
                    <FileText />
                  </div>
                  <span>全部 RFP</span>
                  <strong>{rfps.length}</strong>
                  <small>已进入系统</small>
                </article>
                <article>
                  <div className="metric-icon amber">
                    <CircleGauge />
                  </div>
                  <span>运行中</span>
                  <strong>{activeCount}</strong>
                  <small>自动处理任务</small>
                </article>
                <article>
                  <div className="metric-icon violet">
                    <FileCheck2 />
                  </div>
                  <span>待审核</span>
                  <strong>{reviewCount}</strong>
                  <small>需要人工决策</small>
                </article>
                <article>
                  <div className="metric-icon green">
                    <BookOpen />
                  </div>
                  <span>知识文档</span>
                  <strong>{knowledge.length}</strong>
                  <small>能力判断依据</small>
                </article>
              </section>

              <section className="section-card">
                <div className="section-heading">
                  <div>
                    <span>最近动态</span>
                    <h3>RFP 处理进度</h3>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setView("rfps")}
                  >
                    查看全部 <ChevronRight size={16} />
                  </button>
                </div>
                {rfps.length ? (
                  <RFPTable
                    items={rfps.slice(0, 5)}
                    customers={customers}
                    statuses={statuses}
                    onOpen={openRFP}
                    onDelete={(item) => void deleteItem("rfp", item.id, item.title)}
                    busy={busy}
                  />
                ) : (
                  <EmptyState
                    title="还没有 RFP"
                    detail="上传客户文档后，处理进度会显示在这里。"
                  />
                )}
              </section>
            </>
          )}

          {!loading && view === "rfps" && !selectedRFP && (
            <section className="section-card full-card">
              <div className="section-heading tools">
                <div>
                  <span>PIPELINE</span>
                  <h3>RFP 工作台</h3>
                </div>
                <label className="search-box">
                  <Search size={17} />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    aria-label="搜索 RFP"
                  />
                </label>
              </div>
              {filteredRFPs.length ? (
                <RFPTable
                  items={filteredRFPs}
                  customers={customers}
                  statuses={statuses}
                  onOpen={openRFP}
                  onDelete={(item) => void deleteItem("rfp", item.id, item.title)}
                  busy={busy}
                />
              ) : (
                <EmptyState
                  title="没有匹配的 RFP"
                  detail="调整搜索条件，或新建一个 RFP。"
                />
              )}
            </section>
          )}

          {!loading && view === "rfps" && selectedRFP && (
            <RFPDetail
              key={selectedRFP.id}
              rfp={selectedRFP}
              status={statuses[selectedRFP.id]}
              requirements={requirements}
              capabilities={capabilities}
              proposals={proposals}
              markdown={markdown}
              tab={detailTab}
              busy={busy || detailLoading}
              onTab={setDetailTab}
              onBack={() => setSelectedRFP(null)}
              onDelete={() => void deleteItem("rfp", selectedRFP.id, selectedRFP.title)}
              onRetry={() =>
                void runAction(
                  () => api.retry(selectedRFP.id),
                  "已重新提交失败阶段",
                )
              }
              onReview={(decision, comment) =>
                latestProposal &&
                void runAction(
                  () => api.review(latestProposal.id, decision, comment),
                  decision === "APPROVED" ? "方案已通过审核" : "修改意见已提交",
                )
              }
            />
          )}

          {!loading && view === "knowledge" && (
            <section className="section-card full-card">
              <div className="section-heading">
                <div>
                  <span>GROUNDING</span>
                  <h3>企业知识库</h3>
                </div>
                <button
                  className="secondary"
                  onClick={() => setPanel("knowledge")}
                >
                  <UploadCloud size={17} />
                  上传文档
                </button>
              </div>
              {knowledge.length ? (
                <div className="document-grid">
                  {knowledge.map((item) => (
                    <DocumentCard key={item.id} item={item} busy={busy}
                      onDelete={() => void deleteItem("knowledge", item.id, String(item.extra_data.title ?? item.original_filename))} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="知识库为空"
                  detail="上传企业资料后，能力判断将基于文档证据进行。"
                />
              )}
            </section>
          )}

          {!loading && view === "customers" && (
            <section className="section-card full-card">
              <div className="section-heading">
                <div>
                  <span>ACCOUNTS</span>
                  <h3>客户管理</h3>
                </div>
                <button
                  className="secondary"
                  onClick={() => setPanel("customer")}
                >
                  <Plus size={17} />
                  新增客户
                </button>
              </div>
              {customers.length ? (
                <div className="customer-grid">
                  {customers.map((item) => (
                    <CustomerCard key={item.id} item={item} busy={busy}
                      onDelete={() => void deleteItem("customer", item.id, item.name)} />
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="还没有客户"
                  detail="创建客户后即可为其上传 RFP。"
                />
              )}
            </section>
          )}
        </div>
      </main>

      {panel && (
        <SidePanel
          panel={panel}
          customers={customers}
          busy={busy}
          onClose={() => {
            if (!busy) setPanel(null);
          }}
          onSubmit={runAction}
        />
      )}
    </div>
  );
}

function RFPTable({
  items,
  customers,
  statuses,
  onOpen,
  onDelete,
  busy,
}: {
  items: RFP[];
  customers: Customer[];
  statuses: Record<string, RFPStatus>;
  onOpen: (rfp: RFP) => void;
  onDelete: (rfp: RFP) => void;
  busy: boolean;
}) {
  const customerNames = Object.fromEntries(
    customers.map((item) => [item.id, item.name]),
  );
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>RFP</th>
            <th>客户</th>
            <th>状态</th>
            <th>当前阶段</th>
            <th>进度</th>
            <th>更新时间</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const state = statuses[item.id];
            return (
              <tr key={item.id} onClick={() => onOpen(item)}>
                <td>
                  <button
                    className="rfp-title"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(item);
                    }}
                  >
                    {item.title}
                  </button>
                  <small>{item.reference_number ?? "未设置编号"}</small>
                </td>
                <td>{customerNames[item.customer_id] ?? "—"}</td>
                <td>
                  <StatusBadge value={item.status} />
                </td>
                <td>{state?.stage_label ?? item.current_stage}</td>
                <td>
                  <div className="mini-progress">
                    <span>
                      <i
                        style={{ width: `${state?.progress_percent ?? 0}%` }}
                      />
                    </span>
                    <em>{state?.progress_percent ?? 0}%</em>
                  </div>
                </td>
                <td>{formatDate(item.updated_at)}</td>
                <td>
                  <div className="row-actions">
                    <button className="danger-button" disabled={busy}
                      aria-label={`删除任务 ${item.title}`}
                      onClick={(event) => { event.stopPropagation(); onDelete(item); }}>
                      <Trash2 size={15} />删除
                    </button>
                    <ChevronRight size={17} />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RFPDetail({
  rfp,
  status,
  requirements,
  capabilities,
  proposals,
  markdown,
  tab,
  busy,
  onTab,
  onBack,
  onDelete,
  onRetry,
  onReview,
}: {
  rfp: RFP;
  status?: RFPStatus;
  requirements: Requirement[];
  capabilities: Capability[];
  proposals: Proposal[];
  markdown: string;
  tab: DetailTab;
  busy: boolean;
  onTab: (tab: DetailTab) => void;
  onBack: () => void;
  onDelete: () => void;
  onRetry: () => void;
  onReview: (decision: string, comment: string | null) => void;
}) {
  const [comment, setComment] = useState("");
  const proposal = proposals[0];
  return (
    <>
      <div className="detail-actions">
        <button className="back-button" onClick={onBack}>← 返回工作台</button>
        <button className="danger-button" onClick={onDelete} disabled={busy}>
          <Trash2 size={15} />删除任务
        </button>
      </div>
      <section className="progress-card">
        <div className="progress-top">
          <div>
            <StatusBadge value={status?.status ?? rfp.status} />
            <span>手动重试 {status?.attempt ?? 0} 次 · 阶段估算进度</span>
          </div>
          <strong>{status?.progress_percent ?? 0}%</strong>
        </div>
        <div className="progress-track">
          <i style={{ width: `${status?.progress_percent ?? 0}%` }} />
        </div>
        <div className="progress-meta">
          <span>当前阶段：{status?.stage_label ?? rfp.current_stage}</span>
          <span>
            本阶段已用时：{formatDuration(status?.elapsed_seconds ?? 0)}
          </span>
          <span>开始时间：{formatDate(status?.stage_started_at)}</span>
        </div>
        {status?.status === "FAILED" && (
          <div className="inline-error">
            <AlertCircle size={17} />
            <span>{status.error_message ?? "处理失败"}</span>
            <button onClick={onRetry} disabled={busy}>
              <RotateCcw size={16} />
              重试失败阶段
            </button>
          </div>
        )}
      </section>
      <section className="section-card detail-card">
        <div className="tabs">
          <button
            className={tab === "requirements" ? "active" : ""}
            onClick={() => onTab("requirements")}
          >
            需求 <em>{requirements.length}</em>
          </button>
          <button
            className={tab === "capabilities" ? "active" : ""}
            onClick={() => onTab("capabilities")}
          >
            能力判断 <em>{capabilities.length}</em>
          </button>
          <button
            className={tab === "proposal" ? "active" : ""}
            onClick={() => onTab("proposal")}
          >
            方案与审核 <em>{proposals.length}</em>
          </button>
        </div>
        {busy && (
          <div className="loading compact">
            <LoaderCircle className="spin" />
            正在更新…
          </div>
        )}
        {!busy &&
          tab === "requirements" &&
          (requirements.length ? (
            <div className="item-list">
              {requirements.map((item) => (
                <article key={item.id}>
                  <div>
                    <span className="key-pill">{item.requirement_key}</span>
                    {item.mandatory && <span className="mandatory">必选</span>}
                    <small>{item.category}</small>
                  </div>
                  <p>{item.requirement_text}</p>
                  <em>
                    {item.confidence == null
                      ? "—"
                      : `${Math.round(item.confidence * 100)}% 置信度`}
                  </em>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="暂无需求"
              detail="需求抽取完成后将在这里展示。"
            />
          ))}
        {!busy &&
          tab === "capabilities" &&
          (capabilities.length ? (
            <div className="item-list capability-list">
              {capabilities.map((item) => (
                <article key={item.id}>
                  <div>
                    <span className="key-pill">{item.requirement_key}</span>
                    <StatusBadge value={item.status} />
                  </div>
                  <h4>{item.requirement_text}</h4>
                  <p>{item.reason}</p>
                  {item.customization_notes && (
                    <aside>{item.customization_notes}</aside>
                  )}
                  <em>{item.evidence.length} 条证据</em>
                  {item.evidence.length > 0 && (
                    <details className="evidence">
                      <summary>查看证据片段</summary>
                      {item.evidence.map((entry, index) => (
                        <blockquote key={index}>{entry.snippet}</blockquote>
                      ))}
                    </details>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="暂无判断结果"
              detail="能力判断完成后将在这里展示。"
            />
          ))}
        {!busy &&
          tab === "proposal" &&
          (proposal ? (
            <div
              className={`proposal-layout ${proposal.status !== "REVIEW_PENDING" ? "read-only" : ""}`}
            >
              <article className="markdown-view">
                <div className="markdown-toolbar">
                  <span>版本 {proposal.version}</span>
                  <StatusBadge value={proposal.status} />
                  <a
                    href={`/proposals/${proposal.id}/markdown`}
                    download={`proposal-v${proposal.version}.md`}
                  >
                    下载 Markdown
                  </a>
                </div>
                <MarkdownPreview content={markdown} />
              </article>
              {proposal.status === "REVIEW_PENDING" && (
                <aside className="review-panel">
                  <span>人工审核</span>
                  <h3>确认方案是否可以通过</h3>
                  <p>通过后工作流结束；如需修改，请填写具体意见。</p>
                  <textarea
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                    aria-label="修改意见"
                    maxLength={5000}
                  />
                  <button
                    className="approve"
                    onClick={() => onReview("APPROVED", null)}
                    disabled={busy}
                  >
                    <Check size={17} />
                    通过审核
                  </button>
                  <button
                    className="revision"
                    onClick={() =>
                      comment.trim() &&
                      onReview("CHANGES_REQUESTED", comment.trim())
                    }
                    disabled={busy || !comment.trim()}
                  >
                    <RotateCcw size={17} />
                    要求修改
                  </button>
                </aside>
              )}
            </div>
          ) : (
            <EmptyState
              title="方案尚未生成"
              detail="能力判断完成后，Proposal Agent 将生成 Markdown 方案。"
            />
          ))}
      </section>
    </>
  );
}

function DocumentCard({ item, busy, onDelete }: {
  item: KnowledgeDocument; busy: boolean; onDelete: () => void;
}) {
  return (
    <article className="document-card">
      <div className="document-icon">
        <FileText size={21} />
      </div>
      <div>
        <strong>
          {String(item.extra_data.title ?? item.original_filename)}
        </strong>
        <span>
          {item.knowledge_category ?? "未分类"} ·{" "}
          {item.document_version ?? "未设置版本"}
        </span>
        <small>
          {Math.ceil(item.size_bytes / 1024)} KB · {formatDate(item.created_at)}
        </small>
      </div>
      <div className="card-actions">
        <StatusBadge value={item.status} />
        <button className="danger-button" disabled={busy || ["INDEXING", "PARSING"].includes(item.status)}
          aria-label={`删除知识库文档 ${String(item.extra_data.title ?? item.original_filename)}`} onClick={onDelete}>
          <Trash2 size={15} />删除
        </button>
      </div>
    </article>
  );
}

function CustomerCard({ item, busy, onDelete }: {
  item: Customer; busy: boolean; onDelete: () => void;
}) {
  return (
    <article className="customer-card">
      <div className="avatar">{item.name.slice(0, 1).toUpperCase()}</div>
      <div>
        <strong>{item.name}</strong>
        <span>{item.code}</span>
        <small>{item.industry ?? "未设置行业"}</small>
      </div>
      <button className="danger-button" disabled={busy} aria-label={`删除客户 ${item.name}`} onClick={onDelete}>
        <Trash2 size={15} />删除
      </button>
    </article>
  );
}

function SidePanel({
  panel,
  customers,
  busy,
  onClose,
  onSubmit,
}: {
  panel: Exclude<Panel, null>;
  customers: Customer[];
  busy: boolean;
  onClose: () => void;
  onSubmit: (action: () => Promise<unknown>, success: string) => Promise<void>;
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    for (const [key, value] of Array.from(data.entries())) {
      if (typeof value === "string") {
        if (!value.trim()) data.delete(key);
        else data.set(key, value.trim());
      }
    }
    const dueAt = data.get("due_at");
    if (typeof dueAt === "string") {
      // The database stores UTC-naive datetimes; convert the user's local selection.
      data.set("due_at", new Date(dueAt).toISOString().replace("Z", ""));
    }
    if (panel === "rfp")
      void onSubmit(() => api.createRFP(data), "RFP 已进入处理队列");
    if (panel === "knowledge")
      void onSubmit(() => api.createKnowledge(data), "知识文档已完成入库");
    if (panel === "customer") {
      const body = Object.fromEntries(
        Array.from(data.entries()).filter(([, value]) => value !== ""),
      );
      void onSubmit(
        () => api.createCustomer({ ...body, extra_data: {} }),
        "客户已创建",
      );
    }
  };
  return (
    <div
      className="panel-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <aside
        className="side-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="panel-title"
      >
        <div className="panel-head">
          <div>
            <span>NEW RECORD</span>
            <h2 id="panel-title">
              {panel === "rfp"
                ? "新建 RFP"
                : panel === "knowledge"
                  ? "上传知识文档"
                  : "新增客户"}
            </h2>
          </div>
          <button onClick={onClose} disabled={busy} aria-label="关闭表单">
            <X />
          </button>
        </div>
        <form onSubmit={submit}>
          {panel === "rfp" && (
            <>
              {customers.length === 0 && (
                <p className="form-note">请先到客户管理创建客户。</p>
              )}
              <label>
                客户
                <select name="customer_id" required defaultValue="">
                  <option value="" disabled>
                    请选择客户
                  </option>
                  {customers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                RFP 标题
                <input name="title" required maxLength={255} />
              </label>
              <label>
                项目编号
                <input name="reference_number" maxLength={100} />
              </label>
              <div className="field-row">
                <label>
                  优先级
                  <select name="priority" defaultValue="NORMAL">
                    <option value="LOW">低</option>
                    <option value="NORMAL">普通</option>
                    <option value="HIGH">高</option>
                  </select>
                </label>
                <label>
                  截止时间
                  <input type="datetime-local" name="due_at" />
                </label>
              </div>
              <label className="file-field">
                <UploadCloud />
                <strong>选择 RFP 文档</strong>
                <span>支持 PDF 或 DOCX，最大 50 MB</span>
                <input type="file" name="file" accept=".pdf,.docx" required />
              </label>
            </>
          )}
          {panel === "knowledge" && (
            <>
              <label>
                文档标题
                <input name="title" required />
              </label>
              <label>
                知识分类
                <input name="category" required />
              </label>
              <label>
                版本
                <input name="version" />
              </label>
              <label className="file-field">
                <UploadCloud />
                <strong>选择企业知识文档</strong>
                <span>支持 PDF、DOCX 或 Markdown，将被解析并写入向量库</span>
                <input
                  type="file"
                  name="file"
                  accept=".pdf,.docx,.md,.markdown,text/markdown"
                  required
                />
              </label>
            </>
          )}
          {panel === "customer" && (
            <>
              <label>
                客户名称
                <input name="name" required />
              </label>
              <label>
                客户编码
                <input
                  name="code"
                  required
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                />
              </label>
              <label>
                行业
                <input name="industry" />
              </label>
              <label>
                网站
                <input name="website" />
              </label>
              <div className="field-row">
                <label>
                  联系人
                  <input name="primary_contact_name" />
                </label>
                <label>
                  联系邮箱
                  <input type="email" name="primary_contact_email" />
                </label>
              </div>
            </>
          )}
          <button className="primary submit" disabled={busy}>
            {busy ? <LoaderCircle className="spin" /> : <Check />}确认提交
          </button>
        </form>
      </aside>
    </div>
  );
}
