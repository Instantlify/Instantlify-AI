import { Activity } from "lucide-react";
import type { Audit } from "@/lib/api";
import { Empty } from "./ui";

export function ActivityList({ events }: { events: Audit[] }) {
  if (!events.length) return <Empty>No activity recorded yet.</Empty>;
  return (
    <div>
      {events.map((event) => (
        <div className="activity-row" key={event.id}>
          <span className="activity-icon">
            <Activity size={14} />
          </span>
          <div>
            <strong>{event.action.replace(/[._]/g, " ")}</strong>
            {event.target_id && (
              <span className="muted-text mono">
                {" "}
                {event.target_id.slice(0, 8)}
              </span>
            )}
          </div>
          <time dateTime={event.created_at}>
            {new Date(event.created_at).toLocaleString()}
          </time>
        </div>
      ))}
    </div>
  );
}
