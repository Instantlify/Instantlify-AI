"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { api, type Invitation, type Member, type Page } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { initials } from "@/components/shell";
import {
  ErrorNotice,
  PageHeading,
  Panel,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

export default function TeamPage() {
  const { workspace, user, prefix, manager, refresh } = useWorkspace();
  const router = useRouter();
  const [members, setMembers] = useState<Member[]>([]);
  const [memberCount, setMemberCount] = useState(0);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteLink, setInviteLink] = useState("");
  const [loading, setLoading] = useState(true);
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const [team, invites] = await Promise.all([
          api<Page<Member>>(
            `${prefix}/members/`,
            "GET",
            undefined,
            controller.signal,
          ),
          manager
            ? api<Page<Invitation>>(
                `${prefix}/invitations/`,
                "GET",
                undefined,
                controller.signal,
              )
            : Promise.resolve({ results: [] as Invitation[] }),
        ]);
        if (controller.signal.aborted) return;
        setMembers(team.results);
        setMemberCount(team.count);
        setInvitations(invites.results);
      } catch (err) {
        if (!controller.signal.aborted)
          feedback.setError((err as Error).message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix, manager]);

  async function changeRole(member: Member, role: string) {
    await feedback.run(async () => {
      const updated = await api<Member>(
        `${prefix}/members/${member.id}/`,
        "PATCH",
        { role },
      );
      setMembers((list) =>
        list.map((item) => (item.id === updated.id ? updated : item)),
      );
    }, "Team role updated.");
  }
  async function sendInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setInviteLink("");
    await feedback.run(async () => {
      const created = await api<Invitation>(
        `${prefix}/invitations/`,
        "POST",
        Object.fromEntries(new FormData(form)),
      );
      setInvitations((list) => [
        created,
        ...list.filter((item) => item.email !== created.email),
      ]);
      setInviteLink(created.accept_url || "");
      form.reset();
      feedback.setNotice(
        created.email_sent
          ? `Invitation emailed to ${created.email}.`
          : `Invitation created for ${created.email}, but the email could not be sent. Share the link below with them.`,
      );
    });
  }
  async function revokeInvite(invitation: Invitation) {
    await feedback.run(async () => {
      await api(`${prefix}/invitations/${invitation.id}/`, "DELETE");
      setInvitations((list) =>
        list.filter((item) => item.id !== invitation.id),
      );
      setInviteLink("");
    }, "Invitation revoked.");
  }
  async function removeMember(member: Member) {
    const leaving = member.email === user.email;
    if (
      !window.confirm(
        leaving
          ? "Leave this workspace? You will lose access immediately."
          : `Remove ${member.email} from this workspace?`,
      )
    )
      return;
    await feedback.run(async () => {
      await api(`${prefix}/members/${member.id}/`, "DELETE");
      if (leaving) {
        await refresh();
        router.push("/");
        return;
      }
      setMembers((list) => list.filter((item) => item.id !== member.id));
      setMemberCount((count) => count - 1);
    }, "Member removed. Their conversations returned to the queue.");
  }
  const canRemove = (member: Member) =>
    member.role !== "owner" &&
    (member.email === user.email ||
      workspace.role === "owner" ||
      (workspace.role === "admin" &&
        ["agent", "viewer"].includes(member.role)));

  return (
    <>
      <PageHeading eyebrow="Team" title="Better, together." />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading your team…</p>
      ) : (
        <Panel
          title={
            <>
              Your people <span className="count-badge">{memberCount}</span>
            </>
          }
          aside="Roles keep responsibilities clear"
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Email address</th>
                  <th>Role</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <div className="table-member">
                        <span className="user-avatar">
                          {initials(member.name || member.email)}
                        </span>
                        {member.name || "Team member"}
                      </div>
                    </td>
                    <td>{member.email}</td>
                    <td>
                      {workspace.role === "owner" && member.role !== "owner" ? (
                        <ValidatedSelect
                          name="role"
                          aria-label={`Role for ${member.email}`}
                          value={member.role}
                          disabled={feedback.busy}
                          onChange={(event) =>
                            changeRole(member, event.target.value)
                          }
                        >
                          <option value="viewer">Viewer</option>
                          <option value="agent">Agent</option>
                          <option value="admin">Admin</option>
                        </ValidatedSelect>
                      ) : (
                        <span className="role-pill">{member.role}</span>
                      )}
                    </td>
                    <td>
                      {canRemove(member) && (
                        <button
                          className="text-button"
                          disabled={feedback.busy}
                          onClick={() => removeMember(member)}
                        >
                          {member.email === user.email ? "Leave" : "Remove"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {manager && (
            <div className="invite-section">
              <h3>Invite a teammate</h3>
              <ValidatedForm
                fieldErrors={feedback.fieldErrors}
                validationTarget={feedback.validationTarget}
                onEdit={() => feedback.setError("")}
                className="invite-form"
                onSubmit={sendInvite}
              >
                <label>
                  Email address
                  <ValidatedInput
                    name="email"
                    type="email"
                    maxLength={254}
                    required
                    placeholder="teammate@company.com"
                  />
                </label>
                <label>
                  Role
                  <ValidatedSelect name="role" defaultValue="agent">
                    <option value="agent">Agent</option>
                    <option value="viewer">Viewer (read-only)</option>
                    {workspace.role === "owner" && (
                      <option value="admin">Admin</option>
                    )}
                  </ValidatedSelect>
                </label>
                <button className="button primary" disabled={feedback.busy}>
                  {feedback.busy ? "Inviting…" : "Create invite"}
                  <Plus size={16} />
                </button>
              </ValidatedForm>
              {inviteLink && (
                <label className="invite-link">
                  One-time invite link, valid for 7 days. It works only for the
                  invited email address and is not shown again.
                  <ValidatedInput
                    value={inviteLink}
                    readOnly
                    onFocus={(event) => event.currentTarget.select()}
                  />
                </label>
              )}
              {invitations.length > 0 && (
                <ul className="invite-list">
                  {invitations.map((invitation) => (
                    <li key={invitation.id}>
                      <span>{invitation.email}</span>
                      <span className="role-pill">{invitation.role}</span>
                      <span className="subtle">
                        Expires{" "}
                        {new Date(invitation.expires_at).toLocaleDateString()}
                      </span>
                      {(workspace.role === "owner" ||
                        invitation.role === "agent") && (
                        <button
                          className="text-button"
                          disabled={feedback.busy}
                          onClick={() => revokeInvite(invitation)}
                        >
                          Revoke
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <p className="panel-footnote">
            Owners manage roles and can invite admins. Admins invite agents and
            manage workspace settings. Pending invitations use a seat on your
            plan.
            {memberCount > members.length && " Showing the first 50 members."}
          </p>
        </Panel>
      )}
    </>
  );
}
