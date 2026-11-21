import { useState } from "react";
import { Link } from "react-router-dom";
import { GitBranch, Plus, Search, Workflow as Flow } from "lucide-react";
import {
  params,
  time,
  useApi,
  type Page,
  type Run,
  type Workflow,
} from "../api";
import {
  Badge,
  Button,
  Data,
  Empty,
  Header,
  Pager,
  Panel,
} from "../components/ui";
import { RunTable } from "./Overview";

export function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (s: string) => void;
  placeholder: string;
}) {
  return (
    <label className="search">
      <Search size={16} />
      <input
        aria-label={placeholder}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
export function Listings({ kind }: { kind: "workflows" | "runs" }) {
  const [search, setSearch] = useState(""),
    [status, setStatus] = useState(""),
    [offset, setOffset] = useState(0);
  const [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const workflows = kind === "workflows";
  const path =
    "/" +
    kind +
    params({
      search,
      status,
      limit: 12,
      offset,
      date_from: from ? new Date(from).toISOString() : undefined,
      date_to: to ? new Date(to).toISOString() : undefined,
    });
  const wf = useApi<Page<Workflow>>(path, 5000, workflows),
    runs = useApi<Page<Run>>(path, 5000, !workflows);
  return (
    <>
      <Header
        title={workflows ? "Workflows" : "Executions"}
        sub={
          workflows
            ? "Manage definitions and immutable published versions."
            : "Trace workflow runs from submission to completion."
        }
      >
        {workflows && (
          <Button variant="default" asChild>
            <Link to="/workflows/new">
              <Plus size={16} />
              Create workflow
            </Link>
          </Button>
        )}
      </Header>
      <Panel
        title={workflows ? "Workflow library" : "Execution history"}
        icon={<GitBranch size={17} />}
      >
        <div className="filters">
          <SearchBox
            placeholder={
              workflows ? "Search workflows" : "Search name or run ID"
            }
            value={search}
            onChange={(s) => {
              setSearch(s);
              setOffset(0);
            }}
          />
          <select
            aria-label="Status filter"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {(workflows
              ? ["draft", "active"]
              : [
                  "PENDING",
                  "RUNNING",
                  "PAUSED",
                  "COMPLETED",
                  "FAILED",
                  "CANCELLED",
                ]
            ).map((s) => (
              <option key={s} value={s}>
                {s.toLowerCase()}
              </option>
            ))}
          </select>
          {!workflows && (
            <details>
              <summary>Date range</summary>
              <div className="dates">
                <label>
                  From
                  <input
                    type="datetime-local"
                    value={from}
                    onChange={(e) => {
                      setFrom(e.target.value);
                      setOffset(0);
                    }}
                  />
                </label>
                <label>
                  Through
                  <input
                    type="datetime-local"
                    value={to}
                    onChange={(e) => {
                      setTo(e.target.value);
                      setOffset(0);
                    }}
                  />
                </label>
              </div>
            </details>
          )}
        </div>
        {workflows ? (
          <Data query={wf}>
            {(p) => (
              <>
                {p.items.length ? (
                  <div className="scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Workflow</th>
                          <th>Status</th>
                          <th>Version</th>
                          <th>Executions</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {p.items.map((w) => (
                          <tr key={w.id}>
                            <td>
                              <Link
                                className="workflow-link"
                                to={"/workflows/" + w.id}
                              >
                                <span className="mini-icon">
                                  <Flow size={16} />
                                </span>
                                <span>
                                  {w.name}
                                  <small>{w.description}</small>
                                </span>
                              </Link>
                            </td>
                            <td>
                              <Badge status={w.status} />
                            </td>
                            <td className="mono">
                              {w.latest_version ? "v" + w.latest_version : "—"}
                            </td>
                            <td>{w.run_count}</td>
                            <td>{time(w.created_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty text="No workflows match this view." />
                )}
                <Pager data={p} onChange={setOffset} />
              </>
            )}
          </Data>
        ) : (
          <Data query={runs}>
            {(p) => (
              <>
                <RunTable runs={p.items} details />
                <Pager data={p} onChange={setOffset} />
              </>
            )}
          </Data>
        )}
      </Panel>
    </>
  );
}
