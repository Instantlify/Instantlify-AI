"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
} from "@/components/validated-form";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Copy,
  CreditCard,
  Download,
  Eye,
  RefreshCw,
  Store,
  Upload,
} from "lucide-react";
import {
  api,
  idempotencyKey,
  money,
  upload,
  when,
  type Automation,
  type InstallResult,
  type Page,
  type SellerStatus,
  type Template,
  type TemplatePurchase,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";
import { BrandIcon } from "@/lib/brand-icons";

const CATEGORIES = [
  "sales",
  "support",
  "booking",
  "ecommerce",
  "creator",
  "agency",
  "other",
];

const PURCHASE_TONE: Record<string, "good" | "warn" | "bad" | "neutral"> = {
  installed: "good",
  paid: "good",
  pending: "warn",
  expired: "neutral",
  failed: "bad",
};

const sleep = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

export default function TemplatesPage() {
  const { prefix, manager, workspace } = useWorkspace();
  const owner = workspace.role === "owner";
  const confirm = useConfirmation();
  const feedback = useFeedback();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [market, setMarket] = useState<Template[]>([]);
  const [mine, setMine] = useState<Template[]>([]);
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [seller, setSeller] = useState<SellerStatus | null>(null);
  const [purchases, setPurchases] = useState<TemplatePurchase[]>([]);
  const [country, setCountry] = useState("us");
  const [preview, setPreview] = useState<Template | null>(null);
  const [installed, setInstalled] = useState<string | null>(null);
  const [imported, setImported] = useState<string | null>(null);
  const [pasted, setPasted] = useState("");
  const [exportId, setExportId] = useState("");
  const [exported, setExported] = useState("");

  const loadMarket = useCallback(
    async (signal?: AbortSignal) => {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (category) params.set("category", category);
      const page = await api<Page<Template>>(
        `/api/public/templates/?${params.toString()}`,
        "GET",
        undefined,
        signal,
      );
      setMarket(page.results);
    },
    [search, category],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      loadMarket(controller.signal).catch((err) => {
        if (!controller.signal.aborted)
          feedback.setError(String((err as Error).message));
      });
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadMarket]);

  const loadMine = useCallback(
    async (signal?: AbortSignal) => {
      if (!manager) return;
      const [templates, flows, payouts, bought] = await Promise.all([
        api<Page<Template>>(`${prefix}/templates/`, "GET", undefined, signal),
        api<Page<Automation>>(
          `${prefix}/automations/`,
          "GET",
          undefined,
          signal,
        ),
        api<SellerStatus>(
          `${prefix}/templates/payouts/`,
          "GET",
          undefined,
          signal,
        ),
        api<Page<TemplatePurchase>>(
          `${prefix}/templates/purchases/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setMine(templates.results);
      setAutomations(flows.results);
      setSeller(payouts);
      setPurchases(bought.results);
    },
    [prefix, manager],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      loadMine(controller.signal).catch((err) => {
        if (!controller.signal.aborted)
          feedback.setError(String((err as Error).message));
      });
    }, 0);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadMine]);

  /** Returning from Stripe: confirm a checkout or refresh the payout status. */
  useEffect(() => {
    if (!manager) return;
    const params = new URLSearchParams(window.location.search);
    const purchaseId = params.get("purchase");
    const payouts = params.get("payouts");
    if (!purchaseId && !payouts) return;
    window.history.replaceState(null, "", window.location.pathname);
    let cancelled = false;
    (async () => {
      try {
        if (payouts) {
          setSeller(
            await api<SellerStatus>(`${prefix}/templates/payouts/`, "POST", {
              action: "refresh",
            }),
          );
          feedback.setNotice(
            payouts === "return"
              ? "Payout details saved. Stripe may take a moment to activate transfers."
              : "The Stripe setup link expired. Start it again below.",
          );
        }
        if (purchaseId) {
          if (params.get("cancelled")) {
            feedback.setNotice("Checkout cancelled. Nothing was charged.");
            return;
          }
          let purchase = await api<TemplatePurchase>(
            `${prefix}/templates/purchases/${purchaseId}/`,
            "POST",
            {},
          );
          for (let i = 0; i < 5 && purchase.status === "pending"; i += 1) {
            await sleep(3000);
            if (cancelled) return;
            purchase = await api<TemplatePurchase>(
              `${prefix}/templates/purchases/${purchaseId}/`,
            );
          }
          if (purchase.status === "installed" && purchase.automation_id) {
            setInstalled(purchase.automation_id);
            feedback.setNotice(
              `Thanks! “${purchase.title}” is installed as a draft automation.`,
            );
          } else {
            feedback.setNotice(
              "Payment is still being confirmed. Use “Check payment” below in a minute.",
            );
          }
        }
      } catch (err) {
        if (!cancelled) feedback.setError(String((err as Error).message));
      } finally {
        if (!cancelled) loadMine().catch(() => undefined);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manager, prefix]);

  async function install(template: Template) {
    const paid = template.price_cents > 0;
    const result = await feedback.run(
      () =>
        api<InstallResult>(`${prefix}/templates/install/`, "POST", {
          slug: template.slug,
          idempotency_key: paid ? idempotencyKey() : undefined,
        }),
      paid ? undefined : `“${template.title}” installed as a draft automation.`,
    );
    if (!result) return;
    if (result.checkout_url) {
      window.location.assign(result.checkout_url);
      return;
    }
    if (result.automation_id) {
      setInstalled(result.automation_id);
      if (paid)
        feedback.setNotice(
          `You already own “${template.title}”; installed again as a draft.`,
        );
      loadMarket().catch(() => undefined);
      loadMine().catch(() => undefined);
    }
  }

  async function checkPurchase(purchase: TemplatePurchase) {
    const result = await feedback.run(() =>
      api<TemplatePurchase>(
        `${prefix}/templates/purchases/${purchase.id}/`,
        "POST",
        {},
      ),
    );
    if (!result) return;
    if (result.status === "installed" && result.automation_id) {
      setInstalled(result.automation_id);
      feedback.setNotice("Payment confirmed and template installed.");
    } else if (result.status === "pending") {
      feedback.setNotice("Stripe has not confirmed this payment yet.");
    } else {
      feedback.setNotice(`This checkout is ${result.status}.`);
    }
    loadMine().catch(() => undefined);
  }

  async function payouts(action: "onboard" | "refresh" | "dashboard") {
    const result = await feedback.run(() =>
      api<SellerStatus>(`${prefix}/templates/payouts/`, "POST", {
        action,
        country,
      }),
    );
    if (!result) return;
    setSeller(result);
    if (result.url) {
      window.location.assign(result.url);
      return;
    }
    if (action === "refresh") feedback.setNotice("Payout status refreshed.");
  }

  async function openPreview(template: Template) {
    const full = await feedback.run(() =>
      api<Template>(`/api/public/templates/${template.slug}/`),
    );
    if (full) setPreview(full);
  }

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form)) as Record<
      string,
      string
    >;
    const result = await feedback.run(
      () =>
        api<Template>(`${prefix}/templates/publish/`, "POST", {
          automation: data.automation,
          title: data.title,
          description: data.description,
          category: data.category,
          price_cents: Number(data.price_cents || 0),
        }),
      "Template published to the marketplace.",
    );
    if (result) {
      form.reset();
      await loadMine().catch(() => undefined);
      await loadMarket().catch(() => undefined);
    }
  }

  async function unlist(template: Template) {
    if (!(await confirm(`Unlist “${template.title}” from the marketplace?`)))
      return;
    await feedback.run(
      () => api(`${prefix}/templates/${template.id}/`, "DELETE"),
      "Template unlisted.",
    );
    await loadMine().catch(() => undefined);
    await loadMarket().catch(() => undefined);
  }

  async function importFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = (form.elements.namedItem("file") as HTMLInputElement)
      .files?.[0];
    if (!file) {
      feedback.setError("Choose a .json template file.");
      return;
    }
    const body = new FormData();
    body.append("file", file);
    const result = await feedback.run(
      () => upload<Automation>(`${prefix}/automations/import/`, body),
      "Template imported as a draft automation.",
    );
    if (result) {
      form.reset();
      setImported(result.id);
    }
  }

  async function importPasted(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let parsed: unknown;
    try {
      parsed = JSON.parse(pasted);
    } catch {
      feedback.setError(
        "We couldn’t read this template file. Choose an exported Instantlify template and try again.",
      );
      return;
    }
    const result = await feedback.run(
      () =>
        api<Automation>(`${prefix}/automations/import/`, "POST", {
          template: parsed,
        }),
      "Template imported as a draft automation.",
    );
    if (result) {
      setPasted("");
      setImported(result.id);
    }
  }

  async function exportAutomation() {
    if (!exportId) return;
    const result = await feedback.run(() =>
      api<unknown>(`${prefix}/automations/${exportId}/export/`),
    );
    if (result) setExported(JSON.stringify(result, null, 2));
  }

  async function copyExport() {
    try {
      await navigator.clipboard.writeText(exported);
      feedback.setNotice("Copied to clipboard.");
    } catch {
      feedback.setError("Copy failed. Select the text and copy it manually.");
    }
  }

  const publishable = automations.filter(
    (item) => item.published && Object.keys(item.published).length > 0,
  );
  const canSell = Boolean(seller?.can_sell);

  return (
    <>
      <PageHeading
        eyebrow="Templates"
        title="Start from what already works."
        text="Install proven flows from the community, sell your own, or move automations between workspaces."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {installed && (
        <p className="success-notice">
          <Link href={`/w/${workspace.id}/automations/${installed}`}>
            Open the installed automation →
          </Link>
        </p>
      )}
      {imported && (
        <p className="success-notice">
          <Link href={`/w/${workspace.id}/automations/${imported}`}>
            Open the imported automation →
          </Link>
        </p>
      )}
      <div className="stack">
        <Panel title="Marketplace" aside={`${market.length} template(s)`}>
          <div className="toolbar">
            <ValidatedInput
              type="search"
              placeholder="Search templates"
              aria-label="Search templates"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <ValidatedSelect
              aria-label="Category"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              <option value="">All categories</option>
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </ValidatedSelect>
          </div>
          {market.length === 0 ? (
            <Empty>No templates match yet. Be the first to publish one.</Empty>
          ) : (
            <div className="card-grid">
              {market.map((template) => (
                <article className="card" key={template.id}>
                  <div className="row between">
                    <h3>{template.title}</h3>
                    <Pill>{template.category}</Pill>
                  </div>
                  <span className="muted-text">
                    by {template.author_name || "Anonymous"} ·{" "}
                    {template.install_count} install
                    {template.install_count === 1 ? "" : "s"}
                  </span>
                  {template.description && (
                    <p className="small">{template.description}</p>
                  )}
                  <div className="row between">
                    <strong>
                      {template.price_cents
                        ? money(template.price_cents)
                        : "Free"}
                    </strong>
                    <span className="row">
                      <button
                        className="button secondary small"
                        onClick={() => openPreview(template)}
                      >
                        <Eye size={14} /> Preview
                      </button>
                      <button
                        className="button primary small"
                        disabled={!manager || feedback.busy}
                        onClick={() => install(template)}
                      >
                        {template.price_cents ? (
                          <>
                            <CreditCard size={14} /> Buy{" "}
                            {money(template.price_cents)}
                          </>
                        ) : (
                          <>
                            <Download size={14} /> Install
                          </>
                        )}
                      </button>
                    </span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        {manager && (
          <div className="two-col">
            <Panel
              title="Sell templates"
              aside={
                seller?.connected
                  ? `Payouts: ${seller.transfers_status}`
                  : "Payouts via Stripe"
              }
            >
              {!seller?.connected ? (
                <div className="form-grid">
                  <p className="small">
                    Paid templates are sold through Instantlify and paid out to
                    your own Stripe account. Set up payouts once; buyers never
                    see your account.
                  </p>
                  <label>
                    Country
                    <ValidatedInput
                      value={country}
                      maxLength={2}
                      aria-label="Country code"
                      onChange={(event) =>
                        setCountry(event.target.value.toLowerCase())
                      }
                      disabled={!owner}
                    />
                    <span className="hint">
                      Two-letter code of where your business is based.
                    </span>
                  </label>
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button primary"
                      disabled={!owner || feedback.busy}
                      onClick={() => payouts("onboard")}
                    >
                      <CreditCard size={16} /> Set up payouts
                    </button>
                  </div>
                  {!owner && (
                    <span className="hint">
                      Only the workspace owner can set up payouts.
                    </span>
                  )}
                </div>
              ) : (
                <div className="form-grid">
                  <div className="row">
                    <Pill tone={canSell ? "good" : "warn"}>
                      {canSell ? "Ready to sell" : "Setup incomplete"}
                    </Pill>
                    {seller.requirements_due && (
                      <span className="muted-text">
                        Stripe needs more details before transfers activate.
                      </span>
                    )}
                    <span className="muted-text">
                      Checked {when(seller.checked_at)}
                    </span>
                  </div>
                  <div className="form-actions">
                    {!canSell && (
                      <button
                        type="button"
                        className="button primary"
                        disabled={!owner || feedback.busy}
                        onClick={() => payouts("onboard")}
                      >
                        <BrandIcon name="stripe" size={16} mono /> Finish Stripe
                        setup
                      </button>
                    )}
                    <button
                      type="button"
                      className="button secondary"
                      disabled={!owner || feedback.busy}
                      onClick={() => payouts("refresh")}
                    >
                      <RefreshCw size={16} /> Refresh status
                    </button>
                    <button
                      type="button"
                      className="button secondary"
                      disabled={!owner || feedback.busy}
                      onClick={() => payouts("dashboard")}
                    >
                      Open Stripe dashboard
                    </button>
                  </div>
                </div>
              )}

              <h3 style={{ marginTop: 22 }}>Publish a template</h3>
              {publishable.length === 0 ? (
                <Empty>
                  Publish an automation first; only published flows can be
                  shared.
                </Empty>
              ) : (
                <ValidatedForm
                  fieldErrors={feedback.fieldErrors}
                  validationTarget={feedback.validationTarget}
                  onEdit={() => feedback.setError("")}
                  className="form-grid"
                  onSubmit={publish}
                >
                  <label>
                    Automation
                    <ValidatedSelect name="automation" required>
                      {publishable.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </ValidatedSelect>
                  </label>
                  <label>
                    Title
                    <ValidatedInput name="title" maxLength={120} required />
                  </label>
                  <label>
                    Description
                    <ValidatedTextarea
                      name="description"
                      maxLength={2000}
                      placeholder="What does this flow do, and who is it for?"
                    />
                  </label>
                  <label>
                    Category
                    <ValidatedSelect name="category" defaultValue="sales">
                      {CATEGORIES.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </ValidatedSelect>
                  </label>
                  <label>
                    Price (cents)
                    <ValidatedInput
                      name="price_cents"
                      type="number"
                      min={0}
                      max={100000}
                      step={1}
                      defaultValue={0}
                    />
                    <span className="hint">
                      {canSell
                        ? "0 = free. Paid templates cost at least $1; Instantlify keeps a platform fee and the rest is paid out to your Stripe account."
                        : "0 = free. Set up payouts above before publishing a paid template."}
                    </span>
                  </label>
                  <div className="form-actions">
                    <button className="button primary" disabled={feedback.busy}>
                      <Store size={16} /> Publish
                    </button>
                  </div>
                </ValidatedForm>
              )}
              <h3 style={{ marginTop: 22 }}>Your published templates</h3>
              {mine.length === 0 ? (
                <Empty>You have not published any templates.</Empty>
              ) : (
                <div>
                  {mine.map((template) => (
                    <div className="list-row" key={template.id}>
                      <strong>{template.title}</strong>
                      <Pill
                        tone={
                          template.status === "published" ? "good" : "neutral"
                        }
                      >
                        {template.status}
                      </Pill>
                      <span className="muted-text">
                        {template.price_cents
                          ? money(template.price_cents)
                          : "Free"}{" "}
                        · {template.install_count} install
                        {template.install_count === 1 ? "" : "s"}
                      </span>
                      <span className="spacer" />
                      {template.status === "published" && (
                        <button
                          className="text-button"
                          onClick={() => unlist(template)}
                          disabled={feedback.busy}
                        >
                          Unlist
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <div className="stack">
              <Panel title="Your purchases" aside={`${purchases.length}`}>
                {purchases.length === 0 ? (
                  <Empty>Paid templates you buy will appear here.</Empty>
                ) : (
                  <div>
                    {purchases.map((purchase) => (
                      <div className="list-row" key={purchase.id}>
                        <strong>{purchase.title}</strong>
                        <Pill
                          tone={PURCHASE_TONE[purchase.status] ?? "neutral"}
                        >
                          {purchase.status}
                        </Pill>
                        <span className="muted-text">
                          {money(purchase.amount_cents, purchase.currency)} ·{" "}
                          {when(purchase.paid_at ?? purchase.created_at)}
                        </span>
                        <span className="spacer" />
                        {purchase.status === "pending" && (
                          <button
                            className="text-button"
                            onClick={() => checkPurchase(purchase)}
                            disabled={feedback.busy}
                          >
                            Check payment
                          </button>
                        )}
                        {purchase.status === "paid" && (
                          <button
                            className="text-button"
                            onClick={() => checkPurchase(purchase)}
                            disabled={feedback.busy}
                          >
                            Install
                          </button>
                        )}
                        {purchase.automation_id && (
                          <Link
                            href={`/w/${workspace.id}/automations/${purchase.automation_id}`}
                          >
                            Open
                          </Link>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Panel>

              <Panel title="Import & export">
                <ValidatedForm
                  fieldErrors={feedback.fieldErrors}
                  validationTarget={feedback.validationTarget}
                  onEdit={() => feedback.setError("")}
                  className="form-grid"
                  onSubmit={importFile}
                >
                  <label>
                    Import a template file
                    <ValidatedInput
                      name="file"
                      type="file"
                      accept=".json,application/json"
                    />
                  </label>
                  <div className="form-actions">
                    <button
                      className="button secondary"
                      disabled={feedback.busy}
                    >
                      <Upload size={16} /> Import file
                    </button>
                  </div>
                </ValidatedForm>
                <ValidatedForm
                  fieldErrors={feedback.fieldErrors}
                  validationTarget={feedback.validationTarget}
                  onEdit={() => feedback.setError("")}
                  className="form-grid"
                  onSubmit={importPasted}
                  style={{ marginTop: 16 }}
                >
                  <label>
                    Or paste template JSON
                    <ValidatedTextarea
                      value={pasted}
                      onChange={(event) => setPasted(event.target.value)}
                      placeholder='{"format": "nemio.automation", …}'
                      className="mono"
                    />
                  </label>
                  <div className="form-actions">
                    <button
                      className="button secondary"
                      disabled={feedback.busy || !pasted.trim()}
                    >
                      <Upload size={16} /> Import JSON
                    </button>
                  </div>
                </ValidatedForm>
                <div className="form-grid" style={{ marginTop: 22 }}>
                  <label>
                    Export an automation
                    <ValidatedSelect
                      value={exportId}
                      onChange={(event) => setExportId(event.target.value)}
                    >
                      <option value="">Choose an automation</option>
                      {automations.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </ValidatedSelect>
                  </label>
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button secondary"
                      disabled={!exportId || feedback.busy}
                      onClick={exportAutomation}
                    >
                      <Download size={16} /> Show JSON
                    </button>
                    {exported && (
                      <button
                        type="button"
                        className="button secondary"
                        onClick={copyExport}
                      >
                        <Copy size={16} /> Copy
                      </button>
                    )}
                  </div>
                  {exported && (
                    <ValidatedTextarea
                      className="mono"
                      readOnly
                      value={exported}
                      aria-label="Exported template JSON"
                      onFocus={(event) => event.currentTarget.select()}
                      style={{ minHeight: 200 }}
                    />
                  )}
                </div>
              </Panel>
            </div>
          </div>
        )}
      </div>

      {preview && (
        <Modal title={preview.title} onClose={() => setPreview(null)}>
          <p className="muted-text">
            by {preview.author_name || "Anonymous"} · {preview.category} ·{" "}
            {preview.price_cents ? money(preview.price_cents) : "Free"}
          </p>
          {preview.description && <p>{preview.description}</p>}
          <div className="lead-panel" style={{ marginTop: 14 }}>
            <dl>
              <dt>Triggers</dt>
              <dd>
                {preview.graph?.triggers?.length
                  ? preview.graph.triggers
                      .map((t) => `${t.kind}: “${t.keyword}”`)
                      .join(", ")
                  : "—"}
              </dd>
              <dt>Steps</dt>
              <dd>
                {preview.graph?.nodes?.length
                  ? preview.graph.nodes
                      .map((n) => n.data.kind.replace(/_/g, " "))
                      .join(" → ")
                  : "—"}
              </dd>
              <dt>Nodes</dt>
              <dd>{preview.graph?.nodes?.length ?? 0}</dd>
            </dl>
          </div>
        </Modal>
      )}
    </>
  );
}
