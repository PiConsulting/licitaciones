import { useMemo, useState } from "react";
import { Play } from "lucide-react";

import type { UploadedFile } from "../../types/upload";

const BUSINESS_UNITS = ["CEDI", "PI", "Wemox", "Vulps", "Korex"] as const;
const UNIT_DOT_COLORS: Record<(typeof BUSINESS_UNITS)[number], string> = {
  CEDI: "#0099DB",
  PI: "#003C6B",
  Wemox: "#2F4EF8",
  Vulps: "#A966FF",
  Korex: "#7FF3DE",
};

interface Step3ConfirmationProps {
  files: UploadedFile[];
  primaryIndex: number;
  onBack: () => void;
  onContinueToStart: (metadata: { analysisName: string; businessUnit: string }) => void;
}

export function Step3Confirmation({ files, primaryIndex, onBack, onContinueToStart }: Step3ConfirmationProps) {
  const [analysisName, setAnalysisName] = useState("");
  const [businessUnit, setBusinessUnit] = useState<(typeof BUSINESS_UNITS)[number]>("CEDI");

  const filesForDisplay = useMemo(
    () =>
      files
        .map((file, index) => ({ file, index }))
        .sort((left, right) => {
          const leftIsPrimary = left.index === primaryIndex;
          const rightIsPrimary = right.index === primaryIndex;

          if (leftIsPrimary === rightIsPrimary) {
            return left.index - right.index;
          }
          return leftIsPrimary ? -1 : 1;
        }),
    [files, primaryIndex],
  );

  return (
    <section aria-label="Paso 3: Confirmación" className="flex flex-col gap-5 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white p-6">
      <div>
        <h2 className="font-display text-xl font-semibold text-[#003C6B]">Revisá antes de iniciar</h2>
        <p className="mt-1.5 text-sm text-[rgba(0,60,107,.68)]">
          Los archivos se suben y se verifica si ya fueron analizados. Si hay duplicados, vas a poder resolverlos.
        </p>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <div className="flex flex-col gap-2">
          <label
            htmlFor="analysis-name"
            className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]"
          >
            Nombre del análisis
          </label>
          <input
            id="analysis-name"
            type="text"
            value={analysisName}
            onChange={(event) => setAnalysisName(event.target.value)}
            maxLength={160}
            placeholder="Ej: Licitación mantenimiento edilicio 2026"
            className="h-11 rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] text-sm text-[#003C6B] placeholder:text-[rgba(0,60,107,.45)] focus:border-[#0099DB] focus:outline-none"
          />
          <span className="text-xs text-[rgba(0,60,107,.55)]">
            Opcional. Si lo dejás vacío se usa el nombre del pliego principal.
          </span>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">Unidad de negocio</span>
          <div className="flex flex-wrap gap-2">
            {BUSINESS_UNITS.map((unit) => {
              const active = businessUnit === unit;
              return (
                <button
                  key={unit}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setBusinessUnit(unit)}
                  className={[
                    "inline-flex h-8 items-center gap-2 rounded-full border-[1.5px] px-[14px] text-[13px] font-semibold",
                    active
                      ? "border-[#003C6B] bg-[#003C6B] text-white"
                      : "border-[rgba(0,60,107,.2)] bg-white text-[#003C6B] hover:border-[#0099DB]",
                  ].join(" ")}
                >
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: UNIT_DOT_COLORS[unit] }} aria-hidden="true" />
                  {unit}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">Documentos</span>
        <ul className="flex flex-col gap-2">
          {filesForDisplay.map(({ file, index }) => {
            const isPrimary = index === primaryIndex;
            return (
              <li
                key={file.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-[rgba(0,60,107,.12)] px-[14px] py-[10px] text-sm text-[#003C6B]"
              >
                <span className="min-w-0 truncate font-medium">{file.file.name}</span>
                <span
                  className={[
                    "shrink-0 rounded-full px-[10px] py-[3px] text-[11px] font-bold uppercase tracking-[0.1em]",
                    isPrimary
                      ? "bg-[#003C6B] text-white"
                      : "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]",
                  ].join(" ")}
                >
                  {isPrimary ? "Principal" : "Anexo"}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex justify-between">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex h-11 items-center rounded-full border-2 border-[rgba(0,60,107,.2)] bg-white px-6 text-sm font-semibold text-[#003C6B] hover:border-[#003C6B] disabled:cursor-not-allowed disabled:opacity-40"
        >
          Volver
        </button>
        <button
          type="button"
          onClick={() => {
            onContinueToStart({
              analysisName: analysisName.trim(),
              businessUnit,
            });
          }}
          className="inline-flex h-11 items-center gap-2 rounded-full border-0 bg-[linear-gradient(90deg,#2F4EF8,#A966FF)] px-[26px] text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Play size={14} fill="currentColor" strokeWidth={2} aria-hidden="true" />
          Iniciar análisis
        </button>
      </div>
    </section>
  );
}
