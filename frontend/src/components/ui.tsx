import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useState } from "react";
import { Slot } from "@radix-ui/react-slot";
import * as Dialog from "@radix-ui/react-dialog";
import { cva, type VariantProps } from "class-variance-authority";
import { twMerge } from "tailwind-merge";
import { AlertCircle, ChevronLeft, ChevronRight, Inbox, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Page } from "../api";

const buttonVariants = cva("btn", {
  variants: {
    variant: {
      default: "primary",
      outline: "outline",
      ghost: "ghost",
      danger: "danger",
    },
  },
  defaultVariants: { variant: "outline" },
});
type Props = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };
// shadcn/ui Button and Dialog primitives, styled with the console theme.
export function Button({ asChild, variant, className, ...props }: Props) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      className={twMerge(buttonVariants({ variant }), className)}
      {...props}
    />
  );
}
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content
          className="dialog"
          {...(!description ? {"aria-describedby": undefined} : {})}
        >
          <Dialog.Title>{title}</Dialog.Title>
          {description && (
            <Dialog.Description>{description}</Dialog.Description>
          )}
          <Dialog.Close aria-label="Close" className="close">
            <X size={18} />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function useAction() {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (fn: () => Promise<void>) => fn(),
    onSuccess: () => cache.invalidateQueries(),
    onError: (err: Error) => toast.error(err.message),
  });
}
export function Badge({ status }: { status: string }) {
  return (
    <span className={"badge " + status.toLowerCase()}>
      <i />
      {status.toLowerCase().replaceAll("_", " ")}
    </span>
  );
}
export function Header({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      <div className="actions">{children}</div>
    </header>
  );
}
export function Panel({
  title,
  icon,
  extra,
  children,
  className = "",
}: {
  title: string;
  icon?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <div className="panel-head">
        <h2>
          {icon}
          {title}
        </h2>
        {extra}
      </div>
      {children}
    </section>
  );
}
export function Empty({ text }: { text: string }) {
  return (
    <div className="empty">
      <Inbox size={24} />
      <span>{text}</span>
    </div>
  );
}
export function Loading() {
  return (
    <div aria-label="Loading" className="skeleton">
      <i />
      <i />
      <i />
    </div>
  );
}
export function Failure({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="failure">
      <AlertCircle size={17} />
      {error.message}
      {retry && <Button onClick={retry}>Try again</Button>}
    </div>
  );
}
export function Data<T>({
  query,
  children,
}: {
  query: { data?: T; error: Error | null; refetch: () => unknown };
  children: (data: T) => ReactNode;
}) {
  return (
    <>
      {query.error && (
        <Failure error={query.error} retry={() => query.refetch()} />
      )}{" "}
      {query.data !== undefined
        ? children(query.data)
        : !query.error && <Loading />}
    </>
  );
}
export function JsonView({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2) ?? "—"}</pre>;
}
export function Pager({
  data,
  onChange,
}: {
  data: Page<unknown>;
  onChange: (n: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {data.total
          ? `${data.offset + 1}–${Math.min(data.total, data.offset + data.limit)} of ${data.total}`
          : "0 records"}
      </span>
      <Button
        aria-label="Previous page"
        disabled={!data.offset}
        onClick={() => onChange(Math.max(0, data.offset - data.limit))}
      >
        <ChevronLeft size={15} />
      </Button>
      <Button
        aria-label="Next page"
        disabled={data.offset + data.limit >= data.total}
        onClick={() => onChange(data.offset + data.limit)}
      >
        <ChevronRight size={15} />
      </Button>
    </div>
  );
}
export function Confirmation({
  label,
  action,
  description,
  disabled,
}: {
  label: string;
  action: () => void;
  description: string;
  disabled?: boolean;
}) {
  const [open, set] = useState(false);
  return (
    <>
      <Button disabled={disabled} onClick={() => set(true)}>
        {label}
      </Button>
      <Modal
        open={open}
        onOpenChange={set}
        title={label}
        description={description}
      >
        <div className="actions">
          <Button onClick={() => set(false)}>Go back</Button>
          <Button
            variant="default"
            onClick={() => {
              set(false);
              action();
            }}
          >
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}
