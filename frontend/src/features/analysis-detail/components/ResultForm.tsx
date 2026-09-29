import { zodResolver } from "@hookform/resolvers/zod";
import { Ban, Trophy } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { DatePicker } from "../../../components/DatePicker";
import type {
  BusinessOutcome,
  LossReason,
  PresentationData,
  ResultData,
  ResultPayload,
} from "../../../types/businessStatus";
import {
  LOSS_REASON_OPTIONS,
  amountToInput,
  formatAmountInput,
  parseAmountInput,
  todayIso,
} from "../utils/businessStatus";
import { FIELD_CLASS, FormField, MoneyInput, TEXTAREA_CLASS } from "./BusinessFormFields";

const resultSchema = z.object({
  resulted_at: z.string().min(1, "Elegí la fecha del resultado."),
  awarded_amount: z.string(),
  loss_reason: z.enum(["precio", "puntaje_tecnico", "descalificada", "desierta_cancelada", "otro"]),
  winner_name: z.string().max(200, "Máximo 200 caracteres."),
  winner_amount: z.string(),
  notes: z.string().max(2000, "Máximo 2000 caracteres."),
});

type ResultFormValues = z.infer<typeof resultSchema>;

interface ResultFormProps {
  initial: ResultData | null;
  presentation: PresentationData | null;
  saving: boolean;
  onSubmit: (payload: ResultPayload) => Promise<void> | void;
  onCancel: () => void;
}

function buildDefaults(initial: ResultData | null): ResultFormValues {
  return {
    resulted_at: initial?.resulted_at ?? todayIso(),
    awarded_amount: amountToInput(initial?.awarded_amount),
    loss_reason: LOSS_REASON_OPTIONS.some((option) => option.value === initial?.loss_reason)
      ? (initial?.loss_reason as LossReason)
      : "precio",
    winner_name: initial?.winner_name ?? "",
    winner_amount: amountToInput(initial?.winner_amount),
    notes: initial?.notes ?? "",
  };
}

interface OutcomeCardProps {
  outcome: BusinessOutcome;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}

function OutcomeCard({ outcome, selected, disabled, onSelect }: OutcomeCardProps) {
  const isWon = outcome === "ganada";
  const Icon = isWon ? Trophy : Ban;
  const selectedStyle = isWon
    ? "border-[#1FC9A8] bg-[rgba(127,243,222,.14)]"
    : "border-[#003C6B] bg-[rgba(0,60,107,.05)]";

  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      className={[
        "flex items-center gap-3 rounded-[14px] border-[1.5px] px-4 py-3.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        selected ? selectedStyle : "border-[rgba(0,60,107,.2)] bg-white hover:border-[rgba(0,60,107,.4)]",
      ].join(" ")}
    >
      <span
        className={[
          "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[10px]",
          isWon ? "bg-[rgba(127,243,222,.4)] text-[#0B6B58]" : "bg-[rgba(0,60,107,.08)] text-[rgba(0,60,107,.68)]",
        ].join(" ")}
      >
        <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
      </span>
      <span className="flex flex-col">
        <span className="text-sm font-bold text-[#003C6B]">{isWon ? "Ganada" : "Perdida"}</span>
        <span className="text-xs text-[rgba(0,60,107,.68)]">
          {isWon ? "Nos adjudicaron" : "Adjudicaron a otro / se cayó"}
        </span>
      </span>
    </button>
  );
}

export function ResultForm({ initial, presentation, saving, onSubmit, onCancel }: ResultFormProps) {
  const [outcome, setOutcome] = useState<BusinessOutcome | null>(initial?.outcome ?? null);
  const {
    control,
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResultFormValues>({
    resolver: zodResolver(resultSchema),
    defaultValues: buildDefaults(initial),
  });

  const currency = presentation?.currency ?? "ARS";
  const symbol = currency === "USD" ? "US$" : "$";
  const lockedOutcome = initial?.outcome ?? null;

  const submit = handleSubmit(async (values) => {
    if (!outcome) {
      return;
    }
    const isWon = outcome === "ganada";
    await onSubmit({
      outcome,
      resulted_at: values.resulted_at,
      awarded_amount: isWon ? parseAmountInput(values.awarded_amount) : null,
      loss_reason: isWon ? null : values.loss_reason,
      winner_name: isWon ? null : values.winner_name.trim() || null,
      winner_amount: isWon ? null : parseAmountInput(values.winner_amount),
      notes: values.notes.trim() || null,
    });
  });

  return (
    <section
      aria-label="Registrar resultado"
      className="flex flex-col gap-4 rounded-2xl border border-[rgba(0,60,107,.2)] bg-white px-6 py-5"
      data-testid="result-form"
    >
      <div>
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.55)]">Resultado</span>
        <h3 className="mt-1.5 font-display text-lg font-bold text-[#003C6B]">
          {initial ? "Corregir el resultado" : "¿Cómo terminó la licitación?"}
        </h3>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div role="radiogroup" aria-label="Resultado" className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {(["ganada", "perdida"] as const).map((option) => (
            <OutcomeCard
              key={option}
              outcome={option}
              selected={outcome === option}
              disabled={lockedOutcome !== null && lockedOutcome !== option}
              onSelect={() => setOutcome(option)}
            />
          ))}
        </div>

        {outcome ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
            <FormField label="Fecha de resultado" htmlFor="result-date" error={errors.resulted_at?.message}>
              <Controller
                control={control}
                name="resulted_at"
                render={({ field }) => (
                  <DatePicker
                    id="result-date"
                    aria-label="Fecha de resultado"
                    fullWidth
                    className="h-11 rounded-full pl-[42px] pr-[18px]"
                    value={field.value || null}
                    onChange={field.onChange}
                  />
                )}
              />
            </FormField>

            {outcome === "ganada" ? (
              <FormField label="Monto adjudicado" htmlFor="result-awarded">
                <Controller
                  control={control}
                  name="awarded_amount"
                  render={({ field }) => (
                    <MoneyInput
                      id="result-awarded"
                      value={field.value}
                      onChange={(value) => field.onChange(formatAmountInput(value))}
                      onBlur={field.onBlur}
                      symbol={symbol}
                    />
                  )}
                />
              </FormField>
            ) : (
              <>
                <FormField label="Motivo principal" htmlFor="result-reason">
                  <select id="result-reason" className={FIELD_CLASS} {...register("loss_reason")}>
                    {LOSS_REASON_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Adjudicatario" htmlFor="result-winner" error={errors.winner_name?.message}>
                  <input
                    id="result-winner"
                    type="text"
                    placeholder="Empresa ganadora (opcional)"
                    className={FIELD_CLASS}
                    {...register("winner_name")}
                  />
                </FormField>
                <FormField label="Monto adjudicado al ganador" htmlFor="result-winner-amount">
                  <Controller
                    control={control}
                    name="winner_amount"
                    render={({ field }) => (
                      <MoneyInput
                        id="result-winner-amount"
                        value={field.value}
                        onChange={(value) => field.onChange(formatAmountInput(value))}
                        onBlur={field.onBlur}
                        symbol={symbol}
                        placeholder="Opcional"
                      />
                    )}
                  />
                </FormField>
              </>
            )}
          </div>
        ) : null}

        {outcome ? (
          <FormField label="Aprendizajes / notas" htmlFor="result-notes" error={errors.notes?.message}>
            <textarea
              id="result-notes"
              rows={2}
              placeholder="Opcional"
              className={TEXTAREA_CLASS}
              {...register("notes")}
            />
          </FormField>
        ) : null}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="inline-flex h-10 items-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB] disabled:opacity-40"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving || !outcome}
            className="inline-flex h-10 items-center rounded-full bg-[linear-gradient(90deg,#2F4EF8,#A966FF)] px-5 text-[13px] font-semibold text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Guardar resultado
          </button>
        </div>
      </form>
    </section>
  );
}
