import { z } from "zod";

export const quickReplySchema = z.object({
  label: z.string(),
  value: z.string(),
});

export const selectionListItemMetaSchema = z.object({
  isoDate: z.string().optional(),
  startTime: z.string().optional(),
  endTime: z.string().optional(),
  timezone: z.string().optional(),
});

export const selectionListItemSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().optional(),
  confidence: z.number().optional(),
  meta: selectionListItemMetaSchema.optional(),
});

export const selectionListSchema = z.object({
  type: z.enum(["specialty", "doctor", "slot", "date", "medication"]),
  items: z.array(selectionListItemSchema),
});

export const backendErrorSchema = z.object({
  reasonCode: z.string(),
  userMessage: z.string(),
});

export const confirmationSummarySchema = z.object({
  bookingReferenceId: z.string().optional(),
  correlationId: z.string().optional(),
  doctorLabel: z.string().optional(),
  specialtyLabel: z.string().optional(),
  date: z.string().optional(),
  slotLabel: z.string().optional(),
  renewalItemLabel: z.string().optional(),
});

export const chatResponseSchema = z.object({
  userMessage: z.string(),
  quickReplies: z.array(quickReplySchema).optional(),
  selectionLists: z.array(selectionListSchema).optional(),
  needsClarification: z.boolean().optional(),
  isChronicContinuity: z.boolean().optional(),
  showConsentNotice: z.boolean().optional(),
  requiresDate: z.boolean().optional(),
  correlationId: z.string().optional(),
  errors: z.array(backendErrorSchema).optional(),
  bookingReferenceId: z.string().optional(),
  confirmationType: z.enum(["appointment", "renewal"]).optional(),
  confirmationSummary: confirmationSummarySchema.optional(),
});

export const healthResponseSchema = z.object({
  status: z.string(),
});

export const otpRequestResponseSchema = z.object({
  message: z.string(),
  correlationId: z.string().optional(),
});

export const otpVerifyResponseSchema = z.object({
  verified: z.boolean(),
  correlationId: z.string().optional(),
});
