"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Link2,
  Mail,
  MessageSquare,
  Plus,
  Save,
  Tag,
  Trash2,
  Users,
  Workflow,
} from "lucide-react";
import {
  api,
  apiPages,
  message,
  type Automation,
  type Connection,
  type Member,
} from "@/lib/api";
import { BrandIcon } from "@/lib/brand-icons";
import {
  compileGuidedAutomation,
  GUIDED_CHANNELS,
  type GuidedPlatform,
  type GuidedSettings,
} from "@/lib/guided-automation";
import "./guided-automation.css";

interface SimpleAutomationBuilderProps {
  workspaceId: string;
  workspaceName?: string;
  onBack: () => void;
  onSaved: (automation: Automation) => void;
}

const INITIAL: GuidedSettings = {
  platform: "instagram",
  connectionId: "",
  trigger: "comment",
  matchAny: false,
  keywords: "",
  postScope: "all",
  postIds: [],
  publicReplies: [],
  opening: true,
  openingText:
    "Thanks for your interest! Tap below and I’ll send you the details.",
  openingButton: "Send me the link",
  requireFollow: false,
  followText:
    "Please follow this Instagram account, then tap below to continue.",
  followButton: "I'm following",
  collectEmail: false,
  emailQuestion: "What email address should we save for you?",
  resourceText: "Here are the resources you asked for.",
  trackClicks: false,
  reminder: false,
  reminderDelay: 3600,
  reminderText: "Just checking in—did you get a chance to open the resource?",
  links: [{ title: "Open resource", url: "" }],
  tag: "",
  assignee: "",
  transfer: "",
};

export function SimpleAutomationBuilder({
  workspaceId,
  workspaceName = "Your workspace",
  onBack,
  onSaved,
}: SimpleAutomationBuilderProps) {
  const prefix = `/api/workspaces/${workspaceId}`;
  const [settings, setSettings] = useState<GuidedSettings>(INITIAL);
  const [name, setName] = useState("My automation");
  const [connections, setConnections] = useState<Connection[]>([]);
  const [postResults, setPostResults] = useState<{
    accountId: string;
    posts: { id: string; label: string; permalink: string }[];
    error: string;
  } | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [loading, setLoading] = useState(true);
  const [lookupErrors, setLookupErrors] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [continued, setContinued] = useState(false);
  const savedId = useRef<string | null>(null);
  const [persistedId, setPersistedId] = useState<string | null>(null);
  const [openedAt] = useState(() => Date.now());
  const savingRef = useRef(false);
  const token = useRef("");
  const errorRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    const paths = ["connections/", "members/", "automations/"];
    Promise.allSettled([
      apiPages<Connection>(`${prefix}/${paths[0]}`, controller.signal),
      apiPages<Member>(`${prefix}/${paths[1]}`, controller.signal),
      apiPages<Automation>(`${prefix}/${paths[2]}`, controller.signal),
    ]).then(([accounts, team, flows]) => {
      if (controller.signal.aborted) return;
      if (accounts.status === "fulfilled") setConnections(accounts.value);
      if (team.status === "fulfilled") setMembers(team.value);
      if (flows.status === "fulfilled") setAutomations(flows.value);
      setLookupErrors([
        ...(accounts.status === "rejected"
          ? ["Connected accounts could not be loaded. Reload before saving."]
          : []),
        ...(team.status === "rejected"
          ? ["Team members could not be loaded. Assignment is unavailable."]
          : []),
        ...(flows.status === "rejected"
          ? [
              "Other automations could not be loaded. Transfers are unavailable.",
            ]
          : []),
      ]);
      setLoading(false);
    });
    return () => controller.abort();
  }, [prefix]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const accounts = connections.filter(
    (c) =>
      c.provider === GUIDED_CHANNELS[settings.platform] &&
      c.status === "active" &&
      !c.locked &&
      new Date(c.expires_at).getTime() > openedAt,
  );
  const accountId = accounts.some((c) => c.id === settings.connectionId)
    ? settings.connectionId
    : accounts[0]?.id || "";
  useEffect(() => {
    if (
      !accountId ||
      settings.trigger !== "comment" ||
      settings.postScope !== "specific"
    )
      return;
    const controller = new AbortController();
    api<{ results: { id: string; label: string; permalink: string }[] }>(
      `${prefix}/connections/${accountId}/posts/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted)
          setPostResults({ accountId, posts: result.results, error: "" });
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setPostResults({ accountId, posts: [], error: message(err) });
      });
    return () => controller.abort();
  }, [accountId, prefix, settings.trigger, settings.postScope]);
  const targets = automations.filter(
    (a) =>
      a.id !== persistedId &&
      a.enabled &&
      a.published.nodes?.length &&
      (!a.published.connection_id || a.published.connection_id === accountId) &&
      a.published.triggers?.every(
        (t) => !t.channel || t.channel === GUIDED_CHANNELS[settings.platform],
      ),
  );
  const patch = (change: Partial<GuidedSettings>) => {
    setSettings((s) => ({ ...s, ...change }));
    setDirty(true);
    setContinued(false);
  };
  const changePlatform = (platform: GuidedPlatform) =>
    patch({
      platform,
      connectionId: "",
      postIds: [],
      postScope: "all",
      publicReplies: [],
      trigger: platform === "instagram" ? "comment" : "dm",
      transfer: "",
    });

  async function save(activate: boolean) {
    if (savingRef.current) return;
    setError("");
    try {
      if (!name.trim() || name.trim().length > 100)
        throw new Error("Name your automation using 1–100 characters.");
      if (loading) throw new Error("Wait for connected accounts to load.");
      if (
        settings.assignee &&
        !members.some((m) => String(m.user_id) === settings.assignee)
      )
        throw new Error("Choose an available workspace member.");
      if (settings.transfer && !targets.some((a) => a.id === settings.transfer))
        throw new Error("Choose an enabled automation on this account.");
      token.current ||= `nemio:continue:${crypto.randomUUID()}`;
      const draft = compileGuidedAutomation(
        { ...settings, connectionId: accountId },
        token.current,
      );
      savingRef.current = true;
      setSaving(true);
      const path = savedId.current
        ? `${prefix}/automations/${savedId.current}/`
        : `${prefix}/automations/`;
      let saved = await api<Automation>(
        path,
        savedId.current ? "PATCH" : "POST",
        { name: name.trim(), draft },
      );
      savedId.current = saved.id;
      setPersistedId(saved.id);
      if (activate)
        saved = await api<Automation>(
          `${prefix}/automations/${saved.id}/publish/`,
          "POST",
          { graph: draft },
        );
      setDirty(false);
      onSaved(saved);
    } catch (err) {
      setError(message(err));
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <section
      className="nm-guided"
      aria-label="Guided automation builder"
      aria-busy={saving}
    >
      <header className="nm-guided-top">
        <button
          type="button"
          className="button secondary"
          onClick={() => {
            if (
              !dirty ||
              window.confirm("Discard your unsaved automation changes?")
            )
              onBack();
          }}
          disabled={saving}
        >
          <ArrowLeft size={16} /> Back to automations
        </button>
        <span className="nm-guided-draft">
          Draft · Changes stay private until published
        </span>
        <button
          type="button"
          className="button secondary"
          onClick={() => save(false)}
          disabled={saving || loading}
        >
          <Save size={16} /> Save as Draft
        </button>
        <button
          type="button"
          className="button primary"
          onClick={() => save(true)}
          disabled={saving || loading}
        >
          {saving ? "Saving…" : "Publish automation"}
          <ArrowRight size={16} />
        </button>
      </header>
      {error && (
        <p
          ref={errorRef}
          tabIndex={-1}
          role="alert"
          className="nm-guided-error"
        >
          {error}
        </p>
      )}
      {lookupErrors.map((text) => (
        <p key={text} role="status" className="nm-guided-error">
          {text}
        </p>
      ))}
      <div className="nm-guided-layout">
        <div className="nm-guided-form">
          <div className="nm-guided-intro">
            <span className="eyebrow">A BETTER FOLLOW-UP</span>
            <h1>Turn interest into a conversation.</h1>
            <p>
              Choose a trigger, write your response, and give each lead a clear
              next step.
            </p>
            <label>
              Automation name
              <input
                value={name}
                maxLength={100}
                onChange={(e) => {
                  setName(e.target.value);
                  setDirty(true);
                }}
              />
            </label>
          </div>
          <fieldset>
            <legend>
              <span>01</span> Choose your channel
            </legend>
            <div className="platform-cards-grid">
              {(["instagram", "facebook", "whatsapp", "telegram"] as const).map(
                (platform) => (
                  <button
                    key={platform}
                    type="button"
                    aria-pressed={settings.platform === platform}
                    onClick={() => changePlatform(platform)}
                    className="nm-guided-platform"
                  >
                    <BrandIcon name={platform} size={24} />
                    <span>
                      {platform === "facebook"
                        ? "Facebook"
                        : platform === "whatsapp"
                          ? "WhatsApp"
                          : platform[0].toUpperCase() + platform.slice(1)}
                    </span>
                    {settings.platform === platform && <Check size={14} />}
                  </button>
                ),
              )}
            </div>
            <label>
              Connected account
              <select
                aria-label="Connected account"
                value={accountId}
                onChange={(e) =>
                  patch({
                    connectionId: e.target.value,
                    transfer: "",
                    postIds: [],
                  })
                }
                disabled={loading}
              >
                <option value="">
                  {loading ? "Loading accounts…" : "Choose an account"}
                </option>
                {accounts.map((account) => (
                  <option value={account.id} key={account.id}>
                    {account.display_name}
                  </option>
                ))}
              </select>
            </label>
            {!loading && !accounts.length && (
              <p>
                No available account on this channel.{" "}
                <a href={`/w/${workspaceId}/integrations`}>
                  Connect an account
                </a>{" "}
                before publishing.
              </p>
            )}
          </fieldset>
          <fieldset>
            <legend>
              <span>02</span> Set the trigger
            </legend>
            <label>
              Start when
              <select
                value={settings.trigger}
                onChange={(e) =>
                  patch({
                    trigger: e.target.value as GuidedSettings["trigger"],
                  })
                }
              >
                <option value="dm">Someone sends a direct message</option>
                {["instagram", "facebook"].includes(settings.platform) && (
                  <option value="comment">Someone comments on a post</option>
                )}
                {settings.platform === "instagram" && (
                  <>
                    <option value="story_reply">
                      Someone replies to a story
                    </option>
                    <option value="live_comment">
                      Someone comments on a live stream
                    </option>
                  </>
                )}
              </select>
            </label>
            <p>
              This trigger listens only to the selected account
              {settings.trigger === "comment" &&
              settings.postScope !== "specific"
                ? ", across its posts"
                : ""}
              .
            </p>
            {settings.trigger === "comment" && (
              <>
                <label>
                  Which posts?
                  <select
                    aria-label="Comment post scope"
                    value={settings.postScope || "all"}
                    onChange={(event) =>
                      patch({
                        postScope: event.target
                          .value as GuidedSettings["postScope"],
                        postIds: [],
                      })
                    }
                  >
                    <option value="all">All posts</option>
                    <option value="specific">Choose specific posts</option>
                    <option value="next">The next post I publish</option>
                  </select>
                  {settings.postScope === "next" && (
                    <small>
                      Starts on the first post published after you publish this
                      automation. Republishing arms it for a new post.
                    </small>
                  )}
                </label>
                {settings.postScope === "specific" && (
                  <div className="nm-guided-posts" aria-label="Available posts">
                    {!accountId ? (
                      <p>Connect an account to choose its posts.</p>
                    ) : !postResults || postResults.accountId !== accountId ? (
                      <p role="status">Loading posts…</p>
                    ) : postResults.error ? (
                      <p role="alert">{postResults.error}</p>
                    ) : !postResults.posts.length ? (
                      <p>No posts were found on this account.</p>
                    ) : (
                      <>
                        <p>Choose from the account’s 50 most recent posts.</p>
                        {postResults.posts.map((post) => (
                          <label className="nm-guided-check" key={post.id}>
                            <input
                              type="checkbox"
                              checked={
                                settings.postIds?.includes(post.id) || false
                              }
                              onChange={(event) =>
                                patch({
                                  postIds: event.target.checked
                                    ? [...(settings.postIds || []), post.id]
                                    : (settings.postIds || []).filter(
                                        (id) => id !== post.id,
                                      ),
                                })
                              }
                            />
                            <span>
                              <strong>{post.label}</strong>
                              <small>Post {post.id}</small>
                            </span>
                          </label>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </>
            )}
            <div className="nm-guided-radios">
              <label>
                <input
                  type="radio"
                  name="keyword-match"
                  checked={!settings.matchAny}
                  onChange={() => patch({ matchAny: false })}
                />{" "}
                Specific words
              </label>
              <label>
                <input
                  type="radio"
                  name="keyword-match"
                  checked={settings.matchAny}
                  onChange={() => patch({ matchAny: true })}
                />{" "}
                Any word
              </label>
            </div>
            {!settings.matchAny && (
              <label>
                Trigger keywords
                <input
                  aria-label="Trigger keywords"
                  value={settings.keywords}
                  onChange={(e) => patch({ keywords: e.target.value })}
                  placeholder="GUIDE, INFO, PRICING"
                />
                <small>
                  Separate keywords with commas. Whole words are matched without
                  case sensitivity.
                </small>
              </label>
            )}
            {settings.trigger === "comment" && (
              <div className="nm-guided-public-replies">
                <label className="nm-guided-check">
                  <input
                    type="checkbox"
                    checked={Boolean(settings.publicReplies?.length)}
                    onChange={(event) =>
                      patch({
                        publicReplies: event.target.checked
                          ? ["Thanks! Check your messages for the details."]
                          : [],
                      })
                    }
                  />
                  <span>
                    <strong>Reply publicly to the comment</strong>
                    <small>
                      Send one reply below their comment as well as the private
                      message.
                    </small>
                  </span>
                </label>
                {(settings.publicReplies || []).map((reply, index) => (
                  <div key={index}>
                    <label>
                      Public reply {index + 1}
                      <textarea
                        aria-label={`Public reply ${index + 1}`}
                        rows={2}
                        maxLength={1000}
                        value={reply}
                        onChange={(event) =>
                          patch({
                            publicReplies: settings.publicReplies!.map(
                              (text, i) =>
                                i === index ? event.target.value : text,
                            ),
                          })
                        }
                      />
                    </label>
                    {settings.publicReplies!.length > 1 && (
                      <button
                        type="button"
                        className="button secondary"
                        onClick={() =>
                          patch({
                            publicReplies: settings.publicReplies!.filter(
                              (_, i) => i !== index,
                            ),
                          })
                        }
                      >
                        <Trash2 size={14} /> Remove reply {index + 1}
                      </button>
                    )}
                  </div>
                ))}
                {Boolean(settings.publicReplies?.length) && (
                  <>
                    <small>
                      We vary these replies across matching comments.
                    </small>
                    <button
                      type="button"
                      className="button secondary"
                      disabled={settings.publicReplies!.length >= 10}
                      onClick={() =>
                        patch({
                          publicReplies: [...settings.publicReplies!, ""],
                        })
                      }
                    >
                      <Plus size={14} /> Add reply variation
                    </button>
                  </>
                )}
              </div>
            )}
          </fieldset>
          <fieldset>
            <legend>
              <span>03</span> Start the conversation
            </legend>
            <label className="nm-guided-check">
              <input
                type="checkbox"
                checked={settings.opening}
                onChange={(e) => patch({ opening: e.target.checked })}
              />
              <span>
                <strong>Ask before sending resources</strong>
                <small>
                  The lead taps your reply button before the next message is
                  sent.
                </small>
              </span>
            </label>
            {settings.opening && (
              <>
                <label>
                  Opening message
                  <textarea
                    rows={3}
                    maxLength={2000}
                    value={settings.openingText}
                    onChange={(e) => patch({ openingText: e.target.value })}
                  />
                </label>
                <label>
                  Opening button
                  <input
                    maxLength={20}
                    value={settings.openingButton}
                    onChange={(e) => patch({ openingButton: e.target.value })}
                  />
                </label>
              </>
            )}
            <label className="nm-guided-check">
              <input
                type="checkbox"
                checked={settings.collectEmail}
                onChange={(e) => patch({ collectEmail: e.target.checked })}
              />
              <span>
                <strong>Collect their email</strong>
                <small>
                  Save a valid email address to the contact before delivering
                  resources.
                </small>
              </span>
            </label>
            {settings.collectEmail && (
              <label>
                Email question
                <textarea
                  rows={2}
                  value={settings.emailQuestion}
                  maxLength={2000}
                  onChange={(e) => patch({ emailQuestion: e.target.value })}
                />
              </label>
            )}
          </fieldset>
          {settings.platform === "instagram" && (
            <fieldset>
              <legend>Verify Instagram follow status</legend>
              <label className="nm-guided-switch">
                <input
                  type="checkbox"
                  checked={settings.requireFollow || false}
                  onChange={(event) =>
                    patch({ requireFollow: event.target.checked })
                  }
                />
                <span>
                  Require a verified follow before delivering resources
                </span>
              </label>
              {settings.requireFollow && (
                <>
                  <label>
                    Follow request
                    <textarea
                      aria-label="Follow request"
                      rows={3}
                      maxLength={2000}
                      value={settings.followText || ""}
                      onChange={(event) =>
                        patch({ followText: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Follow confirmation button
                    <input
                      aria-label="Follow confirmation button"
                      maxLength={20}
                      value={settings.followButton || ""}
                      onChange={(event) =>
                        patch({ followButton: event.target.value })
                      }
                    />
                  </label>
                  <p>
                    Nemio checks follow status after a private reply. Tapping
                    the button alone does not unlock resources. Your Instagram
                    connection must allow profile lookup.
                  </p>
                </>
              )}
            </fieldset>
          )}
          <fieldset>
            <legend>
              <span>04</span> Deliver something useful
            </legend>
            <label>
              Resource message
              <textarea
                rows={3}
                value={settings.resourceText}
                maxLength={2000}
                onChange={(e) => patch({ resourceText: e.target.value })}
              />
            </label>
            {settings.links.map((link, index) => (
              <div className="nm-guided-link" key={index}>
                <label>
                  Link {index + 1} label
                  <input
                    maxLength={20}
                    value={link.title}
                    onChange={(e) =>
                      patch({
                        links: settings.links.map((value, i) =>
                          i === index
                            ? { ...value, title: e.target.value }
                            : value,
                        ),
                      })
                    }
                  />
                </label>
                <label>
                  Link {index + 1} URL
                  <input
                    type="url"
                    placeholder="https://example.com/guide"
                    value={link.url}
                    onChange={(e) =>
                      patch({
                        links: settings.links.map((value, i) =>
                          i === index
                            ? { ...value, url: e.target.value }
                            : value,
                        ),
                      })
                    }
                  />
                </label>
                {settings.links.length > 1 && (
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remove link ${index + 1}`}
                    onClick={() =>
                      patch({
                        links: settings.links.filter((_, i) => i !== index),
                      })
                    }
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            ))}
            {settings.links.length < 3 && (
              <button
                type="button"
                className="button secondary"
                onClick={() =>
                  patch({ links: [...settings.links, { title: "", url: "" }] })
                }
              >
                <Plus size={14} /> Add another link
              </button>
            )}
            <label className="nm-guided-switch">
              <input
                type="checkbox"
                checked={settings.trackClicks || false}
                onChange={(event) =>
                  patch({ trackClicks: event.target.checked })
                }
              />
              <span>Track resource link clicks</span>
            </label>
            <label className="nm-guided-switch">
              <input
                type="checkbox"
                checked={settings.reminder || false}
                onChange={(event) => patch({ reminder: event.target.checked })}
              />
              <span>Follow up if they have not clicked</span>
            </label>
            {settings.reminder && (
              <>
                <label>
                  Reminder delay (minutes)
                  <input
                    aria-label="Reminder delay in minutes"
                    type="number"
                    min={1}
                    max={1380}
                    value={(settings.reminderDelay ?? 3600) / 60}
                    onChange={(event) =>
                      patch({ reminderDelay: Number(event.target.value) * 60 })
                    }
                  />
                </label>
                <label>
                  Reminder message
                  <textarea
                    aria-label="Reminder message"
                    rows={3}
                    maxLength={2000}
                    value={settings.reminderText || ""}
                    onChange={(event) =>
                      patch({ reminderText: event.target.value })
                    }
                  />
                </label>
                <p>
                  Click tracking is enabled for this reminder. A click cancels
                  it, and messaging-window rules still apply.
                </p>
              </>
            )}
            {settings.platform === "whatsapp" && (
              <p>
                WhatsApp delivers resource URLs as clickable links in the
                message.
              </p>
            )}
          </fieldset>
          <fieldset>
            <legend>
              <span>05</span> Keep the next step organised
            </legend>
            <label>
              Contact tag <small>Optional</small>
              <input
                value={settings.tag}
                maxLength={40}
                onChange={(e) => patch({ tag: e.target.value })}
                placeholder="e.g. guide-requested"
              />
            </label>
            <label>
              Assign to a teammate
              <select
                value={settings.assignee}
                disabled={loading}
                onChange={(e) => patch({ assignee: e.target.value })}
              >
                <option value="">Keep the current assignee</option>
                {members.map((member) => (
                  <option key={member.id} value={member.user_id}>
                    {member.name || member.email} · {member.role}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Continue with another automation
              <select
                value={settings.transfer}
                disabled={loading}
                onChange={(e) => patch({ transfer: e.target.value })}
              >
                <option value="">Finish this automation</option>
                {targets.map((automation) => (
                  <option key={automation.id} value={automation.id}>
                    {automation.name}
                  </option>
                ))}
              </select>
            </label>
            <small>
              Only enabled automations compatible with this account are shown.
            </small>
          </fieldset>
        </div>
        <aside className="nm-guided-preview" aria-label="Conversation preview">
          <div className="nm-guided-preview-head">
            <MessageSquare size={18} />
            <div>
              <strong>{workspaceName}</strong>
              <p>Conversation preview</p>
            </div>
            <BrandIcon name={settings.platform} size={22} />
          </div>
          <p className="nm-guided-preview-note">
            Preview only. No messages are sent.
          </p>
          <div className="nm-guided-preview-body">
            <div className="nm-guided-bubble incoming">
              {settings.matchAny
                ? "Hi, I’d like to know more."
                : settings.keywords.split(",")[0] || "Your trigger word"}
            </div>
            {settings.trigger === "comment" &&
              Boolean(settings.publicReplies?.length) && (
                <>
                  <div className="nm-guided-public-preview">
                    <small>Public comment reply · example</small>
                    <p>{settings.publicReplies?.[0]}</p>
                  </div>
                  <small>Private messages</small>
                </>
              )}
            {settings.opening && (
              <div className="nm-guided-bubble">
                <p>{settings.openingText}</p>
                <button
                  type="button"
                  className="nm-guided-preview-button"
                  onClick={() => setContinued(true)}
                >
                  {settings.openingButton || "Continue"}
                </button>
              </div>
            )}
            {settings.opening && !continued ? (
              <p className="nm-guided-pause">
                Waiting for the lead to tap the button. Try it above.
              </p>
            ) : (
              <>
                {settings.opening && (
                  <div className="nm-guided-bubble incoming">
                    {settings.openingButton}
                  </div>
                )}
                {settings.collectEmail && (
                  <>
                    <div className="nm-guided-bubble">
                      <Mail size={14} />
                      <p>{settings.emailQuestion}</p>
                    </div>
                    <div className="nm-guided-bubble incoming">
                      lead@example.com
                    </div>
                  </>
                )}
                <div className="nm-guided-bubble">
                  <p>{settings.resourceText}</p>
                  {settings.links.map((link, i) => (
                    <div className="nm-guided-resource" key={i}>
                      <Link2 size={13} />
                      {link.title || "Resource link"}
                    </div>
                  ))}
                </div>
                <ul className="nm-guided-outcomes">
                  {settings.tag && (
                    <li>
                      <Tag size={13} /> Tag: {settings.tag}
                    </li>
                  )}
                  {settings.assignee && (
                    <li>
                      <Users size={13} /> Assign:{" "}
                      {members.find(
                        (m) => String(m.user_id) === settings.assignee,
                      )?.name || "Selected teammate"}
                    </li>
                  )}
                  {settings.transfer && (
                    <li>
                      <Workflow size={13} /> Continue:{" "}
                      {targets.find((a) => a.id === settings.transfer)?.name}
                    </li>
                  )}
                </ul>
              </>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
