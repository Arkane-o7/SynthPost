import React from "react";
import { channelPresentation } from "../channels";
import { useStudio } from "../state/useStudio";
import { StatusBadge } from "./StatusBadge";

export const ChannelSettings: React.FC = () => {
  const studio = useStudio();
  const identity = channelPresentation(
    studio.selectedChannelId,
    studio.selectedChannelProfile,
  );
  const profile = (studio.selectedChannelProfile ?? {}) as Record<string, unknown>;
  const production = (
    profile.production && typeof profile.production === "object"
      ? profile.production
      : {}
  ) as Record<string, unknown>;
  const value = (key: string, fallback = "Configured by channel profile") => {
    const candidate = profile[key];
    return typeof candidate === "string" && candidate.trim() ? candidate : fallback;
  };
  const rows = [
    ["Editorial focus", "editorial_focus"],
    ["Research style", "research_style"],
    ["Script style", "script_style"],
    ["Narration style", "narration_style"],
    ["Visual style", "visual_style"],
    ["Timeline style", "timeline_style"],
    ["Template pack", "template_pack"],
    ["Brand pack", "brand_pack"],
    ["Outro pack", "outro_pack"],
  ];
  const productionRows = [
    ["Composition", "composition_template"],
    ["Template policy", "template_policy"],
    ["Presenter provider", "presenter_provider"],
    ["Presenter renderer", "presenter_renderer"],
    ["Presenter asset", "presenter_asset_path"],
    ["Narrator provider", "narrator_provider"],
    ["Narrator voice", "narrator_voice_id"],
    ["Voice profile path", "narrator_voice_profile_path"],
    ["Outro asset", "outro_path"],
  ];

  return (
    <section
      className="channel-settings-panel animate-fade-in"
      role="tabpanel"
      id="settings-panel-channel"
      aria-labelledby="settings-tab-channel"
    >
      <div className="channel-settings-hero">
        <span className="channel-settings-mark" aria-hidden="true">
          {identity.initials}
        </span>
        <div>
          <div className="topbar-kicker">Active production profile</div>
          <h2>{identity.name}</h2>
          <p>{identity.description}</p>
        </div>
        <StatusBadge tone="green">Active</StatusBadge>
      </div>

      <div className="grid grid-2 channel-settings-grid">
        <article className="card stack channel-settings-card">
          <div className="mobile-section-kicker">Editorial defaults</div>
          <div className="channel-settings-row">
            <span>Default category</span>
            <strong>{value("default_category", "general")}</strong>
          </div>
          <div className="channel-settings-row">
            <span>Render profile</span>
            <strong>{value("default_render_profile", "production")}</strong>
          </div>
          <div className="channel-settings-row">
            <span>Narration mode</span>
            <strong>{value("default_narration_mode", "explained")}</strong>
          </div>
          <div className="channel-settings-row">
            <span>Target runtime</span>
            <strong>
              {typeof profile.default_target_duration_seconds === "number"
                ? `${Math.round(profile.default_target_duration_seconds / 60)} min`
                : "Channel default"}
            </strong>
          </div>
        </article>

        <article className="card stack channel-settings-card">
          <div className="mobile-section-kicker">Pipeline identity</div>
          {rows.map(([label, key]) => (
            <div className="channel-settings-row" key={key}>
              <span>{label}</span>
              <strong>{value(key)}</strong>
            </div>
          ))}
          {productionRows.map(([label, key]) => (
            <div className="channel-settings-row" key={key}>
              <span>{label}</span>
              <strong>
                {typeof production[key] === "string" && production[key]
                  ? String(production[key])
                  : "Not configured"}
              </strong>
            </div>
          ))}
        </article>
      </div>

      <p className="channel-settings-note">
        Channel profiles are versioned with the production pipeline. Switching channels changes
        project scope, editorial policy, narration, visuals and branding without interrupting running jobs.
      </p>
    </section>
  );
};
