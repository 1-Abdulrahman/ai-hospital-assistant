import { z } from "zod";

export const quickReplySchema = z.object({
  label: z.string(),
  value: z.string(),
  action: z.enum(["SEND_MESSAGE", "PROMPT_FOR_TEXT"]).optional().nullable(),
});

export const selectionListItemMetaSchema = z
  .object({
    isoDate: z.string().optional(),
    startTime: z.string().optional(),
    endTime: z.string().optional(),
    timezone: z.string().optional(),

    practitionerRef: z.string().optional(),
    practitionerDisplay: z.string().optional(),
    specialtyId: z.string().optional(),
    specialtyDisplay: z.string().optional(),

    dateKey: z.string().optional(),
    displayDate: z.string().optional(),
    displayTime: z.string().optional(),

    isPreferredPractitioner: z.boolean().optional(),
  })
  .nullable()
  .optional();

export const selectionListItemSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string().optional().nullable(),
  confidence: z.number().optional().nullable(),
  meta: selectionListItemMetaSchema,
});

export const selectionListSchema = z.object({
  type: z.enum(["specialty", "doctor", "slot", "date", "medication"]),
  items: z.array(selectionListItemSchema),
});

export const backendErrorSchema = z.object({
  reasonCode: z.string(),
  userMessage: z.string(),
});

export const continuityPayloadSchema = z
  .object({
    matched: z.boolean(),
    preferredPractitionerRef: z.string().optional().nullable(),
    preferredPractitionerDisplay: z.string().optional().nullable(),
    preferredPractitionerHasAvailability: z.boolean().optional().nullable(),
    message: z.string().optional().nullable(),
  })
  .nullable()
  .optional();

export const confirmationSummarySchema = z
  .object({
    bookingReferenceId: z.string().optional().nullable(),
    correlationId: z.string().optional().nullable(),
    doctorLabel: z.string().optional().nullable(),
    specialtyLabel: z.string().optional().nullable(),
    date: z.string().optional().nullable(),
    slotLabel: z.string().optional().nullable(),
    renewalItemLabel: z.string().optional().nullable(),
  })
  .nullable()
  .optional();

export const chatResponseSchema = z.object({
  userMessage: z.string(),
  quickReplies: z.array(quickReplySchema).optional().nullable(),
  selectionLists: z.array(selectionListSchema).optional().nullable(),
  needsClarification: z.boolean().optional().nullable(),
  isChronicContinuity: z.boolean().optional().nullable(),
  continuity: continuityPayloadSchema,
  showConsentNotice: z.boolean().optional().nullable(),
  requiresContinuityIdentity: z.boolean().optional().nullable(),
  requiresDate: z.boolean().optional().nullable(),
  correlationId: z.string().optional().nullable(),
  errors: z.array(backendErrorSchema).optional().nullable(),
  bookingReferenceId: z.string().optional().nullable(),
  confirmationType: z.enum(["appointment", "renewal"]).optional().nullable(),
  confirmationSummary: confirmationSummarySchema,
});

export const healthResponseSchema = z.object({
  status: z.string(),
});

export const otpRequestResponseSchema = z.object({
  ok: z.boolean().optional().nullable(),
  message: z.string(),
  expiresIn: z.number().optional().nullable(),
  correlationId: z.string().optional().nullable(),
});

export const otpVerifyResponseSchema = z.object({
  verified: z.boolean(),
  message: z.string().optional().nullable(),
  correlationId: z.string().optional().nullable(),
});