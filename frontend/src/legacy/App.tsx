import { useEffect, useState } from "react";
import "./style.css";
type Step = {
  id: number;
  name: string;
  status: string;
  attempts: number;
  error?: string;
};
type Workflow = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  steps: Step[];
};
const api = "/compat";
export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [items, setItems] = useState<Workflow[]>([]);
  const [email, setEmail] = useState("operator@example.com");
  const [password, setPassword] = useState("");
  const [tenant, setTenant] = useState("demo");
  const [message, setMessage] = useState("");
  async function request(path: string, options: any = {}) {
    return fetch(api + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...options.headers,
      },
    });
  }
  async function login() {
    let r = await fetch(api + "/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, tenant_id: tenant }),
    });
    if (r.status === 409)
      r = await fetch(api + "/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, tenant_id: tenant }),
      });
    const d = await r.json();
    if (d.token) {
      localStorage.setItem("token", d.token);
      setToken(d.token);
    } else setMessage(d.detail || "Authentication failed");
  }
  async function load() {
    if (!token) return;
    const r = await request("/workflows");
    if (r.ok) setItems(await r.json());
  }
  useEffect(() => {
    load();
  }, [token]);
  async function create() {
    const r = await request("/workflows", {
      method: "POST",
      body: JSON.stringify({
        name: "Example durable workflow",
        input: { value: "hello" },
        idempotency_key: crypto.randomUUID(),
        steps: [
          {
            name: "Echo input",
            action: "echo",
            retries: 3,
            timeout_seconds: 30,
          },
          { name: "Finalize", action: "echo", retries: 3, timeout_seconds: 30 },
        ],
      }),
    });
    if (r.ok) load();
    else setMessage((await r.json()).detail || "Submit failed");
  }
  async function retry(id: string) {
    await request(`/workflows/${id}/retry`, { method: "POST" });
    load();
  }
  if (!token)
    return (
      <main className="auth">
        <div className="panel">
          <span className="eyebrow">DURABLE WORKFLOW ENGINE</span>
          <h1>Operate workflows with confidence.</h1>
          <p>Transactional state, at-least-once delivery, idempotent steps.</p>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            placeholder="Password"
          />
          <input
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
            placeholder="Tenant"
          />
          <button onClick={login}>Continue</button>
          {message && <small>{message}</small>}
        </div>
      </main>
    );
  return (
    <main>
      <header>
        <div>
          <span className="eyebrow">CONTROL PLANE</span>
          <h1>Workflow operations</h1>
        </div>
        <button onClick={create}>+ New workflow</button>
      </header>
      <section className="grid">
        {["COMPLETED", "RUNNING", "PENDING", "FAILED"].map((s) => (
          <div className="stat" key={s}>
            <span>{s}</span>
            <strong>{items.filter((x) => x.status === s).length}</strong>
          </div>
        ))}
      </section>
      <section className="panel table">
        <div className="tablehead">
          <b>Recent executions</b>
          <button className="ghost" onClick={load}>
            Refresh
          </button>
        </div>
        {items.map((w) => (
          <article key={w.id}>
            <div className="row">
              <div>
                <b>{w.name}</b>
                <small>{w.id}</small>
              </div>
              <span className={"pill " + w.status.toLowerCase()}>
                {w.status}
              </span>
              {w.status === "FAILED" && (
                <button className="ghost" onClick={() => retry(w.id)}>
                  Retry
                </button>
              )}
            </div>
            <div className="steps">
              {w.steps.map((s) => (
                <span key={s.id} className={"step " + s.status.toLowerCase()}>
                  <i /> {s.name}{" "}
                  <em>
                    {s.status} · {s.attempts} attempt
                    {s.attempts === 1 ? "" : "s"}
                  </em>
                </span>
              ))}
            </div>
          </article>
        ))}
        {!items.length && (
          <p className="empty">
            No executions yet. Submit a workflow to begin.
          </p>
        )}
      </section>
    </main>
  );
}
