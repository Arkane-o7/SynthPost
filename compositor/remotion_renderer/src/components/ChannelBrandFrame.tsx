import React from "react";
import {AbsoluteFill} from "remotion";
import {brandVariables} from "../styles/brand";
import type {StoryProps} from "../types";

export const ChannelBrandFrame: React.FC<{
  story: StoryProps;
  children: React.ReactNode;
}> = ({story, children}) => (
  <AbsoluteFill
    data-channel={story.channelId ?? "synthpost"}
    style={brandVariables(story.brandTheme)}
  >
    {children}
  </AbsoluteFill>
);
