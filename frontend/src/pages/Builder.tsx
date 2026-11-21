import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type NodeProps,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowDown,
  ArrowUp,
  Braces,
  Check,
  GitBranch,
  Layers3,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  request,
  useApi,
  type Definition,
  type StepSpec,
  type TaskInfo,
  type Workflow,
} from "../api";
import {
  Button,
  Data,
  Header,
  JsonView,
  Panel,
  useAction,
} from "../components/ui";

type DraftStep = StepSpec & { uid: string; raw: string };
function newStep(number: number): DraftStep {
  return {
    uid: crypto.randomUUID(),
    key: "step_" + number,
    name: "Step " + number,
    task_type: "data.validate_json",
    config: {},
    raw: "{}",
    retry: { max_attempts: 3, delay_seconds: 2, max_delay_seconds: 300 },
    timeout_seconds: 30,
  };
}
function StepNode({
  data,
  selected,
}: NodeProps<Node<{ name: string; type: string; position: number }>>) {
  return (
    <div className={"flow-node " + (selected ? "selected" : "")}>
      <Handle type="target" position={Position.Top} />
      <span className="node-symbol">
        <Layers3 size={17} />
      </span>
      <div>
        <small>STEP {String(data.position + 1).padStart(2, "0")}</small>
        <strong>{data.name}</strong>
        <code>{data.type}</code>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
const nodeTypes = { sequential: StepNode };
export default function Builder() {
  const { workflowId } = useParams();
  const q = useApi<Workflow>("/workflows/" + workflowId, false, !!workflowId);
  return workflowId ? (
    <Data query={q}>{(w) => <Editor key={w.id} initial={w} />}</Data>
  ) : (
    <Editor />
  );
}
export function Editor({ initial }: { initial?: Workflow }) {
  const nav = useNavigate(),
    act = useAction(),
    registry = useApi<TaskInfo[]>("/tasks/registry");
  const [name, setName] = useState(initial?.draft.name || ""),
    [desc, setDesc] = useState(initial?.draft.description || "");
  const [steps, setSteps] = useState<DraftStep[]>(() =>
    initial
      ? initial.draft.steps.map((s) => ({
          ...s,
          uid: crypto.randomUUID(),
          raw: JSON.stringify(s.config, null, 2),
        }))
      : [newStep(1)],
  );
  const [selected, select] = useState(steps[0]?.uid),
    [id, setId] = useState(initial?.id),
    [issue, setIssue] = useState(""),
    [preview, setPreview] = useState(false);
  const index = steps.findIndex((s) => s.uid === selected),
    current = steps[index];
  function update(patch: Partial<DraftStep>) {
    setSteps((ss) =>
      ss.map((s) => (s.uid === selected ? { ...s, ...patch } : s)),
    );
    setIssue("");
  }
  function add() {
    let n = steps.length + 1;
    while (steps.some((s) => s.key === "step_" + n)) n++;
    const next = newStep(n);
    setSteps([...steps, next]);
    select(next.uid);
  }
  function move(by: number) {
    const ss = [...steps];
    [ss[index], ss[index + by]] = [ss[index + by], ss[index]];
    setSteps(ss);
  }
  function remove() {
    const ss = steps.filter((s) => s.uid !== selected);
    setSteps(ss);
    select(ss[Math.min(index, ss.length - 1)]?.uid);
  }
  function definition(): Definition {
    if (!name.trim()) throw Error("Give the workflow a name.");
    if (!steps.length) throw Error("Add at least one step.");
    const keys = new Set<string>();
    return {
      name: name.trim(),
      description: desc,
      steps: steps.map(({ uid, raw, ...s }) => {
        if (
          !s.name.trim() ||
          !/^([a-z][a-z0-9_-]{0,63})$/.test(s.key) ||
          keys.has(s.key)
        )
          throw Error("Each step needs a name and a unique lowercase key.");
        let config;
        try {
          config = JSON.parse(raw);
        } catch {
          throw Error(s.name + " has invalid configuration JSON.");
        }
        if (!config || Array.isArray(config) || typeof config !== "object")
          throw Error(s.name + " configuration must be a JSON object.");
        if (config.source && !keys.has(config.source))
          throw Error(s.name + " must reference an earlier step.");
        keys.add(s.key);
        return { ...s, config };
      }),
    };
  }
  function submit(mode: "validate" | "draft" | "publish") {
    act.mutate(async () => {
      try {
        const body = definition();
        if (mode === "validate") {
          await request("/definitions/validate", "POST", body);
          toast.success("Definition is valid");
          setIssue("");
          return;
        }
        const saved = await request<Workflow>(
          id ? "/workflows/" + id : "/workflows",
          id ? "PUT" : "POST",
          body,
        );
        setId(saved.id);
        if (mode === "publish")
          await request("/workflows/" + saved.id + "/publish", "POST");
        toast.success(mode === "publish" ? "Version published" : "Draft saved");
        nav("/workflows/" + saved.id);
      } catch (e) {
        setIssue((e as Error).message);
        throw e;
      }
    });
  }
  let json: unknown;
  try {
    json = definition();
  } catch (e) {
    json = { validation: (e as Error).message };
  }
  return (
    <>
      <Header
        title={initial ? "Edit workflow" : "Create workflow"}
        sub="Define a sequence and configure how each step executes."
      >
        <Button onClick={() => submit("validate")} disabled={act.isPending}>
          <Check size={15} />
          Validate
        </Button>
        <Button onClick={() => submit("draft")} disabled={act.isPending}>
          <Save size={15} />
          Save draft
        </Button>
        <Button
          variant="default"
          onClick={() => submit("publish")}
          disabled={act.isPending}
        >
          Publish
        </Button>
      </Header>
      {issue && (
        <div role="alert" className="failure">
          {issue}
        </div>
      )}
      <div className="definition-fields">
        <label>
          Workflow name
          <input
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Document processing"
          />
        </label>
        <label>
          Description
          <input
            maxLength={2000}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="What does this workflow do?"
          />
        </label>
      </div>
      <div className="builder-grid">
        <Panel
          title="Sequence"
          icon={<GitBranch size={17} />}
          extra={
            <Button disabled={steps.length >= 40} onClick={add}>
              <Plus size={15} />
              Add step
            </Button>
          }
        >
          <div className="flow">
            <ReactFlow
              nodes={steps.map((s, i) => ({
                id: s.uid,
                type: "sequential",
                position: { x: 30, y: i * 120 },
                selected: s.uid === selected,
                data: { name: s.name, type: s.task_type, position: i },
              }))}
              nodeTypes={nodeTypes}
              edges={steps
                .slice(1)
                .map((s, i) => ({
                  id: s.uid,
                  source: steps[i].uid,
                  target: s.uid,
                  type: "straight",
                  style: { stroke: "#74865f", strokeWidth: 2 },
                }))}
              onNodeClick={(_, node) => select(node.id)}
              fitView
              fitViewOptions={{ maxZoom: 1.1, padding: 0.25 }}
              nodesDraggable={false}
              nodesConnectable={false}
              deleteKeyCode={null}
              proOptions={{ hideAttribution: true }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                color="#373e45"
                gap={18}
              />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </Panel>
        <Panel title="Step configuration" icon={<Braces size={17} />}>
          {current ? (
            <div className="form">
              <div className="actions">
                <select
                  aria-label="Selected step"
                  value={selected}
                  onChange={(e) => select(e.target.value)}
                >
                  {steps.map((s, i) => (
                    <option key={s.uid} value={s.uid}>
                      {i + 1}. {s.name}
                    </option>
                  ))}
                </select>
                <Button
                  aria-label="Move step up"
                  disabled={!index}
                  onClick={() => move(-1)}
                >
                  <ArrowUp size={15} />
                </Button>
                <Button
                  aria-label="Move step down"
                  disabled={index === steps.length - 1}
                  onClick={() => move(1)}
                >
                  <ArrowDown size={15} />
                </Button>
                <Button aria-label="Remove step" onClick={remove}>
                  <Trash2 size={15} />
                </Button>
              </div>
              <div className="field-pair">
                <label>
                  Step name
                  <input
                    value={current.name}
                    onChange={(e) => update({ name: e.target.value })}
                  />
                </label>
                <label>
                  Step key
                  <input
                    value={current.key}
                    onChange={(e) => update({ key: e.target.value })}
                  />
                </label>
              </div>
              <Data query={registry}>
                {(types) => (
                  <label>
                    Task type
                    <select
                      value={current.task_type}
                      onChange={(e) =>
                        update({ task_type: e.target.value, raw: "{}" })
                      }
                    >
                      {types.map((t) => (
                        <option key={t.task_type}>{t.task_type}</option>
                      ))}
                    </select>
                    <small>
                      {
                        types.find((t) => t.task_type === current.task_type)
                          ?.description
                      }
                    </small>
                  </label>
                )}
              </Data>
              <label>
                Configuration JSON
                <textarea
                  rows={4}
                  spellCheck={false}
                  value={current.raw}
                  onChange={(e) => update({ raw: e.target.value })}
                />
              </label>
              <div className="field-pair">
                {(
                  [
                    "max_attempts",
                    "delay_seconds",
                    "max_delay_seconds",
                  ] as const
                ).map((k, i) => (
                  <label key={k}>
                    {
                      [
                        "Maximum attempts",
                        "Retry delay (s)",
                        "Maximum delay (s)",
                      ][i]
                    }
                    <input
                      type="number"
                      min={i === 1 ? 0 : 1}
                      max={i === 0 ? 20 : 3600}
                      value={current.retry[k]}
                      onChange={(e) =>
                        update({
                          retry: {
                            ...current.retry,
                            [k]: Number(e.target.value),
                          },
                        })
                      }
                    />
                  </label>
                ))}
                <label>
                  Timeout (s)
                  <input
                    type="number"
                    min={1}
                    max={600}
                    value={current.timeout_seconds}
                    onChange={(e) =>
                      update({ timeout_seconds: +e.target.value })
                    }
                  />
                </label>
              </div>
            </div>
          ) : (
            <div className="empty">Add a step to configure it.</div>
          )}
        </Panel>
      </div>
      <Panel
        title="Definition JSON"
        icon={<Braces size={17} />}
        extra={
          <Button onClick={() => setPreview(!preview)}>
            {preview ? "Hide" : "Preview"}
          </Button>
        }
      >
        {preview && <JsonView value={json} />}
      </Panel>
    </>
  );
}
