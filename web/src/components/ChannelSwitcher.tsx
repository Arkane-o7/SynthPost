import React from "react";
import type { ChannelId } from "../contracts";
import {
  CHANNEL_IDS,
  channelPresentation,
} from "../channels";
import { useStudio } from "../state/useStudio";

export const ChannelSwitcher: React.FC<{ onChange?: () => void }> = ({
  onChange,
}) => {
  const studio = useStudio();
  const [open, setOpen] = React.useState(false);
  const [switchingTo, setSwitchingTo] = React.useState<ChannelId | null>(null);
  const rootRef = React.useRef<HTMLDivElement>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const optionRefs = React.useRef<Array<HTMLButtonElement | null>>([]);
  const active = channelPresentation(
    studio.selectedChannelId,
    studio.selectedChannelProfile,
  );

  const profileFor = React.useCallback(
    (channelId: ChannelId) =>
      studio.channels.find((profile) => profile.channel_id === channelId),
    [studio.channels],
  );

  React.useEffect(() => {
    if (!open) return;
    const closeOnOutsidePress = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", closeOnOutsidePress);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePress);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const openAndFocus = (index: number) => {
    setOpen(true);
    window.requestAnimationFrame(() => optionRefs.current[index]?.focus());
  };

  const selectChannel = async (channelId: ChannelId) => {
    setOpen(false);
    if (channelId === studio.selectedChannelId) return;
    try {
      setSwitchingTo(channelId);
      onChange?.();
      await studio.switchChannel(channelId);
    } finally {
      setSwitchingTo(null);
    }
  };

  return (
    <div className="channel-switcher" ref={rootRef}>
      <span className="channel-switcher-label">Active channel</span>
      <button
        ref={triggerRef}
        type="button"
        className="channel-switcher-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="channel-switcher-options"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            openAndFocus(Math.max(0, CHANNEL_IDS.indexOf(studio.selectedChannelId)));
          }
        }}
      >
        <span className="channel-switcher-mark" aria-hidden="true">
          {active.initials}
        </span>
        <span className="channel-switcher-copy">
          <strong>{active.name}</strong>
          <small>{active.tagline}</small>
        </span>
        <span className={`channel-switcher-chevron ${open ? "open" : ""}`} aria-hidden="true">
          {switchingTo ? <span className="rail-spinner" /> : "⌄"}
        </span>
      </button>

      {open && (
        <div
          id="channel-switcher-options"
          className="channel-switcher-menu"
          role="listbox"
          aria-label="Production channel"
          onKeyDown={(event) => {
            const currentIndex = optionRefs.current.indexOf(
              document.activeElement as HTMLButtonElement,
            );
            if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
              event.preventDefault();
              let nextIndex = currentIndex;
              if (event.key === "ArrowDown") nextIndex = (currentIndex + 1) % CHANNEL_IDS.length;
              if (event.key === "ArrowUp") nextIndex = (currentIndex - 1 + CHANNEL_IDS.length) % CHANNEL_IDS.length;
              if (event.key === "Home") nextIndex = 0;
              if (event.key === "End") nextIndex = CHANNEL_IDS.length - 1;
              optionRefs.current[nextIndex]?.focus();
            }
          }}
        >
          {CHANNEL_IDS.map((channelId, index) => {
            const option = channelPresentation(channelId, profileFor(channelId));
            const selected = channelId === studio.selectedChannelId;
            return (
              <button
                key={channelId}
                id={`channel-option-${channelId}`}
                ref={(element) => {
                  optionRefs.current[index] = element;
                }}
                type="button"
                role="option"
                aria-selected={selected}
                className={`channel-switcher-option ${selected ? "selected" : ""}`}
                style={{ "--option-accent": option.accent } as React.CSSProperties}
                onClick={() => void selectChannel(channelId)}
              >
                <span className="channel-switcher-option-mark" aria-hidden="true">
                  {option.initials}
                </span>
                <span>
                  <strong>{option.name}</strong>
                  <small>{option.tagline}</small>
                </span>
                <span className="channel-switcher-check" aria-hidden="true">
                  {selected ? "✓" : ""}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
