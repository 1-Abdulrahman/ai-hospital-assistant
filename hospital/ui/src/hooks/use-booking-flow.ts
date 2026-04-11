import { create } from "zustand";
import type { ChatMessage, FlowStep, FlowMode } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

interface BookingFlowState {
  step: FlowStep;
  messages: ChatMessage[];
  currentMode: FlowMode | null;
  selectedSpecialtyId: string | null;
  selectedDoctorId: string | null;
  selectedDate: string | null;
  selectedSlotId: string | null;
  renewalItemId: string | null;
  patientNationalId: string | null;
  patientEmail: string | null;
  otpVerified: boolean;
  isLoading: boolean;
  error: string | null;

  setStep: (step: FlowStep) => void;
  addMessage: (msg: Omit<ChatMessage, "id">) => void;
  setCurrentMode: (m: FlowMode) => void;
  setSelectedSpecialtyId: (s: string) => void;
  setSelectedDoctorId: (d: string) => void;
  setSelectedDate: (d: string) => void;
  setSelectedSlotId: (id: string) => void;
  setRenewalItemId: (id: string) => void;
  setPatientNationalId: (id: string) => void;
  setPatientEmail: (email: string) => void;
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
  selectedDoctorId: null as string | null,
  selectedDate: null as string | null,
  selectedSlotId: null as string | null,
  renewalItemId: null as string | null,
  patientNationalId: null as string | null,
  patientEmail: null as string | null,
  otpVerified: false,
  isLoading: false,
  error: null as string | null,
};

export const useBookingFlow = create<BookingFlowState>((set) => ({
  ...initialState,
  setStep: (step) => set({ step }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, { ...msg, id: uuidv4() }] })),
  setCurrentMode: (currentMode) => set({ currentMode }),
  setSelectedSpecialtyId: (s) => set({ selectedSpecialtyId: s }),
  setSelectedDoctorId: (d) => set({ selectedDoctorId: d }),
  setSelectedDate: (d) => set({ selectedDate: d }),
  setSelectedSlotId: (id) => set({ selectedSlotId: id }),
  setRenewalItemId: (id) => set({ renewalItemId: id }),
  setPatientNationalId: (patientNationalId) => set({ patientNationalId }),
  setPatientEmail: (patientEmail) => set({ patientEmail }),
  setOtpVerified: (v) => set({ otpVerified: v }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  resetFlow: () => set({
    step: "chat",
    currentMode: null,
    selectedSpecialtyId: null,
    selectedDoctorId: null,
    selectedDate: null,
    selectedSlotId: null,
    renewalItemId: null,
    patientNationalId: null,
    patientEmail: null,
    otpVerified: false,
    error: null,
  }),
  reset: () => set(initialState),
}));