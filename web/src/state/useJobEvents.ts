import React from "react";
import type { RenderJob } from "../contracts";

const isRenderJob = (value: unknown): value is RenderJob =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as { job_id?: unknown }).job_id === "string" &&
  typeof (value as { status?: unknown }).status === "string";

const notifyTerminalJobs = (jobs: RenderJob[]) => {
  if (
    localStorage.getItem("synthpost.notifications") !== "enabled" ||
    !("Notification" in window) ||
    Notification.permission !== "granted"
  ) {
    return;
  }
  for (const job of jobs.slice(0, 3)) {
    const title =
      job.status === "failed"
        ? "SynthPost needs attention"
        : "SynthPost task complete";
    const options = {
      body:
        job.status === "failed"
          ? `${job.job_type}: ${job.error ?? "Job failed"}`
          : `${job.job_type}: ${job.stage}`,
      icon: "/synthpost-icon.svg",
      tag: job.job_id,
    };
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.ready.then((registration) =>
        registration.showNotification(title, options),
      );
    } else {
      new Notification(title, options);
    }
  }
};

export const useJobEvents = (
  onJobs: (jobs: RenderJob[]) => void,
  onError: (message: string) => void,
) => {
  const previousJobs = React.useRef<RenderJob[]>([]);
  const onJobsRef = React.useRef(onJobs);
  const onErrorRef = React.useRef(onError);
  onJobsRef.current = onJobs;
  onErrorRef.current = onError;

  React.useEffect(() => {
    const eventSource = new EventSource("/api/job-events");
    eventSource.addEventListener("jobs", (event) => {
      try {
        const value: unknown = JSON.parse(event.data);
        if (!Array.isArray(value) || !value.every(isRenderJob)) {
          throw new Error("Job event payload did not match the RenderJob contract.");
        }
        const jobs = value;
        const terminalTransitions = jobs.filter((job) => {
          const previous = previousJobs.current.find(
            (candidate) => candidate.job_id === job.job_id,
          );
          return (
            previous &&
            previous.status !== job.status &&
            ["completed", "failed"].includes(job.status)
          );
        });
        previousJobs.current = jobs;
        notifyTerminalJobs(terminalTransitions);
        onJobsRef.current(jobs);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Invalid job event payload.";
        console.error("Failed to process jobs event", error);
        onErrorRef.current(message);
      }
    });
    eventSource.onerror = () => {
      // EventSource reconnects automatically; keep the UI usable and expose the state.
      onErrorRef.current("Live job updates disconnected; reconnecting automatically.");
    };
    return () => eventSource.close();
  }, []);
};
