import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  Box,
  Braces,
  Cpu,
  Database,
  GitBranch,
  Layers3,
  ListTree,
  Network,
  Server,
} from "lucide-react";
import {
  BASE,
  params,
  short,
  time,
  useApi,
  type Attempt,
  type EventRow,
  type Health,
  type Page,
  type Stats,
  type Step,
  type TaskInfo,
  type Worker,
} from "../api";
import {
  Badge,
  Button,
  Data,
  Empty,
  Header,
  JsonView,
  Pager,
  Panel,
} from "../components/ui";
import { Services, Metric } from "./Overview";
import { EventLog } from "./Details";
import { SearchBox } from "./Lists";

export function Workers() {
  const [offset, set] = useState(0),
    q = useApi<Page<Worker>>("/workers?limit=20&offset=" + offset, 5000);
  return (
    <>
      <Header
        title="Workers"
        sub="Inspect worker leases, availability and heartbeat history."
      />
      <Panel title="Worker pool" icon={<Cpu size={17} />}>
        <Data query={q}>
          {(p) => (
            <>
              {p.items.length ? (
                <div className="scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Worker</th>
                        <th>Status</th>
                        <th>Hostname</th>
                        <th>Current task</th>
                        <th>Attempts</th>
                        <th>Last heartbeat</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.items.map((w) => (
                        <tr key={w.id}>
                          <td>
                            <Link
                              className="workflow-link"
                              to={"/workers/" + w.id}
                            >
                              <span className="mini-icon">
                                <Cpu size={16} />
                              </span>
                              {w.worker_name}
                            </Link>
                          </td>
                          <td>
                            <Badge status={w.status} />
                          </td>
                          <td className="mono">{w.hostname}</td>
                          <td className="mono">{short(w.current_task_id)}</td>
                          <td>{w.execution_count}</td>
                          <td>{time(w.last_heartbeat_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Empty text="No workers have registered." />
              )}
              <Pager data={p} onChange={set} />
            </>
          )}
        </Data>
      </Panel>
    </>
  );
}
export function WorkerDetails() {
  const { workerId } = useParams(),
    path = "/workers/" + workerId,
    [offset, set] = useState(0),
    q = useApi<Worker>(path, 5000),
    history = useApi<Page<Attempt>>(
      path + "/executions?limit=25&offset=" + offset,
      5000,
    );
  const current = useApi<Step>(
    "/tasks/" + q.data?.current_task_id,
    2000,
    !!q.data?.current_task_id,
  );
  return (
    <Data query={q}>
      {(w) => (
        <>
          <Header title={w.worker_name} sub={w.id}>
            <Badge status={w.status} />
          </Header>
          <div className="record-meta">
            <span>Host {w.hostname}</span>
            <span>Heartbeat {time(w.last_heartbeat_at)}</span>
            <span>{w.execution_count} attempts</span>
          </div>
          {w.current_task_id && (
            <Panel title="Current execution">
              <Data query={current}>
                {(s) => (
                  <Link className="form" to={"/runs/" + s.workflow_run_id}>
                    {s.name} · {s.task_type}
                  </Link>
                )}
              </Data>
            </Panel>
          )}
          <Panel title="Assigned attempts">
            <Data query={history}>
              {(p) => (
                <>
                  {p.items.length ? (
                    <div className="scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Step execution</th>
                            <th>Attempt</th>
                            <th>Status</th>
                            <th>Started</th>
                            <th>Duration</th>
                          </tr>
                        </thead>
                        <tbody>
                          {p.items.map((a) => (
                            <tr key={a.id}>
                              <td className="mono">{a.step_execution_id}</td>
                              <td>{a.attempt_number}</td>
                              <td>
                                <Badge status={a.status} />
                              </td>
                              <td>{time(a.started_at)}</td>
                              <td>{a.duration_ms ?? "—"} ms</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty text="This worker has no attempts." />
                  )}
                  <Pager data={p} onChange={set} />
                </>
              )}
            </Data>
          </Panel>
        </>
      )}
    </Data>
  );
}
export function System() {
  const health = useApi<Health>("/system/health", 5000),
    stats = useApi<Stats>("/system/stats", 5000);
  return (
    <>
      <Header
        title="System health"
        sub="Connectivity, queue depth and execution metrics."
      />
      <Data query={stats}>
        {(s) => (
          <div className="metrics">
            <Metric
              label="Workflows"
              value={s.total_workflows}
              note="Workflow definitions"
              icon={GitBranch}
            />
            <Metric
              label="Executions"
              value={s.total_runs}
              note={s.completed_runs + " completed"}
              icon={Box}
            />
            <Metric
              label="Pending tasks"
              value={s.pending_tasks}
              note="Waiting for execution"
              icon={ListTree}
            />
            <Metric
              label="Active leases"
              value={s.running_tasks}
              note={s.active_workers + " active workers"}
              icon={Cpu}
            />
          </div>
        )}
      </Data>
      <Data query={health}>
        {(h) => (
          <div className="detail-grid">
            <Panel title="Service connectivity" icon={<Network size={17} />}>
              <Services health={h} />
            </Panel>
            <Panel title="PostgreSQL queue" icon={<Database size={17} />}>
              <div className="services">
                {[
                  "PENDING",
                  "QUEUED",
                  "RETRY_WAIT",
                  "RUNNING",
                  "COMPLETED",
                  "FAILED",
                  "CANCELLED",
                ].map((s) => (
                  <div key={s}>
                    <span>{s.toLowerCase().replace("_", " ")}</span>
                    <code>{h.queue[s] ?? 0}</code>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        )}
      </Data>
    </>
  );
}
export function Events() {
  const [filter, setFilter] = useState(""),
    [offset, setOffset] = useState(0),
    q = useApi<Page<EventRow>>(
      "/events" + params({ event_type: filter, offset, limit: 25 }),
      5000,
    );
  return (
    <>
      <Header
        title="Event log"
        sub="Chronological records from the engine and its workers."
      />
      <Panel title="Recent events" icon={<Activity size={17} />}>
        <div className="filters">
          <SearchBox
            placeholder="Filter by exact event type"
            value={filter}
            onChange={(v) => {
              setFilter(v.toUpperCase());
              setOffset(0);
            }}
          />
        </div>
        <Data query={q}>
          {(p) => (
            <>
              <EventLog events={p.items} />
              <Pager data={p} onChange={setOffset} />
            </>
          )}
        </Data>
      </Panel>
    </>
  );
}
export function Settings() {
  const health = useApi<Health>("/system/health"),
    registry = useApi<TaskInfo[]>("/tasks/registry");
  return (
    <>
      <Header
        title="Settings"
        sub="Local runtime configuration and registered task types."
      />
      <Panel title="Environment" icon={<Server size={17} />}>
        <Data query={health}>
          {(h) => (
            <div className="services">
              {[
                ["Environment", h.environment],
                ["Application version", h.version],
                ["API base URL", new URL(BASE, window.location.origin).href],
              ].map(([k, v]) => (
                <div key={k}>
                  <span>{k}</span>
                  <code>{v}</code>
                </div>
              ))}
            </div>
          )}
        </Data>
      </Panel>
      <Panel title="Task registry" icon={<Braces size={17} />}>
        <Data query={registry}>
          {(types) => (
            <div className="registry">
              {types.map((t) => (
                <details key={t.task_type}>
                  <summary>
                    <code>{t.task_type}</code>
                    <span>{t.description}</span>
                  </summary>
                  <JsonView value={t.config_schema} />
                </details>
              ))}
            </div>
          )}
        </Data>
      </Panel>
      <Link className="quiet-link" to="/legacy">
        Open prototype console
      </Link>
    </>
  );
}
