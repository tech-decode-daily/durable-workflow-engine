import { lazy, Suspense, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Activity,
  BookOpen,
  Boxes,
  ChevronRight,
  ClipboardList,
  Cpu,
  ExternalLink,
  GitBranch,
  Layers3,
  LayoutDashboard,
  Menu,
  PanelLeft,
  Radio,
  Server,
  Settings as Cog,
  Workflow as Flow,
  X,
} from "lucide-react";
import { type Health, useApi } from "./api";
import { Loading } from "./components/ui";
import Overview from "./pages/Overview";
import { Listings } from "./pages/Lists";
import {
  Events,
  Settings,
  System,
  Workers,
  WorkerDetails,
} from "./pages/Operations";
import { RunDetails, WorkflowDetails } from "./pages/Details";
const Builder = lazy(() => import("./pages/Builder"));
const links = [
  {
    title: "Workspace",
    nav: [
      ["Overview", "/", LayoutDashboard],
      ["Workflows", "/workflows", Flow],
      ["Executions", "/runs", Layers3],
    ],
  },
  {
    title: "Operations",
    nav: [
      ["Workers", "/workers", Cpu],
      ["Event log", "/events", ClipboardList],
      ["System health", "/system", Activity],
    ],
  },
] as const;
export default function App() {
  const { pathname } = useLocation(),
    [menu, setMenu] = useState(false),
    h = useApi<Health>("/system/health", 5000);
  useEffect(() => {
    setMenu(false);
    window.scrollTo(0, 0);
  }, [pathname]);
  const page =
    links
      .flatMap((x) => [...x.nav])
      .find(([, url]) =>
        url === "/" ? pathname === "/" : pathname.startsWith(url),
      )?.[0] || "Settings";
  const connected = h.data && h.data.api === "healthy" && !h.error;
  const healthy =
    connected &&
    [h.data?.postgres, h.data?.redis, h.data?.workers].every(
      (s) => s === "healthy",
    );
  if (pathname === "/legacy")
    return (
      <iframe
        title="Prototype workflow console"
        className="legacy-frame"
        src="/legacy.html"
      />
    );
  return (
    <div className="shell">
      {menu && (
        <button
          aria-label="Close navigation"
          className="scrim"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={menu ? "open" : ""}>
        <Link className="brand" to="/">
          <img src="/durable.svg" alt="" />
          Durable
        </Link>
        <div className="workspace-id">
          <span className="workspace-icon">
            <Boxes size={19} />
          </span>
          <div>
            <strong>Local workspace</strong>
            <small>Self-hosted engine</small>
          </div>
        </div>
        <nav>
          {links.map((g) => (
            <div key={g.title}>
              <h3>{g.title}</h3>
              {g.nav.map(([label, url, Icon]) => (
                <NavLink end={url === "/"} key={url} to={url}>
                  <Icon size={17} />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="nav-foot">
          <NavLink to="/settings">
            <Cog size={17} />
            Settings
          </NavLink>
          <a href="/compat/docs" target="_blank" rel="noreferrer">
            <BookOpen size={17} />
            API docs
            <ExternalLink className="ext" size={13} />
          </a>
          <div className="engine-id">
            <span className="engine-symbol">
              <Server size={17} />
            </span>
            <div>
              <strong>Durable engine</strong>
              <small>{h.data ? "v" + h.data.version : "Connecting…"}</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-column">
        <div className="topbar">
          <button
            className="mobile"
            aria-label="Open navigation"
            onClick={() => setMenu(true)}
          >
            <Menu size={19} />
          </button>
          <div className="crumb">
            <PanelLeft size={16} />
            <span>Workspace</span>
            <ChevronRight size={13} />
            <b>{page}</b>
          </div>
          <Link
            to="/system"
            className={"live-pill " + (healthy ? "" : "pending")}
          >
            <i />
            {h.isPending
              ? "Connecting"
              : healthy
                ? "System operational"
                : connected
                  ? "System degraded"
                  : "API unavailable"}
          </Link>
        </div>
        <main>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route
                path="/workflows"
                element={<Listings key="workflows" kind="workflows" />}
              />
              <Route
                path="/runs"
                element={<Listings key="runs" kind="runs" />}
              />
              <Route path="/workflows/new" element={<Builder />} />
              <Route path="/workflows/:workflowId/edit" element={<Builder />} />
              <Route
                path="/workflows/:workflowId"
                element={<WorkflowDetails />}
              />
              <Route path="/runs/:runId" element={<RunDetails />} />
              <Route path="/workers" element={<Workers />} />
              <Route path="/workers/:workerId" element={<WorkerDetails />} />
              <Route path="/events" element={<Events />} />
              <Route path="/system" element={<System />} />
              <Route path="/settings" element={<Settings />} />
              <Route
                path="*"
                element={
                  <section>
                    <h1>Page not found</h1>
                    <Link to="/">Return to overview</Link>
                  </section>
                }
              />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
