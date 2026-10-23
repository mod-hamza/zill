import { proxyAgentStream } from "@/lib/agentProxy";

export const dynamic = "force-dynamic";

export function POST(req: Request) {
  return proxyAgentStream(req, "simulate");
}
