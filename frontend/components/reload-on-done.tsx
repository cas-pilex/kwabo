"use client";
import { UploadButton } from "@/components/upload-button";

export function ReloadOnDone() {
  return <UploadButton onDone={() => window.location.reload()} />;
}
