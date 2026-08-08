import React from "react";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import type { AutonomyRunView } from "../contracts";

type DisableableControl =
  | HTMLButtonElement
  | HTMLInputElement
  | HTMLSelectElement
  | HTMLTextAreaElement;

const CONTROL_SELECTOR = "button, input, select, textarea";

/**
 * Leaves the current production checkpoint visible while preventing a second
 * operator from mutating it underneath Hermes. Native controls are disabled so
 * keyboard and assistive-technology users receive the same ownership boundary.
 */
export const AutonomyOwnedWorkspace: React.FC<{
  run?: AutonomyRunView;
  children: React.ReactNode;
}> = ({ run, children }) => {
  const rootRef = React.useRef<HTMLDivElement>(null);
  const originalDisabled = React.useRef(new Map<DisableableControl, boolean>());
  const originalDraggable = React.useRef(new Map<HTMLElement, string | null>());
  const locked = Boolean(run);

  React.useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || !locked) return;

    const enforceReadOnly = () => {
      root.querySelectorAll<DisableableControl>(CONTROL_SELECTOR).forEach((control) => {
        if (!originalDisabled.current.has(control)) {
          originalDisabled.current.set(control, control.disabled);
        }
        if (!control.disabled) control.disabled = true;
        if (control.dataset.autonomyOwnedDisabled !== "true") {
          control.dataset.autonomyOwnedDisabled = "true";
        }
      });
      root.querySelectorAll<HTMLElement>('[draggable="true"]').forEach((element) => {
        if (!originalDraggable.current.has(element)) {
          originalDraggable.current.set(element, element.getAttribute("draggable"));
        }
        element.setAttribute("draggable", "false");
        if (element.dataset.autonomyOwnedDisabled !== "true") {
          element.dataset.autonomyOwnedDisabled = "true";
        }
      });
    };

    enforceReadOnly();
    const observer = new MutationObserver(enforceReadOnly);
    observer.observe(root, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["disabled", "draggable"],
    });

    return () => {
      observer.disconnect();
      originalDisabled.current.forEach((wasDisabled, control) => {
        control.disabled = wasDisabled;
        delete control.dataset.autonomyOwnedDisabled;
      });
      originalDraggable.current.forEach((value, element) => {
        if (value === null) element.removeAttribute("draggable");
        else element.setAttribute("draggable", value);
        delete element.dataset.autonomyOwnedDisabled;
      });
      originalDisabled.current.clear();
      originalDraggable.current.clear();
    };
  }, [locked]);

  if (!run) return <>{children}</>;

  return (
    <section
      className="autonomy-owned-workspace"
      aria-label="Hermes-owned production workspace"
    >
      <div className="autonomy-owned-banner" role="status">
        <span className="autonomy-owned-lock" aria-hidden="true">
          <LockKeyhole size={15} />
        </span>
        <div>
          <strong>Read-only production checkpoint</strong>
          <p>
            {run.status === "cancelled"
              ? "The worker is stopping and still owns this episode until it releases the execution lease."
              : `Hermes owns this episode while the run is ${run.status.replace(/_/g, " ")}.`}
            {run.status === "needs_attention"
              ? " Monitor every desk here, or use the night-shift control above to retry or take over manually before editing."
              : run.status === "cancelled"
                ? " Editing unlocks automatically when the handler has exited."
                : " Monitor every desk here, or stop the night shift above before editing."}
          </p>
        </div>
        <span className="autonomy-owned-policy">
          <ShieldCheck size={13} aria-hidden="true" /> Run {run.run_id.slice(-6)}
        </span>
      </div>
      <div ref={rootRef} className="autonomy-owned-workspace-body">
        {children}
      </div>
    </section>
  );
};
