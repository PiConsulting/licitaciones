import { zodResolver } from "@hookform/resolvers/zod";
import { FileText, Upload, X } from "lucide-react";
import { useRef, useState, type ChangeEvent } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { DatePicker } from "../../../components/DatePicker";
import type { PresentationData, PresentationPayload } from "../../../types/businessStatus";
import {
  CURRENCY_OPTIONS,
  PRESENTATION_CHANNEL_OPTIONS,
  amountToInput,
  formatAmountInput,
  parseAmountInput,
  todayIso,
} from "../utils/businessStatus";
import type { ReceiptChange } from "../hooks/useBusinessState";
import {
  FIELD_CLASS,
  FIELD_LABEL_CLASS,
  FormField,
  MoneyInput,
  SELECT_COMPACT_CLASS,
  TEXTAREA_CLASS,
} from "./BusinessFormFields";

const RECEIPT_MAX_BYTES = 10 * 1024 * 1024;
const RECEIPT_ACCEPT = "application/pdf,image/png,image/jpeg,image/webp";

const presentationSchema = z.object({
  presented_at: z.string().min(1, "Elegí la fecha de presentación."),
  amount: z.string(),
  currency: z.enum(["ARS", "USD"]),
  channel: z.enum(["compr_ar", "bac_caba", "portal_organismo", "mesa_entradas", "otro"]),
  offer_number: z.string().max(120, "Máximo 120 caracteres."),
  notes: z.string().max(2000, "Máximo 2000 caracteres."),
});

type PresentationFormValues = z.infer<typeof presentationSchema>;

interface PresentationFormProps {
  initial: PresentationData | null;
  saving: boolean;
  onSubmit: (payload: PresentationPayload, receipt: ReceiptChange) => Promise<void> | void;
  onCancel: () => void;
}

function buildDefaults(initial: PresentationData | null): PresentationFormValues {
  if (!initial) {
    return {
      presented_at: todayIso(),
      amount: "",
      currency: "ARS",
      channel: "compr_ar",
      offer_number: "",
      notes: "",
    };
  }
  return {
    presented_at: initial.presented_at,
    amount: amountToInput(initial.amount),
    currency: initial.currency === "USD" ? "USD" : "ARS",
    channel: PRESENTATION_CHANNEL_OPTIONS.some((option) => option.value === initial.channel)
      ? (initial.channel as PresentationFormValues["channel"])
      : "otro",
    offer_number: initial.offer_number ?? "",
    notes: initial.notes ?? "",
  };
}

export function PresentationForm({ initial, saving, onSubmit, onCancel }: PresentationFormProps) {
  const {
    control,
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<PresentationFormValues>({
    resolver: zodResolver(presentationSchema),
    defaultValues: buildDefaults(initial),
  });

  const currency = watch("currency");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [keepExistingReceipt, setKeepExistingReceipt] = useState(Boolean(initial?.receipt_filename));
  const [receiptError, setReceiptError] = useState<string | null>(null);

  const receiptName = receiptFile?.name ?? (keepExistingReceipt ? initial?.receipt_filename : null);

  const handleReceiptChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!file) {
      return;
    }
    if (file.size > RECEIPT_MAX_BYTES) {
      setReceiptError("La constancia no puede superar los 10 MB.");
      return;
    }
    setReceiptError(null);
    setReceiptFile(file);
  };

  const handleReceiptRemove = () => {
    setReceiptFile(null);
    setKeepExistingReceipt(false);
    setReceiptError(null);
  };

  const submit = handleSubmit(async (values) => {
    await onSubmit(
      {
        presented_at: values.presented_at,
        amount: parseAmountInput(values.amount),
        currency: values.currency,
        channel: values.channel,
        offer_number: values.offer_number.trim() || null,
        notes: values.notes.trim() || null,
      },
      {
        file: receiptFile,
        remove: !receiptFile && Boolean(initial?.receipt_filename) && !keepExistingReceipt,
      },
    );
  });

  return (
    <section
      aria-label="Registrar presentación"
      className="flex flex-col gap-4 rounded-2xl border border-[rgba(47,78,248,.35)] bg-white px-6 py-5"
      data-testid="presentation-form"
    >
      <div>
        <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#2F4EF8]">Presentación</span>
        <h3 className="mt-1.5 font-display text-lg font-bold text-[#003C6B]">
          {initial ? "Editar datos de la presentación" : "Registrar que ya presentaste la oferta"}
        </h3>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
          <FormField label="Fecha de presentación" htmlFor="presentation-date" error={errors.presented_at?.message}>
            <Controller
              control={control}
              name="presented_at"
              render={({ field }) => (
                <DatePicker
                  id="presentation-date"
                  aria-label="Fecha de presentación"
                  fullWidth
                  className="h-11 rounded-full pl-[42px] pr-[18px]"
                  value={field.value || null}
                  onChange={field.onChange}
                />
              )}
            />
          </FormField>

          <FormField label="Monto ofertado" htmlFor="presentation-amount">
            <div className="flex gap-2">
              <select aria-label="Moneda" className={SELECT_COMPACT_CLASS} {...register("currency")}>
                {CURRENCY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <div className="min-w-0 flex-1">
                <Controller
                  control={control}
                  name="amount"
                  render={({ field }) => (
                    <MoneyInput
                      id="presentation-amount"
                      value={field.value}
                      onChange={(value) => field.onChange(formatAmountInput(value))}
                      onBlur={field.onBlur}
                      symbol={currency === "USD" ? "US$" : "$"}
                    />
                  )}
                />
              </div>
            </div>
          </FormField>

          <FormField label="Canal" htmlFor="presentation-channel">
            <select id="presentation-channel" className={FIELD_CLASS} {...register("channel")}>
              {PRESENTATION_CHANNEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="N° de oferta / comprobante" htmlFor="presentation-offer" error={errors.offer_number?.message}>
            <input
              id="presentation-offer"
              type="text"
              placeholder="Ej: OF-2026-0871"
              className={FIELD_CLASS}
              {...register("offer_number")}
            />
          </FormField>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className={FIELD_LABEL_CLASS}>Constancia de presentación</span>
          <div className="flex flex-wrap items-center gap-2.5">
            <input
              ref={fileInputRef}
              type="file"
              accept={RECEIPT_ACCEPT}
              className="hidden"
              aria-label="Archivo de constancia"
              data-testid="presentation-receipt-input"
              onChange={handleReceiptChange}
            />
            {receiptName ? (
              <span
                className="inline-flex items-center gap-2 rounded-full border border-[rgba(0,60,107,.12)] bg-[#F4F9FC] py-1.5 pl-3.5 pr-1.5 text-[13px] font-semibold text-[#003C6B]"
                data-testid="presentation-receipt-chip"
              >
                <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                {receiptName}
                <button
                  type="button"
                  onClick={handleReceiptRemove}
                  aria-label="Quitar archivo"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-full border-0 bg-transparent text-[rgba(0,60,107,.55)] hover:bg-[rgba(0,60,107,.08)]"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </span>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex h-10 items-center gap-2 rounded-full border-[1.5px] border-dashed border-[rgba(0,60,107,.3)] bg-white px-[18px] text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB]"
                >
                  <Upload className="h-3.5 w-3.5" aria-hidden="true" />
                  Adjuntar archivo
                </button>
                <span className="text-xs text-[rgba(0,60,107,.55)]">Opcional · PDF o imagen</span>
              </>
            )}
          </div>
          {receiptError ? <p className="text-xs text-error">{receiptError}</p> : null}
        </div>

        <FormField label="Notas" htmlFor="presentation-notes" error={errors.notes?.message}>
          <textarea
            id="presentation-notes"
            rows={2}
            placeholder="Opcional"
            className={TEXTAREA_CLASS}
            {...register("notes")}
          />
        </FormField>

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
            disabled={saving}
            className="inline-flex h-10 items-center rounded-full bg-[linear-gradient(90deg,#2F4EF8,#A966FF)] px-5 text-[13px] font-semibold text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Guardar presentación
          </button>
        </div>
      </form>
    </section>
  );
}
