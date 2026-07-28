import React from "react";
import type { NarrationMode } from "../contracts";
import { channelPresentation } from "../channels";
import { useStudio } from "../state/useStudio";

const NARRATION_MODES: Array<{
  id: NarrationMode;
  label: string;
  range: string;
  minSeconds: number;
  maxSeconds: number;
  marker: string;
  description: string;
}> = [
  {
    id: "signal",
    label: "Signal",
    range: "3–5 min",
    minSeconds: 180,
    maxSeconds: 300,
    marker: "01",
    description:
      "Fast, decisive: what happened, why now, who is affected, what comes next.",
  },
  {
    id: "explained",
    label: "Explained",
    range: "8–12 min",
    minSeconds: 480,
    maxSeconds: 720,
    marker: "02",
    description:
      "The main format: event, context, system, consequences and uncertainty.",
  },
  {
    id: "deep_dive",
    label: "Deep Dive",
    range: "15–25 min",
    minSeconds: 900,
    maxSeconds: 1500,
    marker: "03",
    description:
      "Patient and investigative: evidence, stakeholders, trade-offs and scenarios.",
  },
  {
    id: "india_builds",
    label: "India Builds",
    range: "30–120 min",
    minSeconds: 1800,
    maxSeconds: 7200,
    marker: "04",
    description:
      "Documentary systems narration for infrastructure, industry and national capability.",
  },
];

export const isNarrationMode = (value: unknown): value is NarrationMode =>
  NARRATION_MODES.some((mode) => mode.id === value);

export const NarrationModeSelector: React.FC<{
  value: NarrationMode;
  durationSeconds: number;
  disabled?: boolean;
  onChange: (mode: NarrationMode) => void;
}> = ({ value, durationSeconds, disabled, onChange }) => {
  const studio = useStudio();
  const channel = channelPresentation(
    studio.selectedChannelId,
    studio.selectedChannelProfile,
  );
  const selected = NARRATION_MODES.find((mode) => mode.id === value)!;
  const outsideRange =
    durationSeconds < selected.minSeconds ||
    durationSeconds > selected.maxSeconds;

  return (
    <fieldset className="narration-mode-fieldset" disabled={disabled}>
      <legend>
        <span>Narration format</span>
        <small>Choose before generation</small>
      </legend>
      <div className="narration-mode-grid">
        {NARRATION_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            data-narration-mode={mode.id}
            className={`narration-mode-card ${value === mode.id ? "is-selected" : ""}`}
            aria-pressed={value === mode.id}
            onClick={() => onChange(mode.id)}
          >
            <span className="narration-mode-marker">{mode.marker}</span>
            <span className="narration-mode-copy">
              <strong>{channel.name} {mode.label}</strong>
              <small>{mode.range}</small>
              <em>{mode.description}</em>
            </span>
            <span className="narration-mode-check" aria-hidden="true">
              ✓
            </span>
          </button>
        ))}
      </div>
      <p
        className={`narration-mode-guidance ${outsideRange ? "is-warning" : ""}`}
      >
        {outsideRange
          ? `${selected.label} is designed for ${selected.range}; your custom runtime will still be respected.`
          : `${selected.label} pacing matches the selected ${Math.round(durationSeconds / 60)}-minute runtime.`}
      </p>
    </fieldset>
  );
};
