import { z } from "zod";

export const specialtyCandidateSchema = z.object({
  label: z.string(),
  p: z.number(),
});

export const quickReplySchema = z.object({
  label: z.string(),
  value: z.string(),
});

export const selectionListItemSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().optional(),
});

export const selectionListSchema = z.object({
  type: z.enum(["specialty", "doctor", "slot"]),
  items: z.array(selectionListItemSchema),
});

export const backendErrorSchema = z.object({
  reasonCode: z.string(),
  userMessage: z.string(),
});

export const chatResponseSchema = z.object({
  userMessage: z.string(),
  candidates: z.array(specialtyCandidateSchema).optional(),
  ambiguous: z.boolean().optional(),
  quickReplies: z.array(quickReplySchema).optional(),
  selectionLists: z.array(selectionListSchema).optional(),
  needsClarification: z.boolean().optional(),
  isChronicContinuity: z.boolean().optional(),
  showConsentNotice: z.boolean().optional(),
  correlationId: z.string().optional(),
  errors: z.array(backendErrorSchema).optional(),
});

export const healthResponseSchema = z.object({
  status: z.string(),
});

export const bookingConfirmResponseSchema = z.object({
  bookingId: z.string(),
  correlationId: z.string(),
});

export const otpRequestResponseSchema = z.object({
  message: z.string(),
  correlationId: z.string().optional(),
});

export const otpVerifyResponseSchema = z.object({
  verified: z.boolean(),
  correlationId: z.string().optional(),
});
