import { useMemo, useState } from "react";

import type { UploadedFile } from "../types/upload";
import { formatFileSizeMb, validateFileCount, validateFileFormat, validateFileSize, validateTotalSize } from "../utils/fileValidation";

function createFileId(file: File) {
  return `${file.name}-${file.size}-${file.lastModified}`;
}

export function useFileUpload() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [messages, setMessages] = useState<string[]>([]);

  const addFiles = (incomingFiles: File[]) => {
    const countResult = validateFileCount(files.length + incomingFiles.length);
    if (!countResult.valid) {
      setMessages(countResult.error ? [countResult.error] : []);
      return;
    }

    const nextMessages: string[] = [];
    const validCandidates: File[] = [];

    for (const file of incomingFiles) {
      const formatResult = validateFileFormat(file);
      if (!formatResult.valid) {
        if (formatResult.error) {
          nextMessages.push(formatResult.error);
        }
        continue;
      }

      const sizeResult = validateFileSize(file);
      if (!sizeResult.valid) {
        if (sizeResult.error) {
          nextMessages.push(sizeResult.error);
        }
        continue;
      }

      validCandidates.push(file);
    }

    const currentTotal = files.reduce((total, item) => total + item.file.size, 0);
    const incomingTotal = validCandidates.reduce((total, file) => total + file.size, 0);
    const totalResult = validateTotalSize(currentTotal + incomingTotal);

    if (!totalResult.valid) {
      setMessages(totalResult.error ? [totalResult.error] : []);
      return;
    }

    const mappedFiles: UploadedFile[] = validCandidates.map((file) => ({
      id: createFileId(file),
      file,
      sizeMb: formatFileSizeMb(file.size),
      pagesLabel: "N/D páginas",
      status: "validating",
    }));

    if (mappedFiles.length === 0) {
      setMessages(nextMessages);
      return;
    }

    setMessages(nextMessages);
    setFiles((current) => {
      const existing = new Set(current.map((item) => item.id));
      const deduped = mappedFiles.filter((item) => !existing.has(item.id));
      return [...current, ...deduped];
    });

    window.setTimeout(() => {
      setFiles((current) =>
        current.map((item) =>
          mappedFiles.some((added) => added.id === item.id)
            ? {
                ...item,
                status: "valid",
              }
            : item,
        ),
      );
    }, 200);
  };

  const removeFile = (id: string) => {
    setFiles((current) => {
      const next = current.filter((item) => item.id !== id);
      const total = next.reduce((sum, item) => sum + item.file.size, 0);
      const totalResult = validateTotalSize(total);
      if (!totalResult.valid) {
        setMessages(totalResult.error ? [totalResult.error] : []);
      } else {
        setMessages([]);
      }
      return next;
    });
  };

  const hasValidFiles = useMemo(() => files.some((item) => item.status === "valid"), [files]);
  const hasPendingValidation = useMemo(() => files.some((item) => item.status === "validating"), [files]);
  const canContinue = hasValidFiles && !hasPendingValidation && messages.length === 0;

  return {
    files,
    messages,
    canContinue,
    addFiles,
    removeFile,
  };
}
