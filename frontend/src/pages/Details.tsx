import { useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Braces,
  Clock3,
  GitBranch,
  Play,
  SquarePen,
  Terminal,
} from "lucide-react";
import { toast } from "sonner";
import {
  request,
  useApi,
  short,
  time,
  duration,
  live,
  type Run,
  type Page,
  type Workflow,
  type Version,
  type Attempt,
  type Timeline,
  type EventRow,
} from "../api";
import {
  Badge,
  Button,
  Confirmation,
  Data,
  Empty,
  Header,
  JsonView,
  Modal,
  Pager,
  Panel,
  useAction,
} from "../components/ui";
import { RunTable } from "./Overview";

export function WorkflowDetails() {
  const { workflowId } = useParams(),
    path = "/workflows/" + workflowId,
    nav = useNavigate(),
    act = useAction();
  const [open, setOpen] = useState(false),
    [input, setInput] = useState('{"text":"Hello, Durable"}'),
    [version, setVersion] = useState(""),
    [shown, setShown] = useState<number>(),
    [key, setKey] = useState(""),
    [err, setErr] = useState(""),
    [offset, setOffset] = useState(0);
  const wf = useApi<Workflow>(path),
    versions = useApi<Page<Version>>(
      path + "/versions?limit=20&offset=" + offset,
    );
  const runs = useApi<Page<Run>>(
    "/runs?workflow_id=" + workflowId + "&limit=6",
    5000,
  );
  const snapshot = useApi<Version>(
    path + "/versions/" + shown,
    false,
    shown !== undefined,
  );
  function start() {
    act.mutate(async () => {
      try {
        let data;
        try {
          data = JSON.parse(input);
        } catch {
          throw Error("Enter valid input JSON.");
        }
        if (!data || Array.isArray(data) || typeof data !== "object")
          throw Error("Input must be a JSON object.");
        const run = await request<Run>(path + "/runs", "POST", {
          input_data: data,
          idempotency_key: key || undefined,
          version: version ? +version : undefined,
        });
        setOpen(false);
        toast.success("Execution submitted");
        nav("/runs/" + run.id);
      } catch (e) {
        setErr((e as Error).message);
        throw e;
      }
    });
  }
  return (
    <Data query={wf}>
      {(w) => (
        <>
          <Header title={w.name} sub={w.description}>
            <Button asChild>
              <Link to={path + "/edit"}>
                <SquarePen size={15} />
                Edit draft
              </Link>
            </Button>
            <Button
              variant="default"
              disabled={!w.latest_version}
              onClick={() => {
                setKey(crypto.randomUUID());
                setErr("");
                setOpen(true);
              }}
            >
              <Play size={15} />
              Run workflow
            </Button>
          </Header>
          <div className="record-meta">
            <Badge status={w.status} />
            <code>{w.workflow_key}</code>
            <span>{w.run_count} executions</span>
            <span>Created {time(w.created_at)}</span>
          </div>
          <div className="detail-grid">
            <Panel
              title="Definition"
              icon={<Braces size={17} />}
              extra={
                <Button
                  onClick={() =>
                    act.mutate(async () => {
                      await request(path + "/validate", "POST");
                      toast.success("Draft is valid");
                    })
                  }
                >
                  Validate draft
                </Button>
              }
            >
              <JsonView
                value={
                  shown === undefined ? w.draft : snapshot.data?.definition
                }
              />
              {snapshot.error && (
                <div role="alert">{snapshot.error.message}</div>
              )}
            </Panel>
            <Panel
              title="Published versions"
              icon={<GitBranch size={17} />}
              extra={
                <Confirmation
                  label="Publish draft"
                  description="Publish the current draft as a new immutable version."
                  action={() =>
                    act.mutate(async () => {
                      await request(path + "/publish", "POST");
                      toast.success("Version published");
                    })
                  }
                />
              }
            >
              <div className="version-list">
                <button
                  onClick={() => setShown(undefined)}
                  className={shown === undefined ? "selected" : ""}
                >
                  Current draft
                </button>
                <Data query={versions}>
                  {(p) => (
                    <>
                      {p.items.map((v) => (
                        <button
                          className={v.version === shown ? "selected" : ""}
                          onClick={() => setShown(v.version)}
                          key={v.id}
                        >
                          Version {v.version}
                          <small>{v.definition.steps.length} steps</small>
                        </button>
                      ))}
                      <Pager data={p} onChange={setOffset} />
                    </>
                  )}
                </Data>
              </div>
              {w.status === "draft" && (
                <div className="form">
                  <Confirmation
                    label="Delete draft"
                    description="Delete this unpublished workflow draft."
                    action={() =>
                      act.mutate(async () => {
                        await request(path, "DELETE");
                        toast.success("Draft deleted");
                        nav("/workflows");
                      })
                    }
                  />
                </div>
              )}
            </Panel>
          </div>
          <Panel title="Recent executions">
            <Data query={runs}>{(p) => <RunTable runs={p.items} />}</Data>
          </Panel>
          <Modal
            open={open}
            onOpenChange={setOpen}
            title="Run workflow"
            description={w.name}
          >
            <div className="form">
              <label>
                Version
                <input
                  type="number"
                  min="1"
                  max={w.latest_version}
                  value={version}
                  placeholder={"Latest (v" + w.latest_version + ")"}
                  onChange={(e) => setVersion(e.target.value)}
                />
              </label>
              <label>
                Input JSON
                <textarea
                  rows={6}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                />
              </label>
              {err && (
                <p className="failure" role="alert">
                  {err}
                </p>
              )}
              <Button
                variant="default"
                disabled={act.isPending}
                onClick={start}
              >
                <Play size={14} />
                Start execution
              </Button>
            </div>
          </Modal>
        </>
      )}
    </Data>
  );
}
export function EventLog({ events }: { events: EventRow[] }) {
  return events.length ? (
    <div className="events">
      {events.map((e) => (
        <div key={e.id}>
          <time>{time(e.created_at)}</time>
          <span>
            <code>{e.event_type}</code>
            <small>{e.message}</small>
          </span>
          {e.workflow_run_id && (
            <Link className="mono dim" to={"/runs/" + e.workflow_run_id}>
              {short(e.workflow_run_id)}
            </Link>
          )}
        </div>
      ))}
    </div>
  ) : (
    <Empty text="No events in this view." />
  );
}
export function RunDetails() {
  const { runId } = useParams(),
    path = "/runs/" + runId,
    act = useAction(),
    [offset, setOffset] = useState(0);
  const timeline = useQuery({
    queryKey: [path + "/timeline", offset],
    queryFn: () =>
      request<Timeline>(path + "/timeline?limit=25&offset=" + offset),
    refetchInterval: (q) =>
      !q.state.data || live(q.state.data.run.status) ? 2000 : false,
  });
  const [attemptOffset, setAttemptOffset] = useState(0);
  const history = useApi<Page<Attempt>>(
    path + "/attempts?limit=40&offset=" + attemptOffset,
    timeline.data && live(timeline.data.run.status) ? 2000 : false,
  );
  function change(action: string) {
    act.mutate(async () => {
      await request(path + "/" + action, "POST");
      toast.success("Execution updated");
    });
  }
  return (
    <Data query={timeline}>
      {({ run, steps, events }) => (
        <>
          <Header title={run.workflow_name} sub={"Execution " + run.id}>
            <Badge status={run.status} />
            {(run.status === "PAUSED"
              ? ["resume", "cancel"]
              : ["PENDING", "RUNNING"].includes(run.status)
                ? ["pause", "cancel"]
                : run.status === "FAILED"
                  ? ["retry"]
                  : []
            ).map((a) => (
              <Confirmation
                key={a}
                label={a[0].toUpperCase() + a.slice(1)}
                disabled={act.isPending}
                description={
                  a === "retry"
                    ? "Grant one new attempt to the failed step."
                    : a === "pause"
                      ? "An in-flight step can finish. New claims will wait."
                      : a === "cancel"
                        ? "Cancel unfinished steps and revoke the active lease."
                        : "Continue executing from the saved state."
                }
                action={() => change(a)}
              />
            ))}
          </Header>
          <div className="record-meta">
            <Link to={"/workflows/" + run.workflow_id}>
              Workflow v{run.version}
            </Link>
            <span>Started {time(run.started_at)}</span>
            <span>Ended {time(run.completed_at)}</span>
            <span>Duration {duration(run.started_at, run.completed_at)}</span>
          </div>
          {run.error_message && <p className="failure">{run.error_message}</p>}
          <Panel title="Step timeline" icon={<GitBranch size={17} />}>
            <div className="timeline">
              {steps.map((s, i) => (
                <details key={s.id}>
                  <summary>
                    <span className="step-number">{i + 1}</span>
                    <span>
                      <strong>{s.name}</strong>
                      <small>{s.task_type}</small>
                    </span>
                    <span className="step-meta">
                      {s.attempt_count} / {s.max_attempts} attempts
                    </span>
                    <Badge status={s.status} />
                  </summary>
                  <div className="step-body">
                    <p>
                      Started {time(s.started_at)} · Duration{" "}
                      {duration(s.started_at, s.completed_at)}
                    </p>
                    <p>
                      Worker <code>{s.worker_id || "—"}</code>
                    </p>
                    {s.error_message && (
                      <p className="failure">{s.error_message}</p>
                    )}
                    <JsonView value={s.output_data} />
                    {s.status === "FAILED" && run.status === "FAILED" && (
                      <Confirmation
                        label="Retry step"
                        description="Grant one additional attempt to this step."
                        action={() => change("steps/" + s.id + "/retry")}
                      />
                    )}
                  </div>
                </details>
              ))}
            </div>
          </Panel>
          <div className="detail-grid">
            <Panel title="Input JSON" icon={<Braces size={16} />}>
              <JsonView value={run.input_data} />
            </Panel>
            <Panel title="Final output" icon={<Terminal size={16} />}>
              <JsonView value={run.output_data} />
            </Panel>
          </div>
          <Panel title="Execution attempts">
            <Data query={history}>
              {(p) => (
                <>
                  {p.items.length ? (
                    <div className="scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Step</th>
                            <th>Attempt</th>
                            <th>Worker</th>
                            <th>Status</th>
                            <th>Duration</th>
                            <th>Error</th>
                          </tr>
                        </thead>
                        <tbody>
                          {p.items.map((a) => (
                            <tr key={a.id}>
                              <td>
                                {
                                  steps.find(
                                    (s) => s.id === a.step_execution_id,
                                  )?.name
                                }
                              </td>
                              <td>{a.attempt_number}</td>
                              <td>
                                <Link
                                  className="mono"
                                  to={"/workers/" + a.worker_id}
                                >
                                  {short(a.worker_id)}
                                </Link>
                              </td>
                              <td>
                                <Badge status={a.status} />
                              </td>
                              <td>
                                {a.duration_ms === null
                                  ? "—"
                                  : a.duration_ms + " ms"}
                              </td>
                              <td>{a.error_message || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty text="Waiting for the first claim." />
                  )}
                  <Pager data={p} onChange={setAttemptOffset} />
                </>
              )}
            </Data>
          </Panel>
          <Panel title="Event log" icon={<Clock3 size={17} />}>
            <EventLog events={events.items} />
            <Pager data={events} onChange={setOffset} />
          </Panel>
        </>
      )}
    </Data>
  );
}
