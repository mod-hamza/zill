import type { ReactNode } from "react";
import { StageShell } from "@/app-ui/StageShell";
import "./stage.css";

// Route group layout: ONE persistent <Canvas> shared by /film and /app (PRD 13).
export default function StageLayout({ children }: { children: ReactNode }) {
  return <StageShell>{children}</StageShell>;
}
