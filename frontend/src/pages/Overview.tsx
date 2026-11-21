import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  Box,
  CheckCircle2,
  CirclePlay,
  Cpu,
  Database,
  GitBranch,
  Layers3,
  Network,
  Plus,
  Radio,
  Server,
  Workflow as Flow,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  useApi,
  short,
  time,
  duration,
  type Stats,
  type Health,
  type Page,
  type Run,
} from "../api";
import { Badge, Button, Data, Empty, Header, Panel } from "../components/ui";

export function RunTable({
  runs,
  details = false,
}: {
  runs: Run[];
  details?: boolean;
}) {
  if (!runs.length) return <Empty text="No executions match this view." />;
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr>
            <th>Workflow</th>
            <th>Run ID</th>
            <th>Status</th>
            <th>Started</th>
            <th>Duration</th>
            {details && (
              <>
                <th>Steps</th>
                <th>Last error</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                <Link className="workflow-link" to={"/runs/" + r.id}>
                  <span className="mini-icon">
                    <Flow size={15} />
                  </span>
                  {r.workflow_name}
                </Link>
              </td>
              <td>
                <Link className="mono dim" to={"/runs/" + r.id}>
                  {short(r.id)}
                </Link>
              </td>
              <td>
                <Badge status={r.status} />
              </td>
              <td>{time(r.started_at)}</td>
              <td className="mono">{duration(r.started_at, r.completed_at)}</td>
              {details && (
                <>
                  <td>{r.step_count}</td>
                  <td>{r.error_message || "—"}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function Services({ health }: { health: Health }) {
  const list = [
    ["API service", health.api, Radio],
    ["PostgreSQL", health.postgres, Database],
    ["Redis", health.redis, Layers3],
    ["Worker pool", health.workers, Cpu],
  ] as const;
  return (
    <div className="services">
      {list.map(([name, status, Icon]) => (
        <div key={name}>
          <span>
            <Icon size={17} />
            {name}
          </span>
          <span
            className={
              "service-state " + (status === "healthy" ? "good" : "warn")
            }
          >
            <i />
            {status === "healthy" ? "Operational" : "Unavailable"}
          </span>
        </div>
      ))}
    </div>
  );
}
export function Metric({
  label,
  value,
  note,
  icon: Icon,
  tone = "",
}: {
  label: string;
  value: string | number;
  note: string;
  icon: typeof Activity;
  tone?: string;
}) {
  return (
    <div className="metric">
      <div>
        <span>{label}</span>
        <Icon className={tone} size={17} />
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
export default function Overview() {
  const stats = useApi<Stats>("/system/stats", 5000),
    health = useApi<Health>("/system/health", 5000),
    recent = useApi<Page<Run>>("/runs?limit=6", 5000);
  const [hours, setHours] = useState(24);
  return (
    <>
      <Header title="Overview" sub="Live execution activity and engine health.">
        <Button variant="default" asChild>
          <Link to="/workflows/new">
            <Plus size={16} />
            Create workflow
          </Link>
        </Button>
      </Header>
      <Data query={stats}>
        {(s) => {
          const total = s.completed_runs + s.failed_runs;
          return (
            <>
              <div className="metrics">
                <Metric
                  label="Total executions"
                  value={s.total_runs}
                  note={`Across ${s.total_workflows} workflows`}
                  icon={Box}
                />
                <Metric
                  label="Running now"
                  value={s.running_runs}
                  note={`${s.pending_tasks} pending tasks`}
                  icon={CirclePlay}
                  tone="blue"
                />
                <Metric
                  label="Success rate"
                  value={
                    total
                      ? ((s.completed_runs / total) * 100).toFixed(1) + "%"
                      : "—"
                  }
                  note={`${s.completed_runs} completed · ${s.failed_runs} failed`}
                  icon={CheckCircle2}
                  tone="lime"
                />
                <Metric
                  label="Active workers"
                  value={s.active_workers}
                  note={`${s.running_tasks} leased tasks`}
                  icon={Cpu}
                />
              </div>
              <div className="overview-grid">
                <Panel
                  title="Execution activity"
                  icon={<Activity size={18} />}
                  extra={
                    <select
                      aria-label="Activity window"
                      value={hours}
                      onChange={(e) => setHours(+e.target.value)}
                    >
                      <option value={24}>Last 24 hours</option>
                      <option value={12}>Last 12 hours</option>
                      <option value={6}>Last 6 hours</option>
                    </select>
                  }
                >
                  <div className="legend">
                    <span className="lime">
                      <i />
                    </span>
                    Completed
                    <span className="rose">
                      <i />
                    </span>
                    Failed
                    <span className="blue">
                      <i />
                    </span>
                    Started
                  </div>
                  <div className="chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={s.activity.slice(-hours)}
                        margin={{ left: -25, right: 14, top: 10, bottom: 0 }}
                      >
                        <defs>
                          <linearGradient
                            id="completed-fill"
                            x1="0"
                            y1="0"
                            x2="0"
                            y2="1"
                          >
                            <stop
                              offset="0%"
                              stopColor="#b5ec83"
                              stopOpacity={0.32}
                            />
                            <stop
                              offset="100%"
                              stopColor="#b5ec83"
                              stopOpacity={0.01}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid
                          vertical={false}
                          stroke="#2b3238"
                          strokeDasharray="3 5"
                        />
                        <XAxis
                          dataKey="hour"
                          axisLine={false}
                          tickLine={false}
                          minTickGap={36}
                          tickFormatter={(v) =>
                            new Date(v).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          }
                        />
                        <YAxis
                          allowDecimals={false}
                          domain={[0, "auto"]}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip
                          labelFormatter={(v) => time(String(v))}
                          contentStyle={{
                            background: "#1c2328",
                            border: "1px solid #3a4349",
                            borderRadius: 8,
                          }}
                        />
                        <Area
                          type="linear"
                          name="Started"
                          dataKey="started"
                          stroke="#77aafa"
                          strokeDasharray="4 3"
                          fill="transparent"
                          isAnimationActive={false}
                        />
                        <Area
                          type="linear"
                          name="Failed"
                          dataKey="failed"
                          stroke="#ef9299"
                          fill="transparent"
                          isAnimationActive={false}
                        />
                        <Area
                          type="linear"
                          name="Completed"
                          dataKey="completed"
                          stroke="#b5ec83"
                          strokeWidth={2}
                          fill="url(#completed-fill)"
                          isAnimationActive={false}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </Panel>
                <Panel
                  title="System health"
                  icon={<Network size={17} />}
                  extra={
                    <Link className="quiet-link" to="/system">
                      Details
                    </Link>
                  }
                >
                  <Data query={health}>{(h) => <Services health={h} />}</Data>
                </Panel>
              </div>
            </>
          );
        }}
      </Data>
      <Panel
        title="Recent executions"
        icon={<GitBranch size={17} />}
        extra={
          <Link className="quiet-link" to="/runs">
            View all runs
          </Link>
        }
      >
        <Data query={recent}>{(d) => <RunTable runs={d.items} />}</Data>
      </Panel>
    </>
  );
}
