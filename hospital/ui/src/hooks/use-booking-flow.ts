import { create } from "zustand";
import type { ChatMessage, FlowStep, FlowMode } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

interface BookingFlowState {
  step: FlowStep;
  messages: ChatMessage[];
  currentMode: FlowMode | null;

  selectedSpecialtyId: string | null;
  selectedSpecialtyLabel: string | null;

  selectedDoctorId: string | null;
  selectedDoctorLabel: string | null;

  selectedDate: string | null;
  selectedSlotId: string | null;
  selectedSlotLabel: string | null;
  selectedSlotStartUtc: string | null;

  renewalItemId: string | null;
  renewalItemLabel: string | null;

  patientNationalId: string | null;
  patientEmail: string | null;

  otpVerified: boolean;
  isLoading: boolean;
  error: string | null;

  setStep: (step: FlowStep) => void;
  addMessage: (msg: Omit<ChatMessage, "id">) => void;
  setCurrentMode: (m: FlowMode | null) => void;

  setSelectedSpecialtyId: (s: string | null) => void;
  setSelectedSpecialtyLabel: (s: string | null) => void;

  setSelectedDoctorId: (d: string | null) => void;
  setSelectedDoctorLabel: (d: string | null) => void;

  setSelectedDate: (d: string | null) => void;
  setSelectedSlotId: (id: string | null) => void;
  setSelectedSlotLabel: (label: string | null) => void;
  setSelectedSlotStartUtc: (value: string | null) => void;

  setRenewalItemId: (id: string | null) => void;
  setRenewalItemLabel: (label: string | null) => void;

  setPatientNationalId: (id: string | null) => void;
  setPatientEmail: (email: string | null) => void;

  setOtpVerified: (v: boolean) => void;
  setLoading: (l: boolean) => void;
  setError: (e: string | null) => void;

  resetFlow: () => void;
  reset: () => void;
}

const initialState = {
  step: "chat" as FlowStep,
  messages: [] as ChatMessage[],
  currentMode: null as FlowMode | null,

  selectedSpecialtyId: null as string | null,
  selectedSpecialtyLabel: null as string | null,

  selectedDoctorId: null as string | null,
  selectedDoctorLabel: null as string | null,

  selectedDate: null as string | null,
  selectedSlotId: null as string | null,
  selectedSlotLabel: null as string | null,
  selectedSlotStartUtc: null as string | null,

  renewalItemId: null as string | null,
  renewalItemLabel: null as string | null,

  patientNationalId: null as string | null,
  patientEmail: null as string | null,

  otpVerified: false,
  isLoading: false,
  error: null as string | null,
};

export const useBookingFlow = create<BookingFlowState>((set) => ({
  ...initialState,

  setStep: (step) => set({ step }),

  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, { ...msg, id: uuidv4() }],
    })),

  setCurrentMode: (currentMode) => set({ currentMode }),

  setSelectedSpecialtyId: (selectedSpecialtyId) => set({ selectedSpecialtyId }),
  setSelectedSpecialtyLabel: (selectedSpecialtyLabel) =>
    set({ selectedSpecialtyLabel }),

  setSelectedDoctorId: (selectedDoctorId) => set({ selectedDoctorId }),
  setSelectedDoctorLabel: (selectedDoctorLabel) => set({ selectedDoctorLabel }),

  setSelectedDate: (selectedDate) => set({ selectedDate }),
  setSelectedSlotId: (selectedSlotId) => set({ selectedSlotId }),
  setSelectedSlotLabel: (selectedSlotLabel) => set({ selectedSlotLabel }),
  setSelectedSlotStartUtc: (selectedSlotStartUtc) =>
    set({ selectedSlotStartUtc }),

  setRenewalItemId: (renewalItemId) => set({ renewalItemId }),
  setRenewalItemLabel: (renewalItemLabel) => set({ renewalItemLabel }),

  setPatientNationalId: (patientNationalId) => set({ patientNationalId }),
  setPatientEmail: (patientEmail) => set({ patientEmail }),

  setOtpVerified: (otpVerified) => set({ otpVerified }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  resetFlow: () =>
    set({
      step: "chat",
      currentMode: null,

      selectedSpecialtyId: null,
      selectedSpecialtyLabel: null,

      selectedDoctorId: null,
      selectedDoctorLabel: null,

      selectedDate: null,
      selectedSlotId: null,
      selectedSlotLabel: null,
      selectedSlotStartUtc: null,

      renewalItemId: null,
      renewalItemLabel: null,

      patientNationalId: null,
      patientEmail: null,

      otpVerified: false,
      error: null,
    }),

  reset: () => set(initialState),
}));
