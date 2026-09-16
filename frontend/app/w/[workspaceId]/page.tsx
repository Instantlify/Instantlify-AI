"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function WorkspaceIndex() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/w/${workspaceId}/overview`);
  }, [workspaceId, router]);
  return null;
}
