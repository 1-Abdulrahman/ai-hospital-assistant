import { useState, useEffect } from "react";
import { checkHealth } from "@/lib/api-client";

export function useHealthCheck() {
  const [status, setStatus] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    let mounted = true;
    checkHealth()
      .then(() => mounted && setStatus("ok"))
      .catch(() => mounted && setStatus("error"));
    return () => { mounted = false; };
  }, []);

  return status;
}
