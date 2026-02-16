import { create } from "zustand";
import type { ChatMessage, FlowStep, SpecialtyCandidate } from "@/lib/types";
import { v4 as uuidv4 } from "uuid";

interface BookingFlowState {
  step: FlowStep;
  messages: ChatMessage[];
  candidates: SpecialtyCandidate[];
  selectedSpecialty: string | null;
  selectedDate: string | null;
  selectedSlotId: string | null;
  otpVerified: boolean;
  bookingId: string | null;
  correlationId: string | null;
  isLoading: boolean;
  error: string | null;

  setStep: (step: FlowStep) => void;
  addMessage: (msg: Omit<ChatMessage, "id">) => void;
  setCandidates: (c: SpecialtyCandidate[]) => void;
  setSelectedSpecialty: (s: string) => void;
  setSelectedDate: (d: string) => void;
  setSelectedSlotId: (id: string) => void;
  setOtpVerified: (v: boolean) => void;
  setBookingResult: (bookingId: string, correlationId: string) => void;
  setLoading: (l: boolean) => void;
  setError: (e: string | null) => void;
  reset: () => void;
}

const initialState = {
  step: "chat" as FlowStep,
  messages: [],
  candidates: [],
  selectedSpecialty: null,
  selectedDate: null,
  selectedSlotId: null,
  otpVerified: false,
  bookingId: null,
  correlationId: null,
  isLoading: false,
  error: null,
};

export const useBookingFlow = create<BookingFlowState>((set) => ({
  ...initialState,
  setStep: (step) => set({ step }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, { ...msg, id: uuidv4() }] })),
  setCandidates: (candidates) => set({ candidates }),
  setSelectedSpecialty: (s) => set({ selectedSpecialty: s }),
  setSelectedDate: (d) => set({ selectedDate: d }),
  setSelectedSlotId: (id) => set({ selectedSlotId: id }),
  setOtpVerified: (v) => set({ otpVerified: v }),
  setBookingResult: (bookingId, correlationId) => set({ bookingId, correlationId }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  reset: () => set(initialState),
}));
